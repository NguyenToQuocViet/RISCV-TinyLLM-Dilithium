#------------------------------------------------------------------------------
# Module      : data_obi_controller_cocotb
# Description : Directed data OBI ownership, handshake, wait and reset checks.
# Author      : Codex
# Date        : 2026-10-23
#------------------------------------------------------------------------------

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, ReadWrite, RisingEdge, Timer

#ReadWrite after a rising edge models EX/MEM advance in the same timestep.
#ReadOnly then checks the settled controller outputs for the new parent entry.

async def reset_dut(dut):
    await FallingEdge(dut.clk)
    dut.rst_n.value             = 0
    dut.instruction_valid.value = 0
    dut.mem_en.value            = 0
    dut.mem_write.value         = 0
    dut.aligned_address.value   = 0
    dut.byte_enable.value       = 0
    dut.write_data.value        = 0
    dut.gnt.value               = 0
    dut.rvalid.value            = 0
    dut.rdata.value             = 0

    #hold reset through a sampling edge, then release on the falling edge
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await Timer(1, unit="ns")


def check_control(dut, expected_req, expected_wait):
    assert int(dut.req.value) == expected_req, (
        f"req: expected {expected_req}, got {dut.req.value}"
    )
    assert int(dut.mem_wait.value) == expected_wait, (
        f"mem_wait: expected {expected_wait}, got {dut.mem_wait.value}"
    )
    assert int(dut.rready.value) == 1, "rready must remain one"


@cocotb.test()
async def test_idle_control(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)

    await reset_dut(dut)
    check_control(dut, expected_req=0, expected_wait=0)

    #grant alone must not create ownership for a bubble or non-memory instruction
    for valid, mem_en in ((0, 0), (0, 1), (1, 0)):
        await FallingEdge(dut.clk)
        dut.instruction_valid.value = valid
        dut.mem_en.value            = mem_en
        dut.gnt.value               = 1

        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)

        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

    #the first real owner must still present a new request
    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.aligned_address.value   = 0x0001_0020

    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)

    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    #complete the accepted request, then advance the parent at that rising edge
    await FallingEdge(dut.clk)
    dut.gnt.value    = 0
    dut.rvalid.value = 1

    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)

    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.instruction_valid.value = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    clock.stop()


