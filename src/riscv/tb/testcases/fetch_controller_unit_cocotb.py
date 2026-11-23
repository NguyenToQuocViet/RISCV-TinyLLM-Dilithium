#------------------------------------------------------------------------------
# Module      : fetch_controller_unit_cocotb
# Description : Cocotb testcases for the fetch controller
# Author      : Viet Nguyen To Quoc
# Date        : 2026-11-16
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer

def start_clock(dut):
    sys_clock = Clock(dut.clk, 10, "ns")
    sys_clock.start()

async def reset(dut):
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.redirect_fire.value = 0
    dut.fetch_accept.value = 0
    dut.request_fire.value = 0
    dut.raw_response_transfer.value = 0

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

async def drive(dut, redirect_target=None, fetch_accept=0, request_fire=0, raw_response_transfer=0):
    if redirect_target is None:
        dut.redirect_fire.value = 0
    else:
        dut.redirect_fire.value = 1
        dut.redirect_target.value = redirect_target

    dut.fetch_accept.value = fetch_accept
    dut.request_fire.value = request_fire
    dut.raw_response_transfer.value = raw_response_transfer
    await Timer(1, unit="ns")

async def next_edge(dut):
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)

def check_outputs(dut, **expected):
    for name, value in expected.items():
        got = int(getattr(dut, name).value)
        assert got == value, f"{name}: expected {value:#x}, got {got:#x}"

async def fill3(dut):
    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x4)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x4)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x8)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x8)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

async def trace(dut, b):
    await drive(dut, redirect_target=b)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, present_direct=1, fetch_valid=0, pc_write_data=b)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=b)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=b + 4)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=b + 4)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=b + 8)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=b + 8, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=0, present_valid=1, fetch_valid=1, pc_write_data=b + 12)

async def ready(dut):
    await trace(dut, 0x20)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=1, pc_write_data=0x2C)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=2)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=1, pc_write_data=0x2C)

@cocotb.test()
async def test_sequential_allocation(dut):
    start_clock(dut)
    await reset(dut)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x4)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x4)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x8)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x8)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

@cocotb.test()
async def test_reset_loads_reset_vector(dut):
    # sec 9 Reset
    start_clock(dut)
    await reset(dut)
    await trace(dut, 0x1C)

    dut.rst_n.value = 0
    await Timer(1, unit="ns")
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=0, instruction_write_slot=2)

    await drive(dut, fetch_accept=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=0, pc_write_data=0x0)

    await drive(dut, fetch_accept=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=0, pc_write_data=0x0)

    dut.rst_n.value = 1
    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x4)

@cocotb.test()
async def test_reset_clears_entries_and_marks(dut):
    # added: sec 5 reset values, killed clears at reset
    start_clock(dut)
    await reset(dut)
    await fill3(dut)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

    await drive(dut, redirect_target=0x100)
    check_outputs(dut, pc_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x100)

    dut.rst_n.value = 0
    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=0)
    await next_edge(dut)
    dut.rst_n.value = 1

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x4)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x4)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x8)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x8, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=0, present_valid=1, fetch_valid=1, pc_write_data=0xC)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=0, present_valid=1, fetch_valid=1, pc_write_data=0xC)

@cocotb.test()
async def test_hold_when_ring_full(dut):
    # sec 9 Hold when no slot is free
    start_clock(dut)
    await reset(dut)
    await fill3(dut)

    await drive(dut)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

    await drive(dut, fetch_accept=1)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

    await drive(dut)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

    await drive(dut)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

@cocotb.test()
async def test_ring_occupancy_outputs(dut):
    # sec 9 Occupied and empty ring
    start_clock(dut)
    await reset(dut)

    await drive(dut)
    check_outputs(dut, pc_write=1, present_valid=0, fetch_valid=0)

    await fill3(dut)
    await drive(dut)
    check_outputs(dut, pc_write=0, present_valid=1, fetch_valid=0)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=0, present_valid=1, fetch_valid=1)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=1, pc_write_data=0xC)

    await drive(dut)
    check_outputs(dut, pc_write=0, present_valid=0, fetch_valid=1)

@cocotb.test()
async def test_redirect_loads_target(dut):
    # sec 9 Redirect loads the target
    start_clock(dut)
    await reset(dut)

    await drive(dut, redirect_target=0x40)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, present_direct=1, fetch_valid=0, pc_write_data=0x40)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x40)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x44)

