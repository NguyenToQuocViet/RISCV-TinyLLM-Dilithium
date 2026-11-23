#------------------------------------------------------------------------------
# Module      : core_data_obi_cocotb
# Description : core_top data-OBI rows (G5-01..G5-07) and MMIO response-based
#               completion (G7-03), with scripted grant delay and latency.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from cocotb.triggers import FallingEdge

from xp_core_harness import Core, finish
from xp_helpers import xp_test, check
from xp_rv32i import NOP, addi, lb, lbu, lh, lhu, lui, lw, sb, sh, sw

D0 = 0x0001_0000
PRO = [lui(1, 0x10), addi(2, 0, 0x11)]


def check_clean(core, declared=(), tag=""):
    got = [(r, d) for _, r, d in core.mon.violations]
    check(f"{tag}monitor violations", len(got), len(declared))
    for k, (r, d) in enumerate(declared):
        check(f"declared violation {k}", int(k < len(got) and got[k] == (r, d)), 1)


async def run_pass(core):
    await core.boot()
    check("status pass", int(await core.run() == "pass"), 1)


def first_presented(core, tx, prev_end):
    # first edge after prev_end where data_req shows this transaction's address
    for e in range(prev_end + 1, tx["edge"] + 1):
        s = core.at(e)
        if s["data_req"] and s["data_addr"] == tx["addr"]:
            return e
    return tx["edge"]


# sw x2 -> D0, lw x5 <- D0, sw x5 -> D0+4, lw x6 <- D0+4, then the signature
FOUR = PRO + [sw(2, 0, 1), lw(5, 0, 1), sw(5, 4, 1), lw(6, 4, 1), sw(6, 8, 1)] + finish(1)


@xp_test()
async def test_data_delayed_grant(dut):
    # G5-01: gnt delays 0, 1, 3, 120: payload stable to gnt, mem_wait=1 from the request, result right
    core = Core(dut, FOUR, dgrant=[0, 1, 3, 120, 0])
    await run_pass(core)
    prev = 0
    for k, delay in enumerate((0, 1, 3, 120)):
        tx = core.dmem.log[k]
        start = first_presented(core, tx, prev)
        check(f"tx{k} waiting edges", tx["edge"] - start, delay)
        for e in range(start, tx["edge"] + 1):
            s = core.at(e)
            check(f"tx{k} edge {e} mem_wait", s["mem_wait"], 1)
            for f, v in (("addr", tx["addr"]), ("we", tx["we"]), ("be", tx["be"]), ("wdata", tx["wdata"])):
                check(f"tx{k} edge {e} {f}", s[f"data_{f}"], v)
        prev = tx["edge"]
    check("result", core.word(D0 + 8), 0x11)
    check_clean(core)


@xp_test()
async def test_data_delayed_response(dut):
    # G5-02: latencies 1, 2, 5, 40: mem_wait=1 until the response edge, 0 on it; loads take the response
    core = Core(dut, FOUR, data={D0: 0}, dlat=[1, 2, 5, 40, 1])
    await run_pass(core)
    for k, (ea, er) in enumerate(core.data_edges()[:4]):
        check(f"tx{k} latency", er - ea, (1, 2, 5, 40)[k])
        for e in range(ea, er):
            check(f"tx{k} edge {e} mem_wait", core.at(e)["mem_wait"], 1)
        check(f"tx{k} response edge mem_wait", core.at(er)["mem_wait"], 0)
    check("loaded chain result", core.word(D0 + 8), 0x11)
    check_clean(core)


@xp_test()
async def test_data_no_duplicate_request(dut):
    # G5-03: 6 loads and stores at gnt delay 0..3: exactly 6 accepted in program order, req drops after each
    prog = PRO + [sw(2, 0, 1), lw(5, 0, 1), sb(5, 5, 1), lbu(6, 5, 1), sh(6, 10, 1), lhu(7, 10, 1)] + \
        [NOP] * 2 + finish(1)
    core = Core(dut, prog, dgrant=[0, 1, 2, 3, 0, 1, 0], dlat=2)
    await run_pass(core)
    log = core.dmem.log
    check("accepted requests (6 + status)", len(log), 7)
    expect = [(D0, 1), (D0, 0), (D0 + 4, 1), (D0 + 4, 0), (D0 + 8, 1), (D0 + 8, 0)]
    for k, (addr, we) in enumerate(expect):
        check(f"tx{k} addr", log[k]["addr"], addr)
        check(f"tx{k} we", log[k]["we"], we)
    for k, (ea, er) in enumerate(core.data_edges()[:6]):
        for e in range(ea + 1, er + 1):
            check(f"tx{k} edge {e} data_req low after acceptance", core.at(e)["data_req"], 0)
    check("x7 final", core.word(D0 + 8) & 0xFFFF0000, 0x0011_0000)
    check_clean(core)