@cocotb.test()
async def test_payload_routing(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)
    await reset_dut(dut)

    #inactive payload passes through without being zeroed
    await FallingEdge(dut.clk)
    dut.aligned_address.value = 0xFFFF_FFFC
    dut.mem_write.value       = 1
    dut.byte_enable.value     = 0b1000
    dut.write_data.value      = 0xFFFF_FFFF
    dut.rdata.value           = 0x8000_0000
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.addr.value) == 0xFFFF_FFFC
    assert int(dut.we.value) == 1
    assert int(dut.be.value) == 0b1000
    assert int(dut.wdata.value) == 0xFFFF_FFFF
    assert int(dut.read_data.value) == 0x8000_0000

    #load request before grant
    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.mem_write.value         = 0
    dut.aligned_address.value   = 0x19A7_42C0
    dut.byte_enable.value       = 0b0011
    dut.write_data.value        = 0xDEAD_BEEF
    dut.rdata.value             = 0x0123_4567
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    assert int(dut.addr.value) == 0x19A7_42C0
    assert int(dut.we.value) == 0
    assert int(dut.be.value) == 0b0011
    assert int(dut.wdata.value) == 0xDEAD_BEEF
    assert int(dut.read_data.value) == 0x0123_4567

    #grant the load and keep the parent payload while waiting for response
    await FallingEdge(dut.clk)
    dut.gnt.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)
    await FallingEdge(dut.clk)
    dut.gnt.value   = 0
    dut.rdata.value = 0x89AB_CDEF
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=1)
    assert int(dut.addr.value) == 0x19A7_42C0
    assert int(dut.we.value) == 0
    assert int(dut.be.value) == 0b0011
    assert int(dut.wdata.value) == 0xDEAD_BEEF
    assert int(dut.read_data.value) == 0x89AB_CDEF

    #load response data is available before the consuming edge
    await FallingEdge(dut.clk)
    dut.rvalid.value = 1
    dut.rdata.value  = 0x1234_5678
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.read_data.value) == 0x1234_5678
    await RisingEdge(dut.clk)

    #replace the completed load with a store in the same edge's update phase
    await ReadWrite()
    dut.mem_write.value       = 1
    dut.aligned_address.value = 0x8000_0000
    dut.byte_enable.value     = 0b1100
    dut.write_data.value      = 0x8000_8000
    await ReadOnly()
    check_control(dut, expected_req=1, expected_wait=1)
    assert int(dut.addr.value) == 0x8000_0000
    assert int(dut.we.value) == 1
    assert int(dut.be.value) == 0b1100
    assert int(dut.wdata.value) == 0x8000_8000

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    dut.gnt.value    = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.gnt.value    = 0
    dut.rvalid.value = 1
    dut.rdata.value  = 0xFFFF_FFFF
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.read_data.value) == 0xFFFF_FFFF
    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.instruction_valid.value = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    #reset clears validity and ownership, not the payload wires
    await FallingEdge(dut.clk)
    dut.rst_n.value             = 0
    dut.instruction_valid.value = 0
    dut.rvalid.value            = 0
    dut.rdata.value             = 0x7654_3210
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.addr.value) == 0x8000_0000
    assert int(dut.we.value) == 1
    assert int(dut.be.value) == 0b1100
    assert int(dut.wdata.value) == 0x8000_8000
    assert int(dut.read_data.value) == 0x7654_3210
    clock.stop()


@cocotb.test()
async def test_delayed_grant(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)

    #delay counts edges with request high and grant low before acceptance
    for delay in (0, 3, 120):
        await reset_dut(dut)
        check_control(dut, expected_req=0, expected_wait=0)

        #drive request and predetermined grant together on the falling edge
        await FallingEdge(dut.clk)
        dut.gnt.value               = int(delay == 0)
        dut.instruction_valid.value = 1
        dut.mem_en.value            = 1
        dut.mem_write.value         = 1
        dut.aligned_address.value   = 0x724C_DA38
        dut.byte_enable.value       = 0b0010
        dut.write_data.value        = 0xEFEF_EFEF
        await Timer(1, unit="ns")
        check_control(dut, expected_req=1, expected_wait=1)
        assert int(dut.addr.value) == 0x724C_DA38
        assert int(dut.we.value) == 1
        assert int(dut.be.value) == 0b0010
        assert int(dut.wdata.value) == 0xEFEF_EFEF
        assert int(dut.read_data.value) == 0

        #each ungranted edge must leave the request and payload unchanged
        for _ in range(delay):
            await RisingEdge(dut.clk)
            await ReadOnly()
            check_control(dut, expected_req=1, expected_wait=1)
            assert int(dut.addr.value) == 0x724C_DA38
            assert int(dut.we.value) == 1
            assert int(dut.be.value) == 0b0010
            assert int(dut.wdata.value) == 0xEFEF_EFEF
            assert int(dut.read_data.value) == 0
            await FallingEdge(dut.clk)

        #grant alone does not release wait; acceptance occurs at the next edge
        #for delay zero, grant was already driven with the request
        if delay > 0:
            dut.gnt.value = 1
        await Timer(1, unit="ns")
        check_control(dut, expected_req=1, expected_wait=1)
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=1)

        #after grant, the accepted store still waits for its response
        await FallingEdge(dut.clk)
        dut.gnt.value = 0
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=1)

        #response releases wait before its consuming edge
        await FallingEdge(dut.clk)
        dut.rvalid.value = 1
        dut.rdata.value  = 0x1234_5678
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)
        assert int(dut.read_data.value) == 0x1234_5678
        await RisingEdge(dut.clk)

        #the parent advances to a bubble at the response edge
        await ReadWrite()
        dut.instruction_valid.value = 0
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

        await FallingEdge(dut.clk)
        dut.rvalid.value = 0
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

    clock.stop()


