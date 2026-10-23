#------------------------------------------------------------------------------
# Module      : data_obi_controller_cocotb
# Description : Directed data OBI ownership, handshake, wait and reset checks.
# Author      : Codex
# Date        : 2026-10-23
#------------------------------------------------------------------------------

import os

import cocotb
from cocotb.triggers import Timer


def drive(dut, **signals):
    for name, value in signals.items():
        getattr(dut, name).value = value


def check_control(dut, expected_req, expected_wait):
    assert int(dut.req.value) == expected_req, (
        f"req: expected {expected_req}, got {dut.req.value}"
    )
    assert int(dut.mem_wait.value) == expected_wait, (
        f"mem_wait: expected {expected_wait}, got {dut.mem_wait.value}"
    )
    assert int(dut.rready.value) == 1, "rready must remain one"


def check_payload(dut, *, addr, we, be, wdata, read_data):
    for name, expected in (
        ("addr", addr), ("we", we), ("be", be),
        ("wdata", wdata), ("read_data", read_data),
    ):
        actual = int(getattr(dut, name).value)
        assert actual == expected, (
            f"{name}: expected 0x{expected:08X}, got 0x{actual:08X}"
        )


def check_response(dut, response_expected, context):
    if int(dut.rst_n.value) and int(dut.rvalid.value) and int(dut.rready.value):
        if not response_expected:
            raise AssertionError(f"Unexpected OBI response: {context}")


async def tick(
    dut, expected_req, expected_wait, *, response_expected=False,
    next_owner=None, violation=None,
):
    #check the consuming edge before sequential ownership changes
    await Timer(4, unit="ns")
    check_control(dut, expected_req, expected_wait)
    if violation is not None and not os.environ.get("OBI_NEGATIVE_CASE"):
        try:
            check_response(dut, response_expected, violation)
        except AssertionError as error:
            assert str(error) == f"Unexpected OBI response: {violation}"
        else:
            raise AssertionError(f"Checker missed unexpected response: {violation}")
    else:
        check_response(dut, response_expected, violation or "normal traffic")

    dut.clk.value = 1
    await Timer(1, unit="ns")
    #the supplied parent changes EX/MEM only after the consuming edge
    if next_owner is not None:
        drive(dut, **next_owner)
    await Timer(4, unit="ns")
    dut.clk.value = 0
    await Timer(1, unit="ns")


async def reset_controller(dut):
    drive(
        dut, clk=0, rst_n=1, instruction_valid=0, mem_en=0, mem_write=0,
        aligned_address=0, byte_enable=0, write_data=0,
        gnt=0, rvalid=0, rdata=0,
    )
    await Timer(1, unit="ns")
    dut.rst_n.value = 0
    await Timer(1, unit="ns")
    await tick(dut, 0, 0)
    #rst_n is already conditioned by the parent; release follows a clock edge
    dut.clk.value = 1
    await Timer(1, unit="ns")
    dut.rst_n.value = 1
    await Timer(1, unit="ns")
    dut.clk.value = 0
    await Timer(1, unit="ns")
    check_control(dut, 0, 0)


def drive_owner(
    dut, *, mem_write=0, address=0x0001_0020,
    byte_enable=0xF, write_data=0xA5A5_5A5A,
):
    drive(
        dut, instruction_valid=1, mem_en=1, mem_write=mem_write,
        aligned_address=address, byte_enable=byte_enable, write_data=write_data,
    )


async def complete_to_idle(dut, read_data=0x1234_5678):
    drive(dut, rvalid=1, rdata=read_data)
    await tick(
        dut, 0, 0, response_expected=True,
        next_owner={"instruction_valid": 0},
    )
    drive(dut, rvalid=0, gnt=0)
    await Timer(1, unit="ns")
    await tick(dut, 0, 0)


@cocotb.test()
async def test_idle_control(dut):
    await reset_controller(dut)

    #grant alone must not create ownership for a bubble or non-memory instruction
    drive(dut, instruction_valid=0, mem_en=0, gnt=1)
    await tick(dut, 0, 0)
    drive(dut, instruction_valid=0, mem_en=1)
    await tick(dut, 0, 0)
    drive(dut, instruction_valid=1, mem_en=0)
    await tick(dut, 0, 0)

    #the first valid memory owner must still present a new request
    drive_owner(dut)
    await tick(dut, 1, 1)
    check_control(dut, 0, 1)
    await complete_to_idle(dut)


