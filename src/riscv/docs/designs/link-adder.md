# Link Adder — Block Design

**Status:** Accepted by Việt on 2026-10-19.
**Revision:** LA D1 / 2026-10-19.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [EX stage](execute-stage.md#45-link-adder).
**Mapping:** Planned module `link_adder` in `src/riscv/rtl/link_adder.sv`;
instance `ex_link_adder` in `execute_stage`.

## 1. Purpose and boundary

Compute the sequential return address for JAL/JALR in parallel with target
calculation in the ALU. The result feeds `result_mux`.

Instruction decode, target calculation, result selection, register-file writes
and redirect control belong outside this block.

## 2. Interface, timing and state

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `pc` | Input | Unsigned 32-bit logic vector | Byte address of the instruction |
| `pc_plus_4` | Output | 32-bit logic vector | Sequential return address |

At EX integration, `pc` comes from the instruction's ID/EX PC, not the
frontend's current or next fetch PC.

The block is combinational: no clock, reset, storage, handshake or stall
ownership. The output follows the current input after combinational settling.
Parent control determines when the result is consumed; an invalid pipeline
entry's payload cannot authorize an architectural side effect.

## 3. Arithmetic contract

`pc_plus_4` is `ADD(pc, 4)`, retaining the low 32 bits. Addition wraps modulo
2^32; there is no carry/overflow output or trap. No alignment correction or
target masking is performed. The increment is fixed for 32-bit instructions.

## 4. Input validity

The specified input domain contains only 0/1. X/Z behavior is outside this
contract's guaranteed domain, consistent with the pipeline's accepted policy.
