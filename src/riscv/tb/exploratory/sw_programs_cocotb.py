#------------------------------------------------------------------------------
# Module      : sw_programs_cocotb
# Description : SW tests on core_top: three C programs built for rv32i, run
#               with monitors, watchdogs and the completion ABI. Each program
#               runs -O0/-O2 x memory fixed/jitter. The verdict is the
#               signature at 0x1_FF00 against literals, not the status alone.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#------------------------------------------------------------------------------

import random
import time

from xp_core_harness import Core
from xp_helpers import xp_test, check
from xp_sw import SIG_BASE, build, check_ops, load_image, kat_words

SEED = 20261120
VARIANTS = (("O0", "fixed"), ("O0", "jitter"), ("O2", "fixed"), ("O2", "jitter"))
OPS_SEEN = set()


def lazy(seed, low, high):
    # seeded per-transaction value; same index, same value
    rng, vals = random.Random(seed), []

    def f(i):
        while len(vals) <= i:
            vals.append(rng.randint(low, high))
        return vals[i]
    return f


async def run_program(dut, prog, opt, mem, limit, defines=()):
    elf, hexf = build(prog, opt, defines)
    OPS_SEEN.update(check_ops(elf))
    code, data = load_image(hexf)
    kw = {}
    if mem == "jitter":  # grant delay 0..3, response latency 1..4, both ports
        kw = dict(igrant=lazy(SEED, 0, 3), ilat=lazy(SEED + 1, 1, 4),
                  dgrant=lazy(SEED + 2, 0, 3), dlat=lazy(SEED + 3, 1, 4))
    core = Core(dut, [], data=data, total_limit=limit, keep_trace=False, **kw)
    core.imem.words.update(code)
    t0 = time.time()
    await core.boot()
    status = await core.run()
    dut._log.info(f"{prog} {opt} {mem} {' '.join(defines)}: status={status} cycles={core.edge} "
                  f"wall={time.time() - t0:.1f}s seed={SEED if mem == 'jitter' else '-'}")
    return core, status


def sig(core, n):
    return [core.word(SIG_BASE + 4 * i) for i in range(n)]


@xp_test()
async def test_sw_basic(dut):
    # P1: flow and layout, straight line: code constant, .data word, .rodata word, .bss cleared
    for opt, mem in VARIANTS:
        core, status = await run_program(dut, "p1_basic", opt, mem, 5000)
        tag = f"{opt} {mem}"
        check(f"{tag} status pass", int(status == "pass"), 1)
        s = sig(core, 4)
        check(f"{tag} SIG0 code constant", s[0], 0x1234_5678)
        check(f"{tag} SIG1 .data word", s[1], 0xCAFE_0001)
        check(f"{tag} SIG2 .rodata word", s[2], 0xDEAD_BEEF)
        check(f"{tag} SIG3 .bss word cleared", s[3], 0)
        check(f"{tag} monitors", len(core.mon.violations), 0)


@xp_test()
async def test_sw_fib(dut):
    # P2: iterative fib(0..47) table and recursive fib(15)
    for opt, mem in VARIANTS:
        core, status = await run_program(dut, "p2_fib", opt, mem, 300_000)
        tag = f"{opt} {mem}"
        check(f"{tag} status pass", int(status == "pass"), 1)
        t = sig(core, 49)
        check(f"{tag} fib(0)", t[0], 0)
        check(f"{tag} fib(1)", t[1], 1)
        for i in range(2, 48):
            check(f"{tag} fib({i}) = fib({i - 1}) + fib({i - 2})", t[i], (t[i - 1] + t[i - 2]) & 0xFFFF_FFFF)
        check(f"{tag} fib(10)", t[10], 55)
        check(f"{tag} fib(20)", t[20], 6765)
        check(f"{tag} fib(30)", t[30], 832040)
        check(f"{tag} fib(47)", t[47], 0xB119_24E1)
        check(f"{tag} fib_rec(15)", t[48], 610)
        check(f"{tag} monitors", len(core.mon.violations), 0)


# FIPS 202 SHA3-256 known answers
KAT = (("empty", "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a"),
       ("abc", "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532"),
       ("200 x 0xA3", "79f38adec5c20307a98ef76e8324afbfd46cfd81b22e3973c65fa1bd9de31787"))


@xp_test()
async def test_sw_sha3(dut):
    # P3: SHA3-256 of "", "abc", 200 x 0xA3 (two blocks) against the FIPS 202 known answers;
    # -O0 drops "" (1.4M cycles with all three at fixed latency, about 5 min)
    for opt, mem in VARIANTS:
        skip = ("SKIP_EMPTY",) if opt == "O0" else ()
        core, status = await run_program(dut, "p3_sha3", opt, mem, 4_000_000, skip)
        tag = f"{opt} {mem}"
        check(f"{tag} status pass", int(status == "pass"), 1)
        got = sig(core, 24)
        for k, (name, digest) in enumerate(KAT):
            if skip and k == 0:
                continue
            for i, w in enumerate(kat_words(digest)):
                check(f"{tag} {name} digest word {i}", got[8 * k + i], w)
        check(f"{tag} monitors", len(core.mon.violations), 0)
    dut._log.info(f"operations generated across all SW images so far: {sorted(OPS_SEEN)}")


@xp_test()
async def test_sw_negative(dut):
    # negative controls: status 2 is reported; a wrong digest fails even when the program says PASS;
    # the gate rejects operations outside BASE
    core, status = await run_program(dut, "p1_basic", "O2", "fixed", 5000, ("FORCE_FAIL",))
    check("FORCE_FAIL reported as fail", int(status == "fail"), 1)
    core, status = await run_program(dut, "p3_sha3", "O2", "fixed", 3_000_000, ("BREAK_RC", "NO_SELFCHECK"))
    check("BREAK_RC program still says pass", int(status == "pass"), 1)
    got = sig(core, 24)
    wrong = sum(got[8 * k + i] != w for k, (_, d) in enumerate(KAT) for i, w in enumerate(kat_words(d)))
    check("BREAK_RC digest words differ from the known answers", int(wrong > 0), 1)
    elf, _ = build("bad_ops", "O2", march="rv32im")
    try:
        check_ops(elf)
        msg = ""
    except ValueError as e:
        msg = str(e)
    check("gate rejects mul and ecall", int("mul" in msg and "ecall" in msg), 1)
