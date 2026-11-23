#------------------------------------------------------------------------------
# Module      : core_payload_cocotb
# Description : core_top invalid-payload rows (PQ-1..PQ-5, OD-1111). Natural
#               variant: the stale payload a bubble or flush leaves behind.
#               Random variant: a seeded payload deposited on the register
#               output nets of the invalid entry (seeds 11, 22, 33).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

import random

from cocotb.triggers import RisingEdge, Timer

from xp_core_harness import Core, finish
from xp_helpers import xp_test, check
from xp_rv32i import NOP, add, addi, beq, lui, lw, sw

D0 = 0x0001_0000
SEEDS = (11, 22, 33)
# lw x5 (2), add x6,x5,x2 (3) load-use, add x8,x5,x0 (4), add x9,x7,x0 (5); x7 = 0x777
LU = [lui(1, 0x10), addi(2, 0, 0x11), lw(5, 0, 1), add(6, 5, 2), add(8, 5, 0), add(9, 7, 0),
      sw(6, 4, 1), sw(8, 8, 1), sw(9, 12, 1), sw(5, 16, 1), sw(7, 20, 1)] + finish(1)
LU = [addi(7, 0, 0x777), NOP, NOP] + LU  # indices shift by 3: lw at 5, add x6 at 6, add x8 at 7
DATA = {D0: 0x100}


def pc(i):
    return 4 * i


def port(dut, net):
    # core net <reg>_reg_<field> -> output port <reg>_reg.<field>_o (pipeline-register section 3)
    for reg in ("if_id", "id_ex", "ex_mem", "mem_wb"):
        prefix = f"{reg}_reg_"
        if net.startswith(prefix):
            return getattr(getattr(dut, f"{reg}_reg"), net[len(prefix):] + "_o")
    raise KeyError(net)


async def scenario(dut, prog, anchor, deposit=None, **kw):
    # run to the anchor (0.5 ns before its edge), optionally deposit a payload, read the effect nets
    core = Core(dut, prog, data=DATA, **kw)
    await core.boot()
    await core.until(anchor, 200)
    pre = dict(core.trace[-1])
    readback = {}
    if deposit:
        # force the invalid entry's output nets until its edge (a plain deposit does not hold on a net)
        for name, value in deposit.items():
            port(dut, name).value = value
        await Timer(100, unit="ps")
        readback = {n: int(getattr(dut, n).value) for n in deposit}
    effects = {n: int(getattr(dut, n).value) for n in
               ("data_req", "mem_wait", "rf_write_fire", "redirect_fire", "if_id_stall", "id_ex_flush")}
    if deposit:
        await RisingEdge(dut.clk)
    status = await core.run()
    check("status pass", int(status == "pass"), 1)
    for name, value in (deposit or {}).items():
        check(f"deposit took on {name}", readback[name], value)
    return core, pre, effects


def check_results(core, tag):
    check(f"{tag} x6 = x5 + x2", core.word(D0 + 4), 0x111)
    check(f"{tag} x8 = x5", core.word(D0 + 8), 0x100)
    check(f"{tag} x9 = x7", core.word(D0 + 12), 0x777)
    check(f"{tag} x5 kept", core.word(D0 + 16), 0x100)
    check(f"{tag} x7 kept", core.word(D0 + 20), 0x777)
    check(f"{tag} monitors", len(core.mon.violations), 0)


def ex_mem_bubble(s):
    # add x6 in EX, the bubble (stale lw payload) in EX/MEM
    return s["id_ex_reg_valid"] and s["id_ex_reg_pc"] == pc(6) and not s["ex_mem_reg_valid"]


def mem_wb_bubble(s):
    # add x8 in EX, the bubble in MEM/WB
    return s["id_ex_reg_valid"] and s["id_ex_reg_pc"] == pc(7) and not s["mem_wb_reg_valid"]


