#------------------------------------------------------------------------------
# Module      : xp_rv32i
# Description : Small RV32I encoder for the core stimulus. Every encoding used
#               is cross-checked against GNU as (check_encoder_against_gnu_as).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------


def _r(f7, rs2, rs1, f3, rd, op):
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def _i(imm, rs1, f3, rd, op):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def _s(imm, rs2, rs1, f3, op):
    imm &= 0xFFF
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | op


def _b(off, rs2, rs1, f3):
    off &= 0x1FFF
    return (((off >> 12) & 1) << 31) | (((off >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | \
           (f3 << 12) | (((off >> 1) & 0xF) << 8) | (((off >> 11) & 1) << 7) | 0x63


def add(rd, rs1, rs2):  return _r(0, rs2, rs1, 0, rd, 0x33)
def sub(rd, rs1, rs2):  return _r(0x20, rs2, rs1, 0, rd, 0x33)
def addi(rd, rs1, imm): return _i(imm, rs1, 0, rd, 0x13)
def lui(rd, imm20):     return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | 0x37
def lb(rd, off, rs1):   return _i(off, rs1, 0, rd, 0x03)
def lh(rd, off, rs1):   return _i(off, rs1, 1, rd, 0x03)
def lw(rd, off, rs1):   return _i(off, rs1, 2, rd, 0x03)
def lbu(rd, off, rs1):  return _i(off, rs1, 4, rd, 0x03)
def lhu(rd, off, rs1):  return _i(off, rs1, 5, rd, 0x03)
def sb(rs2, off, rs1):  return _s(off, rs2, rs1, 0, 0x23)
def sh(rs2, off, rs1):  return _s(off, rs2, rs1, 1, 0x23)
def sw(rs2, off, rs1):  return _s(off, rs2, rs1, 2, 0x23)
def beq(rs1, rs2, off): return _b(off, rs2, rs1, 0)
def bne(rs1, rs2, off): return _b(off, rs2, rs1, 1)
def jalr(rd, off, rs1): return _i(off, rs1, 0, rd, 0x67)


def jal(rd, off):
    off &= 0x1FFFFF
    return (((off >> 20) & 1) << 31) | (((off >> 1) & 0x3FF) << 21) | (((off >> 11) & 1) << 20) | \
           (((off >> 12) & 0xFF) << 12) | (rd << 7) | 0x6F


NOP = 0x0000_0013  # addi x0, x0, 0

# (assembly text, encoder result) pairs covering every format and field used by the tests
CROSS_CHECK = [
    ("add x6, x5, x2", add(6, 5, 2)),
    ("sub x7, x31, x1", sub(7, 31, 1)),
    ("addi x6, x0, 5", addi(6, 0, 5)),
    ("addi x31, x30, -1", addi(31, 30, -1)),
    ("addi x0, x0, 0", NOP),
    ("lui x1, 0x10", lui(1, 0x10)),
    ("lui x30, 0xfffff", lui(30, 0xFFFFF)),
    ("lb x5, 3(x1)", lb(5, 3, 1)),
    ("lh x5, 2(x1)", lh(5, 2, 1)),
    ("lw x5, 0(x1)", lw(5, 0, 1)),
    ("lw x9, -4(x30)", lw(9, -4, 30)),
    ("lbu x5, 1(x1)", lbu(5, 1, 1)),
    ("lhu x5, 2(x1)", lhu(5, 2, 1)),
    ("sb x2, 3(x1)", sb(2, 3, 1)),
    ("sh x2, 2(x1)", sh(2, 2, 1)),
    ("sw x2, 0(x1)", sw(2, 0, 1)),
    ("sw x31, -4(x30)", sw(31, -4, 30)),
    ("sw x5, 2044(x1)", sw(5, 2044, 1)),
    ("beq x0, x0, 64", beq(0, 0, 64)),
    ("beq x0, x0, -8", beq(0, 0, -8)),
    ("bne x5, x6, 4094", bne(5, 6, 4094)),
    ("bne x5, x6, -4096", bne(5, 6, -4096)),
    ("jal x0, 0", jal(0, 0)),
    ("jal x1, 2048", jal(1, 2048)),
    ("jal x1, -1048576", jal(1, -1048576)),
    ("jalr x0, 0(x1)", jalr(0, 0, 1)),
    ("jalr x5, -3(x7)", jalr(5, -3, 7)),
]
