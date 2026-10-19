# Branch Comparator — Block Design

**Status:** Proposed for final owner acceptance; all local decisions resolved.
**Revision:** BC D2 draft / 2026-10-19; width clarification accepted by Việt.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [EX stage](execute-stage.md#44-branch-comparator),
[BASE execution semantics](5-stage-baseline-core.md#ex-computation-contract).
**Mapping:** [branch_comparator](../../rtl/branch_comparator.sv);
planned instance `ex_branch_comparator` in `execute_stage`.

## 1. Purpose and boundary

Compare the two forwarded architectural register values for a conditional
branch. The one-bit predicate feeds `redirect_unit` while the ALU independently
computes the branch target.

Instruction decode, forwarding, target calculation, jump handling and
valid/advance gating belong outside this block. The comparator does not emit
a redirect or decide whether the current instruction is a branch.

## 2. Interface, timing and state

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `operand_a` | Input | Unsigned `logic [DATA_WIDTH-1:0]` | First comparison operand |
| `operand_b` | Input | Unsigned `logic [DATA_WIDTH-1:0]` | Second comparison operand |
| `branch_kind` | Input | `riscv_pkg::branch_kind_t`, `enum logic [2:0]` | Decoded comparison condition |
| `branch_condition` | Output | 1-bit logic | Selected comparison predicate |

At EX integration, `operand_a` is connected to `fwd_rs1` and `operand_b` to
`fwd_rs2`; forwarding is performed outside this leaf.

The operands belong to the register/datapath domain under the parent's
[width contract](execute-stage.md#width-domains). The block is combinational:
no clock, reset, storage, handshake or stall ownership. The output follows current inputs after
combinational settling and is consumed only for a conditional branch. Parent
control prevents invalid or held instructions from authorizing a redirect.

## 3. Comparison contract

Let A be `operand_a` and B be `operand_b`. Each selected condition returns one when
the predicate holds and zero otherwise.

| Selector | Code | Required predicate |
| --- | --- | --- |
| `BR_EQ` | `3'b000` | A equals B, comparing all 32 bits |
| `BR_NE` | `3'b001` | A does not equal B, comparing all 32 bits |
| `BR_LT_SIGNED` | `3'b100` | Signed A is less than signed B |
| `BR_GE_SIGNED` | `3'b101` | Signed A is greater than or equal to signed B |
| `BR_LT_UNSIGNED` | `3'b110` | Unsigned A is less than unsigned B |
| `BR_GE_UNSIGNED` | `3'b111` | Unsigned A is greater than or equal to unsigned B |

The codes match RISC-V branch funct3 values, avoiding a separate internal
remapping. ID identifies a legal branch and produces this semantic selector;
the comparator receives no raw instruction fields and performs no instruction
decode. Codes `3'b010` and `3'b011` are unassigned. The shared type is defined in
[riscv_pkg](../../rtl/riscv_pkg.sv).

Signed conditions interpret both operands as 32-bit two's-complement values.
The output is a predicate, not the ALU's 32-bit SLT/SLTU result. There is no
cross-leaf comparison-result interface or mandated internal sharing topology.

## 4. Input validity and exceptional conditions

The specified input domain contains only 0/1. X/Z behavior and dedicated
unknown-input checks are outside scope, consistent with the ALU design.

Both unassigned binary selector codes, `3'b010` and `3'b011`, return
`branch_condition = 1'b0` independently of the operands. This fallback does
not distinguish an invalid selector from a false comparison. No error port or
CPU trap is introduced.

At EX integration, a valid conditional branch must select one of the six
defined conditions; either unassigned code must cause checker FAIL. Bubbles
and instructions that are not conditional branches do not trigger this check.
The checker belongs to verification and adds no hardware error mechanism.
