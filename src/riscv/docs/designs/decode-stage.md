# Decode Stage

| Field | Value |
| --- | --- |
| Description | Structural ID stage: register file, immediate generator and control unit driven from one instruction word. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/decode_stage.sv`, module `decode_stage`, instance name `id_stage` |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md) (ID decode contract, instruction semantic table, ID/EX boundary, register-file timing and WB-to-ID bypass, reset architecture); [Hazard control unit](hazard-control-unit.md); [Writeback stage](writeback-stage.md); the three leaves ([register file](register-file.md), [immediate generator](immediate-generator.md), [control unit](control-unit.md)) |

## 1. Overview

- `decode_stage` is the BASE ID stage.
- From the IF/ID `instruction`, it produces the register identifiers and values, the canonical immediate, the semantic control and the source-use qualifiers.
- It is the sole owner of instruction decode, and no other stage re-decodes ([BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract)).
- For each of the 38 supported operations, the outputs equal the BASE semantic tables. For any other encoding, the register write, the memory access and the control flow are inactive (section 6).
- It composes the three leaves of section 4 and has one function of its own, the extraction of `rs1_id`, `rs2_id` and `rd` from `instruction`.
- It has no reset port, because the register file is not reset ([BASE reset architecture](5-stage-baseline-core.md#reset-architecture)) and the other two leaves are combinational ([ID-D3](#10-decisions-and-open-items)).
- It does no hazard detection, because load-use affects IF and ID and belongs to the [hazard control unit](hazard-control-unit.md). The stage exports `rs1_id`, `rs2_id`, `rs1_used` and `rs2_used` for it ([ID-D2](#10-decisions-and-open-items)).
- It holds no pipeline storage, because IF/ID and ID/EX, with their valid, stall, flush and reset, belong to the core ([pipeline-register.md](pipeline-register.md)).
- It has no trap, illegal-instruction flag, error port or recovery for an unsupported encoding ([ID-D4](#10-decisions-and-open-items)).
- CSR, CI, IRQ and other extension decode are outside it, and it decodes the BASE profile only.

## 2. Block Design

```text
                                                clk <- core clock
                                                       |
                                           +-----------------------+
instruction <- IF/ID register              |                       | -> rs1_id, rs2_id (ID/EX register, hazard_control_unit)
rf_write_fire <- writeback_stage           |                       | -> rd, rs1_value, rs2_value, imm (ID/EX register)
wb_rd <- MEM/WB register                   |     decode_stage      | -> reg_write, mem_en, control_flow, mem_write, mem_type, wb_src (ID/EX register)
wb_data <- writeback_stage                 |                       | -> alu_op, alu_src_a, alu_src_b, branch_kind, result_src (ID/EX register)
                                           |                       | -> rs1_used, rs2_used (hazard_control_unit)
                                           +-----------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | Core clock | Clock of the register-file write. |
| `instruction` | Input | `INSTR_WIDTH` | IF/ID register | The IF/ID instruction word. |
| `rf_write_fire` | Input | 1 | `writeback_stage` | Permission to write `wb_rd` with `wb_data` at the rising edge. |
| `wb_rd` | Input | 5 | MEM/WB register | Destination register of the WB instruction. |
| `wb_data` | Input | `DATA_WIDTH` | `writeback_stage` | Selected writeback value. |
| `rs1_id` | Output | 5 | ID/EX register, `hazard_control_unit` | Source register identifier `rs1`, the raw field. |
| `rs2_id` | Output | 5 | ID/EX register, `hazard_control_unit` | Source register identifier `rs2`, the raw field. |
| `rd` | Output | 5 | ID/EX register | Destination register identifier, the raw field. It names a destination only when `reg_write` is 1. |
| `rs1_value` | Output | `DATA_WIDTH` | ID/EX register | Register value after the WB-to-ID bypass. |
| `rs2_value` | Output | `DATA_WIDTH` | ID/EX register | Register value after the WB-to-ID bypass. |
| `rs1_used` | Output | 1 | `hazard_control_unit` | The instruction semantically consumes `rs1`. |
| `rs2_used` | Output | 1 | `hazard_control_unit` | The instruction semantically consumes `rs2`. |
| `imm` | Output | `DATA_WIDTH` | ID/EX register | Canonical immediate. |
| `reg_write` | Output | 1 | ID/EX register | Semantic register-write intent. |
| `mem_en` | Output | 1 | ID/EX register | Data-memory access intent. |
| `control_flow` | Output | `control_flow_t` (2) | ID/EX register | `CF_NONE`, `CF_BRANCH`, `CF_JAL` or `CF_JALR`. |
| `mem_write` | Output | 1 | ID/EX register | `0` for a load, `1` for a store. |
| `mem_type` | Output | `mem_type_t` (3) | ID/EX register | Access width and load signedness. |
| `wb_src` | Output | 1 | ID/EX register | `0` selects the EX result, `1` the load result. |
| `alu_op` | Output | `alu_op_t` (4) | ID/EX register | ALU operation. |
| `alu_src_a` | Output | `alu_src_a_t` (2) | ID/EX register | Source of the first ALU operand. |
| `alu_src_b` | Output | `alu_src_b_t` (1) | ID/EX register | Source of the second ALU operand. |
| `branch_kind` | Output | `branch_kind_t` (3) | ID/EX register | Branch comparison. |
| `result_src` | Output | `result_src_t` (1) | ID/EX register | ALU result or link selection. |