@xp_test()
async def test_data_one_outstanding(dut):
    # G5-04: sw; sw; lw; lw with gnt always ready: request k+1 not presented before response k
    prog = PRO + [sw(2, 0, 1), sw(2, 4, 1), lw(5, 0, 1), lw(6, 4, 1)] + [NOP] * 2 + finish(1)
    core = Core(dut, prog, dlat=3)
    await run_pass(core)
    pairs = core.data_edges()
    for k in range(3):
        nxt = core.dmem.log[k + 1]
        start = first_presented(core, nxt, pairs[k][0])
        check(f"request {k + 1} not presented before response {k}", int(start >= pairs[k][1]), 1)
    check("address list", [t["addr"] for t in core.dmem.log[:4]] == [D0, D0 + 4, D0, D0 + 4], 1)
    check_clean(core)


@xp_test()
async def test_data_port_formatting(dut):
    # G5-05a/b/c: word-aligned addr, be per size and offset, store data on the selected lanes, load results
    W = 0x8344_C2E1  # bytes 0..3: E1 C2 44 83
    loads = [(lb, k) for k in range(4)] + [(lbu, k) for k in range(4)] + [(lh, 0), (lh, 2), (lhu, 0),
                                                                           (lhu, 2), (lw, 0)]
    prog = [lui(1, 0x10)]
    for k, (op, off) in enumerate(loads):
        prog += [op(5, off, 1), sw(5, 0x100 + 4 * k, 1)]
    prog += [addi(6, 0, 0x11), sb(6, 0x40, 1), addi(6, 0, 0x22), sb(6, 0x41, 1), addi(6, 0, 0x33),
             sb(6, 0x42, 1), addi(6, 0, 0x44), sb(6, 0x43, 1)]
    prog += [lui(7, 0xCAFEC), addi(7, 7, -0x111), sh(7, 0x44, 1), sh(7, 0x46, 1)]  # x7 = 0xCAFEBEEF
    prog += [lui(8, 0x12345), addi(8, 8, 0x678), sw(8, 0x48, 1)]
    core = Core(dut, prog + finish(1), data={D0: W})
    await run_pass(core)
    expect = [0xFFFF_FFE1, 0xFFFF_FFC2, 0x0000_0044, 0xFFFF_FF83, 0xE1, 0xC2, 0x44, 0x83,
              0xFFFF_C2E1, 0xFFFF_8344, 0x0000_C2E1, 0x0000_8344, 0x8344_C2E1]
    be = [0b0001, 0b0010, 0b0100, 0b1000] * 2 + [0b0011, 0b1100, 0b0011, 0b1100, 0b1111]
    loads_log = [t for t in core.dmem.log if not t["we"]]
    for k in range(13):
        check(f"load {k} addr aligned", loads_log[k]["addr"], D0)
        check(f"load {k} be", loads_log[k]["be"], be[k])
        check(f"load {k} result", core.word(D0 + 0x100 + 4 * k), expect[k])
    stores = [t for t in core.dmem.log if t["we"] and 0x40 <= t["addr"] - D0 < 0x4C]
    sbe = [0b0001, 0b0010, 0b0100, 0b1000, 0b0011, 0b1100, 0b1111]
    sval = [0x1111_1111, 0x2222_2222, 0x3333_3333, 0x4444_4444, 0xBEEF_BEEF, 0xBEEF_BEEF, 0x1234_5678]
    saddr = [D0 + 0x40] * 4 + [D0 + 0x44] * 2 + [D0 + 0x48]
    for k in range(7):
        mask = sum(0xFF << (8 * b) for b in range(4) if (sbe[k] >> b) & 1)
        check(f"store {k} addr aligned", stores[k]["addr"], saddr[k])
        check(f"store {k} be", stores[k]["be"], sbe[k])
        check(f"store {k} we", stores[k]["we"], 1)
        check(f"store {k} lanes", stores[k]["wdata"] & mask, sval[k] & mask)
    check("sb word", core.word(D0 + 0x40), 0x4433_2211)
    check("sh word", core.word(D0 + 0x44), 0xBEEF_BEEF)
    check("sw word", core.word(D0 + 0x48), 0x1234_5678)
    check_clean(core)


