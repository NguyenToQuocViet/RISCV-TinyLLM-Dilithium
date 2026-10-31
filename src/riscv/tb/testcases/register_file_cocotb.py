#------------------------------------------------------------------------------
# Module      : register_file_cocotb
# Description : Directed storage, bypass and x0 checks for the register file leaf.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-31
#------------------------------------------------------------------------------

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

# P(k) = byte k repeated four times, one distinct pattern per x1..x31.
# Manual literals (plan register_file, section 8 "Write and storage").
PATTERN = {
     1: 0x0101_0101,  2: 0x0202_0202,  3: 0x0303_0303,  4: 0x0404_0404,
     5: 0x0505_0505,  6: 0x0606_0606,  7: 0x0707_0707,  8: 0x0808_0808,
     9: 0x0909_0909, 10: 0x0A0A_0A0A, 11: 0x0B0B_0B0B, 12: 0x0C0C_0C0C,
    13: 0x0D0D_0D0D, 14: 0x0E0E_0E0E, 15: 0x0F0F_0F0F, 16: 0x1010_1010,
    17: 0x1111_1111, 18: 0x1212_1212, 19: 0x1313_1313, 20: 0x1414_1414,
    21: 0x1515_1515, 22: 0x1616_1616, 23: 0x1717_1717, 24: 0x1818_1818,
    25: 0x1919_1919, 26: 0x1A1A_1A1A, 27: 0x1B1B_1B1B, 28: 0x1C1C_1C1C,
    29: 0x1D1D_1D1D, 30: 0x1E1E_1E1E, 31: 0x1F1F_1F1F,
}

# Read index pairs that cover x1..x31 on both ports.
READ_PAIRS = (
    (1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16),
    (17, 18), (19, 20), (21, 22), (23, 24), (25, 26), (27, 28), (29, 30),
    (31, 31),
)


async def write_cycle(dut, rd, data):
    # Caller is at a falling edge. Drive one write, hold it over the rising
    # edge, then drop rf_write_fire at the next falling edge (section 2, section 5 write rule).
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = rd
    dut.wb_data.value       = data
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rf_write_fire.value = 0


async def check_reads(dut, rs1_expected, rs2_expected):
    # Read ports are combinational (section 2): sample 1 ns after the drive,
    # before the next rising edge. The caller drives all inputs.
    await Timer(1, unit="ns")
    assert int(dut.rs1_value.value) == rs1_expected, (
        f"rs1_value: rs1_id={int(dut.rs1_id.value)}, "
        f"expected 0x{rs1_expected:08X}, got 0x{int(dut.rs1_value.value):08X}"
    )
    assert int(dut.rs2_value.value) == rs2_expected, (
        f"rs2_value: rs2_id={int(dut.rs2_id.value)}, "
        f"expected 0x{rs2_expected:08X}, got 0x{int(dut.rs2_value.value):08X}"
    )


async def start_clock(dut):
    # Period 10 ns, falling edge at 5 ns, rising edge at 10 ns (plan timing rules).
    # All inputs start at 0 and change only at falling edges afterwards.
    dut.rs1_id.value        = 0
    dut.rs2_id.value        = 0
    dut.rf_write_fire.value = 0
    dut.wb_rd.value         = 0
    dut.wb_data.value       = 0
    Clock(dut.clk, 10, unit="ns").start(start_high=True)
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_write_read_all(dut):
    # Section 8 "Write and storage": write a distinct pattern to x1..x31, read all back.
    await start_clock(dut)
    for k in range(1, 32):
        await write_cycle(dut, k, PATTERN[k])

    for rs1, rs2 in READ_PAIRS:
        await FallingEdge(dut.clk)
        dut.rs1_id.value = rs1
        dut.rs2_id.value = rs2
        # rf_write_fire=0: no bypass possible, so the value comes from storage
        await check_reads(dut, PATTERN[rs1], PATTERN[rs2])


