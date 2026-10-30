# Control Unit — Block Design

**Status:** Accepted by Việt on 2026-10-30
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Design revision:** CU D2 / 2026-10-30 (draft; D2 adds C4: `FENCE` `alu_op`).
**Parent contract:** [Decode stage](decode-stage.md) (sections 2, 3, 5, 6; D4–D7, O5, O6, O7-R),
[BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract),
[instruction semantic table](5-stage-baseline-core.md#instruction-semantic-table) and
[EX operand mux, section 4.2](execute-stage.md#42-operand-mux).
**RTL mapping:** Planned module `control_unit` in `control_unit.sv`, instance
`id_control_unit` in `decode_stage`; no RTL exists. The shared types used below
exist in `rtl/riscv_pkg.sv`. This document is neither implementation nor
verification evidence.

## 1. Purpose and boundary

`control_unit` recognizes the 38 supported RV32I operations from the IF/ID
`instruction` and produces the semantic control and source-use qualifiers that
`decode_stage` sends to the core, EX, MEM and WB. Observable success criterion:
for each supported operation the outputs equal the per-operation table in
section 5; for any other word exactly `reg_write=0`, `mem_en=0` and
`control_flow=CF_NONE`.

Non-goals:

- No clock, reset or state; the block is purely combinational.
- No trap, error flag, legality output or extra port (decode-stage.md D4).
- No register-field extraction, register file or immediate: `rs1_id`, `rs2_id`
  and `rd` are wrapper wiring and `imm` belongs to
  [immediate-generator.md](immediate-generator.md).
- No hazard detection; `rs1_used` and `rs2_used` only qualify the sources for the
  future Hazard Control Unit.

Inherited by reference, not restated: the leaf set and instance name
(decode-stage.md section 3), the side-effect guard (D5), the don't-care rule
(D5, O5, O6), the safe-without-added-logic principle (D6) and recognition by the
complete RV32I encoding (D7). BASE owns the `rs*_used`, memory-intent,
`reg_write`, `wb_src` and redirect values; EX section 4.2 owns operand sources and
the ALU operation per class. Local refinements are the legality table L1–L9 and
C1–C4 (section 9).

## 2. Interface contract

### Clock, reset and configuration

Clock and reset do not apply. No parameters.

### Ports and payloads

Port names and types equal the `decode_stage` port table, so `decode_stage` only
wires them (decode-stage.md section 2). There is 1 input and 13 outputs.

| Port | Direction | Type / width | Meaning | Valid when |
| --- | --- | --- | --- | --- |
| `instruction` | Input | `logic [INSTR_WIDTH-1:0]` | IF/ID instruction word (`IALIGN=32`, decode-stage.md O7-R) | Any value, any cycle |
| `rs1_used`, `rs2_used` | Output | 1-bit `logic` each | Source is semantically consumed (BASE ID decode contract) | Supported operations; don't care otherwise |
| `reg_write` | Output | 1-bit `logic` | Semantic register-write intent | Always defined; `0` for an unsupported word |
| `mem_en` | Output | 1-bit `logic` | Data-memory access intent | Always defined; `0` for an unsupported word |
| `control_flow` | Output | `control_flow_t` | `CF_NONE`, `CF_BRANCH`, `CF_JAL` or `CF_JALR` | Always defined; `CF_NONE` for an unsupported word |
| `mem_write` | Output | 1-bit `logic` | `0` load, `1` store | Loads and stores; don't care otherwise |
| `mem_type` | Output | `mem_type_t` | Access width and load signedness | Loads and stores; don't care otherwise |
| `wb_src` | Output | 1-bit `logic` | `0` = EX result, `1` = load result | Every supported operation except branches and `FENCE`; don't care otherwise |
| `alu_op` | Output | `alu_op_t` | ALU operation | Every supported operation (`FENCE` decodes `ALU_ADD`, C4); don't care for an unsupported word |
| `alu_src_a` | Output | `alu_src_a_t` | First ALU operand source | Supported operations except `FENCE`; don't care otherwise |
| `alu_src_b` | Output | `alu_src_b_t` | Second ALU operand source | Supported operations except `FENCE`; don't care otherwise |
| `branch_kind` | Output | `branch_kind_t` | Branch comparison | Conditional branches; don't care otherwise |
| `result_src` | Output | `result_src_t` | ALU result or link selection | Operations with an EX result (all but branches and `FENCE`) |

The one width domain is the instruction word, typed with
`riscv_pkg::INSTR_WIDTH`; no width conversion exists in this leaf. `opcode_t`
in the package may be used to name `instruction[6:2]`; that is coding style, not
a contract item. The guaranteed input domain contains only 0 and 1; X/Z behavior
is unspecified and untested, as in the accepted EX and WB contracts and
[register-file.md](register-file.md) (O1).

### Transfer and timing rules

Every output is a combinational function of `instruction` only. There is no
latency, handshake or dependence on IF/ID `valid`; invalid decode output is
discarded at ID/EX (decode-stage.md section 9, O2).

## 3. Internal organization

Two parts: a recognition predicate that decides whether `instruction` is one of
the 38 operations (section 5.1), and the control values selected by the class and
funct fields (section 5.3). The three guarded enables combine both; every other
output follows the control values alone. No arithmetic or state exists. Equivalent
coding styles are free.

## 4. State and ownership; instruction classes

Stateless; no state or ownership table applies. `instruction[6:2]` identifies
the class; the opcode names follow `opcode_t`.

| Class | `instruction[6:2]` | Operations |
| --- | --- | --- |
| LUI | `01101` | `LUI` |
| AUIPC | `00101` | `AUIPC` |
| JAL | `11011` | `JAL` |
| JALR | `11001` | `JALR` |
| BRANCH | `11000` | `BEQ`, `BNE`, `BLT`, `BGE`, `BLTU`, `BGEU` |
| LOAD | `00000` | `LB`, `LH`, `LW`, `LBU`, `LHU` |
| STORE | `01000` | `SB`, `SH`, `SW` |
| OP-IMM | `00100` | `ADDI`, `SLTI`, `SLTIU`, `XORI`, `ORI`, `ANDI`, `SLLI`, `SRLI`, `SRAI` |
| OP | `01100` | `ADD`, `SUB`, `SLL`, `SLT`, `SLTU`, `XOR`, `SRL`, `SRA`, `OR`, `AND` |
| MISC-MEM | `00011` | `FENCE` |

That is 4 (`LUI`, `AUIPC`, `JAL`, `JALR`) + 6 + 5 + 3 + 9 + 10 + 1 = 38 operations.

## 5. Behavioral rules

### 5.1 Recognition: the legality table

Write `i` for `instruction`. A word is a supported operation if and only if L1
holds, `i[6:2]` is one of the opcodes in L2 and the check of its class below
holds (L3–L9). Recognition uses the complete encoding (D7).

| Rule | Applies to | Accept condition |
| --- | --- | --- |
| L1 | Every word | `i[1:0] = 11` |
| L2 | Every word | `i[6:2]` is one of LUI `01101`, AUIPC `00101`, JAL `11011`, JALR `11001`, BRANCH `11000`, LOAD `00000`, STORE `01000`, OP-IMM `00100`, OP `01100`, MISC-MEM `00011`; SYSTEM and every other opcode are unsupported |
| L3 | JALR | `funct3 = 000` |
| L4 | BRANCH | `funct3` is not `010` and not `011` |
| L5 | LOAD | `funct3` in {`000`, `001`, `010`, `100`, `101`} |
| L6 | STORE | `funct3` in {`000`, `001`, `010`} |
| L7 | OP-IMM | `funct3 = 001` requires `i[31:25] = 0000000`; `funct3 = 101` requires `i[31:25]` in {`0000000`, `0100000`}; other `funct3` values have no further check |
| L8 | OP | `i[31:25] = 0000000` with any `funct3`; `i[31:25] = 0100000` only with `funct3 = 000` or `101`; every other `i[31:25]` is unsupported |
| L9 | MISC-MEM | `funct3 = 000` (`FENCE`); `FENCE.I` (`001`) is unsupported |

`LUI`, `AUIPC` and `JAL` have no field check beyond L1 and L2. Here `funct3` is
`i[14:12]` and `funct7` is `i[31:25]`.

**Not checked.** The `rd`, `rs1` and `rs2` fields; immediate bits other than the
`i[31:25]` bits used by L7; for `FENCE` the `fm`, `pred`, `succ`, `rs1` and `rd`
fields; HINT encodings; target and address alignment. `FENCE.TSO` and `PAUSE`
therefore decode as `FENCE`.

### 5.2 Guard rule

For a word that does not satisfy L1–L9 the outputs are exactly

| Output | Value |
| --- | --- |
| `reg_write` | `0` |
| `mem_en` | `0` |
| `control_flow` | `CF_NONE` |

No other output is assigned, and no trap, flag or port exists (D4, D5). For a
word that satisfies L1–L9, the three enables take the values in section 5.3.
This is side-effect blocking only (decode-stage.md section 5).

### 5.3 Control values for the 38 operations

`—` marks a don't care: BASE or EX section 4.2 assigns no value to that field
for the class, so the contract assigns none and verification must not use it
(O5). Every other cell is a value that binds. The columns `[6:2]`, `[14:12]`
and `[31:25]` are the bits that identify the operation after L1–L9 hold; `any`
means the bits do not identify it (they are register fields, immediate bits or
bits L1–L9 do not check for that operation).

| Operation | `[6:2]` | `[14:12]` | `[31:25]` | `rs1_used` | `rs2_used` | `reg_write` | `mem_en` | `control_flow` | `wb_src` | `alu_op` | `alu_src_a` | `alu_src_b` | `result_src` | `branch_kind` | `mem_write` | `mem_type` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LUI | `01101` | any | any | `0` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_ADD` | `ALU_A_ZERO` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| AUIPC | `00101` | any | any | `0` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| JAL | `11011` | any | any | `0` | `0` | `1` | `0` | `CF_JAL` | `0` | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | `RESULT_PC_PLUS_4` | — | — | — |
| JALR | `11001` | `000` | any | `1` | `0` | `1` | `0` | `CF_JALR` | `0` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_PC_PLUS_4` | — | — | — |
| BEQ | `11000` | `000` | any | `1` | `1` | `0` | `0` | `CF_BRANCH` | — | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | — | `BR_EQ` | — | — |
| BNE | `11000` | `001` | any | `1` | `1` | `0` | `0` | `CF_BRANCH` | — | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | — | `BR_NE` | — | — |
| BLT | `11000` | `100` | any | `1` | `1` | `0` | `0` | `CF_BRANCH` | — | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | — | `BR_LT_SIGNED` | — | — |
| BGE | `11000` | `101` | any | `1` | `1` | `0` | `0` | `CF_BRANCH` | — | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | — | `BR_GE_SIGNED` | — | — |
| BLTU | `11000` | `110` | any | `1` | `1` | `0` | `0` | `CF_BRANCH` | — | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | — | `BR_LT_UNSIGNED` | — | — |
| BGEU | `11000` | `111` | any | `1` | `1` | `0` | `0` | `CF_BRANCH` | — | `ALU_ADD` | `ALU_A_PC` | `ALU_B_IMM` | — | `BR_GE_UNSIGNED` | — | — |
| LB | `00000` | `000` | any | `1` | `0` | `1` | `1` | `CF_NONE` | `1` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | `0` | `MEM_BYTE` |
| LH | `00000` | `001` | any | `1` | `0` | `1` | `1` | `CF_NONE` | `1` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | `0` | `MEM_HALF` |
| LW | `00000` | `010` | any | `1` | `0` | `1` | `1` | `CF_NONE` | `1` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | `0` | `MEM_WORD` |
| LBU | `00000` | `100` | any | `1` | `0` | `1` | `1` | `CF_NONE` | `1` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | `0` | `MEM_BYTE_U` |
| LHU | `00000` | `101` | any | `1` | `0` | `1` | `1` | `CF_NONE` | `1` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | `0` | `MEM_HALF_U` |
| SB | `01000` | `000` | any | `1` | `1` | `0` | `1` | `CF_NONE` | `0` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | `1` | `MEM_BYTE` |
| SH | `01000` | `001` | any | `1` | `1` | `0` | `1` | `CF_NONE` | `0` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | `1` | `MEM_HALF` |
| SW | `01000` | `010` | any | `1` | `1` | `0` | `1` | `CF_NONE` | `0` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | `1` | `MEM_WORD` |
| ADDI | `00100` | `000` | any | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| SLTI | `00100` | `010` | any | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_SLT` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| SLTIU | `00100` | `011` | any | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_SLTU` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| XORI | `00100` | `100` | any | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_XOR` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| ORI | `00100` | `110` | any | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_OR` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| ANDI | `00100` | `111` | any | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_AND` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| SLLI | `00100` | `001` | `0000000` | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_SLL` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| SRLI | `00100` | `101` | `0000000` | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_SRL` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| SRAI | `00100` | `101` | `0100000` | `1` | `0` | `1` | `0` | `CF_NONE` | `0` | `ALU_SRA` | `ALU_A_RS1` | `ALU_B_IMM` | `RESULT_ALU` | — | — | — |
| ADD | `01100` | `000` | `0000000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_ADD` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| SUB | `01100` | `000` | `0100000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_SUB` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| SLL | `01100` | `001` | `0000000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_SLL` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| SLT | `01100` | `010` | `0000000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_SLT` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| SLTU | `01100` | `011` | `0000000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_SLTU` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| XOR | `01100` | `100` | `0000000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_XOR` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| SRL | `01100` | `101` | `0000000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_SRL` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| SRA | `01100` | `101` | `0100000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_SRA` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| OR | `01100` | `110` | `0000000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_OR` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| AND | `01100` | `111` | `0000000` | `1` | `1` | `1` | `0` | `CF_NONE` | `0` | `ALU_AND` | `ALU_A_RS1` | `ALU_B_RS2` | `RESULT_ALU` | — | — | — |
| FENCE | `00011` | `000` | any | `0` | `0` | `0` | `0` | `CF_NONE` | — | `ALU_ADD` | — | — | — | — | — | — |

Each operation matches exactly one row and each row matches a nonempty set of
accepted words (section 5.5).

**Where each value comes from.** The table values trace to these records;
no cell uses another source.

| Class | `rs1_used`, `rs2_used` | `reg_write`, `wb_src`, `control_flow` | `mem_en`, `mem_write`, `mem_type` | `alu_op`, `alu_src_a`, `alu_src_b` | `result_src` | `branch_kind` |
| --- | --- | --- | --- | --- | --- | --- |
| LUI, AUIPC | BASE ID decode contract, `rs*_used` table | BASE semantic table, upper-immediate and control-flow table; `wb_src=0` by "a register-writing non-load selects `ex_result`" (BASE, MEM/WB minimum semantic state) | `mem_en=0` (BASE memory table, non-memory) | EX 4.2 rows LUI (`ZERO`, `imm`, ADD) and AUIPC (`pc`, `imm`, ADD) | EX 4.6, ALU result | — |
| JAL, JALR | Same | Same; redirect semantics give `CF_JAL`, `CF_JALR` | `mem_en=0` | EX 4.2 rows JAL (`pc`, `imm`) and JALR (`fwd_rs1`, `imm`) | EX 4.6, link for JAL and JALR | — |
| BRANCH | Same | Same; `reg_write=0`, `CF_BRANCH`; `wb_src` is unspecified in BASE | `mem_en=0` | EX 4.2 row "Conditional branch" (`pc`, `imm`, ADD) | Unspecified: EX 4.6 gives branches no register result | BASE semantic table, one condition per branch (EX 4.4) |
| LOAD | Same | BASE memory table: `reg_write=1`, `wb_src=1`; no redirect | BASE ID decode contract memory-intent table | EX 4.2 row "Load/store" (`fwd_rs1`, `imm`, ADD) | EX 4.6, ALU result as effective address | — |
| STORE | Same | BASE memory table: `reg_write=0`, `wb_src=0`; no redirect | Same | EX 4.2 row "Load/store" | EX 4.6, ALU result as effective address | — |
| OP-IMM | Same | BASE semantic table, integer immediate operations and "all nineteen integer ALU instructions": `reg_write=1`, `wb_src=0` | `mem_en=0` | EX 4.2 row "Immediate arithmetic/logic" (`fwd_rs1`, `imm`); `alu_op` from the BASE immediate table | EX 4.6 | — |
| OP | Same | Same | `mem_en=0` | EX 4.2 row "Register arithmetic/logic" (`fwd_rs1`, `fwd_rs2`); `alu_op` from the BASE register table | EX 4.6 | — |
| MISC-MEM | Same (`FENCE`: both `0`) | BASE FENCE paragraph: no RF write, no redirect; `wb_src` unspecified | `mem_en=0` (no data request) | `alu_op`: C4 (`ALU_ADD`), required by the live-control rule in [alu.md section 4](alu.md#4-input-validity-and-exceptional-conditions); `alu_src_a`, `alu_src_b`: unspecified (EX 4.2: FENCE requires no meaningful ALU operands or result) | Unspecified (no register result) | — |

`alu_op` for a branch, `JAL` and `JALR` is ADD because the ALU computes the
redirect target or effective address (EX 4.2); it binds even though the class
has no register result. `alu_op` for `FENCE` is also ADD, but by C4, not by an EX
section 4.2 row.

### 5.4 Don't-care outputs

For a supported operation the `—` cells of section 5.3 are don't care, and for an
unsupported word every output except the three guarded enables is don't care
(D5, O5). Reserved enum codes may appear on don't-care outputs and no logic is
added to avoid them (O6, D6); EX and MEM checkers apply to supported operations
only (section 6).

### 5.5 Derived property: inputs that matter

Under L1–L9 and section 5.3, every binding output and the three guarded enables
depend only on `i[31:25]`, `i[14:12]` and `i[6:0]` (17 bits). No output depends
on `rd` (`i[11:7]`), `rs1` (`i[19:15]`) or `rs2` (`i[24:20]`). Reasons: L1–L9
read only those 17 bits; the control values in section 5.3 are indexed by
`i[6:2]` and `i[14:12]`; `i[31:25]` matters only through L7, L8 and through bit
30 for `SUB`/`SRA`/`SRAI`. For `LUI`, `AUIPC` and `JAL` neither `i[14:12]` nor
`i[31:25]` matters. Under the table and L1–L9, every accepted word matches
exactly one operation row. This is a statement about the table, not a
requirement on the implementation structure.

## 6. Reset, cancellation and exceptional conditions

- **Reset, flush, stall.** None apply; the block has no state or control input.
- **Unsupported words.** Out of the contract: no error output, default vector or
  legality flag exists (D6). The guard of section 5.2 is the only action.
- **Consumers of don't-care values.** No EX, MEM or WB consumer reads a cell
  marked `—` for that operation: a branch or `FENCE` has `reg_write=0`, so
  `wb_src` and `result_src` are not used for a register write; a non-memory
  instruction has `mem_en=0`, so `mem_write` and `mem_type` are not used;
  `FENCE` has no meaningful operands, so `alu_src_a` and `alu_src_b` are not
  used and the operand-mux checker exempts it. `FENCE` `alu_op` is not a `—`
  cell: it binds to `ALU_ADD` (C4), because the ALU live-control rule requires a
  defined operation for every live instruction. The EX ALU and operand-mux
  checkers apply to supported instructions only (decode-stage.md O6, as
  amended in execute-stage.md and alu.md); the EX branch-kind checker fires only
  for a valid conditional branch and the MEM memory-type checker only for a
  valid memory instruction (`mem_en=1`), and the guard keeps `mem_en=0` and
  `control_flow=CF_NONE` for an unsupported word, so no don't-care value can
  trigger them.
- **Hazard Control Unit.** `rs1_used` and `rs2_used` are don't care for an
  unsupported word; the consequence is in decode-stage.md section 6.
- **Out of scope.** X/Z input values (section 2).

## 7. Representative examples

Every row is a test vector. Words are 32-bit encodings in hex; the `rd`, `rs1`
and `rs2` fields are arbitrary and do not affect any output (section 5.5).

### Accepting words, one per opcode class

Expected outputs are the full binding vector of section 5.3; cells that section
5.3 marks don't care are listed as such and are not checked.

| Class | Assembly | `instruction` | Identifying bits | Expected outputs |
| --- | --- | --- | --- | --- |
| LUI | `lui x5, 0x55555` | `0x5555_52B7` | `[31:25]=0101010`, `[14:12]=101`, `[6:0]=0110111` | `rs1_used=0`, `rs2_used=0`, `reg_write=1`, `mem_en=0`, `control_flow=CF_NONE`, `wb_src=0`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_ZERO`, `alu_src_b=ALU_B_IMM`, `result_src=RESULT_ALU`; don't care: `branch_kind`, `mem_write`, `mem_type` |
| AUIPC | `auipc x3, 0x12345` | `0x1234_5197` | `[31:25]=0001001`, `[14:12]=101`, `[6:0]=0010111` | `rs1_used=0`, `rs2_used=0`, `reg_write=1`, `mem_en=0`, `control_flow=CF_NONE`, `wb_src=0`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_PC`, `alu_src_b=ALU_B_IMM`, `result_src=RESULT_ALU`; don't care: `branch_kind`, `mem_write`, `mem_type` |
| JAL | `jal x1, .+16` | `0x0100_00EF` | `[31:25]=0000000`, `[14:12]=000`, `[6:0]=1101111` | `rs1_used=0`, `rs2_used=0`, `reg_write=1`, `mem_en=0`, `control_flow=CF_JAL`, `wb_src=0`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_PC`, `alu_src_b=ALU_B_IMM`, `result_src=RESULT_PC_PLUS_4`; don't care: `branch_kind`, `mem_write`, `mem_type` |
| JALR | `jalr x1, 8(x2)` | `0x0081_00E7` | `[31:25]=0000000`, `[14:12]=000`, `[6:0]=1100111` | `rs1_used=1`, `rs2_used=0`, `reg_write=1`, `mem_en=0`, `control_flow=CF_JALR`, `wb_src=0`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_RS1`, `alu_src_b=ALU_B_IMM`, `result_src=RESULT_PC_PLUS_4`; don't care: `branch_kind`, `mem_write`, `mem_type` |
| BRANCH | `bltu x1, x2, .+16` | `0x0020_E863` | `[31:25]=0000000`, `[14:12]=110`, `[6:0]=1100011` | `rs1_used=1`, `rs2_used=1`, `reg_write=0`, `mem_en=0`, `control_flow=CF_BRANCH`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_PC`, `alu_src_b=ALU_B_IMM`, `branch_kind=BR_LT_UNSIGNED`; don't care: `wb_src`, `result_src`, `mem_write`, `mem_type` |
| LOAD | `lbu x5, 8(x2)` | `0x0081_4283` | `[31:25]=0000000`, `[14:12]=100`, `[6:0]=0000011` | `rs1_used=1`, `rs2_used=0`, `reg_write=1`, `mem_en=1`, `control_flow=CF_NONE`, `wb_src=1`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_RS1`, `alu_src_b=ALU_B_IMM`, `result_src=RESULT_ALU`, `mem_write=0`, `mem_type=MEM_BYTE_U`; don't care: `branch_kind` |
| STORE | `sh x6, 12(x2)` | `0x0061_1623` | `[31:25]=0000000`, `[14:12]=001`, `[6:0]=0100011` | `rs1_used=1`, `rs2_used=1`, `reg_write=0`, `mem_en=1`, `control_flow=CF_NONE`, `wb_src=0`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_RS1`, `alu_src_b=ALU_B_IMM`, `result_src=RESULT_ALU`, `mem_write=1`, `mem_type=MEM_HALF`; don't care: `branch_kind` |
| OP-IMM | `srai x1, x2, 3` | `0x4031_5093` | `[31:25]=0100000`, `[14:12]=101`, `[6:0]=0010011` | `rs1_used=1`, `rs2_used=0`, `reg_write=1`, `mem_en=0`, `control_flow=CF_NONE`, `wb_src=0`, `alu_op=ALU_SRA`, `alu_src_a=ALU_A_RS1`, `alu_src_b=ALU_B_IMM`, `result_src=RESULT_ALU`; don't care: `branch_kind`, `mem_write`, `mem_type` |
| OP | `sub x3, x4, x5` | `0x4052_01B3` | `[31:25]=0100000`, `[14:12]=000`, `[6:0]=0110011` | `rs1_used=1`, `rs2_used=1`, `reg_write=1`, `mem_en=0`, `control_flow=CF_NONE`, `wb_src=0`, `alu_op=ALU_SUB`, `alu_src_a=ALU_A_RS1`, `alu_src_b=ALU_B_RS2`, `result_src=RESULT_ALU`; don't care: `branch_kind`, `mem_write`, `mem_type` |
| MISC-MEM | `fence` | `0x0FF0_000F` | `[31:25]=0000111`, `[14:12]=000`, `[6:0]=0001111` | `rs1_used=0`, `rs2_used=0`, `reg_write=0`, `mem_en=0`, `control_flow=CF_NONE`, `alu_op=ALU_ADD`; don't care: `wb_src`, `alu_src_a`, `alu_src_b`, `result_src`, `branch_kind`, `mem_write`, `mem_type` |

### Rejecting near-miss words, one per rule

Each word is a supported-looking encoding that fails exactly the stated check.
Expected outputs for every row: `reg_write=0`, `mem_en=0`,
`control_flow=CF_NONE`; every other output is don't care and is not an oracle.

| Rule | `instruction` | Word | Failing field |
| --- | --- | --- | --- |
| L1 | `ADDI x1, x2, 1365` with `i[1:0]=10` | `0x5551_0092` | `i[1:0]=10` |
| L2 (SYSTEM) | `ECALL` | `0x0000_0073` | `i[6:2]=11100` |
| L2 (other opcode) | `AMOSWAP.W x3, x5, (x4)` | `0x0852_21AF` | `i[6:2]=01011` |
| L3 | `JALR x1, 8(x2)` with `funct3=001` | `0x0081_10E7` | `funct3=001` |
| L4 | BRANCH, `funct3=010` | `0x0020_A863` | `funct3=010` |
| L4 | BRANCH, `funct3=011` | `0x0020_B863` | `funct3=011` |
| L5 | `LD x5, 8(x2)` (RV64) | `0x0081_3283` | `funct3=011` |
| L5 | `LWU x5, 8(x2)` (RV64) | `0x0081_6283` | `funct3=110` |
| L6 | `SD x6, 12(x2)` (RV64) | `0x0061_3623` | `funct3=011` |
| L6 | STORE, `funct3=100` | `0x0061_4623` | `funct3=100` |
| L7 (`funct3=001`) | `SLLI x1, x2, 32` (RV64) | `0x0201_1093` | `funct3=001`, `i[31:25]=0000001` |
| L7 (`funct3=101`) | `SRLI x1, x2, 32` (RV64) | `0x0201_5093` | `funct3=101`, `i[31:25]=0000001` |
| L8 (other funct7) | `MUL x3, x4, x5` | `0x0252_01B3` | `i[31:25]=0000001`, `funct3=000` |
| L8 (`0100000`, wrong funct3) | OP, `funct7=0100000`, `funct3=001` | `0x4052_11B3` | `i[31:25]=0100000`, `funct3=001` |
| L9 | `FENCE.I` | `0x0000_100F` | `funct3=001` |

## 8. Verification obligations

Planned leaf-level checks; none exists yet. This section states obligations
only; the test plan belongs to the verification Station. A leaf pass proves only
these checks; it does not show decode integration, hazards or whole-core
behavior.

| Requirement | Scenario | Expected observation |
| --- | --- | --- |
| Guarded enables, C1 | Apply all 2^17 combinations of `instruction[31:25]`, `[14:12]` and `[6:0]`; hold the other 15 bits at any fixed value | For each combination, `reg_write`, `mem_en` and `control_flow` equal the per-class value of section 5.3 when the word passes L1–L9, and `0`, `0`, `CF_NONE` otherwise |
| Oracle source, C1 | The expected values are produced by a predicate written from the legality table of section 5.1 and the class values of section 5.3 | The predicate does not read the DUT or its RTL |
| Binding outputs, C1 | For each of the 38 operations, apply one word built from the section 5.3 identifying bits | Every output in the operation's row that is a value (not `—`) matches, including `rs1_used`, `rs2_used`, `alu_op`, `alu_src_a`, `alu_src_b`, `result_src`, `branch_kind`, `mem_write`, `mem_type` and `wb_src` |
| Section 7 words | The 10 accepting and 15 rejecting rows | As listed in section 7 |
| Unsupported words and `—` cells | Any unsupported word, and any `—` cell of a supported operation | Never an oracle for a non-guarded output |

For information, the section 5.1 predicate accepts 5901 of the 2^17 key
combinations: 3 x 1024 (LUI, AUIPC, JAL) + 128 (JALR) + 768 (BRANCH) + 640
(LOAD) + 384 (STORE) + 771 (OP-IMM) + 10 (OP) + 128 (MISC-MEM). The count comes
from the legality table, not from any implementation.

## 9. Rationale and open decisions

### Decisions recorded for acceptance

Stated by the Owner on 2026-10-29 (legality table) and 2026-10-30 (C1–C4). This
document becomes their record on acceptance.

| Id | Decision | Reason |
| --- | --- | --- |
| L1–L9 | The legality table of section 5.1, including the not-checked list | Recognition by complete encoding (D7); `FENCE.TSO` and `PAUSE` decode as `FENCE` |
| C1 | Section 8 requires the exhaustive 2^17 check of the guarded enables against a predicate written from the legality table, and a directed check of every binding output for each of the 38 operations; unsupported words are never an oracle for non-guarded outputs | The guard is the only safety behavior; independent oracle |
| C2 | Section 7 gives one accepting word per opcode class (10) with its binding vector and one rejecting near-miss word per rule or sub-rule | Visible stimulus and expected values |
| C3 | The RTL is written by Việt | Owner decision |
| C4 | `FENCE` decodes `alu_op = ALU_ADD`; `alu_src_a`, `alu_src_b`, `result_src`, `wb_src`, `branch_kind`, `mem_write` and `mem_type` stay don't care for `FENCE` | The accepted ALU live-control rule (alu.md section 4) requires a defined operation for every live instruction; ADD is the fixed choice |

D6 (safe, no logic beyond what safety requires) is carried from decode-stage.md.

No material open question remains within this document's boundary.

Independent work that can proceed: integration of `decode_stage`. Blocked until
acceptance: `control_unit` RTL and leaf tests. A pass of the planned checks would
not establish integration with `decode_stage`, the core or timing.
