#------------------------------------------------------------------------------
# Module      : core_instr_obi_cocotb
# Description : core_top instruction-OBI rows (G4-01..G4-09) with scripted
#               grant delay and response latency.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from cocotb.triggers import FallingEdge

from xp_core_harness import Core, finish
from xp_helpers import xp_test, check
from xp_rv32i import NOP, addi, beq, lui, sw

D0 = 0x0001_0000


def check_clean(core, declared=()):
    got = [(r, d) for _, r, d in core.mon.violations]
    check("monitor violations", len(got), len(declared))
    for k, (r, d) in enumerate(declared):
        check(f"declared violation {k}", int(k < len(got) and got[k] == (r, d)), 1)


async def run_pass(core):
    await core.boot()
    check("status pass", int(await core.run() == "pass"), 1)


def instr_resp(core):
    return [r for r in core.imem.responses if not r["unexpected"]]


def waiting_edges(core, tx):
    # edges before the grant edge where the same request was presented and not granted
    g = tx["edge"]
    n = 0
    while g - 1 - n >= 1:
        s = core.at(g - 1 - n)
        if s["instr_req"] and not s["instr_gnt"] and s["instr_addr"] == tx["addr"]:
            n += 1
        else:
            break
    return n


@xp_test()
async def test_instr_request_stable(dut):
    # G4-01: with gnt delays 0, 1, 3, 8 the request and address hold until gnt, never retracted
    core = Core(dut, [NOP] * 6 + finish(1), igrant=[0, 1, 3, 8, 0])
    await run_pass(core)
    for k, delay in enumerate((0, 1, 3, 8)):
        tx = core.imem.log[k]
        check(f"tx{k} addr", tx["addr"], 4 * k)
        check(f"tx{k} waiting edges", waiting_edges(core, tx), delay)
    check_clean(core)


@xp_test()
async def test_instr_back_to_back(dut):
    # G4-02: gnt delay 0, latency 1: req stays 1 and one transaction is accepted per edge, addr += 4
    core = Core(dut, [NOP] * 16 + finish(1))
    await run_pass(core)
    log = core.imem.log[:10]
    for k, tx in enumerate(log):
        check(f"tx{k} addr", tx["addr"], 4 * k)
        check(f"tx{k} edge", tx["edge"], log[0]["edge"] + k)
    for e in range(log[0]["edge"], log[-1]["edge"] + 1):
        check(f"edge {e} instr_req", core.at(e)["instr_req"], 1)
    check_clean(core)


@xp_test()
async def test_instr_response_with_next_grant(dut):
    # G4-03: latency 3: request B is presented before the edge where A's response and B's gnt coincide
    core = Core(dut, [NOP] * 6 + finish(1), ilat=3)
    await run_pass(core)
    resp = [r["edge"] for r in instr_resp(core)]
    for k in range(1, 5):
        b = core.imem.log[k]
        check(f"B{k} granted on A's response edge", int(b["edge"] in resp), 1)
        pre = core.at(b["edge"] - 1)
        check(f"B{k} presented one edge before", pre["instr_req"] and pre["instr_addr"], b["addr"])
    check_clean(core)


@xp_test()
async def test_instr_steady_state(dut):
    # G4-04: 16 NOPs at gnt 0, latency 1: IF/ID stays valid and its pc advances by 4 each cycle
    core = Core(dut, [NOP] * 16 + finish(1))
    await run_pass(core)
    first = core.edges(if_id_reg_valid=1)[0]
    for k in range(16):
        s = core.at(first + k)
        check(f"cycle {k} if_id valid", s["if_id_reg_valid"], 1)
        check(f"cycle {k} if_id pc", s["if_id_reg_pc"], 4 * k)
    check_clean(core)


@xp_test()
async def test_instr_no_response_bypass(dut):
    # G4-05: the word answered on edge E is in IF/ID one edge later at the earliest
    core = Core(dut, [NOP] * 6 + finish(1))
    await run_pass(core)
    r0 = instr_resp(core)[0]["edge"]
    check("IF/ID empty right after the first response edge", core.at(r0 + 1)["if_id_reg_valid"], 0)
    entry = core.edges(if_id_reg_valid=1, if_id_reg_pc=0)[0]
    check("first entry not before response edge + 2", int(entry >= r0 + 2), 1)
    check_clean(core)


