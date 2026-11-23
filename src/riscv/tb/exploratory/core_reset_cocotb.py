#------------------------------------------------------------------------------
# Module      : core_reset_cocotb
# Description : core_top reset rows (G6-01..G6-13) in direct-drive mode:
#               rst_n asserts asynchronously and is released at a falling edge.
#               G6-S1..S3 are Blocked (no reset_synchronizer).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from xp_core_harness import Core, finish
from xp_helpers import xp_test, check
from xp_monitors import RESET_CLEAR
from xp_rv32i import NOP, add, addi, beq, jal, jalr, lui, lw, sw

D0 = 0x0001_0000
PRO = [lui(1, 0x10), addi(2, 0, 0x11)]
LOOP = [jal(0, 0)]


def check_clean(core, tag=""):
    check(f"{tag}monitor violations", len(core.mon.violations), 0)


def check_cleared(dut, tag):
    # M7 nets read directly (no edge needed)
    for name in RESET_CLEAR:
        check(f"{tag} {name}", int(getattr(dut, name).value), 0)


async def assert_reset(dut):
    dut.rst_n.value = 0
    await Timer(200, unit="ps")


async def hold_and_release(core, edges=2, program=None):
    # keep rst_n low over `edges` rising edges, optionally swap the program, release at a falling edge
    for _ in range(edges):
        await RisingEdge(core.dut.clk)
    if program is not None:
        core.imem.words.clear()
        core.imem.load(0, program)
    await FallingEdge(core.dut.clk)
    core.dut.rst_n.value = 1
    return len(core.trace)


def first_request_after(core, edge):
    for e in range(edge + 1, len(core.trace) + 1):
        s = core.at(e)
        if s["rst_n"] and s["instr_req"]:
            return e, s["instr_addr"]
    return None, None


async def finish_pass(core, tag=""):
    check(f"{tag}status pass", int(await core.run() == "pass"), 1)


@xp_test()
async def test_reset_idle(dut):
    # G6-01: reset held 5 edges with the pipeline idle: M7 clean, first fetch at PC_RESET_VEC
    core = Core(dut, finish(1))
    await core.boot(reset_edges=5)
    await finish_pass(core)
    held = [s for s in core.trace if not s["rst_n"]]
    # 5 edges held; the first edge comes before the observer's first sample point
    check("reset edges sampled", len(held), 4)
    e, addr = first_request_after(core, 0)
    check("first request address", addr, 0x0000_0000)
    check_clean(core)


@xp_test()
async def test_reset_request_waiting_grant(dut):
    # G6-03a/b: reset while a request waits for gnt: req drops at once, restarts after release
    core = Core(dut, PRO + [sw(2, 0, 1)] + finish(1))
    await core.boot()
    core.imem.never_grant = True
    await core.cycles(4)
    check("a: precondition instr_req waiting", int(dut.instr_req.value) & (1 - int(dut.instr_gnt.value)), 1)
    await Timer(2, unit="ns")
    await assert_reset(dut)
    check("a: instr_req low at once", int(dut.instr_req.value), 0)
    core.imem.never_grant = False
    rel = await hold_and_release(core)
    await finish_pass(core, "a: ")
    check("a: first request after release", first_request_after(core, rel)[1], 0x0000_0000)
    check("a: model kept nothing", core.imem.log[0]["addr"], 0x0000_0000)
    check_clean(core, "a: ")
    core = Core(dut, PRO + [sw(2, 0, 1)] + finish(1))
    await core.boot()
    core.dmem.never_grant = True
    for _ in range(40):
        await FallingEdge(dut.clk)
        if int(dut.data_req.value):
            break
    await Timer(2, unit="ns")
    check("b: precondition data_req waiting", int(dut.data_req.value), 1)
    await assert_reset(dut)
    check("b: data_req low at once", int(dut.data_req.value), 0)
    core.dmem.never_grant = False
    await hold_and_release(core)
    await finish_pass(core, "b: ")
    check("b: data model kept nothing", core.dmem.log[0]["addr"], D0)
    check("b: store landed after restart", core.word(D0), 0x11)
    check_clean(core, "b: ")


