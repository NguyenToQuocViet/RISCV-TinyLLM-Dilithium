#------------------------------------------------------------------------------
# Module      : pipeline_register_cocotb
# Description : Directed tests of the four pipeline registers (D-PR-01..09),
#               one run per top module.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from xp_helpers import xp_test, drive, settle, expect, start_clock, next_edge, reset_dut

# field -> width, per module (core-top section 4 net table)
FIELDS = {
    "if_id_pipeline": {"pc": 32, "instruction": 32},
    "id_ex_pipeline": {"pc": 32, "rs1_id": 5, "rs2_id": 5, "rs1_value": 32, "rs2_value": 32, "imm": 32,
                       "rd": 5, "reg_write": 1, "mem_en": 1, "mem_write": 1, "mem_type": 3, "wb_src": 1,
                       "alu_op": 4, "alu_src_a": 2, "alu_src_b": 1, "branch_kind": 3,
                       "control_flow": 2, "result_src": 1},
    "ex_mem_pipeline": {"ex_result": 32, "store_data": 32, "rd": 5, "reg_write": 1, "wb_src": 1,
                        "mem_en": 1, "mem_write": 1, "mem_type": 3},
    "mem_wb_pipeline": {"ex_result": 32, "load_result": 32, "wb_src": 1, "rd": 5, "reg_write": 1},
}

# pattern literals per width: A = 1010..10 (MSB 1), B = 0101..01, C = all ones, D = zeros
PATTERN = {
    "A": {32: 0xAAAA_AAAA, 5: 0b10101, 4: 0b1010, 3: 0b101, 2: 0b10, 1: 0b1},
    "B": {32: 0x5555_5555, 5: 0b01010, 4: 0b0101, 3: 0b010, 2: 0b01, 1: 0b0},
    "C": {32: 0xFFFF_FFFF, 5: 0b11111, 4: 0b1111, 3: 0b111, 2: 0b11, 1: 0b1},
    "D": {32: 0x0000_0000, 5: 0b00000, 4: 0b0000, 3: 0b000, 2: 0b00, 1: 0b0},
}


def fields(dut):
    return FIELDS[dut._name]


def inputs(dut, pat):
    return {f"{f}_i": PATTERN[pat][w] for f, w in fields(dut).items()}


def outputs(dut, pat):
    return {f"{f}_o": PATTERN[pat][w] for f, w in fields(dut).items()}


def drive_edge(dut, valid_i, stall, flush, pat):
    drive(dut, valid_i=valid_i, stall=stall, flush=flush, **inputs(dut, pat))


def check_state(dut, valid_o, pat):
    expect(dut, valid_o=valid_o, **outputs(dut, pat))


async def start(dut):
    start_clock(dut)
    await reset_dut(dut, edges=2, valid_i=0, stall=0, flush=0)


async def load(dut, pat):
    drive_edge(dut, 1, 0, 0, pat)
    await next_edge(dut)
    check_state(dut, 1, pat)


@xp_test()
async def test_trace_condition_rows(dut):
    # D-PR-01: section 7 trace E1..E8, every Condition row then reset
    await start(dut)
    steps = [((1, 0, 0, "A"), (1, "A")), ((1, 1, 0, "B"), (1, "A")), ((0, 0, 0, "B"), (0, "A")),
             ((1, 0, 0, "B"), (1, "B")), ((1, 1, 1, "C"), (0, "B")), ((1, 0, 0, "C"), (1, "C"))]
    for (v, s, f, pat), (ev, epat) in steps:
        drive_edge(dut, v, s, f, pat)
        await next_edge(dut)
        check_state(dut, ev, epat)
    drive(dut, rst_n=0)
    await settle()
    check_state(dut, 0, "C")
    drive_edge(dut, 1, 0, 0, "D")
    await next_edge(dut)
    check_state(dut, 0, "D")


@xp_test()
async def test_flush_beats_stall(dut):
    # D-PR-02: flush wins over stall, payload kept
    await start(dut)
    await load(dut, "A")
    drive_edge(dut, 1, 1, 1, "B")
    await next_edge(dut)
    check_state(dut, 0, "A")
    await load(dut, "A")
    drive_edge(dut, 0, 1, 1, "B")
    await next_edge(dut)
    check_state(dut, 0, "A")


@xp_test()
async def test_reset_overrides_flush_and_stall(dut):
    # D-PR-03: reset beats flush and stall; payload loads only with stall 0, flush 0, valid_i 1
    await start(dut)
    await load(dut, "A")
    drive(dut, rst_n=0)
    for (f, s, pat) in ((0, 0, "B"), (0, 1, "C"), (1, 0, "A"), (1, 1, "C")):
        drive_edge(dut, 1, s, f, pat)
        await next_edge(dut)
        check_state(dut, 0, "B")
    drive_edge(dut, 0, 0, 0, "C")
    await next_edge(dut)
    check_state(dut, 0, "B")


@xp_test()
async def test_invalid_entry_clears_valid(dut):
    # D-PR-04: a bubble clears valid and keeps the payload
    await start(dut)
    await load(dut, "A")
    drive_edge(dut, 0, 0, 0, "B")
    await next_edge(dut)
    check_state(dut, 0, "A")


@xp_test()
async def test_stall_retains(dut):
    # D-PR-05: stall keeps valid and payload, also when the source presents none
    await start(dut)
    await load(dut, "A")
    drive_edge(dut, 1, 1, 0, "B")
    for _ in range(3):
        await next_edge(dut)
        check_state(dut, 1, "A")
    drive_edge(dut, 0, 1, 0, "B")
    await next_edge(dut)
    check_state(dut, 1, "A")


@xp_test()
async def test_flush_retains_payload(dut):
    # D-PR-06: flush clears valid and keeps the payload
    await start(dut)
    await load(dut, "A")
    drive_edge(dut, 1, 0, 1, "B")
    await next_edge(dut)
    check_state(dut, 0, "A")


@xp_test()
async def test_load(dut):
    # D-PR-07: normal load from empty and from full
    await start(dut)
    expect(dut, valid_o=0)
    await load(dut, "A")
    await load(dut, "B")


@xp_test()
async def test_each_field_stored_alone(dut):
    # D-PR-08: each field reaches its own output and no other
    await start(dut)
    widths = fields(dut)
    for k in widths:
        for ones_k in (True, False):
            val = {f: (PATTERN["C"][w] if (f == k) == ones_k else 0) for f, w in widths.items()}
            drive(dut, valid_i=1, stall=0, flush=0, **{f"{f}_i": v for f, v in val.items()})
            await next_edge(dut)
            expect(dut, valid_o=1, **{f"{f}_o": v for f, v in val.items()})


@xp_test()
async def test_outputs_change_only_at_rising_edge(dut):
    # D-PR-09: no output follows an input within the cycle, except the async clear
    await start(dut)
    await load(dut, "A")
    drive_edge(dut, 1, 0, 0, "B")
    await settle()
    check_state(dut, 1, "A")
    await next_edge(dut)
    check_state(dut, 1, "B")
    drive(dut, flush=1)
    await settle()
    check_state(dut, 1, "B")
    await next_edge(dut)
    check_state(dut, 0, "B")
