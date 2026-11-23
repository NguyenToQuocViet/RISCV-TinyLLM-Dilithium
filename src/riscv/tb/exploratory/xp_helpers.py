#------------------------------------------------------------------------------
# Module      : xp_helpers
# Description : Clock, reset, drive and check helpers for the exploratory tests.
#               XP_FLIP=1 flips bit 0 of every expected value (negative control).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

import functools
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

FLIP = os.environ.get("XP_FLIP") == "1"
_checks = [0]


def xp_test(**kwargs):
    # cocotb.test that fails when the body ran no check
    def deco(func):
        @functools.wraps(func)
        async def wrapper(dut):
            _checks[0] = 0
            await func(dut)
            assert _checks[0] > 0, "vacuous test: no check ran"
        return cocotb.test(**kwargs)(wrapper)
    return deco


def check(label, got, expected):
    exp = expected ^ 1 if FLIP else expected
    _checks[0] += 1
    assert got == exp, f"{label}: expected {exp:#x}, got {got:#x}"


def expect(dut, **ports):
    for name, value in ports.items():
        check(name, int(getattr(dut, name).value), value)


def drive(dut, **ports):
    for name, value in ports.items():
        getattr(dut, name).value = value


async def settle():
    await Timer(1, unit="ns")


def start_clock(dut, period_ns=10):
    Clock(dut.clk, period_ns, unit="ns").start()


async def next_edge(dut):
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)


async def reset_dut(dut, edges=1, **idle):
    # rst_n low over `edges` rising edges, released at a falling edge
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    drive(dut, **idle)
    for _ in range(edges):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