@xp_test()
async def test_reset_instr_outstanding(dut):
    # G6-04: reset between instr request_fire and rvalid: the model drops it, the first word after is correct
    prog = PRO + [sw(2, 0, 1)] + finish(1)
    core = Core(dut, prog, ilat=[1, 10, 1])
    await core.boot()
    for _ in range(40):
        await FallingEdge(dut.clk)
        if core.imem.pending and core.imem.pending["left"] > 3:
            break
    check("precondition: transaction outstanding", int(core.imem.pending is not None), 1)
    await Timer(2, unit="ns")
    await assert_reset(dut)
    n_resp = len(core.imem.responses)
    rel = await hold_and_release(core)
    await finish_pass(core)
    after = core.imem.responses[n_resp:]
    check("first response after reset is word 0", after[0]["rdata"], prog[0])
    first_acc = [t for t in core.imem.log if t["edge"] > rel][0]
    check("no response before the first new request", int(after[0]["edge"] > first_acc["edge"]), 1)
    check("result", core.word(D0), 0x11)
    check_clean(core)


@xp_test()
async def test_reset_data_outstanding(dut):
    # G6-05a: reset while lw waits: data_req and mem_wait stay 0, no load result
    core = Core(dut, PRO + [lw(5, 0, 1), sw(5, 4, 1)] + finish(1), data={D0: 0x77}, dlat=[20, 1])
    await core.boot()
    for _ in range(60):
        await FallingEdge(dut.clk)
        if core.dmem.pending:
            break
    await Timer(2, unit="ns")
    check("a: precondition lw outstanding", int(core.dmem.pending is not None), 1)
    await assert_reset(dut)
    start = len(core.trace)
    rel = await hold_and_release(core, edges=3)
    for e in range(start + 1, rel + 1):
        s = core.at(e)
        check(f"a: edge {e} data_req", s["data_req"], 0)
        check(f"a: edge {e} mem_wait", s["mem_wait"], 0)
        check(f"a: edge {e} no x5 write", int(s["rf_write_fire"] and s["mem_wb_reg_rd"] == 5), 0)
    await finish_pass(core, "a: ")
    check("a: result after restart", core.word(D0 + 4), 0x77)
    check_clean(core, "a: ")
    # G6-05b: a store accepted before reset is not rolled back
    core = Core(dut, PRO + [sw(2, 0, 1)] + LOOP, dlat=20)
    await core.boot()
    for _ in range(60):
        await FallingEdge(dut.clk)
        if core.dmem.log:
            break
    await Timer(2, unit="ns")
    check("b: precondition store accepted", len(core.dmem.log), 1)
    await assert_reset(dut)
    await hold_and_release(core, program=[lui(1, 0x10), lw(5, 0, 1), sw(5, 4, 1)] + finish(1))
    await finish_pass(core, "b: ")
    check("b: stored word kept", core.word(D0), 0x11)
    check("b: lw returns it", core.word(D0 + 4), 0x11)
    check_clean(core, "b: ")


@xp_test()
async def test_reset_killed_response_pending(dut):
    # G6-06: wrong-path instr response pending after a taken branch, then reset: post-reset fetch is clean
    prog = [lui(1, 0x10), NOP, beq(0, 0, 24)] + [addi(9, 0, 9)] * 5 + [addi(8, 0, 8), sw(8, 0, 1)] + finish(1)
    core = Core(dut, prog, ilat=[1, 1, 1, 12, 1])
    await core.boot()
    red = await core.until(lambda s: s["redirect_fire"] == 1, 80)
    check("precondition: 0xC outstanding at the redirect",
          int(core.imem.pending is not None and core.imem.log[3]["addr"] == 0xC), 1)
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    await assert_reset(dut)
    n_resp = len(core.imem.responses)
    await hold_and_release(core)
    await finish_pass(core)
    check("first word after reset is word 0", core.imem.responses[n_resp]["rdata"], prog[0])
    check("x9 never retired", 9 in core.retire(), 0)
    check("target path ran", core.word(D0), 8)
    check_clean(core)


async def reset_on_handshake(dut, core, cond, tag):
    e = await core.until(cond, 80)
    await assert_reset(dut)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    check(f"{tag}: nothing accepted on the reset edge",
          len([t for t in core.imem.log + core.dmem.log if t["edge"] == e]), 0)
    return e