@cocotb.test()
async def test_data_width(dut):
    # Section 8 "Data width": all 32 bits are stored and returned.
    await start_clock(dut)
    await write_cycle(dut, 1, 0xFFFF_FFFF)
    await write_cycle(dut, 2, 0xA5A5_A5A5)
    await write_cycle(dut, 3, 0x5A5A_5A5A)

    await FallingEdge(dut.clk)
    dut.rs1_id.value = 1
    dut.rs2_id.value = 2
    await check_reads(dut, 0xFFFF_FFFF, 0xA5A5_A5A5)

    await FallingEdge(dut.clk)
    dut.rs1_id.value = 3
    dut.rs2_id.value = 3
    await check_reads(dut, 0x5A5A_5A5A, 0x5A5A_5A5A)


@cocotb.test()
async def test_write_isolation(dut):
    # Section 8 "Write isolation": a write to x16 changes only x16.
    await start_clock(dut)
    for k in range(1, 32):
        await write_cycle(dut, k, PATTERN[k])
    await write_cycle(dut, 16, 0xC3C3_C3C3)

    expected = dict(PATTERN)
    expected[16] = 0xC3C3_C3C3   # the only register that changes
    for rs1, rs2 in READ_PAIRS:
        await FallingEdge(dut.clk)
        dut.rs1_id.value = rs1
        dut.rs2_id.value = rs2
        await check_reads(dut, expected[rs1], expected[rs2])


@cocotb.test()
async def test_bypass_each_port(dut):
    # Section 8 "Bypass, each port"; section 5 concurrent rows 1, 3 and 8; trace E1.
    await start_clock(dut)
    await write_cycle(dut, 7, 0x1111_1111)
    await write_cycle(dut, 8, 0x2222_2222)

    # (a) bypass on port 1: rs1_id == wb_rd, rs2_id reads x8 from storage (row 1, row 8)
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 7
    dut.wb_data.value       = 0xDDDD_DDDD
    dut.rs1_id.value        = 7
    dut.rs2_id.value        = 8
    await check_reads(dut, 0xDDDD_DDDD, 0x2222_2222)
    await RisingEdge(dut.clk)     # x7 commits 0xDDDD_DDDD

    # (b) bypass on port 2 (row 3). Storage now holds 0xDDDD_DDDD, so 0xEEEE_EEEE
    # on rs2_value can only come from the bypass.
    await FallingEdge(dut.clk)
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 7
    dut.wb_data.value       = 0xEEEE_EEEE
    dut.rs1_id.value        = 8
    dut.rs2_id.value        = 7
    await check_reads(dut, 0x2222_2222, 0xEEEE_EEEE)


@cocotb.test()
async def test_bypass_both_ports(dut):
    # Section 8 "Bypass, both ports"; section 5 concurrent row 2.
    await start_clock(dut)
    await write_cycle(dut, 7, 0x1111_1111)

    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 7
    dut.wb_data.value       = 0xDDDD_DDDD
    dut.rs1_id.value        = 7
    dut.rs2_id.value        = 7
    await check_reads(dut, 0xDDDD_DDDD, 0xDDDD_DDDD)


@cocotb.test()
async def test_read_during_write(dut):
    # Section 8 "Read-during-write independence"; trace E1 then E2.
    await start_clock(dut)
    await write_cycle(dut, 7, 0x1111_1111)
    await write_cycle(dut, 8, 0x2222_2222)

    # Before the edge: x7 is bypassed from wb_data (section 2 read-during-write)
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 7
    dut.wb_data.value       = 0xDDDD_DDDD
    dut.rs1_id.value        = 7
    dut.rs2_id.value        = 8
    await check_reads(dut, 0xDDDD_DDDD, 0x2222_2222)

    # After the edge: rf_write_fire=0, so the same value must come from storage
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rf_write_fire.value = 0
    dut.rs1_id.value        = 7
    dut.rs2_id.value        = 8
    await check_reads(dut, 0xDDDD_DDDD, 0x2222_2222)


