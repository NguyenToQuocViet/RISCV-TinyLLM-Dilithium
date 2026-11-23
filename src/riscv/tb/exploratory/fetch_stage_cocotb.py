#------------------------------------------------------------------------------
# Module      : fetch_stage_cocotb
# Description : Integrated tests of fetch_stage with its real children (I-IF-01..17).
#               Inputs use the plan notation: "R=t A G V=a", "V=junk" or "-".
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from cocotb.triggers import FallingEdge, RisingEdge

from xp_helpers import xp_test, drive, settle, expect, start_clock, next_edge, reset_dut

JUNK = 0xDEAD_C0DE
LOW = None  # req 0 or fetch_valid 0


def W(a):
    # instruction memory content of the test: W(a) = 0xC000_0000 + a
    return 0xC000_0000 + a


def inputs(text):
    ports = dict(redirect_fire=0, fetch_accept=0, gnt=0, rvalid=0)
    for tok in text.split():
        if tok.startswith("R="):
            ports.update(redirect_fire=1, redirect_target=int(tok[2:], 16))
        elif tok == "A":
            ports["fetch_accept"] = 1
        elif tok == "G":
            ports["gnt"] = 1
        elif tok == "V=junk":
            ports.update(rvalid=1, rdata=JUNK)
        elif tok.startswith("V="):
            ports.update(rvalid=1, rdata=W(int(tok[2:], 16)))
    return ports


def check(dut, req, fv, const=False):
    if req is LOW:
        expect(dut, req=0)
    else:
        expect(dut, req=1, addr=req)
    if fv is LOW:
        expect(dut, fetch_valid=0)
    else:
        expect(dut, fetch_valid=1, fetch_pc=fv, fetch_instruction=W(fv))
    if const:
        expect(dut, we=0, be=0b1111, wdata=0x0000_0000, rready=1)


def offered(dut, fv):
    # before-edge view of the delivery outputs (bypass included, IF-A4)
    if fv is LOW:
        expect(dut, fetch_valid=0)
    else:
        expect(dut, fetch_valid=1, fetch_pc=fv, fetch_instruction=W(fv))


async def e(dut, text, req, fv, const=False, offer=None):
    # one edge: drive at the falling edge, optionally check what is offered before the
    # edge, rising edge, then inputs idle and check the registered after-values
    # (fetch_valid follows rvalid within a cycle, so stale inputs are cleared first)
    drive(dut, **inputs(text))
    await settle()
    if offer is not None:
        offered(dut, offer)
    await next_edge(dut)
    drive(dut, **inputs("-"))
    await settle()
    check(dut, req, fv, const)


async def start(dut):
    start_clock(dut)
    await reset_dut(dut, edges=2, fetch_accept=0, redirect_fire=0, redirect_target=0, gnt=0, rvalid=0, rdata=0)


async def trace(dut, b, const=False):
    # TRACE(b): READY b, OUTSTANDING b+4, QUEUED and presented b+8
    # the free issue slot presents the target directly after the redirect edge (IF-A4)
    await e(dut, f"R={b:#x}", b, LOW, const)
    await e(dut, "-", b, LOW, const)
    await e(dut, "G", b + 4, LOW, const)
    await e(dut, f"G V={b:#x}", b + 8, b, const)


async def ready(dut):
    # READY: three READY entries 0x20, 0x24, 0x28
    await trace(dut, 0x20)
    await e(dut, "G V=0x24", LOW, 0x20)
    await e(dut, "V=0x28", LOW, 0x20)


async def fill3(dut):
    # FILL3: three QUEUED entries, gnt never given
    for _ in range(3):
        await e(dut, "-", 0x0, LOW)


@xp_test()
async def test_steady_state_trace(dut):
    # I-IF-01: one delivery per edge, one outstanding (section 7 trace), constant port fields
    await start(dut)
    await trace(dut, 0x08, const=True)
    await e(dut, "A G V=0x0C", 0x14, 0x0C, const=True)
    await e(dut, "A G V=0x10", 0x18, 0x10, const=True)
    await e(dut, "A G V=0x14", 0x1C, 0x14, const=True)
    await e(dut, "A G V=0x18", 0x20, 0x18, const=True)


@xp_test()
async def test_inputs_no_path_to_outputs(dut):
    # I-IF-02: no combinational path from any input to req, addr or fetch outputs
    await start(dut)
    await trace(dut, 0x08)
    drive(dut, gnt=1, rvalid=1, rdata=W(0x0C))
    await settle()
    check(dut, 0x10, 0x08)
    drive(dut, fetch_accept=1, rdata=0xFFFF_FFFF)
    await settle()
    check(dut, 0x10, 0x08)
    drive(dut, redirect_target=0x100, redirect_fire=1)
    await settle()
    check(dut, 0x10, 0x08)
    drive(dut, **inputs("-"))
    await settle()
    check(dut, 0x10, 0x08)
    await next_edge(dut)
    check(dut, 0x10, 0x08)
    # IF-A4 bypass: with the oldest entry live OUTSTANDING, only rvalid and rdata reach
    # fetch_valid and fetch_instruction within the cycle; req, addr and fetch_pc do not move
    await reset_dut(dut, edges=2, **inputs("-"))
    await e(dut, "R=0x40", 0x40, LOW)
    await e(dut, "G", 0x44, LOW)
    drive(dut, gnt=1, fetch_accept=1, redirect_target=0x200, redirect_fire=1)
    await settle()
    check(dut, 0x44, LOW)
    drive(dut, **inputs("V=0x40"))
    await settle()
    check(dut, 0x44, 0x40)
    drive(dut, rdata=W(0x80))
    await settle()
    expect(dut, req=1, addr=0x44, fetch_valid=1, fetch_pc=0x40, fetch_instruction=W(0x80))
    drive(dut, **inputs("-"))
    await settle()
    check(dut, 0x44, LOW)