@xp_test()
async def test_payload_forwarding(dut):
    # PQ-1a/b: an invalid EX/MEM or MEM/WB entry naming the consumer's source is never forwarded
    core, pre, _ = await scenario(dut, LU, ex_mem_bubble)
    check("1a natural: stale rd=5 in invalid EX/MEM", pre["ex_mem_reg_rd"], 5)
    check_results(core, "1a natural")
    for seed in SEEDS:
        rng = random.Random(seed)
        dep = dict(ex_mem_reg_rd=2, ex_mem_reg_reg_write=1, ex_mem_reg_ex_result=rng.getrandbits(32))
        core, _, _ = await scenario(dut, LU, ex_mem_bubble, dep)
        check_results(core, f"1a seed {seed}")
    for seed in SEEDS:
        rng = random.Random(seed)
        dep = dict(mem_wb_reg_rd=5, mem_wb_reg_reg_write=1, mem_wb_reg_wb_src=rng.getrandbits(1),
                   mem_wb_reg_ex_result=rng.getrandbits(32), mem_wb_reg_load_result=rng.getrandbits(32))
        core, _, _ = await scenario(dut, LU, mem_wb_bubble, dep)
        check_results(core, f"1b seed {seed}")


def lu_response(s):
    # the load's response edge: bubble in ID/EX (stale lw payload), add x6 held in IF/ID
    return s["data_rvalid"] and not s["id_ex_reg_valid"] and s["if_id_reg_pc"] == pc(6)


@xp_test()
async def test_payload_load_use(dut):
    # PQ-2a/b: an invalid ID/EX load, or an invalid IF/ID reader, raises no load-use stall
    core, pre, eff = await scenario(dut, LU, lu_response)
    check("2a natural: stale load payload in ID/EX", pre["id_ex_reg_mem_en"] and pre["id_ex_reg_rd"], 5)
    check("2a natural if_id_stall", eff["if_id_stall"], 0)
    check("2a natural id_ex_flush", eff["id_ex_flush"], 0)
    check_results(core, "2a natural")
    for seed in SEEDS:
        rng = random.Random(seed)
        dep = dict(id_ex_reg_mem_en=1, id_ex_reg_mem_write=0, id_ex_reg_rd=5, id_ex_reg_reg_write=1,
                   id_ex_reg_imm=rng.getrandbits(32))
        core, _, eff = await scenario(dut, LU, lu_response, dep)
        check(f"2a seed {seed} if_id_stall", eff["if_id_stall"], 0)
        check(f"2a seed {seed} id_ex_flush", eff["id_ex_flush"], 0)
        check_results(core, f"2a seed {seed}")
    # 2b: live lw x5,0(x5) in EX; IF/ID empty (slow fetch) with the stale lw word, which reads x5
    prog = [lui(5, 0x10), NOP, NOP, NOP, lw(5, 0, 5), NOP, NOP, lui(1, 0x10), sw(5, 16, 1)] + finish(1)

    def anchor(s):
        return s["id_ex_reg_valid"] and s["id_ex_reg_pc"] == pc(4) and not s["if_id_reg_valid"]

    core, pre, eff = await scenario(dut, prog, anchor, ilat=[1, 1, 1, 1, 1, 10, 1])
    check("2b natural: stale lw word in invalid IF/ID", pre["if_id_reg_instruction"], lw(5, 0, 5))
    check("2b natural if_id_stall", eff["if_id_stall"], 0)
    check("2b natural id_ex_flush", eff["id_ex_flush"], 0)
    check("2b result", core.word(D0 + 16), 0x100)
    for seed in SEEDS:
        rng = random.Random(seed)
        word = (rng.getrandbits(7) << 25) | (5 << 20) | (5 << 15) | (rng.getrandbits(3) << 12) | \
            (rng.getrandbits(5) << 7) | 0x33  # an OP word reading x5 twice
        core, _, eff = await scenario(dut, prog, anchor, dict(if_id_reg_instruction=word),
                                      ilat=[1, 1, 1, 1, 1, 10, 1])
        check(f"2b seed {seed} if_id_stall", eff["if_id_stall"], 0)
        check(f"2b seed {seed} id_ex_flush", eff["id_ex_flush"], 0)
        check(f"2b seed {seed} result", core.word(D0 + 16), 0x100)