@cocotb.test()
async def test_payload_routing(dut):
    await reset_controller(dut)

    #inactive payload is passed through, not zeroed
    drive(
        dut, aligned_address=0xFFFF_FFFC, mem_write=1,
        byte_enable=0x8, write_data=0xFFFF_FFFF, rdata=0x8000_0000,
    )
    await tick(dut, 0, 0)
    check_payload(
        dut, addr=0xFFFF_FFFC, we=1, be=0x8,
        wdata=0xFFFF_FFFF, read_data=0x8000_0000,
    )

    #load request, then its held payload while response data changes
    drive_owner(dut, address=0x19A7_42C0, byte_enable=0x3, write_data=0xDEAD_BEEF)
    drive(dut, rdata=0x0123_4567)
    await tick(dut, 1, 1)
    check_payload(
        dut, addr=0x19A7_42C0, we=0, be=0x3,
        wdata=0xDEAD_BEEF, read_data=0x0123_4567,
    )
    dut.gnt.value = 1
    await tick(dut, 1, 1)
    drive(dut, gnt=0, rdata=0x89AB_CDEF)
    await tick(dut, 0, 1)
    check_payload(
        dut, addr=0x19A7_42C0, we=0, be=0x3,
        wdata=0xDEAD_BEEF, read_data=0x89AB_CDEF,
    )
    await complete_to_idle(dut)

    #store control and payload also pass through unchanged
    drive_owner(
        dut, mem_write=1, address=0x8000_0000,
        byte_enable=0xC, write_data=0x8000_8000,
    )
    dut.gnt.value = 1
    await tick(dut, 1, 1)
    check_payload(
        dut, addr=0x8000_0000, we=1, be=0xC,
        wdata=0x8000_8000, read_data=0x1234_5678,
    )
    await complete_to_idle(dut, read_data=0xFFFF_FFFF)

    #shared reset clears validity and ownership, not payload wires
    drive(dut, rst_n=0, instruction_valid=0, rdata=0x7654_3210)
    await Timer(1, unit="ns")
    check_control(dut, 0, 0)
    check_payload(
        dut, addr=0x8000_0000, we=1, be=0xC,
        wdata=0x8000_8000, read_data=0x7654_3210,
    )


@cocotb.test()
async def test_delayed_grant(dut):
    #delay counts edges with request high and grant low before acceptance
    for delay in (0, 3, 120):
        await reset_controller(dut)
        dut.gnt.value = int(delay == 0)
        await Timer(1, unit="ns")
        drive_owner(
            dut, mem_write=1, address=0x724C_DA38,
            byte_enable=0x2, write_data=0xEFEF_EFEF,
        )
        for _ in range(delay):
            await tick(dut, 1, 1)
            check_payload(
                dut, addr=0x724C_DA38, we=1, be=0x2,
                wdata=0xEFEF_EFEF, read_data=0,
            )

        dut.gnt.value = 1
        await tick(dut, 1, 1)
        check_control(dut, 0, 1)
        await complete_to_idle(dut)


@cocotb.test()
async def test_delayed_response(dut):
    await reset_controller(dut)
    drive_owner(dut)
    dut.gnt.value = 1
    await tick(dut, 1, 1)

    #predetermined grant changes cannot grant another request while req is zero
    for grant in (1, 0, 1, 0):
        dut.gnt.value = grant
        await tick(dut, 0, 1)
        check_payload(
            dut, addr=0x0001_0020, we=0, be=0xF,
            wdata=0xA5A5_5A5A, read_data=0,
        )
    await complete_to_idle(dut)


@cocotb.test()
async def test_completion_timing(dut):
    #both load and store wait for a response; response data does not control wait
    for mem_write in (0, 1):
        for data in (0x0000_0000, 0xFFFF_FFFF):
            await reset_controller(dut)
            drive_owner(dut, mem_write=mem_write)
            dut.gnt.value = 1
            await tick(dut, 1, 1)
            check_control(dut, 0, 1)

            #earliest supported response: cycle after the accepting edge
            drive(dut, rvalid=1, rdata=data)
            await Timer(1, unit="ns")
            check_control(dut, 0, 0)
            assert int(dut.clk.value) == 0
            assert int(dut.read_data.value) == data
            await tick(
                dut, 0, 0, response_expected=True,
                next_owner={"instruction_valid": 0},
            )
            drive(dut, rvalid=0, gnt=0)
            await tick(dut, 0, 0)


@cocotb.test()
async def test_consecutive_transactions(dut):
    await reset_controller(dut)

    #load A is accepted exactly once
    drive_owner(dut, address=0x1000_0020)
    dut.gnt.value = 1
    await tick(dut, 1, 1)
    await tick(dut, 0, 1)

    #no store B request at A's response edge, even with grant already high
    drive(dut, rvalid=1, rdata=0x1111_2222)
    await tick(
        dut, 0, 0, response_expected=True,
        next_owner={
            "instruction_valid": 1, "mem_en": 1, "mem_write": 1,
            "aligned_address": 0x2000_0040, "byte_enable": 0xC,
            "write_data": 0xBEEF_BEEF,
        },
    )
    dut.rvalid.value = 0
    await Timer(1, unit="ns")
    check_control(dut, 1, 1)
    check_payload(
        dut, addr=0x2000_0040, we=1, be=0xC,
        wdata=0xBEEF_BEEF, read_data=0x1111_2222,
    )
    await tick(dut, 1, 1)
    await tick(dut, 0, 1)
    await complete_to_idle(dut, read_data=0x3333_4444)

    #bubble before load C must not leave a stale owner or duplicate request
    dut.gnt.value = 1
    await tick(dut, 0, 0)
    drive_owner(dut, address=0x3000_0080, byte_enable=0x1)
    await tick(dut, 1, 1)
    await tick(dut, 0, 1)
    await complete_to_idle(dut, read_data=0x5555_6666)


