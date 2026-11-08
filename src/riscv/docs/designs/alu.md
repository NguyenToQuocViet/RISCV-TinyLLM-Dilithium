# ALU

| Field | Value |
| --- | --- |
| Description | Combinational 32-bit arithmetic, logic, shift and comparison. |
| Last modified | 2026-11-08 |
| Status | Accepted by Việt on 2026-11-08 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/alu.sv`, module `alu`, instance `ex_alu` in `execute_stage` |
| Parent | [Execute stage](execute-stage.md#4-internal-structure); [BASE execution semantics](5-stage-baseline-core.md#ex-computation-contract) |

## 1. Overview

- `alu` computes one 32-bit arithmetic, logic, shift or comparison result from two operands and an operation selector.
- The decode side supplies the selector, and the [operand mux](operand-mux.md) supplies the operands after forwarding.
- The [result mux](result-mux.md) and the [redirect unit](redirect-unit.md) consume the result, the latter for the target calculation.
- The block is purely combinational, with no clock, reset, storage, handshake or stall input.
- It decodes no instruction, forwards nothing, selects no operand, computes no branch predicate or link, masks no jump target and controls no architectural side effect.
- BASE owns the execution semantics, the execute stage owns the composition, and this block owns the ten operations.

## 2. Block Design

```text
operand_a, operand_b <- operand_mux               +-------+
                                                  |       | -> alu_result (result_mux, redirect_unit)
alu_op <- ID/EX register                          |  alu  |
                                                  |       |
                                                  +-------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `operand_a` | Input | `DATA_WIDTH` | `operand_mux` | First operand. |
| `operand_b` | Input | `DATA_WIDTH` | `operand_mux` | Second operand. |
| `alu_op` | Input | `alu_op_t` (4) | ID/EX register | Operation selector. |
| `alu_result` | Output | `DATA_WIDTH` | `result_mux`, `redirect_unit` | Selected result, including computed addresses. |