@xp_test()
async def test_reset_edge_with_handshake_high(dut):
    # G6-07a..d: reset on an edge with a handshake or a response high leaves no state behind
    prog = PRO + [NOP, sw(2, 0, 1)] + finish(1)
    core = Core(dut, prog)
    await core.boot()
    await reset_on_handshake(dut, core, lambda s: s["instr_req"] and s["instr_gnt"], "a")
    rel = await hold_and_release(core)
    await finish_pass(core, "a: ")
    check("a: first request after release", first_request_after(core, rel)[1], 0)
    check_clean(core, "a: ")
    core = Core(dut, prog)
    await core.boot()
    await reset_on_handshake(dut, core, lambda s: s["data_req"] and s["data_gnt"], "b")
    await hold_and_release(core)
    await finish_pass(core, "b: ")
    check("b: store after restart", core.word(D0), 0x11)
    check_clean(core, "b: ")
    # c: instr rvalid held high at the reset edge (forced; the model itself drops it)
    core = Core(dut, prog)
    await core.boot()
    e = await core.until(lambda s: s["instr_rvalid"] == 1, 80)
    await assert_reset(dut)
    dut.instr_rvalid.value = 1
    dut.instr_rdata.value = 0xDEAD_BEEF
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    check("c: no instruction captured", int(dut.fetch_valid.value), 0)
    check("c: IF/ID empty", int(dut.if_id_reg_valid.value), 0)
    await hold_and_release(core)
    await finish_pass(core, "c: ")
    check("c: junk never in IF/ID", len(core.edges(if_id_reg_instruction=0xDEAD_BEEF)), 0)
    check_clean(core, "c: ")
    # d: data rvalid of a lw at the reset edge: no load result, x5 keeps its old value
    core = Core(dut, [addi(5, 0, 0x55), lui(1, 0x10), lw(5, 0, 1)] + LOOP, data={D0: 0x1234_5678}, dlat=5)
    await core.boot()
    await core.until(lambda s: s["data_rvalid"] == 1, 80)
    await assert_reset(dut)
    dut.data_rvalid.value = 1
    dut.data_rdata.value = 0x1234_5678
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    await hold_and_release(core, program=[lui(1, 0x10), sw(5, 4, 1)] + finish(1))
    await finish_pass(core, "d: ")
    check("d: x5 keeps its old value", core.word(D0 + 4), 0x55)
    check_clean(core, "d: ")


async def reset_between_edges(dut, edge_trigger, tag):
    core = Core(dut, PRO + [addi(3, 0, 3), lw(5, 0, 1), addi(6, 0, 6), sw(5, 4, 1)] + finish(1),
                data={D0: 0x66}, dlat=[12, 1])
    await core.boot()
    await core.until(lambda s: s["mem_wait"] == 1, 80)
    await edge_trigger(dut.clk)
    await Timer(2, unit="ns")
    check(f"{tag}: precondition mem_wait", int(dut.mem_wait.value), 1)
    check(f"{tag}: precondition EX/MEM valid", int(dut.ex_mem_reg_valid.value), 1)
    dut.rst_n.value = 0
    await Timer(1, unit="ns")
    check_cleared(dut, f"{tag}: within 1 ns")
    await hold_and_release(core)
    await finish_pass(core, f"{tag}: ")
    check(f"{tag}: result after restart", core.word(D0 + 4), 0x66)
    check_clean(core, f"{tag}: ")


@xp_test()
async def test_reset_between_edges(dut):
    # G6-08a/b: rst_n falls 2 ns after a rising edge, then after a falling edge: cleared within 1 ns
    await reset_between_edges(dut, RisingEdge, "a")
    await reset_between_edges(dut, FallingEdge, "b")


@xp_test()
async def test_reset_clock_stopped(dut):
    # G6-09: clock stopped, reset asserted: M7 holds and both models drop rvalid with no edge
    core = Core(dut, PRO + [lw(5, 0, 1), sw(5, 4, 1)] + finish(1), data={D0: 0x99}, dlat=[10, 1])
    await core.boot()
    await core.until(lambda s: s["mem_wait"] == 1, 80)
    await FallingEdge(dut.clk)
    core.clock.stop()
    dut.clk.value = 0
    await Timer(3, unit="ns")
    await assert_reset(dut)
    await Timer(1, unit="ns")
    check_cleared(dut, "clock stopped")
    check("instr_rvalid", int(dut.instr_rvalid.value), 0)
    check("data_rvalid", int(dut.data_rvalid.value), 0)
    await Timer(30, unit="ns")
    check_cleared(dut, "still stopped")
    core.clock = Clock(dut.clk, 10, unit="ns")
    core.clock.start(start_high=False)
    await hold_and_release(core)
    await finish_pass(core)
    check("program completes after restart", core.word(D0 + 4), 0x99)
    check_clean(core)


