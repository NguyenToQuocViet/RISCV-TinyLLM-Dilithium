#------------------------------------------------------------------------------
# Module      : core_pipeline_control_cocotb
# Description : core_top pipeline-control rows (G3-01..G3-11). Scenario
#               anchors come from pipeline occupancy and port events; the
#               checked controls come from HCU section 6 and CT7.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from xp_core_harness import Core, finish
from xp_helpers import xp_test, check
from xp_rv32i import NOP, add, addi, beq, lui, lw, sw

D0 = 0x0001_0000          # x1 after the prologue; data word preset to 0x100
PRO = [lui(1, 0x10), addi(2, 0, 0x11)]
DATA = {D0: 0x0000_0100, D0 + 4: 0x0000_0200}
ROWS = dict(mem_wait=(0, 0, 1, 0, 1, 0, 1, 1), redirect=(1, 0, 0, 1, 0, 1, 0, 0),
            load_use=(1, 0, 1, 0, 0, 1, 0, 0), normal=(1, 1, 0, 0, 0, 0, 0, 0))
HCU_OUTS = ("advance_allowed", "fetch_accept", "if_id_stall", "if_id_flush",
            "id_ex_stall", "id_ex_flush", "ex_mem_stall", "mem_wb_stall")


def pc(i):
    return 4 * i


def check_row(label, s, row):
    for name, value in zip(HCU_OUTS, ROWS[row]):
        check(f"{label} {name}", s[name], value)


def check_clean(core):
    # M1..M7 clean on every core test (G3-11, T-01)
    check("monitor violations", len(core.mon.violations), 0)


async def run_pass(core):
    await core.boot()
    check("status pass", int(await core.run() == "pass"), 1)


@xp_test()
async def test_drain_without_new_instruction(dut):
    # G3-01: with fetch starved (latency 40), the four older instructions retire once each, in order
    prog = [lui(1, 0x10), addi(5, 0, 1), addi(6, 0, 2), addi(7, 0, 3), sw(5, 0, 1), sw(6, 4, 1),
            sw(7, 8, 1)] + finish(1)
    core = Core(dut, prog, ilat=[1, 1, 1, 1, 40, 1])
    await run_pass(core)
    starve = core.imem.log[4]["edge"]
    resp = [r["edge"] for r in core.imem.responses if not r["unexpected"]][4]
    window = range(starve + 1, resp)
    empty_if = [e for e in window if not core.at(e)["if_id_reg_valid"]]
    check("IF/ID empty during the starve window", int(len(empty_if) > 0), 1)
    pulses = [core.at(e)["mem_wb_reg_rd"] for e in range(1, resp + 1) if core.at(e)["rf_write_fire"]]
    check("retired before the starved word arrives", len(pulses), 4)
    for k, rd in enumerate((1, 5, 6, 7)):
        check(f"retire {k} rd", pulses[k], rd)
    last = core.at(resp)
    check("pipeline empty before the response", last["id_ex_reg_valid"] | last["ex_mem_reg_valid"] |
          last["mem_wb_reg_valid"] | last["if_id_reg_valid"], 0)
    check("x5", core.word(D0), 1)
    check("x6", core.word(D0 + 4), 2)
    check("x7", core.word(D0 + 8), 3)
    check_clean(core)


# lw at index 2, add at index 3
LOAD_USE = PRO + [lw(5, 0, 1), add(6, 5, 2), sw(6, 8, 1)] + finish(1)