@cocotb.test()
async def test_unexpected_response(dut):
    selected_case = os.environ.get("OBI_NEGATIVE_CASE")
    cases = (selected_case,) if selected_case else (
        "idle", "waiting", "first_grant", "duplicate",
    )
    for case in cases:
        await reset_controller(dut)

        if case == "idle":
            #raw response drains, but must not manufacture ownership
            dut.rvalid.value = 1
            await tick(dut, 0, 0, violation=case)
            dut.rvalid.value = 0
            drive_owner(dut)
            dut.gnt.value = 1
            await tick(dut, 1, 1)

        elif case == "waiting":
            #ungranted request cannot be completed by an unrelated response
            drive_owner(dut)
            dut.rvalid.value = 1
            await tick(dut, 1, 1, violation=case)
            dut.rvalid.value = 0
            await tick(dut, 1, 1)
            dut.gnt.value = 1
            await tick(dut, 1, 1)

        elif case == "first_grant":
            #same-edge raw response cannot complete the newly granted request
            drive_owner(dut)
            drive(dut, gnt=1, rvalid=1)
            await tick(dut, 1, 1, violation=case)
            dut.rvalid.value = 0

        elif case == "duplicate":
            drive_owner(dut)
            dut.gnt.value = 1
            await tick(dut, 1, 1)
            await complete_to_idle(dut)
            #a second response after completion is also unexpected
            dut.rvalid.value = 1
            await tick(dut, 0, 0, violation=case)
            dut.rvalid.value = 0
            drive_owner(dut)
            dut.gnt.value = 1
            await tick(dut, 1, 1)

        else:
            raise AssertionError(f"Unknown negative case: {case}")

        #each injected response leaves a real accepted request waiting normally
        await tick(dut, 0, 1)
        await complete_to_idle(dut)


@cocotb.test()
async def test_reset_during_transaction(dut):
    for phase in ("idle", "waiting", "outstanding", "grant_edge", "response_edge"):
        await reset_controller(dut)
        if phase != "idle":
            drive_owner(dut, mem_write=1)
            await tick(dut, 1, 1)
        if phase in ("outstanding", "response_edge"):
            dut.gnt.value = 1
            await tick(dut, 1, 1)
            check_control(dut, 0, 1)

        #prepare transfer signals before asserting shared reset
        if phase == "grant_edge":
            dut.gnt.value = 1
            await Timer(1, unit="ns")
            check_control(dut, 1, 1)
        if phase == "response_edge":
            dut.rvalid.value = 1
            await Timer(1, unit="ns")
            check_control(dut, 0, 0)

        #parent validity clears with reset; no reset edge may accept work
        drive(dut, rst_n=0, instruction_valid=0)
        await Timer(1, unit="ns")
        check_control(dut, 0, 0)
        await tick(dut, 0, 0)
        #the subordinate flushes its pre-reset response before release
        drive(dut, gnt=0, rvalid=0)
        dut.clk.value = 1
        await Timer(1, unit="ns")
        dut.rst_n.value = 1
        await Timer(1, unit="ns")
        dut.clk.value = 0
        await Timer(1, unit="ns")
        await tick(dut, 0, 0)

        #a fresh post-reset request must not inherit old ownership
        drive_owner(dut, address=0xF631_8BCC)
        dut.gnt.value = 1
        await tick(dut, 1, 1)
        await tick(dut, 0, 1)
        await complete_to_idle(dut)


@cocotb.test()
async def test_reset_without_clock(dut):
    await reset_controller(dut)
    drive_owner(dut)
    dut.gnt.value = 1
    await tick(dut, 1, 1)
    check_control(dut, 0, 1)

    #stop the clock with an outstanding request, then assert shared reset
    drive(dut, rst_n=0, instruction_valid=0, gnt=0, rvalid=0)
    await Timer(20, unit="ns")
    assert int(dut.clk.value) == 0
    check_control(dut, 0, 0)

    #keep reset conditioned low until clock restart; this leaf has no synchronizer
    await Timer(20, unit="ns")
    assert int(dut.rst_n.value) == 0
    dut.clk.value = 1
    await Timer(1, unit="ns")
    dut.rst_n.value = 1
    await Timer(1, unit="ns")
    dut.clk.value = 0
    await Timer(1, unit="ns")
    drive_owner(dut, address=0x91B5_0C70)
    dut.gnt.value = 1
    await tick(dut, 1, 1)
    await complete_to_idle(dut)
