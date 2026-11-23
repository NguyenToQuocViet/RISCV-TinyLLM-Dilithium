#------------------------------------------------------------------------------
# Module      : hazard_control_unit_cocotb
# Description : Directed tests of hazard_control_unit (D-HCU-01..10).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from xp_helpers import xp_test, drive, settle, expect

OUTS = ("advance_allowed", "fetch_accept", "if_id_stall", "if_id_flush",
        "id_ex_stall", "id_ex_flush", "ex_mem_stall", "mem_wb_stall")
MEM_WAIT = (0, 0, 1, 0, 1, 0, 1, 1)
REDIRECT = (1, 0, 0, 1, 0, 1, 0, 0)
LOAD_USE = (1, 0, 1, 0, 0, 1, 0, 0)
NORMAL = (1, 1, 0, 0, 0, 0, 0, 0)

IDLE = {}
LU1 = dict(ex_valid=1, ex_mem_en=1, ex_mem_write=0, ex_rd=5, id_valid=1, id_rs1_id=5, id_rs1_used=1, id_rs2_id=7)
LU2 = dict(ex_valid=1, ex_mem_en=1, ex_mem_write=0, ex_rd=5, id_valid=1, id_rs1_id=3, id_rs2_id=5, id_rs2_used=1)
LU12 = dict(LU1, id_rs2_id=5, id_rs2_used=1)

INPUTS = ("rst_n", "mem_wait", "redirect_fire", "id_valid", "id_rs1_id", "id_rs2_id", "id_rs1_used",
          "id_rs2_used", "ex_valid", "ex_mem_en", "ex_mem_write", "ex_rd")


async def apply(dut, vector, **extra):
    ports = {name: 0 for name in INPUTS}
    ports["rst_n"] = 1
    ports.update(vector)
    ports.update(extra)
    drive(dut, **ports)
    await settle()


async def check_row(dut, vector, row, **extra):
    await apply(dut, vector, **extra)
    expect(dut, **dict(zip(OUTS, row)))


@xp_test()
async def test_reset_row(dut):
    # D-HCU-01: advance_allowed is 0 in reset, whatever else is true (HCU-D3)
    all_ones = dict(mem_wait=1, redirect_fire=1, id_valid=1, id_rs1_id=31, id_rs2_id=31, id_rs1_used=1,
                    id_rs2_used=1, ex_valid=1, ex_mem_en=1, ex_mem_write=1, ex_rd=31)
    for vector in (IDLE, dict(mem_wait=1), dict(redirect_fire=1), LU1, all_ones):
        await apply(dut, vector, rst_n=0)
        expect(dut, advance_allowed=0)


@xp_test()
async def test_mem_wait_row(dut):
    # D-HCU-02: MEM wait stalls all four registers and blocks fetch
    await check_row(dut, IDLE, MEM_WAIT, mem_wait=1)


@xp_test()
async def test_redirect_row(dut):
    # D-HCU-03: redirect flushes IF/ID and ID/EX, stalls nothing (HCU-D4)
    await check_row(dut, IDLE, REDIRECT, redirect_fire=1)


@xp_test()
async def test_load_use_row(dut):
    # D-HCU-04: load-use holds IF/ID and bubbles ID/EX, through rs1, rs2 and both
    for vector in (LU1, LU2, LU12):
        await check_row(dut, vector, LOAD_USE)


@xp_test()
async def test_normal_row(dut):
    # D-HCU-05: no event, everything advances and fetch is accepted
    await check_row(dut, IDLE, NORMAL)


@xp_test()
async def test_mem_wait_with_load_use(dut):
    # D-HCU-06: no ID/EX flush while the load must hold behind a MEM wait (HCU-D5)
    await check_row(dut, LU1, MEM_WAIT, mem_wait=1)
    await check_row(dut, LU12, MEM_WAIT, mem_wait=1)


@xp_test()
async def test_response_with_load_use(dut):
    # D-HCU-07: section 7 trace, load-use behind MEM wait, then the response
    await check_row(dut, LU1, MEM_WAIT, mem_wait=1)
    await check_row(dut, LU1, LOAD_USE, mem_wait=0)


@xp_test()
async def test_response_with_redirect(dut):
    # D-HCU-08: the response edge may redirect
    await check_row(dut, IDLE, MEM_WAIT, mem_wait=1)
    await check_row(dut, IDLE, REDIRECT, redirect_fire=1)


@xp_test()
async def test_stateless(dut):
    # D-HCU-09: outputs depend on current inputs only, both orders
    seq = [(IDLE, MEM_WAIT, dict(mem_wait=1)), (IDLE, REDIRECT, dict(redirect_fire=1)),
           (LU1, LOAD_USE, {}), (IDLE, NORMAL, {})]
    for vector, row, extra in seq + seq[::-1]:
        await check_row(dut, vector, row, **extra)


@xp_test()
async def test_load_use_qualifiers(dut):
    # D-HCU-10: what counts as a load-use (section 6 definition)
    negatives = [dict(LU1, ex_valid=0), dict(LU1, ex_mem_en=0), dict(LU1, ex_mem_write=1),
                 dict(LU1, ex_rd=0, id_rs1_id=0), dict(LU1, id_rs1_used=0), dict(LU2, id_rs2_used=0),
                 dict(LU1, id_valid=0), dict(LU1, id_rs1_id=4)]
    negatives += [dict(LU1, ex_rd=31, id_rs1_id=31 ^ (1 << b)) for b in range(5)]
    for vector in negatives:
        await check_row(dut, vector, NORMAL)
    await check_row(dut, dict(LU1, ex_rd=31, id_rs1_id=31), LOAD_USE)