@xp_test()
async def test_store_accepted_with_older_wb_held(dut):
    # G5-06: A (addi x6) sits in MEM/WB while S waits; S accepted with rf_write_fire=0; A retires once
    prog = PRO + [addi(6, 0, 5), sw(2, 0, 1), NOP, NOP, sw(6, 4, 1)] + finish(1)
    core = Core(dut, prog, dlat=[6, 1])
    await run_pass(core)
    ea, er = core.data_edges()[0]
    s = core.at(ea)
    check("precondition: A in MEM/WB at S's request", s["mem_wb_reg_valid"] and s["mem_wb_reg_rd"], 6)
    check("rf_write_fire at S's acceptance", s["rf_write_fire"], 0)
    check("A retires on S's response edge", core.at(er)["rf_write_fire"] and core.at(er)["mem_wb_reg_rd"], 6)
    check("A retires once", core.retire().count(6), 1)
    check("x6 = 5", core.word(D0 + 4), 5)
    check("S landed", core.word(D0), 0x11)
    check_clean(core)


@xp_test()
async def test_unexpected_data_response(dut):
    # G5-07a/b/c: unexpected data rvalid (0xBAD0_0001) is drained, never taken as a load result
    prog = PRO + [NOP] * 6 + [lw(5, 0, 1)] + [NOP] * 4 + [sw(5, 4, 1)] + finish(1)
    data = {D0: 0x0000_5A5A}
    # a: idle port
    core = Core(dut, prog, data=data)
    await core.boot()
    await core.cycles(4)
    core.dmem.inject = 1
    check("a: status pass", int(await core.run() == "pass"), 1)
    check("a: result", core.word(D0 + 4), 0x5A5A)
    check_clean(core, [("M3", "data")], "a: ")
    # b: while the lw waits for gnt
    core = Core(dut, prog, data=data, dgrant=[6, 0])
    await core.boot()
    for _ in range(60):
        await FallingEdge(dut.clk)
        if int(dut.data_req.value) and not int(dut.data_gnt.value):
            break
    core.dmem.inject = 1
    check("b: status pass", int(await core.run() == "pass"), 1)
    ea, er = core.data_edges()[0]
    for e in range(ea, er):
        check(f"b: edge {e} mem_wait not released early", core.at(e)["mem_wait"], 1)
    check("b: result", core.word(D0 + 4), 0x5A5A)
    check_clean(core, [("M3", "data")], "b: ")
    # c: right after the expected response
    core = Core(dut, prog, data=data)
    await core.boot()
    core.dmem.inject_after_response = 1  # after boot: the boot reset flushes model hooks
    check("c: status pass", int(await core.run() == "pass"), 1)
    check("c: result", core.word(D0 + 4), 0x5A5A)
    check_clean(core, [("M3", "data")], "c: ")


@xp_test()
async def test_mmio_response_completion(dut):
    # G7-03: peripheral latencies 1, 7, 20: access n+1 is requested only after the response of access n
    io = 0x0001_8000
    prog = [lui(1, 0x18), addi(2, 0, 0x21), sw(2, 0, 1), sw(2, 4, 1), lw(5, 0, 1), lui(3, 0x10),
            sw(5, 0, 3)] + finish(1)
    core = Core(dut, prog, dlat=[1, 7, 20, 1])
    await run_pass(core)
    pairs = core.data_edges()
    for k in range(3):
        check(f"access {k} addr", core.dmem.log[k]["addr"], io + (0, 4, 0)[k])
    for k in range(3):
        nxt = core.dmem.log[k + 1]
        start = first_presented(core, nxt, pairs[k][0])
        check(f"access {k + 1} after response {k}", int(start >= pairs[k][1]), 1)
    check("read back", core.word(0x0001_0000), 0x21)
    check_clean(core)