@cocotb.test()
async def test_delayed_response(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)
    await reset_dut(dut)

    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.aligned_address.value   = 0x0001_0020
    dut.byte_enable.value       = 0b1111
    dut.write_data.value        = 0xA5A5_5A5A
    dut.gnt.value               = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    #grant changes cannot accept anything while the DUT keeps req low
    for grant in (1, 0, 1, 0):
        await FallingEdge(dut.clk)
        dut.gnt.value = grant
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=1)
        assert int(dut.addr.value) == 0x0001_0020
        assert int(dut.we.value) == 0
        assert int(dut.be.value) == 0b1111
        assert int(dut.wdata.value) == 0xA5A5_5A5A
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.gnt.value    = 0
    dut.rvalid.value = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.instruction_valid.value = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    clock.stop()


@cocotb.test()
async def test_completion_timing(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)

    #load and store both wait for response, regardless of response data
    for mem_write in (0, 1):
        for data in (0x0000_0000, 0xFFFF_FFFF):
            await reset_dut(dut)
            await FallingEdge(dut.clk)
            dut.instruction_valid.value = 1
            dut.mem_en.value            = 1
            dut.mem_write.value         = mem_write
            dut.gnt.value               = 1
            await Timer(1, unit="ns")
            check_control(dut, expected_req=1, expected_wait=1)
            await RisingEdge(dut.clk)
            await ReadOnly()
            check_control(dut, expected_req=0, expected_wait=1)

            #earliest response: falling edge after grant, before the next rising edge
            await FallingEdge(dut.clk)
            dut.gnt.value    = 0
            dut.rvalid.value = 1
            dut.rdata.value  = data
            await Timer(1, unit="ns")
            check_control(dut, expected_req=0, expected_wait=0)
            assert int(dut.clk.value) == 0
            assert int(dut.read_data.value) == data
            await RisingEdge(dut.clk)

            await ReadWrite()
            dut.instruction_valid.value = 0
            await ReadOnly()
            check_control(dut, expected_req=0, expected_wait=0)

            await FallingEdge(dut.clk)
            dut.rvalid.value = 0
            await Timer(1, unit="ns")
            check_control(dut, expected_req=0, expected_wait=0)
            await RisingEdge(dut.clk)
            await ReadOnly()
            check_control(dut, expected_req=0, expected_wait=0)

    clock.stop()


@cocotb.test()
async def test_consecutive_transactions(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)
    await reset_dut(dut)

    #load A is accepted once
    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.aligned_address.value   = 0x1000_0020
    dut.byte_enable.value       = 0b1111
    dut.gnt.value               = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    #A's response edge must not also accept a request for B
    await FallingEdge(dut.clk)
    dut.rvalid.value = 1
    dut.rdata.value  = 0x1111_2222
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.read_data.value) == 0x1111_2222
    await RisingEdge(dut.clk)

    #A completes; EX/MEM changes to store B in the same timestep
    await ReadWrite()
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.mem_write.value         = 1
    dut.aligned_address.value   = 0x2000_0040
    dut.byte_enable.value       = 0b1100
    dut.write_data.value        = 0xBEEF_BEEF
    await ReadOnly()
    check_control(dut, expected_req=1, expected_wait=1)
    assert int(dut.addr.value) == 0x2000_0040
    assert int(dut.we.value) == 1
    assert int(dut.be.value) == 0b1100
    assert int(dut.wdata.value) == 0xBEEF_BEEF

    #memory drops A's response; B is accepted on the next rising edge
    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 1
    dut.rdata.value  = 0x3333_4444
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    await RisingEdge(dut.clk)

    #B completes; a valid non-memory instruction must not present another request
    await ReadWrite()
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 0
    dut.mem_write.value         = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    await RisingEdge(dut.clk)

    #the non-memory instruction advances to a bubble with grant still high
    await ReadWrite()
    dut.instruction_valid.value = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    #the following parent update admits load C with a new address and byte enable
    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.mem_write.value         = 0
    dut.aligned_address.value   = 0x3000_0080
    dut.byte_enable.value       = 0b0001
    await ReadOnly()
    check_control(dut, expected_req=1, expected_wait=1)
    assert int(dut.addr.value) == 0x3000_0080
    assert int(dut.we.value) == 0
    assert int(dut.be.value) == 0b0001

    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.gnt.value    = 0
    dut.rvalid.value = 1
    dut.rdata.value  = 0x5555_6666
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.read_data.value) == 0x5555_6666
    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.instruction_valid.value = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    clock.stop()