@xp_test()
async def test_load_use_hold_and_bubble(dut):
    # G3-02: load in EX, user in ID: IF/ID holds, ID/EX gets a one-cycle bubble (HCU load-use row)
    core = Core(dut, LOAD_USE, data=DATA)
    await run_pass(core)
    lu = core.edges(id_ex_reg_valid=1, id_ex_reg_pc=pc(2), if_id_reg_valid=1, if_id_reg_pc=pc(3))
    check("load-use cycles", len(lu), 1)
    e = lu[0]
    s = core.at(e)
    check("if_id_stall", s["if_id_stall"], 1)
    check("id_ex_flush", s["id_ex_flush"], 1)
    check("id_ex_stall", s["id_ex_stall"], 0)
    check("if_id_flush", s["if_id_flush"], 0)
    check("fetch_accept", s["fetch_accept"], 0)
    check("advance_allowed", s["advance_allowed"], 1)
    after = core.at(e + 1)
    check("IF/ID pc held", after["if_id_reg_pc"], pc(3))
    check("IF/ID valid held", after["if_id_reg_valid"], 1)
    check("bubble in ID/EX", after["id_ex_reg_valid"], 0)
    # the load's own MEM wait (DTC, latency >= 1) stalls all four registers, so the bubble is held
    # until the load's response edge; the user enters EX on that edge (row gap: "for 1 cycle")
    ea, er = core.data_edges()[0]
    check("load request on the edge after the load-use edge", ea, e + 1)
    for k in range(e + 1, er + 1):
        check(f"edge {k} bubble held", core.at(k)["id_ex_reg_valid"], 0)
    later = core.at(er + 1)
    check("user enters EX after the load's response", later["id_ex_reg_valid"] and later["id_ex_reg_pc"], pc(3))
    check("x6 = mem + x2", core.word(D0 + 8), 0x111)
    check_clean(core)


# addi x3 (index 2) is in WB while lw (index 3) waits in MEM; younger ALU work fills the pipe
FREEZE = PRO + [addi(3, 0, 3), lw(5, 0, 1), addi(7, 0, 7), addi(8, 0, 8), addi(9, 0, 9),
                sw(5, 8, 1), sw(3, 12, 1)] + finish(1)


async def freeze_run(dut, dlat=6):
    core = Core(dut, FREEZE, data=DATA, dlat=dlat)
    await run_pass(core)
    ea, er = core.data_edges()[0]
    s = core.at(ea)
    check("precondition: pipeline full at the request",
          s["if_id_reg_valid"] & s["id_ex_reg_valid"] & s["ex_mem_reg_valid"] & s["mem_wb_reg_valid"], 1)
    check("precondition: lw owns MEM", s["ex_mem_reg_rd"], 5)
    check("precondition: addi x3 in WB", s["mem_wb_reg_rd"], 3)
    check("response latency", er - ea, dlat)
    return core, ea, er


@xp_test()
async def test_mem_wait_freeze(dut):
    # G3-03: every waiting cycle stalls all four registers, blocks fetch, retires nothing
    core, ea, er = await freeze_run(dut)
    first = core.at(ea)
    for e in range(ea, er):
        s = core.at(e)
        check(f"edge {e} mem_wait", s["mem_wait"], 1)
        check_row(f"edge {e}", s, "mem_wait")
        check(f"edge {e} rf_write_fire", s["rf_write_fire"], 0)
        for net in ("if_id_reg_pc", "mem_wb_reg_valid", "mem_wb_reg_rd", "mem_wb_reg_ex_result"):
            check(f"edge {e} {net} stable", s[net], first[net])
    check_clean(core)


@xp_test()
async def test_response_release(dut):
    # G3-04: on the response edge the held WB instruction retires once, the load enters MEM/WB
    core, ea, er = await freeze_run(dut)
    s = core.at(er)
    check("rf_write_fire on the response edge", s["rf_write_fire"], 1)
    check("held instruction retires", s["mem_wb_reg_rd"], 3)
    check("x3 retired exactly once", core.retire().count(3), 1)
    after = core.at(er + 1)
    check("load in MEM/WB", after["mem_wb_reg_valid"], 1)
    check("load rd in MEM/WB", after["mem_wb_reg_rd"], 5)
    check("x5 stored", core.word(D0 + 8), 0x100)
    check("x3 stored", core.word(D0 + 12), 3)
    check_clean(core)


