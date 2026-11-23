#------------------------------------------------------------------------------
# Module      : xp_sw
# Description : SW test build flow: gcc build (rv32i), BASE operation gate on
#               the ELF, verilog-hex image split into code and data words,
#               known-answer digest to signature words.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-20
#------------------------------------------------------------------------------

import collections
import os
import subprocess
from pathlib import Path

SW = Path(__file__).resolve().parent / "sw"
BUILD = SW / "build"
PREFIX = os.environ.get("XP_RISCV_PREFIX", "/opt/Xilinx/2026.1/Vitis/gnu/riscv/lin/bin/riscv64-unknown-elf-")
CFLAGS = ["-march=rv32i", "-mabi=ilp32", "-nostdlib", "-nostartfiles", "-ffreestanding",
          "-Wl,--build-id=none", "-msmall-data-limit=0", "-mno-relax", "-Wall", "-Werror",
          "-T", str(SW / "link.ld")]

CODE = (0x0000_0000, 0x0001_0000)
DATA = (0x0001_0000, 0x0001_FF00)   # signature 0x1_FF00.. and TEST_STATUS are reserved
SIG_BASE = 0x0001_FF00

# 37 RV32I operations of BASE plus FENCE (core-verification section 6 gate)
BASE_OPS = {
    "lui", "auipc", "jal", "jalr", "beq", "bne", "blt", "bge", "bltu", "bgeu",
    "lb", "lh", "lw", "lbu", "lhu", "sb", "sh", "sw",
    "addi", "slti", "sltiu", "xori", "ori", "andi", "slli", "srli", "srai",
    "add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and", "fence",
}


def build(prog, opt="O2", defines=(), march="rv32i"):
    # prog.c (or prog.S alone) -> build/<tag>.elf and .hex; returns (elf, hex)
    BUILD.mkdir(exist_ok=True)
    tag = "_".join([prog, opt] + [d.lower() for d in defines])
    elf, hexf = BUILD / f"{tag}.elf", BUILD / f"{tag}.hex"
    src = SW / f"{prog}.S"
    files = [str(src)] if src.exists() else [str(SW / "start.S"), str(SW / "common.c"), str(SW / f"{prog}.c")]
    flags = [f.replace("rv32i", march) if f == "-march=rv32i" else f for f in CFLAGS]
    cmd = [PREFIX + "gcc", f"-{opt}"] + flags + [f"-D{d}" for d in defines] + files + ["-lgcc", "-o", str(elf)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    subprocess.run([PREFIX + "objcopy", "-O", "verilog", str(elf), str(hexf)], check=True)
    return elf, hexf


def check_ops(elf):
    # disassemble without aliases; fail on any operation outside BASE; return the histogram
    out = subprocess.run([PREFIX + "objdump", "-d", "-M", "no-aliases,numeric", str(elf)],
                         check=True, capture_output=True, text=True).stdout
    hist = collections.Counter()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].strip().endswith(":"):
            hist[parts[2].split()[0]] += 1
    bad = sorted(set(hist) - BASE_OPS)
    if bad:
        raise ValueError(f"{elf.name}: operations outside BASE: {bad}")
    return hist


def load_image(hexf):
    # verilog hex (@addr then bytes) -> (code words, data words), little-endian
    words = {}
    addr = 0
    for tok in Path(hexf).read_text().split():
        if tok.startswith("@"):
            addr = int(tok[1:], 16)
            continue
        if not (CODE[0] <= addr < CODE[1] or DATA[0] <= addr < DATA[1]):
            raise ValueError(f"image byte at {addr:#x} outside the code and data regions")
        w = addr & ~3
        words[w] = words.get(w, 0) | (int(tok, 16) << (8 * (addr & 3)))
        addr += 1
    code = {a: v for a, v in words.items() if a < CODE[1]}
    data = {a: v for a, v in words.items() if a >= DATA[0]}
    return code, data


def kat_words(hexdigest):
    # published digest bytes -> 8 signature words as the program stores them (little-endian)
    b = bytes.fromhex(hexdigest)
    return [int.from_bytes(b[4 * i:4 * i + 4], "little") for i in range(len(b) // 4)]