@cocotb.test()
async def test_redirect_target_no_path_to_pc_write_data(dut):
    # sec 9 No path from redirect to pc_write_data
    start_clock(dut)
    await reset(dut)

    await drive(dut)
    dut.redirect_target.value = 0x100
    await Timer(1, unit="ns")
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    dut.redirect_target.value = 0xFFFFFFFC
    await Timer(1, unit="ns")
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x4)

    await drive(dut, redirect_target=0x100)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x4)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x100)

@cocotb.test()
async def test_inputs_no_path_to_state_outputs(dut):
    # sec 9 Write enables off the presented path
    start_clock(dut)
    await reset(dut)
    await trace(dut, 0x1C)

    await drive(dut, fetch_accept=1)
    check_outputs(dut, pc_write=1, instruction_write=0, present_valid=1, fetch_valid=1, present_slot=2, fetch_slot=0, pc_write_slot=0, pc_write_data=0x28)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=1, present_valid=1, fetch_valid=1, present_slot=2, fetch_slot=0, pc_write_slot=0, pc_write_data=0x28)

    await drive(dut, fetch_accept=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, instruction_write=1, instruction_write_slot=1, present_valid=1, fetch_valid=1, present_slot=2, fetch_slot=0, pc_write_slot=0, pc_write_data=0x28)

    await drive(dut)
    check_outputs(dut, pc_write=0, instruction_write=0, present_valid=1, fetch_valid=1, present_slot=2, fetch_slot=0, pc_write_slot=0, pc_write_data=0x28)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=0, present_valid=1, fetch_valid=1, pc_write_data=0x28)

@cocotb.test()
async def test_redirect_all_ready(dut):
    # sec 9 Redirect with all entries READY
    start_clock(dut)
    await reset(dut)
    await ready(dut)

    await drive(dut, redirect_target=0x100)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, present_direct=1, fetch_valid=0, pc_write_data=0x100)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x100)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x104)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x104)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x108)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x108, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=1, pc_write_data=0x10C)

@cocotb.test()
async def test_redirect_ignores_delivery(dut):
    # sec 9 Delivery ignored on a redirect
    start_clock(dut)
    await reset(dut)
    await ready(dut)

    await drive(dut, redirect_target=0x100, fetch_accept=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x2C, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, present_direct=1, fetch_valid=0, pc_write_data=0x100)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x100)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x104)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x104)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x108)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x108)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x10C)

@cocotb.test()
async def test_redirect_trace_kept_entries(dut):
    # sec 9 Trace
    start_clock(dut)
    await reset(dut)
    await trace(dut, 0x1C)

    await drive(dut, redirect_target=0x100, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=2, present_valid=1, present_direct=1, fetch_valid=0, pc_write_data=0x100)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x100)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=2, present_valid=1, fetch_valid=0, pc_write_data=0x104)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x104, instruction_write=1, instruction_write_slot=2, fetch_valid=0)
    await next_edge(dut)
    # slot 0 is the live OUTSTANDING oldest entry; the response input is still high (FCU-D12)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=1, fetch_bypass=1, pc_write_data=0x108)

    # sec 7 trace edge 4: the target is delivered from the response word
    await drive(dut, fetch_accept=1, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x108, instruction_write=1, instruction_write_slot=0, fetch_valid=1, fetch_bypass=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=1, present_valid=1, present_direct=0, fetch_bypass=1, pc_write_data=0x10C)

@cocotb.test()
async def test_redirect_keeps_outstanding_and_queued(dut):
    # sec 9 Slot-role table, Killed drain
    start_clock(dut)
    await reset(dut)
    await fill3(dut)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

    await drive(dut, redirect_target=0x100)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x100)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x100)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x104)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x104, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=2, fetch_slot=1, present_valid=1, fetch_valid=0, pc_write_data=0x108)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x108, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=0, fetch_slot=2, present_valid=1, fetch_valid=1, fetch_bypass=1, pc_write_data=0x10C)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=2)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=2, present_valid=1, fetch_valid=1, pc_write_data=0x10C)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=2, present_valid=1, fetch_valid=1, pc_write_data=0x10C)

@cocotb.test()
async def test_redirect_all_queued(dut):
    # sec 9 Slot-role table
    start_clock(dut)
    await reset(dut)
    await fill3(dut)

    await drive(dut, redirect_target=0x100)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x100)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x100)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x104)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x104)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x108)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x108, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=2, fetch_slot=1, present_valid=1, fetch_valid=1, fetch_bypass=1, pc_write_data=0x10C)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=2, fetch_slot=1, present_valid=1, fetch_valid=1, pc_write_data=0x10C)