# beq at index 4 (0x10) jumps to index 12 (0x30); 0x14.. are wrong path
REDIRECT = [lui(1, 0x10), NOP, NOP, NOP, beq(0, 0, 32)] + [addi(9, 0, 0x99)] * 7 + \
    [addi(8, 0, 8), sw(8, 0, 1)] + finish(1)


@xp_test()
async def test_redirect_disposition_committed_waiting(dut):
    # G4-08e: wrong-path request presented without gnt across the redirect edge stays until its gnt
    core = Core(dut, REDIRECT, igrant=[0, 0, 0, 0, 0, 8, 0])
    await run_pass(core)
    red = core.edges(redirect_fire=1)[0]
    s = core.at(red)
    check("precondition: 0x14 presented, not granted, on the redirect edge",
          int(s["instr_req"] == 1 and s["instr_addr"] == 0x14 and s["instr_gnt"] == 0), 1)
    g14 = [t for t in core.imem.log if t["addr"] == 0x14][0]["edge"]
    for e in range(red, g14 + 1):
        check(f"edge {e} request held", core.at(e)["instr_req"] and core.at(e)["instr_addr"], 0x14)
    first_target = core.edges(instr_req=1, instr_addr=0x30)[0]
    check("target requested only after the wrong-path grant", int(first_target > g14), 1)
    check("wrong path never delivered", len(core.edges(if_id_reg_valid=1, if_id_reg_pc=0x14)), 0)
    check("x9 never retired", 9 in core.retire(), 0)
    check("target path ran", core.word(D0), 8)
    check_clean(core)


@xp_test()
async def test_redirect_disposition_unpresented(dut):
    # G4-08f: 0x14 outstanding, 0x18 presented, a later wrong-path address is never presented
    core = Core(dut, REDIRECT, ilat=[1, 1, 1, 1, 1, 8, 1])
    await run_pass(core)
    red = core.edges(redirect_fire=1)[0]
    s = core.at(red)
    check("precondition: 0x18 presented on the redirect edge", s["instr_req"] and s["instr_addr"], 0x18)
    check("precondition: 0x14 accepted before the redirect",
          int(any(t["addr"] == 0x14 and t["edge"] < red for t in core.imem.log)), 1)
    check("0x1C never presented", len(core.edges(instr_req=1, instr_addr=0x1C)), 0)
    check("x9 never retired", 9 in core.retire(), 0)
    check("target path ran", core.word(D0), 8)
    check_clean(core)


@xp_test()
async def test_redirect_target_timing(dut):
    # G4-08g: the target is requested two cycles after the redirect cycle at the earliest
    core = Core(dut, REDIRECT)
    await run_pass(core)
    red = core.edges(redirect_fire=1)[0]
    for e in (red, red + 1):
        s = core.at(e)
        check(f"edge {e} no target request", int(s["instr_req"] == 1 and s["instr_addr"] == 0x30), 0)
    first_target = core.edges(instr_req=1, instr_addr=0x30)[0]
    check("target not before redirect + 2", int(first_target >= red + 2), 1)
    check("redirect target net", core.at(red)["redirect_target"], 0x30)
    check_clean(core)


@xp_test()
async def test_unexpected_instr_response(dut):
    # G4-09a/b: an unexpected instr response is drained: no entry, no IF/ID valid, one M3 per pulse
    prog = [lui(1, 0x10), addi(5, 0, 5)] + [NOP] * 6 + [sw(5, 0, 1)] + finish(1)
    # a: idle port (no grants, nothing outstanding), one pulse
    core = Core(dut, prog)
    await core.boot()
    core.imem.never_grant = True
    for _ in range(20):
        await FallingEdge(dut.clk)
        if core.imem.pending is None:
            break
    core.imem.inject = 1
    await core.cycles(4)
    core.imem.never_grant = False
    check("a: status pass", int(await core.run() == "pass"), 1)
    check("a: sentinel never in IF/ID", len(core.edges(if_id_reg_instruction=core.imem.sentinel)), 0)
    check("a: program result", core.word(D0), 5)
    check_clean(core, [("M3", "instr")])
    # b: duplicate right after an expected response, no new grant in between
    core = Core(dut, prog)
    await core.boot()
    await core.cycles(6)
    core.imem.never_grant = True
    core.imem.inject_after_response = 1
    await core.cycles(6)
    core.imem.never_grant = False
    check("b: status pass", int(await core.run() == "pass"), 1)
    check("b: sentinel never in IF/ID", len(core.edges(if_id_reg_instruction=core.imem.sentinel)), 0)
    check("b: program result", core.word(D0), 5)
    check_clean(core, [("M3", "instr")])
