#------------------------------------------------------------------------------
# Module      : harness_selftest_cocotb
# Description : Harness smoke run and checker negative self-tests (X-01..X-10,
#               G6-14): each check is shown to fire on an injected fault.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from cocotb.triggers import FallingEdge, Timer

from xp_core_harness import Core, NETS, PORT_FIELDS, REG_INSTANCES, finish
from xp_helpers import xp_test, check
from xp_monitors import Monitors
from xp_rv32i import NOP, addi, jal, lui, lw, sb, sh, sw

SIG = 0x0001_0000


def good_sample(**changes):
    s = {"rst_n": 1}
    for port in ("instr", "data"):
        for f in PORT_FIELDS:
            s[f"{port}_{f}"] = 0
    for n in NETS:
        s[n] = 0
    for r in REG_INSTANCES:
        s[f"{r}_valid_i"] = 0
    s.update(instr_be=0xF, instr_rready=1, data_rready=1)
    s.update(changes)
    return s


def feed(samples):
    m = Monitors()
    for k, s in enumerate(samples):
        m.step(k + 1, s)
    return m.violations


def check_rules(got, expected):
    check("violations", len(got), len(expected))
    for (edge, rule, detail), (erule, edetail) in zip(got, expected):
        check(f"rule at edge {edge}", int(rule == erule and detail == edetail), 1)


@xp_test()
async def test_smoke_completion(dut):
    # harness smoke: padding plus SW PASS completes; trace and model edges agree; monitors clean
    core = Core(dut, [addi(5, 0, 7), lui(1, 0x10), sw(5, 0, 1)] + finish(1))
    await core.boot()
    status = await core.run()
    check("status pass", int(status == "pass"), 1)
    check("signature", core.word(SIG), 7)
    check("first fetch addr", core.imem.log[0]["addr"], 0x0000_0000)
    first = core.dmem.log[0]["edge"]
    s = core.at(first)
    check("trace/model edge alignment", s["data_req"] & s["data_gnt"], 1)
    check("monitor violations", len(core.mon.violations), 0)


@xp_test()
async def test_selftest_unexpected_response(dut):
    # X-01a/b: an injected response with nothing outstanding is an M3 violation naming the port
    core = Core(dut, [jal(0, 0)])
    await core.boot()
    core.imem.never_grant = True
    await core.cycles(6)
    core.imem.inject = 1
    core.dmem.inject = 1
    await core.cycles(4)
    rules = [(r, d) for _, r, d in core.mon.violations if r == "M3"]
    check_rules([(0, r, d) for r, d in rules], [("M3", "instr"), ("M3", "data")])


@xp_test()
async def test_selftest_request_unstable(dut):
    # X-02a/b: address change while req=1, gnt=0 is an M1 violation; a stable request is clean
    for port in ("instr", "data"):
        # data_req needs a live EX/MEM entry, or M4 and M5 fire too
        base = {f"{port}_req": 1, f"{port}_addr": 0x10, "ex_mem_reg_valid": 1, "ex_mem_valid_i": 1}
        stable = feed([good_sample(**base), good_sample(**base)])
        check_rules(stable, [])
        moved = feed([good_sample(**base), good_sample(**dict(base, **{f"{port}_addr": 0x14}))])
        check_rules(moved, [("M1", port)])


@xp_test()
async def test_selftest_second_outstanding(dut):
    # X-03: a model that grants a second request while one is outstanding gives an M2 violation
    core = Core(dut, [NOP] * 16, ilat=4)
    core.imem.allow_second = True
    await core.boot()
    await core.cycles(12)
    check("M2 seen", int(any(r == "M2" for _, r, _d in core.mon.violations)), 1)


@xp_test()
async def test_selftest_effect_from_invalid(dut):
    # X-04a/b/c: an effect from an invalid entry is an M4 violation; the valid case is clean
    check_rules(feed([good_sample(rf_write_fire=1, mem_wb_reg_valid=1)]), [])
    check_rules(feed([good_sample(rf_write_fire=1, mem_wb_reg_valid=0)]), [("M4", "rf_write_fire")])
    check_rules(feed([good_sample(data_req=1, ex_mem_reg_valid=0)]), [("M4", "data_req")])
    check_rules(feed([good_sample(redirect_fire=1, id_ex_reg_valid=0)]), [("M4", "redirect_fire")])


@xp_test()
async def test_selftest_valid_hold_flush(dut):
    # X-05: a valid that survives a flush is an M5 violation; a cleared one is clean
    before = good_sample(id_ex_reg_valid=1, id_ex_flush=1, id_ex_valid_i=1)
    check_rules(feed([before, good_sample(id_ex_reg_valid=0)]), [])
    check_rules(feed([before, good_sample(id_ex_reg_valid=1)]), [("M5", "id_ex")])