- The type comes from `riscv_pkg`, and every vector is unsigned.
- The vectors belong to the datapath domain of the [width domains](execute-stage.md#width-domains), so `alu_result` keeps the datapath width when a consumer uses it as an address.
- There is no error port and no CPU trap.

### alu_op encoding

| Member | Code |
| --- | --- |
| `ALU_ADD` | `4'h0` |
| `ALU_SUB` | `4'h1` |
| `ALU_AND` | `4'h2` |
| `ALU_OR` | `4'h3` |
| `ALU_XOR` | `4'h4` |
| `ALU_SLL` | `4'h5` |
| `ALU_SRL` | `4'h6` |
| `ALU_SRA` | `4'h7` |
| `ALU_SLT` | `4'h8` |
| `ALU_SLTU` | `4'h9` |

- The codes `4'hA` through `4'hF` are unassigned.

## 4. Internal Structure

- The block has no sub-module and no internal net, and one case on `alu_op` selects the operation.
- Shared adder, comparison or shift hardware is not required ([ALU-D3](#10-decisions-and-open-items)).

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

### Operations

| `alu_op` | `alu_result` equals |
| --- | --- |
| `ALU_ADD` | The sum of the operands, low 32 bits |
| `ALU_SUB` | The second operand subtracted from the first, low 32 bits |
| `ALU_AND` | The bitwise AND of the operands |
| `ALU_OR` | The bitwise OR of the operands |
| `ALU_XOR` | The bitwise XOR of the operands |
| `ALU_SLL` | The first operand shifted left by the low 5 bits of the second operand, zero fill, low 32 bits |
| `ALU_SRL` | The first operand shifted right by the low 5 bits of the second operand, zero fill |
| `ALU_SRA` | The first operand shifted right by the low 5 bits of the second operand, filled with the top bit of the first operand |
| `ALU_SLT` | 32-bit one if the first operand is less than the second as signed values, otherwise zero |
| `ALU_SLTU` | 32-bit one if the first operand is less than the second as unsigned values, otherwise zero |
| Unassigned code | `32'hDEAD_BEEF` at any operand value |

- The ten operations are the full set, with no dedicated FENCE, operand-copy or link operation ([EX-D5](execute-stage.md#10-decisions-and-open-items)).
- Addition and subtraction wrap at 32 bits, with no carry or overflow output and no trap.
- Signed operations read the operands as two's-complement values.
- The upper 27 bits of the second operand cannot affect a shift.
- The unassigned-code row is the diagnostic fallback of [ALU-D1](#10-decisions-and-open-items), and it is not an additional operation.

## 7. Timing and Control

- The output follows the current inputs after combinational settling, and it retains no earlier result.
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
| A live supported EX instruction selects an assigned `alu_op` code | The [control unit](control-unit.md) in ID ([ALU-D2](#10-decisions-and-open-items)) | The result is the fallback value, and the EX checker of [EX-D10](execute-stage.md#10-decisions-and-open-items) fails. |
| The result of an unsupported word or an invalid entry authorizes no side effect | The core, which uses a result only for a valid instruction that needs it ([execute stage](execute-stage.md#8-assumptions-and-corner-cases)) | An arbitrary payload could cause a side effect. |

| Case | Inputs | Result |
| --- | --- | --- |
| An addition that yields `0xDEADBEEF` | `ALU_ADD`, `operand_a` `0xDEADBEEF`, `operand_b` `0` | `alu_result` equals the fallback value, so the fallback is not a unique error signature. |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_alu.py` and cocotb module `tb/testcases/alu_cocotb.py`.
- The module has 10 tests, one per operation, and no test selects an unassigned code.
- The directed vectors are literals in the tests. The random vectors take their expected value from the golden function of the module, which computes on Python integers and not on the DUT.
- Each test ends with 100000 random pairs from the seed 2026.
- The shift tests draw the upper bits of the second operand at random too.
- The [execute stage](execute-stage.md#9-verification) owns the six ALU vectors, the checks of the six unassigned codes and the checker of EX-D10.

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Addition | Ordinary positive and negative pairs, zero on either input, and 32-bit wrap and signed overflow in both operand orders | The sum, low 32 bits | `test_add` |
| Subtraction | Ordinary pairs with positive and negative results, zero on either input, equal operands, and 32-bit underflow and both signed overflow directions | The difference, low 32 bits | `test_sub` |
| AND | Bits set in both operands, zero and all ones, the top and bottom bit, and the complementary patterns `0xAAAAAAAA` and `0x55555555` | The bitwise AND | `test_and` |
| OR | Bits set in either operand, zero and all ones, the top and bottom bit, and the complementary patterns `0xAAAAAAAA` and `0x55555555` | The bitwise OR | `test_or` |
| XOR | Bits that differ, zero, equal operands and all ones, the top and bottom bit, and the complementary patterns `0xAAAAAAAA` and `0x55555555` | The bitwise XOR | `test_xor` |
| Shift left | Ordinary amounts, zero shift, zero first operand, shift by 31, discarded high bits, and second operands 32, 33, 63, `0xFFFFFFE0` and `0xFFFFFFFF` | The first operand shifted by the low 5 bits, zero filled | `test_sll` |
| Logical shift right | Positive and top-bit-set first operands, zero shift, shift by 31, discarded low bits, and the same second operands as `test_sll` | The first operand shifted by the low 5 bits, zero filled | `test_srl` |
| Arithmetic shift right | Positive and negative first operands, rounding toward negative infinity, zero and -1, both signed extremes, shift by 31, and the second operands of `test_sll` | The first operand shifted by the low 5 bits, filled with its top bit | `test_sra` |
| Signed less than | Both outcomes in each sign group, equality, zero against both signs, the extremes `0x7FFFFFFF` and `0x80000000`, and cross-sign pairs | 1 when the first operand is the smaller signed value, otherwise 0, over the full width | `test_slt` |
| Unsigned less than | Both outcomes including values with the top bit set, equality, zero against `0xFFFFFFFF`, the top-bit boundary and neighbors of `0xFFFFFFFF` | 1 when the first operand is the smaller unsigned value, otherwise 0, over the full width | `test_sltu` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| ALU-D1 | The six unassigned codes `4'hA` through `4'hF` return `32'hDEAD_BEEF` at any operand value, as a diagnostic fallback. The block adds no error port and no CPU trap. | None recorded. |
| ALU-D2 | The control of a live supported EX instruction selects a defined operation. An unsupported word or an invalid entry may carry an arbitrary payload. | The live-control scope follows the decode stage ([ID-D10](decode-stage.md#10-decisions-and-open-items)). |
| ALU-D3 | Shared adder, comparison or shift hardware is not required, and synthesis maps the resources. Timing evidence that the ALU path limits EX may reopen the organization, and any new organization keeps the behavior of section 6. | None recorded. |

- History: 2026-10-15 the Owner accepted the spec.
- 2026-10-19 the revision ALU D4. The old file also records, with no date, a width clarification that the Owner accepted.
- 2026-10-30 the amendment ALU D5 changed only the live-control sentence, and the Owner accepted it on 2026-10-31.
- 2026-11-08 rewritten in the block spec format, with IDs for three decisions that the old file stated in prose.
- Length: 4 pages, above the limit, because the encoding, operations and planned-checks tables have ten rows each, one per operation.
- Open items: none.
