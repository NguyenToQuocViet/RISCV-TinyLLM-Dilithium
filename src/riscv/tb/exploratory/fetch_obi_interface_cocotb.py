#------------------------------------------------------------------------------
# Module      : fetch_obi_interface_cocotb
# Description : Directed tests of fetch_obi_interface (D-FOI-01..06).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from xp_helpers import xp_test, drive, settle, expect

PC_A, PC_B = 0x0000_0010, 0xFFFF_FFFC
WORD_A, WORD_B, WORD_I2 = 0x5A5A_5A5A, 0xA5A5_A5A5, 0x0020_8133


async def apply(dut, **ports):
    drive(dut, **ports)
    await settle()


@xp_test()
async def test_pass_through(dut):
    # D-FOI-01: req, addr and response_data follow their inputs
    await apply(dut, rst_n=1, gnt=0, rvalid=1, present_valid=1, present_pc=PC_A, rdata=WORD_A)
    expect(dut, req=1, addr=PC_A, response_data=WORD_A)
    await apply(dut, present_pc=PC_B, rdata=WORD_B)
    expect(dut, req=1, addr=PC_B, response_data=WORD_B)
    await apply(dut, present_valid=0)
    expect(dut, req=0)


@xp_test()
async def test_request_ignores_response_side_inputs(dut):
    # D-FOI-02: no path from gnt, rvalid, rdata or rst_n to req and addr (FOI-D5)
    await apply(dut, present_pc=PC_A)
    for pv in (1, 0):
        for rst_n in (0, 1):
            for gnt in (0, 1):
                for rvalid in (0, 1):
                    for rdata in (0x0000_0000, 0xFFFF_FFFF):
                        await apply(dut, present_valid=pv, rst_n=rst_n, gnt=gnt, rvalid=rvalid, rdata=rdata)
                        if pv:
                            expect(dut, req=1, addr=PC_A)
                        else:
                            expect(dut, req=0)


@xp_test()
async def test_event_table(dut):
    # D-FOI-03: request_fire and raw_response_transfer match the 6 table for all 16 inputs
    # (rst_n, present_valid, gnt, rvalid) -> (request_fire, raw_response_transfer)
    table = {
        0b1000: (0, 0), 0b1001: (0, 1), 0b1010: (0, 0), 0b1011: (0, 1),
        0b1100: (0, 0), 0b1101: (0, 1), 0b1110: (1, 0), 0b1111: (1, 1),
    }
    for v in range(8):
        table[v] = (0, 0)
    await apply(dut, present_pc=PC_A, rdata=WORD_A)
    for order in (range(16), range(15, -1, -1)):
        for v in order:
            await apply(dut, rst_n=(v >> 3) & 1, present_valid=(v >> 2) & 1, gnt=(v >> 1) & 1, rvalid=v & 1)
            rf, rrt = table[v]
            expect(dut, request_fire=rf, raw_response_transfer=rrt)


@xp_test()
async def test_constant_fields(dut):
    # D-FOI-04: we, be, wdata and rready are constant, reset included
    await apply(dut, present_pc=0xFFFF_FFFF)
    for v in range(32):
        await apply(dut, rst_n=(v >> 4) & 1, present_valid=(v >> 3) & 1, gnt=(v >> 2) & 1,
                    rvalid=(v >> 1) & 1, rdata=0xFFFF_FFFF if v & 1 else 0)
        expect(dut, we=0, be=0xF, wdata=0x0000_0000, rready=1)


@xp_test()
async def test_trace_cycles_c1_to_c4(dut):
    # D-FOI-05: the section 7 trace, one vector per cycle
    await apply(dut, rst_n=1, present_valid=1, present_pc=0x10, gnt=0, rvalid=0)
    expect(dut, req=1, addr=0x10, request_fire=0, raw_response_transfer=0)
    await apply(dut, rst_n=1, present_valid=1, present_pc=0x10, gnt=0, rvalid=0)
    expect(dut, req=1, addr=0x10, request_fire=0, raw_response_transfer=0)
    await apply(dut, present_pc=0x10, gnt=1, rvalid=1, rdata=WORD_I2)
    expect(dut, req=1, addr=0x10, request_fire=1, raw_response_transfer=1, response_data=WORD_I2)
    await apply(dut, present_pc=0x14, gnt=0, rvalid=0)
    expect(dut, req=1, addr=0x14, request_fire=0, raw_response_transfer=0)


@xp_test()
async def test_unexpected_response(dut):
    # D-FOI-06: a response with no granted request is still a raw response transfer
    await apply(dut, rst_n=1, rvalid=1, rdata=WORD_B, present_pc=PC_A)
    for pv, gnt in ((0, 0), (0, 1), (1, 0)):
        await apply(dut, present_valid=pv, gnt=gnt)
        expect(dut, raw_response_transfer=1, request_fire=0, response_data=WORD_B)
