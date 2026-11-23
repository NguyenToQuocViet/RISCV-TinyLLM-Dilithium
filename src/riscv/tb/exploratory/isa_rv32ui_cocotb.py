#------------------------------------------------------------------------------
# Module      : isa_rv32ui_cocotb
# Description : riscv-tests rv32ui on core_top with the BASE env: 40 tests,
#               memory fixed and jitter. Verdict per run: status pass, last
#               test number at 0x1_FFF8 equal to the source's last test case,
#               no monitor violation. Expected values are the literals in the
#               riscv-tests sources (pin in xp_isa.PIN).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#------------------------------------------------------------------------------

import time

from xp_core_harness import Core
from xp_helpers import xp_test, check
from xp_isa import LAST_TESTNUM, TESTS, build, check_pin, first_broken, jitter_kw, last_testnum
from xp_sw import check_ops, load_image

SEED = 20261120
LIMIT = 20000


async def run_test(dut, name, mem, defines=()):
    # build, gate, load, run; returns (status, reported test number, cycles, violations)
    elf, hexf = build(name, defines)
    check_ops(elf)
    code, data = load_image(hexf)
    kw = jitter_kw(SEED) if mem == "jitter" else {}
    core = Core(dut, [], data=data, total_limit=LIMIT, keep_trace=False, **kw)
    core.imem.words.update(code)
    t0 = time.time()
    await core.boot()
    status = await core.run()
    num = core.word(LAST_TESTNUM)
    dut._log.info(f"{name} {mem} {' '.join(defines)}: status={status} testnum={num} cycles={core.edge} "
                  f"wall={time.time() - t0:.1f}s")
    return status, num, core.edge, len(core.mon.violations)


@xp_test()
async def test_isa_rv32ui(dut):
    # rv32ui x {fixed, jitter}: every run passes through its last test case with no violation
    check_pin()
    bad, cycles = [], []
    for name in TESTS:
        last = last_testnum(name)
        for mem in ("fixed", "jitter"):
            status, num, edges, viol = await run_test(dut, name, mem)
            cycles.append(edges)
            if (status, num, viol) != ("pass", last, 0):
                bad.append(f"{name} {mem}: status={status} testnum={num} (last {last}) violations={viol}")
    for line in bad:
        dut._log.error(line)
    dut._log.info(f"cycles min={min(cycles)} max={max(cycles)} total={sum(cycles)}")
    check("runs", len(cycles), 2 * len(TESTS))
    check("failing runs", len(bad), 0)


@xp_test()
async def test_isa_negative(dut):
    # broken expected values must make the program report fail at the predicted test case
    check_pin()
    status, num, _, _ = await run_test(dut, "add", "fixed", ("XP_BREAK_CASE=5",))
    check("add case 5 broken: status fail", int(status == "fail"), 1)
    check("add case 5 broken: reported case", num, 5)
    bad, unaffected = [], []
    for name in TESTS:
        first = first_broken(name)
        status, num, _, _ = await run_test(dut, name, "fixed", ("XP_BREAK_ALL",))
        want = ("pass", last_testnum(name)) if first is None else ("fail", first)
        if first is None:
            unaffected.append(name)
        if (status, num) != want:
            bad.append(f"{name}: status={status} testnum={num}, expected {want}")
    for line in bad:
        dut._log.error(line)
    dut._log.info(f"no TEST_CASE (break has no effect): {unaffected}")
    check("break-all mismatches", len(bad), 0)
    # gate: fence_i needs Zifencei; its fence.i must be rejected
    elf, _ = build("fence_i", march="rv32i_zifencei")
    try:
        check_ops(elf)
        rejected = 0
    except ValueError as e:
        rejected = int("fence.i" in str(e))
    check("gate rejects fence.i", rejected, 1)