- The ports are individual signals, and the stage defines no packed payload type.
- The enum types come from `riscv_pkg`.
- [memory-stage.md](memory-stage.md) owns `mem_type_t`, and [alu.md](alu.md) owns the ALU operation table.
- [control-unit.md](control-unit.md#class-table) owns the value of every control output per class.
- Each port name equals the name of the port it connects to in [execute-stage.md](execute-stage.md#3-interface), [memory-stage.md](memory-stage.md) and [writeback-stage.md](writeback-stage.md).
- `wb_src` stays a one-bit signal, because no shared enum exists.
- `rs1_used` and `rs2_used` qualify the sources for hazard detection and are not ID/EX state ([BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract)).
- Neither `pc` nor the IF/ID valid is a port ([ID-D8](#10-decisions-and-open-items)).
- The stage has no parameter, and the supported configuration is `DATA_WIDTH` 32.

### Width domains

| Domain | Package constant | Signals |
| --- | --- | --- |
| Instruction word | `INSTR_WIDTH` | `instruction` |
| Register and arithmetic datapath | `DATA_WIDTH` | `imm`, `rs1_value`, `rs2_value`, `wb_data` |

- `INSTR_WIDTH` is a separate domain from `DATA_WIDTH`, and its value is fixed in [ID-D11](#10-decisions-and-open-items).
- The rebuild of `imm` from `instruction` is the only width crossing, and BASE and [immediate-generator.md](immediate-generator.md) own its rules.

## 4. Internal Structure

| Module | Instance | File | Spec |
| --- | --- | --- | --- |
| `decode_stage` | `id_stage` | `rtl/decode_stage.sv` | This spec |
| `register_file` | `id_register_file` | `rtl/register_file.sv` | [register-file.md](register-file.md) |
| `immediate_generator` | `id_immediate_generator` | `rtl/immediate_generator.sv` | [immediate-generator.md](immediate-generator.md) |
| `control_unit` | `id_control_unit` | `rtl/control_unit.sv` | [control-unit.md](control-unit.md) |

### Leaf connections

| Instance | Takes | Drives |
| --- | --- | --- |
| `id_register_file` | `clk`, `rs1_id`, `rs2_id`, `rf_write_fire`, `wb_rd`, `wb_data` | `rs1_value`, `rs2_value` |
| `id_immediate_generator` | `instruction` | `imm` |
| `id_control_unit` | `instruction` | `rs1_used`, `rs2_used`, `alu_src_a`, `alu_src_b`, `alu_op`, `branch_kind`, `result_src`, `control_flow`, `mem_type`, `mem_write`, `mem_en`, `reg_write`, `wb_src` |

- The stage has no internal net, because every leaf port connects to the stage port of the same name. The outputs `rs1_id` and `rs2_id` also feed `id_register_file`.
- The stage instantiates the three leaves, one each. Its only other logic is the extraction of `rs1_id`, `rs2_id` and `rd`, which is wiring and not a leaf ([ID-D1](#10-decisions-and-open-items)).

## 5. State

- None, because the stage owns no register, pipeline entry, valid bit or control state.
- The only storage in the hierarchy is the register file, and [register-file.md](register-file.md) and the [BASE reset architecture](5-stage-baseline-core.md#reset-architecture) own its state, update and reset.
- The core owns IF/ID and ID/EX and decides whether the combinational outputs are captured.

## 6. Behavior

### Output table

| Output | Supported operation | Unsupported word | Rule owner |
| --- | --- | --- | --- |
| `rs1_id` | `instruction` bits 19 to 15 | Same | This spec |
| `rs2_id` | `instruction` bits 24 to 20 | Same | This spec |
| `rd` | `instruction` bits 11 to 7 | Same | This spec |
| `rs1_value`, `rs2_value` | The register file read with the WB-to-ID bypass | Same | [register-file.md](register-file.md), [BASE register-file timing](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass) |
| `imm` | The canonical immediate of the class, and any for a class without one | Any | [immediate-generator.md](immediate-generator.md) |
| `reg_write`, `mem_en`, `control_flow` | The BASE semantic values | 0, 0 and `CF_NONE` | [control-unit.md](control-unit.md#class-table), [BASE instruction semantic table](5-stage-baseline-core.md#instruction-semantic-table) |
| `rs1_used`, `rs2_used`, `mem_write`, `mem_type`, `wb_src`, `alu_op`, `alu_src_a`, `alu_src_b`, `branch_kind`, `result_src` | The BASE values, and any for a cell that the class table marks any | Any | [control-unit.md](control-unit.md#class-table), [BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract), [execute-stage.md](execute-stage.md#class-to-operand-table) |

- A word is supported when the control unit recognizes it from its complete RV32I encoding, and the [legality table](control-unit.md#legality-table) decides it ([ID-D7](#10-decisions-and-open-items)).
- Only the three forced outputs can start a register write, a memory access or a redirect, so forcing them blocks every side effect ([ID-D5](#10-decisions-and-open-items)).
- A forced word is not reported, replaced or retired differently, so it travels through EX, MEM and WB with inactive enables.
- FENCE is a live non-writing instruction: `reg_write` 0, `mem_en` 0, `control_flow` `CF_NONE` and `alu_op` ADD ([CU-D4](control-unit.md#10-decisions-and-open-items)).
- Every value that BASE assigns to a supported instruction binds, for example `wb_src` 0 for a store and `rs1_used`, `rs2_used` of every class ([ID-D5](#10-decisions-and-open-items)).
- Any means no required value, and verification must not use it as an oracle.
  - It applies to the non-enable outputs of an unsupported word.
  - It applies to fields that BASE leaves unspecified for a class, such as `mem_write` and `mem_type` of a non-memory instruction.
  - It also covers `wb_src` of a branch and FENCE, and `imm` of a class without an immediate.
- `rs1_id`, `rs2_id` and `rd` are never any, because they are raw extraction.
- An any output may carry a reserved `alu_op` or operand-select code, and the stage adds no logic to avoid it ([ID-D10](#10-decisions-and-open-items)). The EX leaf specs own the fallback of those codes.

## 7. Timing and Control

- Every output except the register-file write is a combinational function of `instruction` and, for `rs1_value` and `rs2_value`, of `rf_write_fire`, `wb_rd` and `wb_data`.
- The only clocked behavior is the register-file write at the rising edge of `clk`.
- The stage has no handshake, valid output or stall input, and the core decides whether the outputs are captured.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the stage has no reset port and no state of its own. The [BASE reset architecture](5-stage-baseline-core.md#reset-architecture) keeps an invalid stage from writing the register file. |
| Stall | None: the stage has no stall input. A held IF/ID presents the same `instruction`, so every output stays stable. The hazard control unit holds IF/ID for load-use ([ID-D2](#10-decisions-and-open-items)). |
| Flush | None: the stage has no flush input. The core flushes and bubbles IF/ID and ID/EX outside the stage. |

### Trace

- Pre-state: `x7` holds V, written before C1. `instruction` reads `x7` as `rs1`, so `rs1_id` is 7 in every cycle. V and D are different values.

| Cycle | Inputs | `rs1_value` | `x7` after the edge that ends the cycle |
| --- | --- | --- | --- |
| C1 | `rf_write_fire` 0, `wb_rd` 7, `wb_data` D | V | V |
| C2 | `rf_write_fire` 1, `wb_rd` 7, `wb_data` D | D | D |
| C3 | `rf_write_fire` 0, `wb_rd` 7, `wb_data` any | D | D |

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment, as in each leaf spec | X and Z behavior is unspecified and untested. |
| The core keeps an invalid IF/ID payload from taking effect: it discards the decode through the ID/EX valid, which it takes from the IF/ID valid | The core ([ID-D8](#10-decisions-and-open-items)) | An invalid payload could take effect. The guard of section 6 acts on the encoding alone and does not replace this gating. |
| The hazard control unit qualifies `rs1_used` and `rs2_used` with the IF/ID valid | [hazard-control-unit.md](hazard-control-unit.md#3-interface) | A bubble could follow an invalid entry, and the pipeline would only be delayed. |
| `wb_data` and `rf_write_fire` do not depend combinationally on any output of this stage | `writeback_stage`, which drives them from the registered MEM/WB entry through its combinational selection | The core would contain a combinational loop. |
| EX handles a reserved `alu_op` or operand-select code under its leaf contracts, and its checkers apply to supported instructions only | EX ([alu.md](alu.md), [operand-mux.md](operand-mux.md), [EX-D10](execute-stage.md#10-decisions-and-open-items)) | A reserved code of an unsupported word could raise a false checker error. |

| Case | Inputs | Result |
| --- | --- | --- |
| Unsupported word behind a load | An unsupported word in ID, with `rs1_used` and `rs2_used` any, and a load in EX | The hazard control unit may insert a load-use bubble. This only delays the pipeline and creates no architectural side effect, so the unit must not rely on `rs1_used` or `rs2_used` for an unsupported encoding. |
| Destination x0 | A register-writing instruction with `rd` 0 | `reg_write` stays 1, and `rf_write_fire` suppresses the physical write ([BASE](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass)). |

## 9. Verification

- No test of `decode_stage` exists in `tb/`.
- The leaves have directed tests with their own runners: `tb/runners/test_register_file.py`, `tb/runners/test_immediate_generator.py` and `tb/runners/test_control_unit.py`. A leaf pass shows only the vectors of that leaf, so it makes no claim about the composition.
- Expected values come from the BASE tables and the decisions of section 10, never from the DUT. The [legality table](control-unit.md#legality-table) is the oracle for recognition.
- A pass of the planned checks shows only the stated vectors, not load-use, ID/EX storage, redirect, flush, timing or whole-core behavior.

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Hierarchy ([ID-D1](#10-decisions-and-open-items)) | Verilator elaboration of `decode_stage` | Exactly three leaves with the instance names of section 4, and no other instance |
| Raw extraction | Any encoding, supported or not | `rs1_id`, `rs2_id` and `rd` equal the instruction bits of the Output table |
| BASE decode | Each of the 38 operations, with every register-field combination that matters, including `rd` x0 | Every output that is not any equals the BASE tables and the [class table](control-unit.md#class-table) |
| Guard ([ID-D4](#10-decisions-and-open-items), [ID-D5](#10-decisions-and-open-items)) | Unsupported words: all-zero, `0xFFFFFFFF`, `ECALL`, a CSR word, `FENCE.I`, `MUL`, `LD` (LOAD `funct3` 011), BRANCH `funct3` 010, `SLLI` with a nonzero `funct7` | `reg_write` 0, `mem_en` 0 and `control_flow` `CF_NONE`. No test uses `imm`, `rs1_used`, `rs2_used`, `wb_src`, `mem_write`, `mem_type`, `alu_op`, `alu_src_a`, `alu_src_b`, `branch_kind` or `result_src` as an oracle. |
| Immediate | One word per format | Canonical `imm` per BASE ([immediate-generator.md](immediate-generator.md)) |
| Register file through the stage | Write then read; same-cycle bypass on each port independently; `rf_write_fire` 0 with a matching `wb_rd`; `x0` | BASE priority; `x0` reads zero; no bypass without `rf_write_fire` |
| Read before any write | A read of a register never written | Value unspecified ([register-file.md](register-file.md)), not an oracle |
| Port contract | Elaborate with the EX, MEM and WB stage ports | Names and types connect without conversion |

### Decode vectors

| Instruction | Assembly | Class | Expected outputs |
| --- | --- | --- | --- |
| `0x0081_2283` | `lw x5, 8(x2)` | Load | `rs1_id=2`, `rd=5`, `rs1_used=1`, `rs2_used=0`, `imm=8`, `reg_write=1`, `mem_en=1`, `mem_write=0`, `mem_type=MEM_WORD`, `wb_src=1`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_RS1`, `alu_src_b=ALU_B_IMM`, `control_flow=CF_NONE` |
| `0x0061_2623` | `sw x6, 12(x2)` | Store | `rs1_used=1`, `rs2_used=1`, `imm=12`, `reg_write=0`, `mem_en=1`, `mem_write=1`, `mem_type=MEM_WORD`, `wb_src=0`, `control_flow=CF_NONE` |
| `0x0100_00EF` | `jal x1, .+16` | Jump | `rs1_used=0`, `rs2_used=0`, `imm=16`, `reg_write=1`, `mem_en=0`, `control_flow=CF_JAL`, `result_src=RESULT_PC_PLUS_4`, `wb_src=0` |
| `0x0000_0073` | `ecall` | Unsupported | `reg_write=0`, `mem_en=0`, `control_flow=CF_NONE`, `rs1_id=0`, `rs2_id=0`, `rd=0` |
| `0x0252_01B3` | `mul x3, x4, x5` | Unsupported | `reg_write=0`, `mem_en=0`, `control_flow=CF_NONE`, `rs1_id=4`, `rs2_id=5`, `rd=3` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| ID-D1 | `decode_stage` contains exactly three leaves, and the field extraction is stage wiring and not a leaf. Module and file names are functional, with no `riscv_` prefix, and instance names take the stage prefix `id_`. | The hierarchy stays visible as in EX, and the `id_` prefix follows the `ex_` convention ([EX-D1](execute-stage.md#10-decisions-and-open-items)). |
| ID-D2 | ID has no load-use detector. It exports `rs1_id`, `rs2_id`, `rs1_used` and `rs2_used`. | Load-use affects IF and ID, so the [hazard control unit](hazard-control-unit.md) owns it. |
| ID-D3 | `register_file` sits inside `decode_stage`. The stage ports are `clk` and the register-file write inputs, with no `rst_n`. The write destination input is `wb_rd`, the name of the EX producer port. | The hierarchy is logical, the register file has no reset, and `wb_rd` is the same net as the EX producer port. |
| ID-D4 | An unsupported encoding stays unsupported: no trap, flag or port. | BASE has no illegal-instruction handling. |
| ID-D5 | The stage forces `reg_write`, `mem_en` and `control_flow` inactive for an unsupported encoding. Every value that BASE assigns to a supported instruction binds, and the other outputs are any where BASE assigns nothing. | The forcing blocks side effects with the minimum logic, and BASE stays the single source for instruction semantics, with no BASE edit. |
| ID-D6 | ID is safe with no added logic, or the minimum needed for safety. The guard of section 6 is that minimum, and ID adds no default vector, legality flag or output cleanup. | None recorded. |
| ID-D7 | The control unit recognizes an operation only by its complete RV32I encoding, and the exact table is the [legality table](control-unit.md#legality-table). | None recorded. |
| ID-D8 | Neither `pc` nor the IF/ID valid is a port of `decode_stage`. | No block inside ID consumes them. The register-file write is authorized by `rf_write_fire`. An invalid decode is discarded through the ID/EX valid, so gating the outputs with valid adds logic without a safety gain (ID-D6). |
| ID-D9 | `rd`, `reg_write`, `mem_en`, `mem_write`, `mem_type` and `wb_src` are outputs of `decode_stage`. | They originate in ID. |
| ID-D10 | A reserved `alu_op` or operand-select code may appear for an unsupported encoding, and the stage adds no logic to avoid it. EX checkers apply to supported instructions only. | ID-D6 applies, and an unsupported encoding is outside BASE. |
| ID-D11 | `riscv_pkg` holds `INSTR_WIDTH`, 32, in the style of `DATA_WIDTH` and `ADDR_WIDTH`, and `instruction` has that width. `INSTR_WIDTH` names the width of the 32-bit base encoding (`IALIGN=32`), not ILEN. It is not a configuration point, because the bit positions in [immediate-generator.md](immediate-generator.md) fix the value at 32. | The names stay consistent, and the instruction and data widths stay separate domains. |

- History: 2026-10-29 the Owner stated D1 to D7 and the resolutions O1 to O7 and accepted the spec at composition level. The same day the Owner amended O7 to O7-R (`INSTR_WIDTH`), under the revision label ID D2.
- 2026-11-07 rewritten in the block spec format, with IDs renumbered. The "future Hazard Control Unit" wording became a link, and the readiness remarks went.

| Old ID | New ID | Status |
| --- | --- | --- |
| D1 | ID-D1 | Kept; takes O1 |
| D2 | ID-D2 | Kept |
| D3 | ID-D3 | Kept; takes O3 |
| D4 | ID-D4 | Kept |
| D5 | ID-D5 | Kept; takes O5 |
| D6 | ID-D6 | Kept |
| D7 | ID-D7 | Kept |
| O1 | ID-D1 | Merged: the instance names are part of the hierarchy decision |
| O2 | ID-D8 | Kept; its fact that the hazard control unit qualifies `rs1_used` and `rs2_used` with the IF/ID valid is an assumption in section 8 |
| O3 | ID-D3 | Merged: the `wb_rd` name belongs with the register file placement |
| O4 | ID-D9 | Kept |
| O5 | ID-D5 | Merged: it refines the don't-care rule of D5 |
| O6 | ID-D10 | Kept |
| O7 | none | Retired: O7-R supersedes it |
| O7-R | ID-D11 | Kept |
| ID D2 (revision label, 2026-10-29) | none | Retired as a label: History carries the date. It is not the decision D2. No spec cites it. |

- Length: 7 pages, above the 2-4 limit, because the spec has 24 ports, 8 check rows, 11 decisions and a 16-row map.
- Open items: none.