async def reset_at_anchor(dut, prog, cond, tag, data=None, dlat=1, target=None):
    core = Core(dut, prog, data=data or {D0: 0x100}, dlat=dlat)
    await core.boot()
    e = await core.until(cond, 120)
    await assert_reset(dut)
    for name in ("if_id_reg_valid", "id_ex_reg_valid", "ex_mem_reg_valid", "mem_wb_reg_valid", "redirect_fire"):
        check(f"{tag}: {name} cleared", int(getattr(dut, name).value), 0)
    await hold_and_release(core)
    await finish_pass(core, f"{tag}: ")
    check(f"{tag}: no data accepted on the reset edge", len([t for t in core.dmem.log if t["edge"] == e]), 0)
    check(f"{tag}: no write after the reset edge", core.at(e + 1)["rf_write_fire"], 0)
    req_e, addr = first_request_after(core, e)
    check(f"{tag}: first request after reset", addr, 0)
    if target is not None:
        stale = [k for k in range(e + 1, req_e + 1) if core.at(k)["instr_req"] and core.at(k)["instr_addr"] == target]
        check(f"{tag}: stale target never requested", len(stale), 0)
    check_clean(core, f"{tag}: ")
    return core


@xp_test()
async def test_reset_during_stall_events(dut):
    # G6-10a..d: reset during a MEM wait, load-use, redirect and response-with-redirect edge: no side effect
    freeze = PRO + [addi(3, 0, 3), lw(5, 0, 1), addi(7, 0, 7), sw(5, 8, 1)] + finish(1)
    await reset_at_anchor(dut, freeze, lambda s: s["mem_wait"] == 1 and s["ex_mem_reg_rd"] == 5, "a", dlat=[8, 1])
    lu = PRO + [lw(5, 0, 1), add(6, 5, 2), sw(6, 8, 1)] + finish(1)
    await reset_at_anchor(dut, lu, lambda s: s["id_ex_reg_pc"] == 8 and s["id_ex_reg_valid"] and
                          s["if_id_reg_pc"] == 12 and s["if_id_reg_valid"], "b")
    br = PRO + [NOP, beq(0, 0, 28)] + [addi(9, 0, 9)] * 6 + [sw(2, 0, 1)] + finish(1)
    await reset_at_anchor(dut, br, lambda s: s["redirect_fire"] == 1, "c", target=0x2C)
    ct7 = PRO + [addi(3, 0, 3), lw(5, 0, 1), beq(0, 0, 32), addi(9, 0, 9)] + [NOP] * 8 + [sw(5, 20, 1)] + finish(1)
    await reset_at_anchor(dut, ct7, lambda s: s["data_rvalid"] == 1 and s["redirect_fire"] == 1, "d",
                          dlat=[2, 1], target=0x30)


@xp_test()
async def test_reset_ex_mem_valid_gates_mem(dut):
    # G6-11: a retained mem_en=1 payload in EX/MEM raises no data_req or mem_wait during reset, clock on then off
    core = Core(dut, PRO + [sw(2, 0, 1), NOP, NOP] + finish(1))
    await core.boot()
    core.dmem.never_grant = True
    await core.until(lambda s: s["data_req"] == 1 and s["ex_mem_reg_mem_en"] == 1, 80)
    core.dmem.never_grant = False
    await assert_reset(dut)
    start = len(core.trace)
    for _ in range(4):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    window = [core.at(e) for e in range(start + 1, len(core.trace) + 1)]
    check("precondition: mem_en=1 payload seen during reset", int(any(s["ex_mem_reg_mem_en"] for s in window)), 1)
    for k, s in enumerate(window):
        check(f"clock on {k} data_req", s["data_req"], 0)
        check(f"clock on {k} mem_wait", s["mem_wait"], 0)
    core.clock.stop()
    dut.clk.value = 0
    for _ in range(3):
        await Timer(10, unit="ns")
        check("clock off data_req", int(dut.data_req.value), 0)
        check("clock off mem_wait", int(dut.mem_wait.value), 0)
    core.clock = Clock(dut.clk, 10, unit="ns")
    core.clock.start(start_high=False)
    await hold_and_release(core)
    await finish_pass(core)
    check_clean(core)


