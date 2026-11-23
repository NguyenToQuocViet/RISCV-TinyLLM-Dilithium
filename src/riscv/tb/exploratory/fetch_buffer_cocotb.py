#------------------------------------------------------------------------------
# Module      : fetch_buffer_cocotb
# Description : Directed tests of fetch_buffer (D-FB-01..05).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from cocotb.triggers import FallingEdge, RisingEdge

from xp_helpers import xp_test, drive, settle, expect, start_clock

PC_A, PC_B, PC_C, PC_D, PC_E = 0xA5A5_A5A4, 0x5A5A_5A58, 0x0000_0020, 0xFFFF_FFFC, 0x8000_0004
INS_A, INS_B, INS_C, INS_D, INS_E = 0xDEAD_BEEF, 0x0123_4567, 0xFEDC_BA98, 0xFFFF_FFFF, 0x8000_0001


async def at_fall(dut, **ports):
    await FallingEdge(dut.clk)
    drive(dut, **ports)
    await settle()


async def edge(dut):
    await RisingEdge(dut.clk)
    await settle()


async def write(dut, **ports):
    # one write edge; enables not named are low
    ports.setdefault("pc_write", 0)
    ports.setdefault("instruction_write", 0)
    await at_fall(dut, **ports)
    await edge(dut)


async def read_slot(dut, slot, pc, ins):
    await at_fall(dut, pc_write=0, instruction_write=0, present_slot=slot, fetch_slot=slot)
    expect(dut, present_pc=pc, fetch_pc=pc, fetch_instruction=ins)


async def fill(dut):
    for slot, pc in ((0, PC_A), (1, PC_B), (2, PC_C)):
        await write(dut, pc_write=1, pc_write_slot=slot, pc_write_data=pc)
    for slot, ins in ((0, INS_A), (1, INS_B), (2, INS_C)):
        await write(dut, instruction_write=1, instruction_write_slot=slot, instruction_write_data=ins)


@xp_test()
async def test_write_each_slot(dut):
    # D-FB-01: each slot written and read back, selectors independent, other slots unchanged
    start_clock(dut)
    await fill(dut)
    for (p, f), (ppc, fpc, fins) in zip(((0, 1), (1, 2), (2, 0)),
                                         ((PC_A, PC_B, INS_B), (PC_B, PC_C, INS_C), (PC_C, PC_A, INS_A))):
        await at_fall(dut, present_slot=p, fetch_slot=f)
        expect(dut, present_pc=ppc, fetch_pc=fpc, fetch_instruction=fins)
    await write(dut, pc_write=1, pc_write_slot=1, pc_write_data=PC_D)
    await write(dut, instruction_write=1, instruction_write_slot=1, instruction_write_data=INS_D)
    for (p, f), (ppc, fpc, fins) in zip(((0, 1), (1, 2), (2, 0)),
                                         ((PC_A, PC_D, INS_D), (PC_D, PC_C, INS_C), (PC_C, PC_A, INS_A))):
        await at_fall(dut, present_slot=p, fetch_slot=f)
        expect(dut, present_pc=ppc, fetch_pc=fpc, fetch_instruction=fins)


@xp_test()
async def test_enable_low_holds(dut):
    # D-FB-02: a slot holds while its enable is low, whatever slot and data ports carry
    start_clock(dut)
    await fill(dut)
    await at_fall(dut, pc_write=0, instruction_write=0, pc_write_slot=1, pc_write_data=PC_E,
                  instruction_write_slot=1, instruction_write_data=INS_E)
    for _ in range(3):
        await edge(dut)
    await read_slot(dut, 0, PC_A, INS_A)
    await read_slot(dut, 1, PC_B, INS_B)
    await read_slot(dut, 2, PC_C, INS_C)
    await write(dut, pc_write=1, pc_write_slot=0, pc_write_data=PC_E,
                instruction_write_slot=0, instruction_write_data=INS_E)
    await read_slot(dut, 0, PC_E, INS_A)
    await read_slot(dut, 1, PC_B, INS_B)
    await read_slot(dut, 2, PC_C, INS_C)
    await write(dut, instruction_write=1, instruction_write_slot=2, instruction_write_data=INS_E,
                pc_write_slot=2, pc_write_data=PC_E)
    await read_slot(dut, 0, PC_E, INS_A)
    await read_slot(dut, 1, PC_B, INS_B)
    await read_slot(dut, 2, PC_C, INS_E)


@xp_test()
async def test_both_writes_same_edge(dut):
    # D-FB-03: both arrays written on one edge, different then same slot
    start_clock(dut)
    await fill(dut)
    await write(dut, pc_write=1, pc_write_slot=0, pc_write_data=PC_D,
                instruction_write=1, instruction_write_slot=2, instruction_write_data=INS_D)
    await read_slot(dut, 0, PC_D, INS_A)
    await read_slot(dut, 2, PC_C, INS_D)
    await write(dut, pc_write=1, pc_write_slot=1, pc_write_data=PC_E,
                instruction_write=1, instruction_write_slot=1, instruction_write_data=INS_E)
    await read_slot(dut, 1, PC_E, INS_E)
    await read_slot(dut, 0, PC_D, INS_A)
    await read_slot(dut, 2, PC_C, INS_D)


@xp_test()
async def test_read_is_combinational(dut):
    # D-FB-04: a read follows its slot port in the same cycle, no edge
    start_clock(dut)
    await fill(dut)
    await FallingEdge(dut.clk)
    drive(dut, pc_write=0, instruction_write=0)
    for p, f, ppc, fpc, fins in ((0, 2, PC_A, PC_C, INS_C), (1, 0, PC_B, PC_A, INS_A),
                                 (2, 1, PC_C, PC_B, INS_B)):
        drive(dut, present_slot=p, fetch_slot=f)
        await settle()
        expect(dut, present_pc=ppc, fetch_pc=fpc, fetch_instruction=fins)


@xp_test()
async def test_write_visible_after_edge(dut):
    # D-FB-05: a write reaches no output before its edge and shows right after (trace E1, E2)
    start_clock(dut)
    await write(dut, pc_write=1, pc_write_slot=2, pc_write_data=PC_D)
    await write(dut, instruction_write=1, instruction_write_slot=2, instruction_write_data=INS_D)
    await at_fall(dut, pc_write=1, pc_write_slot=2, pc_write_data=0x20, instruction_write=0,
                  present_slot=2, fetch_slot=2)
    expect(dut, present_pc=PC_D)
    await edge(dut)
    expect(dut, present_pc=0x20)
    await at_fall(dut, pc_write=0, instruction_write=1, instruction_write_slot=2,
                  instruction_write_data=INS_B)
    expect(dut, fetch_instruction=INS_D, fetch_pc=0x20)
    await edge(dut)
    expect(dut, fetch_pc=0x20, fetch_instruction=INS_B)