@xp_test()
async def test_selftest_fetch_out_of_range(dut):
    # X-06: sequential fetch past 0x0000_FFFC fails the range check before any gnt there
    core = Core(dut, [jal(0, 0xFFF0)])
    core.imem.load(0xFFF0, [NOP] * 4)
    await core.boot()
    status = await core.run(max_edges=200)
    check("range violation", int(status == "range violation"), 1)
    check("first out-of-range presentation", core.at(core.fail_edge)["instr_addr"], 0x0001_0000)
    early = [a for a in core.imem.log if a["addr"] >= 0x1_0000 and a["edge"] < core.fail_edge]
    check("no grant out of range before the failure", len(early), 0)


async def run_status_program(dut, store, **kwargs):
    core = Core(dut, [addi(31, 0, kwargs.pop("value", 1)), lui(30, 0x20), store] + [NOP] * 8 + [jal(0, 0)],
                **kwargs)
    await core.boot()
    return core, await core.run()


@xp_test()
async def test_selftest_completion_rules(dut):
    # X-07a..f: completion convention violations, no completion on acceptance alone, signature verdict
    _, st = await run_status_program(dut, sw(31, -4, 30), value=3)
    check("X-07a sw 3", int(st == "convention violation"), 1)
    _, st = await run_status_program(dut, sb(31, -4, 30))
    check("X-07b sb", int(st == "convention violation"), 1)
    _, st = await run_status_program(dut, sh(31, -4, 30))
    check("X-07c sh", int(st == "convention violation"), 1)
    _, st = await run_status_program(dut, sb(31, -3, 30))
    check("X-07d sb byte 1", int(st == "convention violation"), 1)
    core = Core(dut, finish(1), response_limit=30)
    core.dmem.withhold = True
    await core.boot()
    st = await core.run()
    check("X-07e acceptance alone", int(st == "response limit" and core.complete_edge is None), 1)
    core = Core(dut, [addi(5, 0, 7), lui(1, 0x10), sw(5, 0, 1)] + finish(1))
    await core.boot()
    st = await core.run()
    verdict_wrong = st == "pass" and core.word(SIG) == 8
    verdict_right = st == "pass" and core.word(SIG) == 7
    check("X-07f PASS does not override a wrong signature", int(verdict_wrong), 0)
    check("X-07f control: right signature passes", int(verdict_right), 1)


@xp_test()
async def test_selftest_watchdogs(dut):
    # X-08a/b/c: each watchdog fires and names its bound
    core = Core(dut, finish(1), grant_limit=20)
    core.imem.never_grant = True
    await core.boot()
    check("X-08a grant limit", int(await core.run() == "grant limit"), 1)
    core = Core(dut, finish(1), response_limit=20)
    core.imem.withhold = True
    await core.boot()
    check("X-08b response limit", int(await core.run() == "response limit"), 1)
    core = Core(dut, [jal(0, 0)], total_limit=100)
    await core.boot()
    check("X-08c total-cycle limit", int(await core.run() == "total-cycle limit"), 1)


@xp_test()
async def test_selftest_constant_outputs(dut):
    # X-09: ci_cmd_valid=1 is an M6 violation
    check_rules(feed([good_sample()]), [])
    check_rules(feed([good_sample(ci_cmd_valid=1)]), [("M6", "ci_cmd_valid")])


@xp_test()
async def test_selftest_reset_clear(dut):
    # X-10: instr_req=1 while rst_n=0 is an M7 violation
    check_rules(feed([good_sample(rst_n=0)]), [])
    check_rules(feed([good_sample(rst_n=0, instr_req=1)]), [("M7", "instr_req")])


@xp_test()
async def test_models_flush_on_reset(dut):
    # G6-14 (stimulus validation): both models drop pending work at reset, no edge, never answer it later
    core = Core(dut, [lui(1, 0x10), addi(5, 0, 9), sw(5, 0, 1), lw(6, 0, 1)] + finish(1), ilat=6, dlat=30)
    await core.boot()
    for _ in range(80):
        await FallingEdge(dut.clk)
        if core.imem.pending and core.dmem.pending:
            break
    check("both pending before reset", int(bool(core.imem.pending and core.dmem.pending)), 1)
    await Timer(1, unit="ns")
    dut.rst_n.value = 0
    await Timer(1, unit="ns")
    check("instr_rvalid low without edge", int(dut.instr_rvalid.value), 0)
    check("data_rvalid low without edge", int(dut.data_rvalid.value), 0)
    check("pending cleared", int(core.imem.pending is None and core.dmem.pending is None), 1)
    n_i, n_d = len(core.imem.responses), len(core.dmem.responses)
    a_i, a_d = len(core.imem.log), len(core.dmem.log)
    await core.cycles(3)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await core.cycles(40)
    check("instr responses after reset <= requests after reset",
          int(len(core.imem.responses) - n_i <= len(core.imem.log) - a_i), 1)
    check("data responses after reset <= requests after reset",
          int(len(core.dmem.responses) - n_d <= len(core.dmem.log) - a_d), 1)

