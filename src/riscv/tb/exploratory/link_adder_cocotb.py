#------------------------------------------------------------------------------
# Module      : link_adder_cocotb
# Description : Directed tests of link_adder (D-LA-01..05).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from xp_helpers import xp_test, drive, settle, expect


async def check_link(dut, pc, expected):
    drive(dut, pc=pc)
    await settle()
    expect(dut, pc_plus_4=expected)


@xp_test()
async def test_plain_increment(dut):
    # D-LA-01: the increment is 4
    await check_link(dut, 0x0000_0000, 0x0000_0004)
    await check_link(dut, 0x0000_1000, 0x0000_1004)


@xp_test()
async def test_carry_chain(dut):
    # D-LA-02: a carry crosses the bits
    await check_link(dut, 0x0000_FFFC, 0x0001_0000)
    await check_link(dut, 0x7FFF_FFFC, 0x8000_0000)


@xp_test()
async def test_wrap(dut):
    # D-LA-03: wraps at 2^32, no carry output
    await check_link(dut, 0xFFFF_FFFC, 0x0000_0000)
    await check_link(dut, 0xFFFF_FFFF, 0x0000_0003)


@xp_test()
async def test_no_alignment_correction(dut):
    # D-LA-04: low bits are added, not cleared
    await check_link(dut, 0x0000_0001, 0x0000_0005)
    await check_link(dut, 0x0000_0002, 0x0000_0006)
    await check_link(dut, 0x0000_0003, 0x0000_0007)


@xp_test()
async def test_every_bit_position(dut):
    # D-LA-05: each pc bit reaches the result
    expected = [
        0x0000_0005, 0x0000_0006, 0x0000_0008, 0x0000_000C,
        0x0000_0014, 0x0000_0024, 0x0000_0044, 0x0000_0084,
        0x0000_0104, 0x0000_0204, 0x0000_0404, 0x0000_0804,
        0x0000_1004, 0x0000_2004, 0x0000_4004, 0x0000_8004,
        0x0001_0004, 0x0002_0004, 0x0004_0004, 0x0008_0004,
        0x0010_0004, 0x0020_0004, 0x0040_0004, 0x0080_0004,
        0x0100_0004, 0x0200_0004, 0x0400_0004, 0x0800_0004,
        0x1000_0004, 0x2000_0004, 0x4000_0004, 0x8000_0004,
    ]
    for k in range(32):
        await check_link(dut, 1 << k, expected[k])