@cocotb.test()
async def test_back_to_back_redirect(dut):
    # sec 9, sec 8 Back-to-back redirect
    start_clock(dut)
    await reset(dut)
    await trace(dut, 0x1C)

    await drive(dut, redirect_target=0x100)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=1, present_valid=1, fetch_valid=0, pc_write_data=0x100)

    await drive(dut, redirect_target=0x200)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x100, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=1, present_valid=1, fetch_valid=0, pc_write_data=0x200)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x200)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=2, fetch_slot=1, present_valid=1, fetch_valid=0, pc_write_data=0x204)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x204, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=2, fetch_slot=2, present_valid=1, fetch_valid=0, pc_write_data=0x208)

@cocotb.test()
async def test_pointer_wrap(dut):
    # sec 9 Pointer wrap, fill and steady
    start_clock(dut)
    await reset(dut)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x4)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x4)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0x8)

    await drive(dut, redirect_target=0x20, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x8, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=2, fetch_slot=1, present_valid=1, present_direct=1, fetch_valid=0, pc_write_data=0x20)

    # fill: drain the killed slot 1 while 0x20 is presented directly and granted
    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x20, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=2, present_valid=1, present_direct=1, pc_write_data=0x24)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x24, instruction_write=1, instruction_write_slot=2)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=1, fetch_slot=2, present_valid=1, present_direct=1, fetch_valid=1, pc_write_data=0x28)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x28, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=2, fetch_slot=2, present_valid=0, fetch_valid=1, pc_write_data=0x2C)

    # steady: deliveries 0x20, 0x24, 0x28
    await drive(dut, fetch_accept=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x2C, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=0, present_valid=1, present_direct=0, fetch_valid=1, pc_write_data=0x30)

    await drive(dut, fetch_accept=1, request_fire=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x30, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=1, present_valid=1, present_direct=0, fetch_valid=1, pc_write_data=0x34)

    await drive(dut, fetch_accept=1, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x34, instruction_write=1, instruction_write_slot=2)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=2, present_valid=1, present_direct=0, fetch_valid=1, pc_write_data=0x38)

@cocotb.test()
async def test_slot_reuse_same_edge(dut):
    # sec 9 Reuse of a slot freed on the edge
    start_clock(dut)
    await reset(dut)
    await trace(dut, 0x08)

    await drive(dut)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=2, fetch_slot=0, present_valid=1, fetch_valid=1, pc_write_data=0x14)

    await drive(dut, fetch_accept=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x14)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=2, fetch_slot=1, present_valid=1, fetch_valid=0, pc_write_data=0x18)

    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=1, present_valid=1, fetch_valid=1, pc_write_data=0x18)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=1, instruction_write_slot=2)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=1, present_valid=1, fetch_valid=1, pc_write_data=0x18)

@cocotb.test()
async def test_unexpected_response(dut):
    # sec 9, sec 8 Unexpected response
    start_clock(dut)
    await reset(dut)
    await fill3(dut)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

    await drive(dut)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=1, fetch_valid=0, pc_write_data=0xC)

    await reset(dut)
    await ready(dut)

    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=1, pc_write_data=0x2C)

    await drive(dut)
    check_outputs(dut, pc_write=0, instruction_write=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=0, present_valid=0, fetch_valid=1, pc_write_data=0x2C)

@cocotb.test()
async def test_start_after_reset(dut):
    # sec 9 Start after reset: no direct presentation before the first edge
    start_clock(dut)
    await reset(dut)

    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x0, present_valid=0, present_direct=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, present_valid=1, present_direct=0, pc_write_data=0x4)

@cocotb.test()
async def test_direct_presentation_grant(dut):
    # sec 9 Direct presentation with a grant
    start_clock(dut)
    await reset(dut)

    await drive(dut, redirect_target=0x40)
    await next_edge(dut)
    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x40, present_slot=0, present_valid=1, present_direct=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=1, fetch_slot=0, present_valid=1, present_direct=1, pc_write_data=0x44)

    # slot 0 answers as OUTSTANDING: it never passed QUEUED
    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, instruction_write=1, instruction_write_slot=0, fetch_valid=1, fetch_bypass=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, present_direct=0, fetch_valid=1, fetch_bypass=0, pc_write_data=0x48)

