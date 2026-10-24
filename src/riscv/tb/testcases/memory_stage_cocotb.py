#------------------------------------------------------------------------------
# Module      : memory_stage_cocotb
# Description : Directed MEM request/response wiring and coordination checks.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-24
#------------------------------------------------------------------------------

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, ReadWrite, RisingEdge, Timer


async def reset_dut(dut):
    await FallingEdge(dut.clk)
    dut.rst_n.value             = 0
    dut.instruction_valid.value = 0
    dut.ex_result.value         = 0
    dut.store_data.value        = 0
    dut.mem_en.value            = 0
    dut.mem_write.value         = 0
    dut.mem_type.value          = 0
    dut.gnt.value               = 0
    dut.rvalid.value            = 0
    dut.rdata.value             = 0

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


def check_request(dut, expected_addr, expected_be, expected_we):
    assert int(dut.addr.value) == expected_addr, (
        f"addr: expected 0x{expected_addr:08X}, got {dut.addr.value}"
    )
    assert int(dut.be.value) == expected_be, (
        f"be: expected {expected_be:04b}, got {dut.be.value}"
    )
    assert int(dut.we.value) == expected_we, (
        f"we: expected {expected_we}, got {dut.we.value}"
    )


@cocotb.test()
async def test_access_paths(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)
    await reset_dut(dut)

    #test each load once; nonzero offsets distinguish original and aligned addresses
    #name, effective address, mem_type, aligned address, byte enable, response, expected load
    for name, address, mem_type, aligned, be, response, expected in (
        ("LB",  0x19A7_42C3, 0, 0x19A7_42C0, 0b1000, 0x8034_5678, 0xFFFF_FF80),
        ("LBU", 0xC407_EB19, 4, 0xC407_EB18, 0b0010, 0x1234_FE78, 0x0000_00FE),
        ("LH",  0x07DC_F526, 1, 0x07DC_F524, 0b1100, 0x8001_5678, 0xFFFF_8001),
        ("LHU", 0x4F10_CAE6, 5, 0x4F10_CAE4, 0b1100, 0xFEDC_1234, 0x0000_FEDC),
        ("LW",  0x8000_0020, 2, 0x8000_0020, 0b1111, 0x89AB_CDEF, 0x89AB_CDEF),
    ):
        dut._log.info("load path: %s", name)
        await FallingEdge(dut.clk)
        dut.instruction_valid.value = 1
        dut.mem_en.value            = 1
        dut.mem_write.value         = 0
        dut.mem_type.value          = mem_type
        dut.ex_result.value         = address
        dut.store_data.value        = 0xDEAD_BEEF
        dut.gnt.value               = 1
        dut.rvalid.value            = 0
        await Timer(1, unit="ns")
        check_control(dut, expected_req=1, expected_wait=1)
        check_request(dut, expected_addr=aligned, expected_be=be, expected_we=0)

        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=1)

        #response data must be formatted before the consuming rising edge
        await FallingEdge(dut.clk)
        dut.gnt.value    = 0
        dut.rvalid.value = 1
        dut.rdata.value  = response
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)
        result = int(dut.load_result.value)
        assert result == expected, f"{name}: expected 0x{expected:08X}, got 0x{result:08X}"

        await RisingEdge(dut.clk)
        await ReadWrite()
        dut.instruction_valid.value = 0
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

        await FallingEdge(dut.clk)
        dut.rvalid.value = 0

    #test each store once; upper store bits must not leak into byte/halfword replication
    #name, effective address, mem_type, store value, aligned address, byte enable, expected write data
    for name, address, mem_type, store, aligned, be, expected in (
        ("SB", 0x724C_DA39, 0, 0x1234_56A5, 0x724C_DA38, 0b0010, 0xA5A5_A5A5),
        ("SH", 0x91B5_0C72, 1, 0x1234_BEEF, 0x91B5_0C70, 0b1100, 0xBEEF_BEEF),
        ("SW", 0xF631_8BCC, 2, 0x89AB_CDEF, 0xF631_8BCC, 0b1111, 0x89AB_CDEF),
    ):
        dut._log.info("store path: %s", name)
        await FallingEdge(dut.clk)
        dut.instruction_valid.value = 1
        dut.mem_en.value            = 1
        dut.mem_write.value         = 1
        dut.mem_type.value          = mem_type
        dut.ex_result.value         = address
        dut.store_data.value        = store
        dut.gnt.value               = 1
        dut.rvalid.value            = 0
        await Timer(1, unit="ns")
        check_control(dut, expected_req=1, expected_wait=1)
        check_request(dut, expected_addr=aligned, expected_be=be, expected_we=1)
        result = int(dut.wdata.value)
        assert result == expected, f"{name}: expected 0x{expected:08X}, got 0x{result:08X}"

        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=1)

        #a store completes on its response; load_result has no required value here
        await FallingEdge(dut.clk)
        dut.gnt.value    = 0
        dut.rvalid.value = 1
        dut.rdata.value  = 0xDEAD_BEEF
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)

        await RisingEdge(dut.clk)
        await ReadWrite()
        dut.instruction_valid.value = 0
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

        await FallingEdge(dut.clk)
        dut.rvalid.value = 0

    clock.stop()


