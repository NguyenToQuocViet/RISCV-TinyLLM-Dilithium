#------------------------------------------------------------------------------
# Module      : xp_isa
# Description : riscv-tests rv32ui build flow on the BASE env (isa/env): gcc
#               build with the SW linker script, host-side oracles from the
#               preprocessed source (last test number, first broken case).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#------------------------------------------------------------------------------

import random
import re
import subprocess
from pathlib import Path

from xp_sw import PREFIX, SW

ISA = Path(__file__).resolve().parent / "isa"
RT = ISA / "riscv-tests"
BUILD = ISA / "build"
PIN = "3df703cd52d5f0d8224e3c50bf03c6cb70efff98"
LAST_TESTNUM = 0x0001_FFF8

FLAGS = ["-march=rv32i", "-mabi=ilp32", "-nostdlib", "-nostartfiles", "-Wl,--build-id=none",
         "-mno-relax", "-T", str(SW / "link.ld"),
         "-I", str(ISA / "env"), "-I", str(RT / "isa" / "macros" / "scalar")]

# rv32ui minus fence_i (Zifencei, self-modifying code) and ma_data (misaligned access)
TESTS = ("simple", "add", "addi", "and", "andi", "auipc", "beq", "bge", "bgeu", "blt", "bltu", "bne",
         "jal", "jalr", "lb", "lbu", "lh", "lhu", "lui", "lw", "ld_st", "st_ld", "or", "ori", "sb", "sh",
         "sll", "slli", "slt", "slti", "sltiu", "sltu", "sra", "srai", "srl", "srli", "sub", "sw",
         "xor", "xori")
SKIPS = {"fence_i": "Zifencei, rewrites code through the data port",
         "ma_data": "misaligned load/store, no exception mechanism in BASE"}
LABEL = re.compile(r"\btest_(\d+):")
BREAK_MARK = "^ 0x00000001"


def check_pin():
    head = subprocess.run(["git", "-C", str(RT), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    if head != PIN:
        raise RuntimeError(f"riscv-tests at {head}, expected pin {PIN}")


def _src(name):
    return RT / "isa" / "rv32ui" / f"{name}.S"


def build(name, defines=(), march="rv32i"):
    # rv32ui/<name>.S -> build/<tag>.elf and .hex; returns (elf, hex)
    BUILD.mkdir(exist_ok=True)
    tag = "_".join([name] + [d.lower().replace("=", "") for d in defines])
    elf, hexf = BUILD / f"{tag}.elf", BUILD / f"{tag}.hex"
    flags = [f"-march={march}" if f == "-march=rv32i" else f for f in FLAGS]
    cmd = [PREFIX + "gcc"] + flags + [f"-D{d}" for d in defines] + [str(_src(name)), "-o", str(elf)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    subprocess.run([PREFIX + "objcopy", "-O", "verilog", str(elf), str(hexf)], check=True)
    return elf, hexf


def _preprocess(name, defines=()):
    cmd = [PREFIX + "gcc", "-E"] + FLAGS + [f"-D{d}" for d in defines] + [str(_src(name))]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def last_testnum(name):
    # number of the last test case in program order (0 when the file has none)
    nums = [int(n) for n in LABEL.findall(_preprocess(name))]
    if nums != sorted(nums):
        raise ValueError(f"{name}: test numbers not in program order")
    return nums[-1] if nums else 0


def first_broken(name):
    # first test case whose expected value XP_BREAK_ALL flips; None when no TEST_CASE is used
    text = _preprocess(name, ("XP_BREAK_ALL",))
    marks = list(LABEL.finditer(text))
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        if BREAK_MARK in text[m.end():end]:
            return int(m.group(1))
    return None


def lazy(seed, low, high):
    # seeded per-transaction value; same index, same value
    rng, vals = random.Random(seed), []

    def f(i):
        while len(vals) <= i:
            vals.append(rng.randint(low, high))
        return vals[i]
    return f


def jitter_kw(seed):
    # grant delay 0..3, response latency 1..4, both ports (same recipe as the SW tests)
    return dict(igrant=lazy(seed, 0, 3), ilat=lazy(seed + 1, 1, 4),
                dgrant=lazy(seed + 2, 0, 3), dlat=lazy(seed + 3, 1, 4))