async def redirect_behind(dut, mem_op):
    # mem op at index 2, beq at index 3 jumps to index 10; indices 4..9 are wrong path
    prog = PRO + [mem_op, beq(0, 0, 28)] + [addi(9, 0, 0x99)] * 6 + [sw(9, 16, 1)] + finish(1)
    core = Core(dut, prog, data=DATA, dlat=6)
    await run_pass(core)
    ea, er = core.data_edges()[0]
    check("precondition: beq in EX at the request",
          core.at(ea)["id_ex_reg_valid"] and core.at(ea)["id_ex_reg_pc"], pc(3))
    for e in range(ea, er):
        check(f"edge {e} redirect_fire held", core.at(e)["redirect_fire"], 0)
    check("redirect on the response edge", core.at(er)["redirect_fire"], 1)
    check("redirect target", core.at(er)["redirect_target"], pc(10))
    check("one redirect pulse", len(core.edges(redirect_fire=1)), 1)
    check_clean(core)
    return core


@xp_test()
async def test_redirect_behind_mem_wait(dut):
    # G3-06a/b: a branch behind a waiting load or store redirects once, on the response edge
    core = await redirect_behind(dut, lw(5, 0, 1))
    check("x9 stored from the target path only", 9 in core.retire(), 0)
    core = await redirect_behind(dut, sw(2, 0, 1))
    check("older store landed", core.word(D0), 0x11)
    check("x9 stored from the target path only", 9 in core.retire(), 0)


@xp_test()
async def test_response_with_redirect(dut):
    # G3-07: CT7 trace: Y in ID, J in EX, L in MEM, B in WB; rvalid low in cycle 1, high in cycle 2
    # B=addi x3 (2), L=lw x5 (3), J=beq (4) to index 12, Y=addi x9 (5)
    prog = PRO + [addi(3, 0, 3), lw(5, 0, 1), beq(0, 0, 32), addi(9, 0, 0x99)] + [NOP] * 8 + \
        [sw(5, 20, 1)] + finish(1)
    core = Core(dut, prog, data=DATA, dlat=2)
    await run_pass(core)
    ea, er = core.data_edges()[0]
    c1, c2 = core.at(er - 1), core.at(er)
    check("precondition Y in ID", c1["if_id_reg_valid"] and c1["if_id_reg_pc"], pc(5))
    check("precondition J in EX", c1["id_ex_reg_valid"] and c1["id_ex_reg_pc"], pc(4))
    check("precondition L in MEM", c1["ex_mem_reg_valid"] and c1["ex_mem_reg_rd"], 5)
    check("precondition B in WB", c1["mem_wb_reg_valid"] and c1["mem_wb_reg_rd"], 3)
    for name in ("if_id_stall", "id_ex_stall", "ex_mem_stall", "mem_wb_stall"):
        check(f"cycle 1 {name}", c1[name], 1)
    check("cycle 1 redirect_fire", c1["redirect_fire"], 0)
    check("cycle 1 advance_allowed", c1["advance_allowed"], 0)
    check("cycle 2 mem_wait", c2["mem_wait"], 0)
    check("cycle 2 advance_allowed", c2["advance_allowed"], 1)
    check("cycle 2 redirect_fire", c2["redirect_fire"], 1)
    check("cycle 2 if_id_flush", c2["if_id_flush"], 1)
    check("cycle 2 id_ex_flush", c2["id_ex_flush"], 1)
    check("cycle 2 B retires", c2["rf_write_fire"] and c2["mem_wb_reg_rd"], 3)
    after = core.at(er + 1)
    check("L in MEM/WB", after["mem_wb_reg_valid"] and after["mem_wb_reg_rd"], 5)
    check("J in EX/MEM", after["ex_mem_reg_valid"], 1)
    check("ID invalid", after["if_id_reg_valid"], 0)
    check("EX invalid", after["id_ex_reg_valid"], 0)
    check("x5 loaded", core.word(D0 + 20), 0x100)
    check("Y never retired", 9 in core.retire(), 0)
    check_clean(core)


