# Control Unit

| Field | Value |
| --- | --- |
| Description | Recognize the 38 RV32I operations and produce ID control values. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/control_unit.sv`, module `control_unit`, instance `id_control_unit` in `decode_stage` |
| Parent | [Decode stage](decode-stage.md); [Five-stage BASE core](5-stage-baseline-core.md) (ID decode contract, instruction semantic table); [Execute stage](execute-stage.md) (operand mux); [ALU](alu.md) (input validity) |

## 1. Overview

- `control_unit` recognizes the 38 RV32I operations from the IF/ID `instruction`.
- It drives the control values and source-use qualifiers that `decode_stage` sends to the core, EX, MEM and WB.
- For each supported operation, the outputs equal the class and funct tables of section 6.
- An unsupported word produces no register write, memory access or control flow.
- It is purely combinational, with no clock, reset or state.
- It has no trap, error flag, legality output or extra port, because BASE has no illegal-instruction handling ([decode-stage D4](decode-stage.md#9-rationale-and-open-decisions)).
- It does not extract `rs1_id`, `rs2_id` or `rd`, because `decode_stage` wires them.
- It does not build `imm`, because [immediate-generator.md](immediate-generator.md) owns it.
- It does not detect hazards, and `rs1_used` and `rs2_used` only qualify the sources for the [hazard control unit](hazard-control-unit.md).

## 2. Block Design

```text
                               +----------------------+
                               |                      | -> rs1_used (decode_stage)
                               |                      | -> rs2_used (decode_stage)
                               |                      | -> reg_write (decode_stage)
                               |                      | -> mem_en (decode_stage)
                               |                      | -> control_flow (decode_stage)
                               |                      | -> mem_write (decode_stage)
instruction <- decode_stage    |     control_unit     | -> mem_type (decode_stage)
                               |                      | -> wb_src (decode_stage)
                               |                      | -> alu_op (decode_stage)
                               |                      | -> alu_src_a (decode_stage)
                               |                      | -> alu_src_b (decode_stage)
                               |                      | -> branch_kind (decode_stage)
                               |                      | -> result_src (decode_stage)
                               +----------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `instruction` | Input | `INSTR_WIDTH` | `decode_stage` | The IF/ID instruction word. |
| `rs1_used` | Output | 1 | `decode_stage` | The operation semantically consumes `rs1`. |
| `rs2_used` | Output | 1 | `decode_stage` | The operation semantically consumes `rs2`. |
| `reg_write` | Output | 1 | `decode_stage` | Semantic register-write intent. |
| `mem_en` | Output | 1 | `decode_stage` | Data-memory access intent. |
| `control_flow` | Output | `control_flow_t` (2) | `decode_stage` | `CF_NONE`, `CF_BRANCH`, `CF_JAL` or `CF_JALR`. |
| `mem_write` | Output | 1 | `decode_stage` | `0` for a load, `1` for a store. |
| `mem_type` | Output | `mem_type_t` (3) | `decode_stage` | Access width and load signedness. |
| `wb_src` | Output | 1 | `decode_stage` | `0` selects the EX result, `1` the load result. |
| `alu_op` | Output | `alu_op_t` (4) | `decode_stage` | ALU operation. |
| `alu_src_a` | Output | `alu_src_a_t` (2) | `decode_stage` | Source of the first ALU operand. |
| `alu_src_b` | Output | `alu_src_b_t` (1) | `decode_stage` | Source of the second ALU operand. |
| `branch_kind` | Output | `branch_kind_t` (3) | `decode_stage` | Branch comparison. |
| `result_src` | Output | `result_src_t` (1) | `decode_stage` | ALU result or link selection. |

