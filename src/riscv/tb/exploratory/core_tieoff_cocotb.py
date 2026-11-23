#------------------------------------------------------------------------------
# Module      : core_tieoff_cocotb
# Description : core_top tie-off rows: constant CI and flush outputs (T-01),
#               unused inputs have no effect (T-02), no data-to-fetch path (T-05).
#               T-03 (profile elaboration) is in the runner, test_profile_elaboration.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from xp_core_harness import Core, finish
from xp_helpers import xp_test, check
from xp_monitors import CONSTANTS
from xp_rv32i import NOP, add, addi, beq, lui, lw, sw

D0 = 0x0001_0000
SEED = 20261119
PROG = [lui(1, 0x10), addi(2, 0, 0x11), lw(5, 0, 1), add(6, 5, 2), beq(0, 0, 12), addi(9, 0, 9),
        addi(9, 0, 9), sw(6, 4, 1)] + finish(1)


@xp_test()
async def test_constant_outputs(dut):
    # T-01: CI outputs and the two EX/MEM, MEM/WB flushes are 0 every cycle, reset included
    core = Core(dut, PROG, data={D0: 0x100})
    await core.boot(reset_edges=3)
    check("status pass", int(await core.run() == "pass"), 1)
    check("reset cycles sampled", int(any(not s["rst_n"] for s in core.trace)), 1)
    for name, value in CONSTANTS.items():
        bad = [k for k, s in enumerate(core.trace) if s[name] != value]
        check(f"{name} constant", len(bad), 0)
    check("monitor violations", len(core.mon.violations), 0)


async def toggle(dut, rng):
    while True:
        await FallingEdge(dut.clk)
        dut.ci_cmd_ready.value = rng.getrandbits(1)
        dut.ci_cmd_result.value = rng.getrandbits(32)
        dut.irq_external.value = rng.getrandbits(1)


async def run_with_inputs(dut, mode):
    core = Core(dut, PROG, data={D0: 0x100})
    level = 1 if mode == "one" else 0
    await core.boot(ci_cmd_ready=level, ci_cmd_result=0xFFFF_FFFF if level else 0, irq_external=level)
    task = None
    if mode == "toggle":
        task = cocotb.start_soon(toggle(dut, random.Random(SEED)))
    status = await core.run()
    if task:
        task.cancel()
    events = dict(
        instr=[(t["edge"], t["addr"]) for t in core.imem.log],
        data=[(t["edge"], t["addr"], t["we"], t["be"], t["wdata"]) for t in core.dmem.log],
        redirect=core.edges(redirect_fire=1),
    )
    return status, core.word(D0 + 4), events, core


@xp_test()
async def test_unused_inputs_no_effect(dut):
    # T-02: ci_cmd_ready, ci_cmd_result, irq_external held 0, held 1, toggled (seed 20261119): same run
    base = await run_with_inputs(dut, "zero")
    check("zero: status pass", int(base[0] == "pass"), 1)
    check("zero: signature", base[1], 0x111)
    for mode in ("one", "toggle"):
        status, sig, events, core = await run_with_inputs(dut, mode)
        check(f"{mode}: status pass", int(status == "pass"), 1)
        check(f"{mode}: signature", sig, 0x111)
        for key in ("instr", "data", "redirect"):
            check(f"{mode}: {key} events identical", int(events[key] == base[2][key]), 1)
        check(f"{mode}: monitors", len(core.mon.violations), 0)


@xp_test()
async def test_no_data_to_fetch_path(dut):
    # T-05: data_rvalid rises at a falling edge with fetch quiescent; instr_req does not move before the edge
    core = Core(dut, [lui(1, 0x10), lw(5, 0, 1)] + [NOP] * 8 + finish(1), data={D0: 7}, dlat=[8, 1])
    await core.boot()
    seen = 0
    for _ in range(80):
        await RisingEdge(dut.clk)
        await Timer(4, unit="ns")
        before = int(dut.instr_req.value)
        quiet = core.trace[-1]["instr_req"] == before if core.trace else False
        await FallingEdge(dut.clk)
        await Timer(1, unit="ps")
        if int(dut.data_rvalid.value) and core.trace[-1]["data_rvalid"] == 0:
            check("precondition: fetch quiescent", int(quiet), 1)
            check("instr_req in the same step", int(dut.instr_req.value), before)
            await Timer(1, unit="ns")
            check("instr_req 1 ns later", int(dut.instr_req.value), before)
            await Timer(3, unit="ns")
            check("instr_req before the rising edge", int(dut.instr_req.value), before)
            seen = 1
            break
    check("data_rvalid rise observed", seen, 1)
    check("status pass", int(await core.run() == "pass"), 1)
    check("monitor violations", len(core.mon.violations), 0)