@cocotb.test()
async def test_unexpected_response(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)

    #these injections check DUT behavior, not a protocol monitor's diagnostic
    for case in ("idle", "waiting", "first_grant", "duplicate"):
        await reset_dut(dut)

        #prepare an ungranted request, or a transaction to complete before duplication
        if case in ("waiting", "first_grant", "duplicate"):
            await FallingEdge(dut.clk)
            dut.instruction_valid.value = 1
            dut.mem_en.value            = 1
            dut.aligned_address.value   = 0x0001_0020
            dut.gnt.value               = int(case == "duplicate")
            await Timer(1, unit="ns")
            check_control(dut, expected_req=1, expected_wait=1)

        if case == "duplicate":
            await RisingEdge(dut.clk)
            await ReadOnly()
            check_control(dut, expected_req=0, expected_wait=1)
            await FallingEdge(dut.clk)
            dut.gnt.value    = 0
            dut.rvalid.value = 1
            await Timer(1, unit="ns")
            check_control(dut, expected_req=0, expected_wait=0)
            await RisingEdge(dut.clk)
            await ReadWrite()
            dut.instruction_valid.value = 0
            await ReadOnly()
            check_control(dut, expected_req=0, expected_wait=0)

            await FallingEdge(dut.clk)
            dut.rvalid.value = 0
            await Timer(1, unit="ns")
            check_control(dut, expected_req=0, expected_wait=0)

        #inject the unrelated response; only first_grant also accepts a new request
        await FallingEdge(dut.clk)
        dut.rvalid.value = 1
        dut.gnt.value    = int(case == "first_grant")
        await Timer(1, unit="ns")
        if case in ("idle", "duplicate"):
            check_control(dut, expected_req=0, expected_wait=0)
        else:
            check_control(dut, expected_req=1, expected_wait=1)
        await RisingEdge(dut.clk)

        #remove the injected response before another rising edge
        await FallingEdge(dut.clk)
        dut.rvalid.value = 0
        dut.gnt.value    = 0
        await Timer(1, unit="ns")
        if case == "first_grant":
            #the grant established ownership; the unrelated response did not complete it
            check_control(dut, expected_req=0, expected_wait=1)
        else:
            if case == "waiting":
                check_control(dut, expected_req=1, expected_wait=1)
            else:
                check_control(dut, expected_req=0, expected_wait=0)

            #idle/duplicate start a fresh owner; waiting finally receives its grant
            await FallingEdge(dut.clk)
            dut.instruction_valid.value = 1
            dut.mem_en.value            = 1
            dut.aligned_address.value   = 0x0001_0020
            dut.gnt.value               = 1
            await Timer(1, unit="ns")
            check_control(dut, expected_req=1, expected_wait=1)
            await RisingEdge(dut.clk)
            await ReadOnly()
            check_control(dut, expected_req=0, expected_wait=1)

        #all four cases must still wait normally for a genuine accepted response
        await FallingEdge(dut.clk)
        dut.gnt.value    = 0
        dut.rvalid.value = 1
        dut.rdata.value  = 0x1234_5678
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)
        assert int(dut.read_data.value) == 0x1234_5678
        await RisingEdge(dut.clk)
        await ReadWrite()
        dut.instruction_valid.value = 0
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

        await FallingEdge(dut.clk)
        dut.rvalid.value = 0
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)

    clock.stop()