@xp_test()
async def test_oldest_first_delivery(dut):
    # I-IF-03: delivery in allocation order across a redirect to a lower PC
    await start(dut)
    await e(dut, "R=0x100", 0x100, LOW)
    await e(dut, "-", 0x100, LOW)
    await e(dut, "G", 0x104, LOW)
    # each response is delivered on its own edge through the bypass (IF-A4)
    await e(dut, "A G V=0x100", 0x108, LOW, offer=0x100)
    await e(dut, "A G V=0x104", 0x10C, LOW, offer=0x104)
    await e(dut, "A G V=0x108", 0x110, LOW, offer=0x108)
    await e(dut, "R=0x40 G V=0x10C", 0x40, LOW)
    await e(dut, "A V=0x110", 0x40, LOW, offer=LOW)
    await e(dut, "A G", 0x44, LOW)
    await e(dut, "A G V=0x40", 0x48, LOW, offer=0x40)
    await e(dut, "A G V=0x44", 0x4C, LOW, offer=0x44)
    await e(dut, "A G V=0x48", 0x50, LOW, offer=0x48)


@xp_test()
async def test_redirect_ready_entries_not_delivered(dut):
    # I-IF-04: a redirect frees READY entries without delivering them
    await start(dut)
    await ready(dut)
    await e(dut, "R=0x100 A", 0x100, LOW)
    await e(dut, "-", 0x100, LOW)
    await e(dut, "G", 0x104, LOW)
    await e(dut, "V=0x100", 0x104, 0x100)
    await e(dut, "A", 0x104, LOW)


@xp_test()
async def test_redirect_response_on_edge_discarded(dut):
    # I-IF-05: a response on the redirect edge is discarded
    await start(dut)
    await e(dut, "R=0x20", 0x20, LOW)
    await e(dut, "-", 0x20, LOW)
    await e(dut, "G", 0x24, LOW)
    await e(dut, "R=0x100 V=0x20", 0x24, LOW)
    await e(dut, "-", 0x24, LOW)
    await e(dut, "G", 0x100, LOW)
    await e(dut, "G V=0x24", 0x104, LOW)
    await e(dut, "V=0x100", 0x104, 0x100)
    await e(dut, "A", 0x104, LOW)


@xp_test()
async def test_redirect_presented_entry_granted_on_edge(dut):
    # I-IF-06: presented entry granted on the redirect edge becomes killed OUTSTANDING
    await start(dut)
    await e(dut, "R=0x20", 0x20, LOW)
    await e(dut, "-", 0x20, LOW)
    await e(dut, "R=0x100 G", 0x100, LOW)
    await e(dut, "-", 0x100, LOW)
    await e(dut, "G V=0x20", 0x104, LOW)
    await e(dut, "V=0x100", 0x104, 0x100)
    await e(dut, "A", 0x104, LOW)


@xp_test()
async def test_redirect_unpresented_entry_freed(dut):
    # I-IF-07: unpresented QUEUED entries are freed, never requested
    await start(dut)
    await fill3(dut)
    await e(dut, "R=0x100", 0x0, LOW)
    await e(dut, "-", 0x0, LOW)
    await e(dut, "G", 0x100, LOW)
    await e(dut, "G V=0x0", 0x104, LOW)
    await e(dut, "V=0x100", 0x104, 0x100)
    await e(dut, "A", 0x104, LOW)


@xp_test()
async def test_redirect_target_allocation(dut):
    # I-IF-08: no live entry allocated on the redirect edge; the target is presented
    # directly in the next cycle, one cycle after the redirect cycle (IF-A4)
    await start(dut)
    await ready(dut)
    await e(dut, "R=0x100", 0x100, LOW)
    await e(dut, "-", 0x100, LOW)
    await e(dut, "G", 0x104, LOW)
    await e(dut, "G V=0x100", 0x108, 0x100)


@xp_test()
async def test_redirect_kept_outstanding_and_presented(dut):
    # I-IF-09: killed OUTSTANDING and presented entries drain before the target transfers
    await start(dut)
    await trace(dut, 0x1C)
    await e(dut, "R=0x100", 0x24, LOW)
    await e(dut, "-", 0x24, LOW)
    await e(dut, "G V=0x20", 0x100, LOW)
    await e(dut, "-", 0x100, LOW)
    await e(dut, "G V=0x24", 0x104, LOW)
    await e(dut, "V=0x100", 0x104, 0x100)
    await e(dut, "A", 0x104, LOW)