@xp_test()
async def test_payload_rf_write(dut):
    # PQ-3: an invalid MEM/WB entry with reg_write=1 never writes the register file
    core, pre, eff = await scenario(dut, LU, mem_wb_bubble)
    check("natural: stale reg_write=1 in invalid MEM/WB", pre["mem_wb_reg_reg_write"], 1)
    check("natural rf_write_fire", eff["rf_write_fire"], 0)
    check_results(core, "natural")
    for seed in SEEDS:
        rng = random.Random(seed)
        dep = dict(mem_wb_reg_rd=7, mem_wb_reg_reg_write=1, mem_wb_reg_wb_src=rng.getrandbits(1),
                   mem_wb_reg_ex_result=rng.getrandbits(32), mem_wb_reg_load_result=rng.getrandbits(32))
        core, _, eff = await scenario(dut, LU, mem_wb_bubble, dep)
        check(f"seed {seed} rf_write_fire", eff["rf_write_fire"], 0)
        check_results(core, f"seed {seed}")


@xp_test()
async def test_payload_data_req(dut):
    # PQ-4: an invalid EX/MEM entry with mem_en=1 raises no data_req, no mem_wait, no access
    core, pre, eff = await scenario(dut, LU, ex_mem_bubble)
    check("natural: stale mem_en=1 in invalid EX/MEM", pre["ex_mem_reg_mem_en"], 1)
    check("natural data_req", eff["data_req"], 0)
    check("natural mem_wait", eff["mem_wait"], 0)
    n = len(core.dmem.log)
    check("natural access count (lw, 5 sw, status)", n, 7)
    check_results(core, "natural")
    for seed in SEEDS:
        rng = random.Random(seed)
        dep = dict(ex_mem_reg_mem_en=1, ex_mem_reg_mem_write=rng.getrandbits(1),
                   ex_mem_reg_ex_result=D0 + 4 * rng.getrandbits(8))
        core, _, eff = await scenario(dut, LU, ex_mem_bubble, dep)
        check(f"seed {seed} data_req", eff["data_req"], 0)
        check(f"seed {seed} mem_wait", eff["mem_wait"], 0)
        check(f"seed {seed} access count", len(core.dmem.log), 7)
        check_results(core, f"seed {seed}")


@xp_test()
async def test_payload_redirect(dut):
    # PQ-5: an invalid ID/EX entry holding a taken branch or jump never redirects
    # beq x0,x0 at index 3 to index 9; after its redirect, ID/EX is flushed and keeps the beq payload
    prog = [lui(1, 0x10), NOP, NOP, beq(0, 0, 24)] + [addi(9, 0, 9)] * 5 + \
        [NOP, NOP, NOP, addi(8, 0, 8), sw(8, 0, 1)] + finish(1)

    def after_redirect(s):
        return not s["id_ex_reg_valid"] and s["id_ex_reg_control_flow"] == 1 and s["id_ex_reg_pc"] == pc(3)

    core, pre, eff = await scenario(dut, prog, after_redirect)
    check("natural redirect_fire", eff["redirect_fire"], 0)
    check("natural one redirect", len(core.edges(redirect_fire=1)), 1)
    check("natural result", core.word(D0), 8)
    tgt = [t["addr"] for t in core.imem.log if t["addr"] >= pc(9)][:4]
    check("natural sequential after the target", int(tgt == [pc(9), pc(10), pc(11), pc(12)]), 1)
    for seed in SEEDS:
        rng = random.Random(seed)
        dep = dict(id_ex_reg_control_flow=rng.choice((1, 2, 3)), id_ex_reg_imm=rng.getrandbits(12) << 1)
        core, _, eff = await scenario(dut, prog, after_redirect, dep)
        check(f"seed {seed} redirect_fire", eff["redirect_fire"], 0)
        check(f"seed {seed} one redirect", len(core.edges(redirect_fire=1)), 1)
        check(f"seed {seed} result", core.word(D0), 8)
        check(f"seed {seed} monitors", len(core.mon.violations), 0)