@cocotb.test()
async def test_reset_during_transaction(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)

    for phase in ("idle", "waiting", "outstanding", "grant_edge", "response_edge"):
        await reset_dut(dut)
        if phase != "idle":
            await FallingEdge(dut.clk)
            dut.instruction_valid.value = 1
            dut.mem_en.value            = 1
            dut.mem_write.value         = 1
            dut.aligned_address.value   = 0x8000_0000
            dut.byte_enable.value       = 0b1100
            dut.write_data.value        = 0xBEEF_BEEF
            await Timer(1, unit="ns")
            check_control(dut, expected_req=1, expected_wait=1)
            await RisingEdge(dut.clk)
            await ReadOnly()
            check_control(dut, expected_req=1, expected_wait=1)

        if phase in ("outstanding", "response_edge"):
            await FallingEdge(dut.clk)
            dut.gnt.value = 1
            await RisingEdge(dut.clk)
            await ReadOnly()
            check_control(dut, expected_req=0, expected_wait=1)

        #shared reset clears parent valid; pending transfer signals cannot complete work
        await FallingEdge(dut.clk)
        dut.rst_n.value             = 0
        dut.instruction_valid.value = 0
        if phase == "grant_edge":
            dut.gnt.value = 1
        if phase == "response_edge":
            dut.rvalid.value = 1
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

        #the subordinate drops pre-reset bus work before reset release
        await FallingEdge(dut.clk)
        dut.gnt.value    = 0
        dut.rvalid.value = 0
        dut.rst_n.value  = 1
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)

        #a fresh load must not inherit the old transaction's ownership
        await FallingEdge(dut.clk)
        dut.instruction_valid.value = 1
        dut.mem_en.value            = 1
        dut.mem_write.value         = 0
        dut.aligned_address.value   = 0xF631_8BCC
        dut.byte_enable.value       = 0b1111
        dut.gnt.value               = 1
        await Timer(1, unit="ns")
        check_control(dut, expected_req=1, expected_wait=1)
        assert int(dut.addr.value) == 0xF631_8BCC
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=1)

        await FallingEdge(dut.clk)
        dut.gnt.value    = 0
        dut.rvalid.value = 1
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)
        await RisingEdge(dut.clk)
        await ReadWrite()
        dut.instruction_valid.value = 0
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

        await FallingEdge(dut.clk)
        dut.rvalid.value = 0
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)

    clock.stop()


@cocotb.test()
async def test_reset_without_clock(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)
    await reset_dut(dut)

    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.aligned_address.value   = 0x0001_0020
    dut.gnt.value               = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    #stop low; asynchronous reset is deliberately asserted without any clock edge
    await FallingEdge(dut.clk)
    dut.gnt.value = 0
    clock.stop()
    await Timer(2, unit="ns")
    dut.rst_n.value             = 0
    dut.instruction_valid.value = 0
    await Timer(20, unit="ns")
    assert int(dut.clk.value) == 0
    check_control(dut, expected_req=0, expected_wait=0)
    await Timer(20, unit="ns")
    assert int(dut.clk.value) == 0
    check_control(dut, expected_req=0, expected_wait=0)

    #restart under reset, then release at a falling edge
    clock.start(start_high=False)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)

    #a fresh post-reset request must be accepted normally
    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.aligned_address.value   = 0x91B5_0C70
    dut.gnt.value               = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.gnt.value    = 0
    dut.rvalid.value = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.instruction_valid.value = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    clock.stop()