@xp_test()
async def test_hcu_stall(dut):
    # I-IF-10: fetch_accept low holds delivery; nothing lost (IF-D5)
    await start(dut)
    await trace(dut, 0x08)
    await e(dut, "G V=0x0C", LOW, 0x08)
    await e(dut, "V=0x10", LOW, 0x08)
    await e(dut, "A", 0x14, 0x0C)
    await e(dut, "A", 0x14, 0x10)
    await e(dut, "A", 0x14, LOW)


@xp_test()
async def test_accept_without_valid_entry(dut):
    # I-IF-11: fetch_accept with fetch_valid low has no effect
    await start(dut)
    await e(dut, "R=0x40 A", 0x40, LOW)
    await e(dut, "A", 0x40, LOW)
    await e(dut, "A G", 0x44, LOW, offer=LOW)
    # the response of 0x40 makes fetch_valid high, so this A delivers it (IF-A4)
    await e(dut, "A G V=0x40", 0x48, LOW, offer=0x40)
    await e(dut, "A", 0x48, LOW, offer=LOW)


@xp_test()
async def test_unexpected_response(dut):
    # I-IF-12: a response with nothing OUTSTANDING changes no state
    await start(dut)
    await fill3(dut)
    await e(dut, "V=junk", 0x0, LOW)
    await e(dut, "-", 0x0, LOW)
    await reset_dut(dut, edges=2, **inputs("-"))
    await ready(dut)
    await e(dut, "V=junk", LOW, 0x20)
    await e(dut, "-", LOW, 0x20)


async def reset_steps(dut):
    # s1..s4 of the reset row
    await FallingEdge(dut.clk)
    drive(dut, rst_n=0, **inputs("-"))
    await settle()
    check(dut, LOW, LOW, const=True)
    drive(dut, **inputs("A"))
    for _ in range(2):
        await next_edge(dut)
        check(dut, LOW, LOW, const=True)
    drive(dut, rst_n=1, **inputs("-"))
    await next_edge(dut)
    check(dut, 0x0, LOW, const=True)
    await e(dut, "G", 0x4, LOW, const=True)


@xp_test()
async def test_reset_with_entries_in_every_state(dut):
    # I-IF-13: reset clears entries in every state; first request is PC_RESET_VEC
    await start(dut)
    await trace(dut, 0x1C)
    await reset_steps(dut)
    await reset_dut(dut, edges=2, **inputs("-"))
    await trace(dut, 0x1C)
    await e(dut, "R=0x100", 0x24, LOW)
    await reset_steps(dut)


@xp_test()
async def test_pointer_wrap(dut):
    # I-IF-14: delivery order holds across slot reuse
    await start(dut)
    await e(dut, "-", 0x0, LOW)
    await e(dut, "G", 0x4, LOW)
    await e(dut, "R=0x20 G V=0x0", 0x20, LOW)
    # drain the killed 0x4 while 0x20 is presented directly and granted
    await e(dut, "G V=0x4", 0x24, LOW)
    await e(dut, "G V=0x20", 0x28, 0x20)
    await e(dut, "A G V=0x24", 0x2C, 0x24)
    await e(dut, "A G V=0x28", 0x30, 0x28)
    await e(dut, "A G V=0x2C", 0x34, 0x2C)


async def hold_tail(dut):
    await e(dut, "G", 0x100, LOW)
    await e(dut, "G V=0x0", 0x104, LOW)
    await e(dut, "V=0x100", 0x104, 0x100)
    await e(dut, "A", 0x104, LOW)


@xp_test()
async def test_hold_rule(dut):
    # I-IF-15: req stays on the presented entry until its grant, also across a redirect
    await start(dut)
    await e(dut, "-", 0x0, LOW)
    await e(dut, "-", 0x0, LOW)
    await e(dut, "R=0x100", 0x0, LOW)
    for _ in range(3):
        await e(dut, "-", 0x0, LOW)
    await hold_tail(dut)
    await reset_dut(dut, edges=2, **inputs("-"))
    await e(dut, "-", 0x0, LOW)
    await e(dut, "R=0x100", 0x0, LOW)
    for _ in range(3):
        await e(dut, "-", 0x0, LOW)
    await hold_tail(dut)


@xp_test()
async def test_composition_with_reset(dut):
    # I-IF-16: reset in the middle of a sequence, then restart at PC_RESET_VEC
    await start(dut)
    await e(dut, "R=0x0C", 0x0C, LOW)
    await e(dut, "-", 0x0C, LOW)
    await e(dut, "G", 0x10, LOW)
    await e(dut, "-", 0x10, LOW)
    await e(dut, "-", 0x10, LOW)
    await e(dut, "-", 0x10, LOW)
    await e(dut, "G V=0x0C", 0x14, 0x0C)
    await e(dut, "-", 0x14, 0x0C)
    drive(dut, rst_n=0)
    await settle()
    check(dut, LOW, LOW)
    await next_edge(dut)
    check(dut, LOW, LOW)
    drive(dut, rst_n=1, **inputs("-"))
    await next_edge(dut)
    check(dut, 0x0, LOW)
