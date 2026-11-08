# Branch Comparator

| Field | Value |
| --- | --- |
| Description | Combinational 32-bit comparison for six branch conditions. |
| Last modified | 2026-11-08 |
| Status | Accepted by Việt on 2026-11-08 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/branch_comparator.sv`, module `branch_comparator`, instance `ex_branch_comparator` in `execute_stage` |
| Parent | [Execute stage](execute-stage.md#4-internal-structure); [BASE execution semantics](5-stage-baseline-core.md#ex-computation-contract) |

## 1. Overview

- `branch_comparator` compares the two forwarded register values and returns one predicate bit for the selected branch condition.
- The [redirect unit](redirect-unit.md) consumes the predicate, while the [ALU](alu.md) computes the branch target independently.
- The block is purely combinational, with no clock, reset, storage, handshake or stall input.
- It decodes no instruction, forwards nothing, computes no target, emits no redirect and does not decide whether the instruction in EX is a conditional branch.
- BASE owns the branch semantics, the execute stage owns the composition, and this block owns the six comparisons.

## 2. Block Design

```text
operand_a, operand_b <- forwarding_unit            +-------------------+
                                                   |                   |
branch_kind <- ID/EX register                      | branch_comparator | -> branch_condition (redirect_unit)
                                                   |                   |
                                                   +-------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `operand_a` | Input | `DATA_WIDTH` | `forwarding_unit` | First comparison operand, the forwarded first register source. |
| `operand_b` | Input | `DATA_WIDTH` | `forwarding_unit` | Second comparison operand, the forwarded second register source. |
| `branch_kind` | Input | `branch_kind_t` (3) | ID/EX register | Decoded comparison condition. |
| `branch_condition` | Output | 1 | `redirect_unit` | Selected comparison predicate. |

- The type comes from `riscv_pkg`, every vector is unsigned, and the operands belong to the datapath domain of the [width domains](execute-stage.md#width-domains).
- There is no error port and no CPU trap.

### branch_kind encoding

| Member | Code |
| --- | --- |
| `BR_EQ` | `3'b000` |
| `BR_NE` | `3'b001` |
| `BR_LT_SIGNED` | `3'b100` |
| `BR_GE_SIGNED` | `3'b101` |
| `BR_LT_UNSIGNED` | `3'b110` |
| `BR_GE_UNSIGNED` | `3'b111` |

- The codes `3'b010` and `3'b011` are unassigned, and the assigned codes equal the RISC-V branch `funct3` values ([BC-D1](#10-decisions-and-open-items)).

## 4. Internal Structure

- The block has no sub-module and no internal net, and one case on `branch_kind` selects the comparison.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

### Comparison

| `branch_kind` | `branch_condition` is 1 when |
| --- | --- |
| `BR_EQ` | All 32 bits of the operands are equal |
| `BR_NE` | At least one bit of the operands differs |
| `BR_LT_SIGNED` | The first operand is less than the second, as signed 32-bit values |
| `BR_GE_SIGNED` | The first operand is greater than or equal to the second, as signed 32-bit values |
| `BR_LT_UNSIGNED` | The first operand is less than the second, as unsigned 32-bit values |
| `BR_GE_UNSIGNED` | The first operand is greater than or equal to the second, as unsigned 32-bit values |
| Unassigned code | Never: the output is 0 at any operand value |

- The unassigned-code row is the fallback of [BC-D2](#10-decisions-and-open-items). It does not distinguish an unassigned code from a false comparison.
- The output is a predicate and not the 32-bit SLT or SLTU result of the ALU. The comparator and the ALU keep separate interfaces, with no shared comparison result ([EX-D6](execute-stage.md#10-decisions-and-open-items)).

## 7. Timing and Control

- The output follows the current inputs after combinational settling.
- The block has no latency, no handshake and no registered output.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input and no state. |
| Stall | None: the block has no stall input. |
| Flush | None: the block has no flush input. |

- Trace: None, because the block has no sequence in time, and its output depends on the current inputs alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| `branch_condition` authorizes a redirect only for a valid, advancing conditional branch | The execute stage, through the [redirect unit](redirect-unit.md#6-behavior) | A non-branch or held instruction redirects. |
| A valid conditional branch selects an assigned `branch_kind` code | The [control unit](control-unit.md) in ID | The output is 0, like a false comparison. |

| Case | Inputs | Result |
| --- | --- | --- |
| Sign boundary | `operand_a` `0x80000000`, `operand_b` `0x7FFFFFFF` | `BR_LT_SIGNED` gives 1 and `BR_LT_UNSIGNED` gives 0, so the same operands branch differently under the two readings. |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_branch_comparator.py` and cocotb module `tb/testcases/branch_comparator_cocotb.py`.
- The module has 6 tests, one per assigned code, and no test selects an unassigned code.
- Expected values come from the golden function of the module, which compares Python integers and not the DUT.
- Each test ends with 100000 random pairs from the seed 2026.
- The `execute_stage_cocotb` module holds a checker for a valid conditional branch with an unassigned code. It validates the checker with the codes `3'b010` and `3'b011`.
- The [execute stage](execute-stage.md#9-verification) owns integration verification.

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Equal | `BR_EQ` with ordinary, negative and equal-extreme operands, zero with zero, and a one-bit difference at each of 32 positions in both orders | 1 for equal operands and 0 otherwise | `test_eq` |
| Not equal | The `test_eq` vectors with `BR_NE` | The complement of `test_eq` | `test_ne` |
| Signed less than | `BR_LT_SIGNED` with ordinary and negative pairs, the extremes `0x7FFFFFFF` and `0x80000000` with neighbors, and pairs of 0, 1 and -1 | 1 when the first operand is the smaller signed value | `test_lt_signed` |
| Signed greater or equal | The `test_lt_signed` vectors with `BR_GE_SIGNED` | The complement of `test_lt_signed` | `test_ge_signed` |
| Unsigned less than | `BR_LT_UNSIGNED` with ordinary pairs, pairs around the most significant bit, 0 against `0xFFFFFFFF`, and equal extremes | 1 when the first operand is the smaller unsigned value | `test_lt_unsigned` |
| Unsigned greater or equal | The `test_lt_unsigned` vectors with `BR_GE_UNSIGNED` | The complement of `test_lt_unsigned` | `test_ge_unsigned` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| BC-D1 | The `branch_kind` codes equal the RISC-V branch `funct3` values. | The core needs no separate internal remapping. |
| BC-D2 | An unassigned code returns 0 with no error port and no CPU trap. A valid conditional branch with such a code is a checker FAIL in verification, which adds no hardware mechanism. | None recorded. |

- History: 2026-10-19 the Owner accepted the spec, under the revision label BC D2.
- 2026-11-08 rewritten in the block spec format, with IDs for two decisions that the old file stated in prose.
- Open items: the [execute stage](execute-stage.md#9-verification) lists no planned check for the branch-kind checker of [BC-D2](#10-decisions-and-open-items), although its test module has one. Consequence: the checker has a test and no stated requirement.