@cocotb.test()
async def test_direct_presentation_no_grant(dut):
    # sec 9 Direct presentation without a grant
    start_clock(dut)
    await reset(dut)

    await drive(dut, redirect_target=0x40)
    await next_edge(dut)
    await drive(dut)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x40, present_slot=0, present_valid=1, present_direct=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=0, fetch_slot=0, present_valid=1, present_direct=0, fetch_valid=0, pc_write_data=0x44)

    await drive(dut, request_fire=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x44)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=1, fetch_slot=0, present_valid=1, present_direct=0, fetch_valid=0, pc_write_data=0x48)

@cocotb.test()
async def test_redirect_direct_presented(dut):
    # sec 9 Redirect with a slot presented directly
    start_clock(dut)
    await reset(dut)

    await drive(dut, redirect_target=0x20)
    await next_edge(dut)
    await drive(dut, request_fire=1)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=1, present_slot=1, fetch_slot=0, present_valid=1, present_direct=1, pc_write_data=0x24)

    await drive(dut, redirect_target=0x100, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=1, pc_write_data=0x24, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=2, present_slot=2, fetch_slot=1, present_valid=1, present_direct=1, fetch_valid=0, pc_write_data=0x100)

    # killed drain of slot 1 while the target is presented directly and granted
    await drive(dut, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x100, instruction_write=1, instruction_write_slot=1, fetch_valid=0)
    await next_edge(dut)
    check_outputs(dut, pc_write_slot=0, present_slot=0, fetch_slot=2, present_valid=1, present_direct=1, pc_write_data=0x104)

    await drive(dut, fetch_accept=1, request_fire=1, raw_response_transfer=1)
    check_outputs(dut, pc_write=1, pc_write_slot=0, pc_write_data=0x104, instruction_write=1, instruction_write_slot=2, fetch_valid=1, fetch_bypass=1, fetch_slot=2)
    await next_edge(dut)
    # slot 2 freed without READY; slot 0 is the oldest entry, OUTSTANDING 0x104
    check_outputs(dut, pc_write_slot=1, present_slot=1, fetch_slot=0, present_valid=1, present_direct=1, fetch_bypass=1, pc_write_data=0x108)
    await drive(dut)
    check_outputs(dut, fetch_valid=0, fetch_bypass=1, fetch_slot=0)

@cocotb.test()
async def test_response_bypass(dut):
    # sec 9 Response bypass, accepted and held; killed drain is never bypassed
    start_clock(dut)
    await reset(dut)

    await drive(dut, redirect_target=0x40)
    await next_edge(dut)
    await drive(dut, request_fire=1)
    await next_edge(dut)
    # slot 0 live OUTSTANDING at tail_ptr, slot 1 presented directly
    await drive(dut)
    check_outputs(dut, fetch_slot=0, fetch_bypass=1, fetch_valid=0)

    # held: response with fetch_accept low; slot 0 becomes READY, and slot 1,
    # presented directly without a grant, becomes QUEUED with 0x44
    await drive(dut, raw_response_transfer=1)
    check_outputs(dut, fetch_valid=1, fetch_bypass=1, instruction_write=1, instruction_write_slot=0)
    await next_edge(dut)
    await drive(dut)
    check_outputs(dut, fetch_slot=0, fetch_valid=1, fetch_bypass=0, present_slot=1, present_valid=1, present_direct=0)

    # deliver READY slot 0 while slot 1 (0x44) is granted; 0x48 is allocated as QUEUED
    await drive(dut, fetch_accept=1, request_fire=1)
    await next_edge(dut)
    await drive(dut)
    check_outputs(dut, fetch_slot=1, fetch_bypass=1, fetch_valid=0, present_slot=2, present_direct=0, pc_write_data=0x4C)

    # accepted: response of slot 1 is delivered on its edge, the slot is freed without READY
    await drive(dut, fetch_accept=1, raw_response_transfer=1)
    check_outputs(dut, fetch_valid=1, fetch_bypass=1, fetch_slot=1, instruction_write=1, instruction_write_slot=1)
    await next_edge(dut)
    await drive(dut)
    check_outputs(dut, fetch_slot=2, fetch_valid=0, fetch_bypass=0, present_slot=2, present_valid=1, pc_write_slot=1, pc_write_data=0x50)