@xp_test()
async def test_reset_payload_not_reset(dut):
    # G6-12: payload nets keep their values while the valids fall; x1..x31 unchanged (PR-E7 reading)
    values = {1: D0}
    values.update({k: k * 7 + 1 for k in range(2, 32)})
    prog = [lui(1, 0x10)] + [addi(k, 0, values[k]) for k in range(2, 32)] + \
        [NOP] * 4 + [addi(0, 0, 0x123), addi(0, 0, 0x456), addi(0, 0, 0x789)] + LOOP
    core = Core(dut, prog)
    await core.boot()
    await core.until(lambda s: s["id_ex_reg_valid"] and s["id_ex_reg_imm"] == 0x456, 200)
    nets = ("id_ex_reg_imm", "ex_mem_reg_ex_result", "if_id_reg_pc")
    before = {n: int(getattr(dut, n).value) for n in nets}
    check("precondition EX/MEM holds the 0x123 result", before["ex_mem_reg_ex_result"], 0x123)
    await assert_reset(dut)
    for n in nets:
        check(f"{n} kept", int(getattr(dut, n).value), before[n])
    for n in ("if_id_reg_valid", "id_ex_reg_valid", "ex_mem_reg_valid", "mem_wb_reg_valid"):
        check(f"{n} cleared", int(getattr(dut, n).value), 0)
    await hold_and_release(core, program=[sw(k, 4 * k, 1) for k in range(1, 32)] + finish(1))
    await finish_pass(core)
    for k in range(1, 32):
        check(f"x{k}", core.word(D0 + 4 * k), values[k])
    check_clean(core)


async def ex_async(dut, branch, tag, target):
    core = Core(dut, [lui(1, 0x10), NOP, NOP, branch] + [NOP] * 12 + finish(1))
    await core.boot()
    await core.until(lambda s: s["id_ex_reg_valid"] and s["id_ex_reg_pc"] == 0xC and s["mem_wait"] == 0, 80)
    check(f"{tag}: precondition redirect_fire", int(dut.redirect_fire.value), 1)
    check(f"{tag}: precondition target", int(dut.redirect_target.value), target)
    await assert_reset(dut)
    check(f"{tag}: redirect_fire cleared without an edge", int(dut.redirect_fire.value), 0)
    check(f"{tag}: id_ex valid cleared without an edge", int(dut.id_ex_reg_valid.value), 0)
    e = len(core.trace)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    check(f"{tag}: EX/MEM stays empty", int(dut.ex_mem_reg_valid.value), 0)
    await hold_and_release(core)
    await finish_pass(core, f"{tag}: ")
    req_e, addr = first_request_after(core, e)
    check(f"{tag}: first request after release", addr, 0)
    stale = [k for k in range(e + 1, req_e) if core.at(k)["instr_req"] and core.at(k)["instr_addr"] == target]
    check(f"{tag}: stale target not requested", len(stale), 0)
    check_clean(core, f"{tag}: ")


@xp_test()
async def test_reset_ex_async(dut):
    # G6-13a/b/c: EX under asynchronous reset: branch, jalr and store have no effect
    await ex_async(dut, beq(0, 0, 0x34), "a", 0x40)
    await ex_async(dut, jalr(0, 0x40, 0), "b", 0x40)
    core = Core(dut, PRO + [NOP, sw(2, 0, 1)] + [NOP] * 4 + LOOP)
    await core.boot()
    await core.until(lambda s: s["id_ex_reg_valid"] and s["id_ex_reg_pc"] == 0xC, 80)
    await assert_reset(dut)
    check("c: id_ex valid cleared without an edge", int(dut.id_ex_reg_valid.value), 0)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    check("c: EX/MEM stays empty", int(dut.ex_mem_reg_valid.value), 0)
    await hold_and_release(core, program=finish(1))
    await finish_pass(core, "c: ")
    check("c: the store never reached the port", len([t for t in core.dmem.log if t["addr"] == D0]), 0)
    check_clean(core, "c: ")