@cocotb.test()
async def test_wait_and_successors(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)
    await reset_dut(dut)

    #load A: hold an unsigned byte request through three ungranted rising edges
    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.mem_write.value         = 0
    dut.mem_type.value          = 4
    dut.ex_result.value         = 0x1000_0021
    dut.store_data.value        = 0x1234_56A5

    for _ in range(3):
        await Timer(1, unit="ns")
        check_control(dut, expected_req=1, expected_wait=1)
        check_request(dut, expected_addr=0x1000_0020, expected_be=0b0010, expected_we=0)
        assert int(dut.wdata.value) == 0xA5A5_A5A5
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=1, expected_wait=1)
        check_request(dut, expected_addr=0x1000_0020, expected_be=0b0010, expected_we=0)
        assert int(dut.wdata.value) == 0xA5A5_A5A5
        await FallingEdge(dut.clk)

    dut.gnt.value = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    #keep grant high: four response-wait edges must not accept another request
    for _ in range(4):
        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=1)
        check_request(dut, expected_addr=0x1000_0020, expected_be=0b0010, expected_we=0)
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 1
    dut.rdata.value  = 0x89AB_FE01
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.load_result.value) == 0x0000_00FE

    #A completes; parent replaces it with store B at the same rising edge
    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.mem_write.value  = 1
    dut.mem_type.value   = 1
    dut.ex_result.value  = 0x2000_0042
    dut.store_data.value = 0x1234_BEEF
    await ReadOnly()
    check_control(dut, expected_req=1, expected_wait=1)
    check_request(dut, expected_addr=0x2000_0040, expected_be=0b1100, expected_we=1)
    assert int(dut.wdata.value) == 0xBEEF_BEEF

    #B is presented after A's response edge, then accepted at the next rising edge
    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 1
    dut.rdata.value  = 0xFFFF_FFFF
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)

    #B completes; parent replaces it with signed byte load C
    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.mem_write.value  = 0
    dut.mem_type.value   = 0
    dut.ex_result.value  = 0x3000_0083
    dut.store_data.value = 0
    await ReadOnly()
    check_control(dut, expected_req=1, expected_wait=1)
    check_request(dut, expected_addr=0x3000_0080, expected_be=0b1000, expected_we=0)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.gnt.value    = 0
    dut.rvalid.value = 1
    dut.rdata.value  = 0x8034_5678
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.load_result.value) == 0xFFFF_FF80

    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.instruction_valid.value = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    clock.stop()


@cocotb.test()
async def test_idle_and_reset(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    clock.start(start_high=False)
    await reset_dut(dut)

    #bubble and non-memory owners must not issue despite grant and store-like payload
    for valid, mem_en in ((0, 1), (1, 0)):
        await FallingEdge(dut.clk)
        dut.instruction_valid.value = valid
        dut.mem_en.value            = mem_en
        dut.mem_write.value         = 1
        dut.mem_type.value          = 1
        dut.ex_result.value         = 0x724C_DA3A
        dut.store_data.value        = 0x1234_BEEF
        dut.gnt.value               = 1
        await Timer(1, unit="ns")
        check_control(dut, expected_req=0, expected_wait=0)
        await RisingEdge(dut.clk)
        await ReadOnly()
        check_control(dut, expected_req=0, expected_wait=0)

    #accept a load, then reset while its response is still pending
    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.mem_write.value         = 0
    dut.mem_type.value          = 2
    dut.ex_result.value         = 0x8000_0020
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    #shared reset clears parent valid and bus work; payload need not clear
    await FallingEdge(dut.clk)
    dut.rst_n.value             = 0
    dut.instruction_valid.value = 0
    dut.gnt.value               = 0
    dut.rvalid.value            = 0
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    #a fresh halfword load must use its own address, type and response after reset
    await FallingEdge(dut.clk)
    dut.instruction_valid.value = 1
    dut.mem_en.value            = 1
    dut.mem_write.value         = 0
    dut.mem_type.value          = 1
    dut.ex_result.value         = 0x91B5_0C72
    dut.gnt.value               = 1
    await Timer(1, unit="ns")
    check_control(dut, expected_req=1, expected_wait=1)
    check_request(dut, expected_addr=0x91B5_0C70, expected_be=0b1100, expected_we=0)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=1)

    await FallingEdge(dut.clk)
    dut.gnt.value    = 0
    dut.rvalid.value = 1
    dut.rdata.value  = 0xF123_4567
    await Timer(1, unit="ns")
    check_control(dut, expected_req=0, expected_wait=0)
    assert int(dut.load_result.value) == 0xFFFF_F123

    await RisingEdge(dut.clk)
    await ReadWrite()
    dut.instruction_valid.value = 0
    await ReadOnly()
    check_control(dut, expected_req=0, expected_wait=0)

    await FallingEdge(dut.clk)
    dut.rvalid.value = 0
    clock.stop()
