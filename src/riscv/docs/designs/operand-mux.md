# Operand Mux — Block Design

**Status:** Accepted by Việt on 2026-10-19.
**Revision:** OM D1 / 2026-10-19.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [EX stage](execute-stage.md#42-operand-mux).
**Mapping:** Planned module `operand_mux` in `src/riscv/rtl/operand_mux.sv`;
instance `ex_operand_mux` in `execute_stage`.

## 1. Purpose and boundary

Select two 32-bit operands for the [ALU](alu.md) from register values, the
instruction PC, the canonical immediate and a constant zero source.

ID owns instruction decode and immediate reconstruction; `forwarding_unit`
supplies the register values. This leaf performs neither operation and receives
no instruction encoding or register identifiers.

Branch comparison consumes the forwarded register values directly. Store data
also bypasses this leaf; selecting an immediate for operand B cannot replace
the store's register data. Instruction-class selections are owned by the parent.

## 2. Interface, timing and state

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `rs1_value` | Input | Unsigned 32-bit logic vector | First register value |
| `rs2_value` | Input | Unsigned 32-bit logic vector | Second register value |
| `pc` | Input | Unsigned 32-bit logic vector | Instruction byte address |
| `imm` | Input | Unsigned 32-bit logic vector | Canonical immediate from ID |
| `alu_src_a` | Input | `riscv_pkg::alu_src_a_t`, 2-bit enum (planned) | Decoded source for operand A |
| `alu_src_b` | Input | `riscv_pkg::alu_src_b_t`, 1-bit enum (planned) | Decoded source for operand B |
| `operand_a` | Output | 32-bit logic vector | First ALU operand |
| `operand_b` | Output | 32-bit logic vector | Second ALU operand |

At EX integration, the register inputs connect to `fwd_rs1` and `fwd_rs2`.
The PC and immediate belong to the instruction in ID/EX; ID produces both
selectors, which ID/EX carries to this leaf. Shared types belong in
[riscv_pkg](../../rtl/riscv_pkg.sv).

The block is combinational: no clock, reset, storage, handshake or stall
ownership. Outputs follow current inputs after combinational settling.
Parent pipeline control owns capture and prevents invalid payload from
authorizing architectural side effects.

## 3. Selection contract

Both operands are selected independently and concurrently.

| Selector | Member | Code | Selected output |
| --- | --- | --- | --- |
| `alu_src_a` | `ALU_A_RS1` | `2'b00` | `operand_a = rs1_value` |
| `alu_src_a` | `ALU_A_PC` | `2'b01` | `operand_a = pc` |
| `alu_src_a` | `ALU_A_ZERO` | `2'b10` | `operand_a = 32'h0000_0000` |
| `alu_src_b` | `ALU_B_RS2` | `1'b0` | `operand_b = rs2_value` |
| `alu_src_b` | `ALU_B_IMM` | `1'b1` | `operand_b = imm` |

Selected data passes unchanged, preserving all 32 bits. The leaf performs no
arithmetic, sign extension, shifting, alignment correction or immediate-format
selection. ZERO is an internal constant, not a value read from a register input.
FENCE requires no meaningful ALU operands; parent control governs their use.

## 4. Input validity and exceptional conditions

The specified input domain contains only 0/1. X/Z behavior is outside this
contract's guaranteed domain, consistent with the pipeline's accepted policy.

The unassigned A selector code `2'b11` returns `operand_a = 32'hDEAD_BEEF`
independently of the data inputs. Operand B continues to follow its own selector.
This diagnostic fallback introduces no error port or CPU trap. Both binary B
selector values are assigned.