- `INSTR_WIDTH` is 32, and the enum types come from `riscv_pkg` ([decode-stage O7-R](decode-stage.md#9-rationale-and-open-decisions)).
- The port names and types equal the `decode_stage` port table, so `decode_stage` only wires them ([decode-stage section 2](decode-stage.md#2-interface-contract)).

## 4. Internal Structure

- None, because the block has no sub-blocks.

## 5. State

- None, because the block is stateless (section 1).

## 6. Behavior

- `funct3` is `instruction[14:12]`, and `funct7` is `instruction[31:25]`.
- `any` means that every value is acceptable in a cell.
  - An input field with `any` does not identify the operation.
  - An output with `any` has no required value, because BASE and the EX operand mux assign it none.
  - A cell that is not `any` is binding.
- A word is supported exactly when it passes the legality table, and recognition uses the complete RV32I encoding ([decode-stage D7](decode-stage.md#9-rationale-and-open-decisions)).

### Legality table

| Rule | Applies to | Accept condition |
| --- | --- | --- |
| L1 | Every word | `instruction[1:0]` is `11` |
| L2 | Every word | `instruction[6:2]` is one of LUI `01101`, AUIPC `00101`, JAL `11011`, JALR `11001`, BRANCH `11000`, LOAD `00000`, STORE `01000`, OP-IMM `00100`, OP `01100`, MISC-MEM `00011`. SYSTEM and every other opcode are unsupported. |
| L3 | JALR | `funct3` is `000` |
| L4 | BRANCH | `funct3` is not `010` and not `011` |
| L5 | LOAD | `funct3` is one of `000`, `001`, `010`, `100`, `101` |
| L6 | STORE | `funct3` is one of `000`, `001`, `010` |
| L7 | OP-IMM | `funct3` `001` requires `funct7` `0000000`; `funct3` `101` requires `funct7` `0000000` or `0100000`; other `funct3` values have no further check |
| L8 | OP | `funct7` `0000000` with any `funct3`; `funct7` `0100000` only with `funct3` `000` or `101`; every other `funct7` is unsupported |
| L9 | MISC-MEM | `funct3` is `000` (FENCE); `funct3` `001` (FENCE.I) is unsupported |

- LUI, AUIPC and JAL have no check beyond L1 and L2.
- The rules do not check the `rd`, `rs1` and `rs2` fields, the FENCE fields `fm`, `pred` and `succ`, or HINT encodings.
- They do not check the immediate bits other than the `funct7` bits that L7 uses, or target and address alignment.
- For an unsupported word, `reg_write` is 0, `mem_en` is 0 and `control_flow` is `CF_NONE` ([decode-stage D5](decode-stage.md#9-rationale-and-open-decisions)).
- These three outputs are the guarded enables.
- Every other output of an unsupported word is `any`.
- An `any` output may carry a reserved enum code, and the block adds no logic to avoid it ([decode-stage O6 and D6](decode-stage.md#9-rationale-and-open-decisions)).
- A cell `by funct` takes its value from the funct table of the same output.
- The values come from the [BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract), the [BASE instruction semantic table](5-stage-baseline-core.md#instruction-semantic-table) and the [EX operand mux](execute-stage.md#42-operand-mux).
- `alu_op` is ADD for a branch, JAL and JALR, because the ALU computes the redirect target (EX operand mux).
  - It binds for a branch although a branch writes no register.
- Every binding output and the three guarded enables depend only on `instruction[31:25]`, `instruction[14:12]` and `instruction[6:0]`.
- No output depends on `rd`, `rs1` or `rs2`.

### Class table

| Operation class | `rs1_used` | `rs2_used` | `reg_write` | `mem_en` | `control_flow` | `wb_src` | `alu_op` | `alu_src_a` | `alu_src_b` | `result_src` | `branch_kind` | `mem_write` | `mem_type` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LUI | 0 | 0 | 1 | 0 | `CF_NONE` | 0 | `ALU_ADD` | `ALU_A_ZERO` | `ALU_B_IMM` | `RESULT_ALU` | any | any | any |
| AUIPC | 0 | 0 | 1 | 0 | `CF_NONE` | 0 | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | `RESULT_ALU` | any | any | any |
| JAL | 0 | 0 | 1 | 0 | `CF_JAL` | 0 | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | `RESULT_PC_PLUS_4` | any | any | any |
| JALR | 1 | 0 | 1 | 0 | `CF_JALR` | 0 | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_PC_PLUS_4` | any | any | any |
| BRANCH | 1 | 1 | 0 | 0 | `CF_BRANCH` | any | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | any | by funct | any | any |
| LOAD | 1 | 0 | 1 | 1 | `CF_NONE` | 1 | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | any | 0 | by funct |
| STORE | 1 | 1 | 0 | 1 | `CF_NONE` | 0 | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | any | 1 | by funct |
| OP-IMM | 1 | 0 | 1 | 0 | `CF_NONE` | 0 | by funct | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | any | any | any |
| OP | 1 | 1 | 1 | 0 | `CF_NONE` | 0 | by funct | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | any | any | any |
| MISC-MEM | 0 | 0 | 0 | 0 | `CF_NONE` | any | `ALU_ADD` | any | any | any | any | any | any |

### alu_op table

| Class | `funct3` | `funct7` | Operation | `alu_op` |
| --- | --- | --- | --- | --- |
| OP-IMM | `000` | any | ADDI | `ALU_ADD` |
| OP-IMM | `010` | any | SLTI | `ALU_SLT` |
| OP-IMM | `011` | any | SLTIU | `ALU_SLTU` |
| OP-IMM | `100` | any | XORI | `ALU_XOR` |
| OP-IMM | `110` | any | ORI | `ALU_OR` |
| OP-IMM | `111` | any | ANDI | `ALU_AND` |
| OP-IMM | `001` | `0000000` | SLLI | `ALU_SLL` |
| OP-IMM | `101` | `0000000` | SRLI | `ALU_SRL` |
| OP-IMM | `101` | `0100000` | SRAI | `ALU_SRA` |
| OP | `000` | `0000000` | ADD | `ALU_ADD` |
| OP | `000` | `0100000` | SUB | `ALU_SUB` |
| OP | `001` | `0000000` | SLL | `ALU_SLL` |
| OP | `010` | `0000000` | SLT | `ALU_SLT` |
| OP | `011` | `0000000` | SLTU | `ALU_SLTU` |
| OP | `100` | `0000000` | XOR | `ALU_XOR` |
| OP | `101` | `0000000` | SRL | `ALU_SRL` |
| OP | `101` | `0100000` | SRA | `ALU_SRA` |
| OP | `110` | `0000000` | OR | `ALU_OR` |
| OP | `111` | `0000000` | AND | `ALU_AND` |

### branch_kind table

| `funct3` | Operation | `branch_kind` |
| --- | --- | --- |
| `000` | BEQ | `BR_EQ` |
| `001` | BNE | `BR_NE` |
| `100` | BLT | `BR_LT_SIGNED` |
| `101` | BGE | `BR_GE_SIGNED` |
| `110` | BLTU | `BR_LT_UNSIGNED` |
| `111` | BGEU | `BR_GE_UNSIGNED` |

### mem_type table

| Class | `funct3` | Operation | `mem_type` |
| --- | --- | --- | --- |
| LOAD | `000` | LB | `MEM_BYTE` |
| LOAD | `001` | LH | `MEM_HALF` |
| LOAD | `010` | LW | `MEM_WORD` |
| LOAD | `100` | LBU | `MEM_BYTE_U` |
| LOAD | `101` | LHU | `MEM_HALF_U` |
| STORE | `000` | SB | `MEM_BYTE` |
| STORE | `001` | SH | `MEM_HALF` |
| STORE | `010` | SW | `MEM_WORD` |

## 7. Timing and Control

- Every output is a combinational function of `instruction` alone, so the block adds no latency and has no handshake.
- No output depends on the IF/ID `valid`, because ID/EX discards an invalid decode ([decode-stage O2](decode-stage.md#9-rationale-and-open-decisions)).

### When valid

| Signal group | When valid |
| --- | --- |
| `reg_write`, `mem_en`, `control_flow` | Every cycle, for every `instruction` value |
| All other outputs | For a supported operation, except the cells marked `any` in the class and funct tables |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input and no state. |
| Stall | None: the block has no stall input. A held IF/ID presents the same `instruction`, so every output stays stable. |
| Flush | None: the block has no flush input. |

- Trace: None, because the block has no sequence in time, and each output depends on the current `instruction` alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every `instruction` bit is 0 or 1 | The environment ([register-file.md](register-file.md) O1) | X and Z behavior is unspecified and untested. |
| The EX ALU and operand-mux checkers apply to supported instructions only, and the operand-mux checker exempts FENCE | EX and ALU ([decode-stage O6](decode-stage.md#9-rationale-and-open-decisions), [execute-stage.md](execute-stage.md), [alu.md](alu.md)) | A reserved code or an `any` cell of an unsupported word or FENCE could raise a false error. |
| The EX branch-kind checker fires only for a valid conditional branch, and the MEM memory-type checker only for a valid memory instruction (`mem_en` 1) | EX and MEM gate the checkers, and the guarded enables of an unsupported word ([section 6](#6-behavior)) keep them quiet | An `any` `branch_kind` or `mem_type` could raise a false error. |
| No EX, MEM or WB consumer reads an `any` cell | EX, MEM and WB: `wb_src` and `result_src` serve only a register write. `mem_write` and `mem_type` serve only a memory access. FENCE has no meaningful operands. | A consumer would act on a value that no record assigns. |

| Case | Inputs | Result |
| --- | --- | --- |
| FENCE.TSO or PAUSE | MISC-MEM word with `funct3` `000` and any `fm`, `pred`, `succ`, `rs1` or `rd` | Decodes as FENCE, because section 6 does not check those fields. |
| Unsupported word in ID behind a load | `rs1_used` and `rs2_used` are `any` for the unsupported word | The hazard control unit may insert a load-use bubble. This only delays the pipeline and has no architectural side effect ([decode-stage section 6](decode-stage.md#6-reset-cancellation-and-exceptional-conditions)). |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_control_unit.py` and cocotb module `tb/testcases/control_unit_cocotb.py`.
- It drives the 38 operation words and the 15 rejecting words.
- The exhaustive sweep of CU-D2 has no test, because the Owner deferred it.
- A pass shows only the checked vectors, not decode integration, hazards or whole-core behavior.
- The word `FENCE.I` cannot fail the enable check, because FENCE and an unsupported word give the same three enables.
  - So L9 rejection is not observable at the ports, and the row stays for completeness of CU-D3.
- The legality table accepts 5901 of the 2^17 combinations of `instruction[31:25]`, `instruction[14:12]` and `instruction[6:0]`.
  - The count is 3 x 1024 (LUI, AUIPC, JAL), 128 (JALR), 768 (BRANCH), 640 (LOAD), 384 (STORE), 771 (OP-IMM), 10 (OP) and 128 (MISC-MEM).

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Guarded enables (CU-D2) | All 2^17 combinations of `instruction[31:25]`, `instruction[14:12]` and `instruction[6:0]`; the other 15 bits at any fixed value | `reg_write`, `mem_en` and `control_flow` equal the class table when the word passes the legality table, and 0, 0 and `CF_NONE` otherwise |
| Oracle source (CU-D2) | The expected values come from a predicate written from the legality table and the class table | The predicate does not read the DUT or its RTL |
| Binding outputs (CU-D2) | For each of the 38 operations, one word built from the legality and funct tables | Every output that is not `any` equals the class and funct tables |
| Accepting words (CU-D3) | The 10 words of Accepting words | The rows of the class and funct tables named in the Expected cell |
| Rejecting words (CU-D3) | The 15 words of Rejecting words | `reg_write` 0, `mem_en` 0, `control_flow` `CF_NONE`; no other output is an oracle |
| Unsupported words and `any` cells | Any unsupported word, and any `any` cell of a supported operation | Never an oracle for a non-guarded output |

### Accepting words

| Class | Assembly | `instruction` | Expected |
| --- | --- | --- | --- |
| LUI | `lui x5, 0x55555` | `0x5555_52B7` | Class table, row LUI |
| AUIPC | `auipc x3, 0x12345` | `0x1234_5197` | Class table, row AUIPC |
| JAL | `jal x1, .+16` | `0x0100_00EF` | Class table, row JAL |
| JALR | `jalr x1, 8(x2)` | `0x0081_00E7` | Class table, row JALR |
| BRANCH | `bltu x1, x2, .+16` | `0x0020_E863` | Class table, row BRANCH; `branch_kind` table, row BLTU |
| LOAD | `lbu x5, 8(x2)` | `0x0081_4283` | Class table, row LOAD; `mem_type` table, row LBU |
| STORE | `sh x6, 12(x2)` | `0x0061_1623` | Class table, row STORE; `mem_type` table, row SH |
| OP-IMM | `srai x1, x2, 3` | `0x4031_5093` | Class table, row OP-IMM; `alu_op` table, row SRAI |
| OP | `sub x3, x4, x5` | `0x4052_01B3` | Class table, row OP; `alu_op` table, row SUB |
| MISC-MEM | `fence` | `0x0FF0_000F` | Class table, row MISC-MEM |

### Rejecting words

| Rule | Assembly | `instruction` | Failing field |
| --- | --- | --- | --- |
| L1 | `ADDI x1, x2, 1365`, low bits changed | `0x5551_0092` | `instruction[1:0]` is `10` |
| L2 | `ECALL` | `0x0000_0073` | `instruction[6:2]` is `11100` |
| L2 | `AMOSWAP.W x3, x5, (x4)` | `0x0852_21AF` | `instruction[6:2]` is `01011` |
| L3 | `JALR x1, 8(x2)`, `funct3` changed | `0x0081_10E7` | `funct3` is `001` |
| L4 | none, a reserved BRANCH encoding | `0x0020_A863` | `funct3` is `010` |
| L4 | none, a reserved BRANCH encoding | `0x0020_B863` | `funct3` is `011` |
| L5 | `LD x5, 8(x2)` (RV64) | `0x0081_3283` | `funct3` is `011` |
| L5 | `LWU x5, 8(x2)` (RV64) | `0x0081_6283` | `funct3` is `110` |
| L6 | `SD x6, 12(x2)` (RV64) | `0x0061_3623` | `funct3` is `011` |
| L6 | none, a reserved STORE encoding | `0x0061_4623` | `funct3` is `100` |
| L7 | `SLLI x1, x2, 32` (RV64) | `0x0201_1093` | `funct3` is `001`, `funct7` is `0000001` |
| L7 | `SRLI x1, x2, 32` (RV64) | `0x0201_5093` | `funct3` is `101`, `funct7` is `0000001` |
| L8 | `MUL x3, x4, x5` | `0x0252_01B3` | `funct7` is `0000001`, `funct3` is `000` |
| L8 | none, a reserved OP encoding | `0x4052_11B3` | `funct7` is `0100000`, `funct3` is `001` |
| L9 | `FENCE.I` | `0x0000_100F` | `funct3` is `001` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| CU-D1 | The legality table L1 to L9 decides recognition, with its list of unchecked fields. | Recognition uses the complete RV32I encoding ([decode-stage D7](decode-stage.md#9-rationale-and-open-decisions)). |
| CU-D2 | Verification requires the exhaustive 2^17 check of the three guarded enables against a predicate written from the legality table. It also requires a directed check of every binding output of the 38 operations. Unsupported words and `any` cells are never an oracle for a non-guarded output. | The guard is the only safety behavior, and the oracle must be independent of the RTL. |
| CU-D3 | Section 9 gives one accepting word per opcode class (10) and one rejecting near-miss word per rule or sub-rule (15). | The stimulus and the expected values stay visible. |
| CU-D4 | FENCE decodes `alu_op` ADD. `alu_src_a`, `alu_src_b`, `result_src`, `wb_src`, `branch_kind`, `mem_write` and `mem_type` are `any` for FENCE. | The ALU live-control rule ([alu.md section 4](alu.md#4-input-validity-and-exceptional-conditions)) requires a defined operation for every live instruction, and ADD is the fixed choice. |

- History: 2026-10-29 the Owner stated the legality table; 2026-10-30 the Owner stated C1 to C4 and accepted the spec; 2026-11-07 rewritten in the block spec format, with IDs renumbered, the 38-row table split and the vectors moved to section 9.

| Old ID | New ID | Status |
| --- | --- | --- |
| L1 to L9 (the table decision) | CU-D1 | Kept; L1 to L9 stay as the row labels of the legality table, because the RTL and the tests cite them |
| C1 | CU-D2 | Kept |
| C2 | CU-D3 | Kept; the expected vector now sits in the section 6 tables |
| C3 | none | Retired: it records who writes the RTL, not a design choice |
| C4 | CU-D4 | Kept |
| Design revision CU D2 | none | Retired: History carries the dates |

- Length: 7 pages, above the 3-5 limit, because the spec holds a 14-column class table, 33 funct rows and 25 test words.
- Open items: none.