# M = lw x3 (2), L = lw x5 (3), U = add x6 (4)
RESP_LU = PRO + [lw(3, 4, 1), lw(5, 0, 1), add(6, 5, 2), sw(6, 8, 1), sw(3, 12, 1)] + finish(1)


@xp_test()
async def test_response_with_load_use(dut):
    # G3-08: an older access completes on the load-use edge: M to MEM/WB, L to EX/MEM, bubble in ID/EX
    core = Core(dut, RESP_LU, data=DATA, dlat=[3, 1])
    await run_pass(core)
    ea, er = core.data_edges()[0]
    s = core.at(er)
    check("precondition L in EX", s["id_ex_reg_valid"] and s["id_ex_reg_pc"], pc(3))
    check("precondition U in ID", s["if_id_reg_valid"] and s["if_id_reg_pc"], pc(4))
    check("precondition M in MEM", s["ex_mem_reg_rd"], 3)
    check_row("response edge", s, "load_use")
    after = core.at(er + 1)
    check("M in MEM/WB", after["mem_wb_reg_valid"] and after["mem_wb_reg_rd"], 3)
    check("L in EX/MEM", after["ex_mem_reg_valid"] and after["ex_mem_reg_rd"], 5)
    check("bubble in ID/EX", after["id_ex_reg_valid"], 0)
    check("IF/ID holds U", after["if_id_reg_valid"] and after["if_id_reg_pc"], pc(4))
    check("x6", core.word(D0 + 8), 0x111)
    check("x3", core.word(D0 + 12), 0x200)
    check_clean(core)


@xp_test()
async def test_mem_wait_with_load_use(dut):
    # G3-09: MEM wait beats load-use: all four stall, no ID/EX flush, the load stays in ID/EX (HCU-D5)
    core = Core(dut, RESP_LU, data=DATA, dlat=[6, 1])
    await run_pass(core)
    ea, er = core.data_edges()[0]
    held = [e for e in range(ea, er) if core.at(e)["id_ex_reg_pc"] == pc(3) and core.at(e)["if_id_reg_pc"] == pc(4)]
    check("precondition: load-use pair held behind the wait", int(len(held) >= 3), 1)
    for e in held:
        s = core.at(e)
        check_row(f"edge {e}", s, "mem_wait")
        check(f"edge {e} load stays valid in ID/EX", core.at(e + 1)["id_ex_reg_valid"], 1)
    check("x6", core.word(D0 + 8), 0x111)
    check_clean(core)


@xp_test()
async def test_per_boundary_arbitration(dut):
    # G3-10: one sampled cycle per condition matches its HCU section 6 row; reset gives advance_allowed 0
    # normal: addi x4 (3) in EX; load-use: lw (4) in EX, add (5) in ID; MEM wait: lw in MEM; redirect: beq (6)
    prog = PRO + [addi(3, 0, 3), addi(4, 0, 4), lw(5, 0, 1), add(6, 5, 2), beq(0, 0, 16)] + [NOP] * 3 + \
        [sw(6, 8, 1)] + finish(1)
    core = Core(dut, prog, data=DATA, dlat=4)
    await run_pass(core)
    reset = [s for s in core.trace if not s["rst_n"]]
    check("reset sampled", int(len(reset) > 0), 1)
    check("reset advance_allowed", reset[-1]["advance_allowed"], 0)
    normal = core.edges(id_ex_reg_valid=1, id_ex_reg_pc=pc(3), mem_wait=0)
    check_row("normal", core.at(normal[0]), "normal")
    lu = core.edges(id_ex_reg_valid=1, id_ex_reg_pc=pc(4), if_id_reg_valid=1, if_id_reg_pc=pc(5))
    check_row("load-use", core.at(lu[0]), "load_use")
    ea, er = core.data_edges()[0]
    check_row("MEM wait", core.at(ea + 1), "mem_wait")
    rd = core.edges(id_ex_reg_valid=1, id_ex_reg_pc=pc(6), mem_wait=0)
    check_row("redirect", core.at(rd[0]), "redirect")
    check_clean(core)