@cocotb.test()
async def test_no_bypass_without_fire(dut):
    # Section 8 "No bypass without fire"; section 5 concurrent row 4; trace E2.
    await start_clock(dut)
    await write_cycle(dut, 7, 0xDDDD_DDDD)

    dut.rf_write_fire.value = 0
    dut.wb_rd.value         = 7
    dut.wb_data.value       = 0xEEEE_EEEE
    dut.rs1_id.value        = 7
    dut.rs2_id.value        = 7
    await check_reads(dut, 0xDDDD_DDDD, 0xDDDD_DDDD)


@cocotb.test()
async def test_x0_read(dut):
    # Section 8 "x0 read"; section 5 read priority rule 1, concurrent rows 6 and 7; R2.
    await start_clock(dut)

    # fire=0, wb_rd=0
    dut.rf_write_fire.value = 0
    dut.wb_rd.value         = 0
    dut.wb_data.value       = 0xEEEE_EEEE
    dut.rs1_id.value        = 0
    dut.rs2_id.value        = 0
    await check_reads(dut, 0x0000_0000, 0x0000_0000)

    # fire=1, wb_rd=0 (row 6)
    await FallingEdge(dut.clk)
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 0
    dut.wb_data.value       = 0xEEEE_EEEE
    await check_reads(dut, 0x0000_0000, 0x0000_0000)

    # fire=1, wb_rd nonzero (row 7)
    await FallingEdge(dut.clk)
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 7
    dut.wb_data.value       = 0xDDDD_DDDD
    await check_reads(dut, 0x0000_0000, 0x0000_0000)


@cocotb.test()
async def test_x0_write_ignored(dut):
    # Section 8 "x0 write ignored"; section 5 concurrent row 5; trace E3; R2.
    await start_clock(dut)
    for k in range(1, 32):
        await write_cycle(dut, k, PATTERN[k])

    # wb_rd=0 with fire=1: no target. rs1 reads x0, rs2 reads x8 from storage.
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 0
    dut.wb_data.value       = 0xEEEE_EEEE
    dut.rs1_id.value        = 0
    dut.rs2_id.value        = 8
    await check_reads(dut, 0x0000_0000, 0x0808_0808)
    await RisingEdge(dut.clk)

    # After the edge no register changed
    await FallingEdge(dut.clk)
    dut.rf_write_fire.value = 0
    for rs1, rs2 in READ_PAIRS:
        await FallingEdge(dut.clk)
        dut.rs1_id.value = rs1
        dut.rs2_id.value = rs2
        await check_reads(dut, PATTERN[rs1], PATTERN[rs2])

    # x0 still reads zero on both ports
    await FallingEdge(dut.clk)
    dut.rs1_id.value = 0
    dut.rs2_id.value = 0
    await check_reads(dut, 0x0000_0000, 0x0000_0000)


@cocotb.test()
async def test_consecutive_writes(dut):
    # Section 8 "Consecutive writes"; section 5 last paragraph.
    await start_clock(dut)

    # Edge 1 writes x7 = 0x1111_1111
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 7
    dut.wb_data.value       = 0x1111_1111

    # Edge 2 writes x7 = 0xDDDD_DDDD. Before it, rs1 sees the bypass.
    # rs2_id=0 is unused and reads zero (section 5 read priority rule 1).
    await FallingEdge(dut.clk)
    dut.rf_write_fire.value = 1
    dut.wb_rd.value         = 7
    dut.wb_data.value       = 0xDDDD_DDDD
    dut.rs1_id.value        = 7
    dut.rs2_id.value        = 0
    await check_reads(dut, 0xDDDD_DDDD, 0x0000_0000)
    await RisingEdge(dut.clk)

    # After edge 2 storage holds the later value; 0x1111_1111 is never observed
    await FallingEdge(dut.clk)
    dut.rf_write_fire.value = 0
    dut.rs1_id.value        = 7
    dut.rs2_id.value        = 0
    await check_reads(dut, 0xDDDD_DDDD, 0x0000_0000)
