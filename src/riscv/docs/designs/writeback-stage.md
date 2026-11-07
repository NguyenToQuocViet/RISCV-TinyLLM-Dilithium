# Writeback Stage

| Field | Value |
| --- | --- |
| Description | Select writeback data and qualify register-file writes. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/writeback_stage.sv`, module `writeback_stage`, instance name `wb_stage` |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md) ([result selection](5-stage-baseline-core.md#exmem-boundary-and-data-request-ownership), [MEM/WB payload](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary), [architectural side effects](5-stage-baseline-core.md#architectural-side-effects), [reset architecture](5-stage-baseline-core.md#reset-architecture)); [Memory stage](memory-stage.md#10-decisions-and-open-items) (MEM-D2, MEM-D3); [Hazard control unit](hazard-control-unit.md); [Register file](register-file.md) |

## 1. Overview

- `writeback_stage` selects the architectural result of the MEM/WB instruction and qualifies the register-file write of that instruction.
- It is one combinational leaf with no clock, reset, state, stall or flush port.
- It has no wrapper, mux leaf or write-control leaf, because separate leaves would add hierarchy without separating a storage or protocol responsibility.
- BASE owns result semantics, retirement and the interlock rules, and this spec refines the local WB interface.
- It does no instruction decode, arithmetic, load formatting, pipeline storage or arbitration.
- The register file owns storage, the read ports and the WB-to-ID bypass, and the EX forwarding unit owns producer matching and operand selection. This block only supplies `wb_data`.
- CI, CSR/MRET and IRQ are outside the block, and it reserves no extension result input.

## 2. Block Design

```text
ex_result, load_result, wb_src <- MEM/WB register       +-----------------+
rd, reg_write, instruction_valid <- MEM/WB register     |                 | -> wb_data (decode_stage, execute_stage)
                                                        | writeback_stage |
                                                        |                 | -> rf_write_fire (decode_stage)
                                                        +-----------------+
                                                                 ^
                                                  advance_allowed <- hazard_control_unit
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `ex_result` | Input | `DATA_WIDTH` | MEM/WB register | EX result of the MEM/WB instruction. |
| `load_result` | Input | `DATA_WIDTH` | MEM/WB register | Formatted load value of the MEM/WB instruction. |
| `rd` | Input | 5 | MEM/WB register | Destination register of the MEM/WB instruction. |
| `wb_src` | Input | 1 | MEM/WB register | Result selector decoded in ID and retained in MEM/WB. |
| `reg_write` | Input | 1 | MEM/WB register | Register-write intent of the MEM/WB instruction. |
| `instruction_valid` | Input | 1 | MEM/WB register | The MEM/WB entry is live. |
| `advance_allowed` | Input | 1 | `hazard_control_unit` | The core permits WB to advance at the next rising edge. |
| `wb_data` | Output | `DATA_WIDTH` | `decode_stage`, `execute_stage` | Selected writeback value. |
| `rf_write_fire` | Output | 1 | `decode_stage` | Permission for the register file to write `rd` with `wb_data` at the rising edge. |

- `ex_result` is architectural when a live writer has `wb_src` 0, and `load_result` is architectural when a live writer has `wb_src` 1.
- `wb_src` and `rd` are meaningful for a live writer only.
- The core also routes the MEM/WB destination, valid and `reg_write` directly to the register file and EX forwarding, so the block has no pass-through output for them.
- The block has no module parameter. Data vectors use `DATA_WIDTH`, and the supported configuration is `DATA_WIDTH` 32. All vectors are unsigned bit patterns with no width conversion.
- `riscv_pkg` has no shared WB-selector type, and the block adds none ([WB-D3](#10-decisions-and-open-items)).

## 4. Internal Structure

| Module | Instance | File | Spec |
| --- | --- | --- | --- |
| `writeback_stage` | `wb_stage` | `rtl/writeback_stage.sv` | This spec |

### Internal nets

| Net | Width | Driver | Consumers |
| --- | --- | --- | --- |
| `wb_retire_fire` | 1 | `wb_stage` logic, from ports `instruction_valid` and `advance_allowed` | `wb_stage` logic of port `rf_write_fire` |

- The block has no sub-module. It has one two-input data selection for `wb_data` and one write qualification for `rf_write_fire`.
- `wb_retire_fire` is a combinational net. It is not an output port and holds no state, because BASE has no functional consumer for a public retirement port ([WB-D2](#10-decisions-and-open-items)).
- The RTL has no instantiation of the block yet, and `wb_stage` is the instance name for the core integration.

## 5. State

- None, because the block is purely combinational (section 1).
- The core owns the MEM/WB validity, the payload retention and replacement, and the permission to advance.
- The register file owns the architectural registers.

## 6. Behavior

### Output table

| Output | Equals | Rule owner |
| --- | --- | --- |
| `wb_data` | `ex_result` when `wb_src` is 0, and `load_result` when `wb_src` is 1. Every bit is kept, with no arithmetic or sign conversion. | [BASE MEM/WB payload](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary), [WB-D3](#10-decisions-and-open-items) |
| `rf_write_fire` | 1 for a retiring writer with a nonzero destination, and 0 otherwise | [Write qualification](#write-qualification), [BASE architectural side effects](5-stage-baseline-core.md#architectural-side-effects) |

- Both values of `wb_src` are defined. ALU, `LUI`, `AUIPC` and jump-link writers select 0, and loads select 1.
- The jump link (`pc` plus 4) is already selected into `ex_result` in EX, so the block needs no PC input and no third data source.
- Branches, stores and `FENCE` retire with `reg_write` 0.
- Unused data is not required to be zero, including during bubbles.
- `wb_data` does not depend on retirement. The block neither gates nor zeroes it with the retirement or write permission.
- Forwarding may use `wb_data` for an eligible live producer even when the producer cannot retire. The eligibility is the BASE [forwarding rule](5-stage-baseline-core.md#forwarding-and-load-use-hazards).
- The register file consumes `wb_data` only with `rf_write_fire` 1.

### Write qualification

| Condition | Required for `rf_write_fire` 1 | Reason |
| --- | --- | --- |
| `instruction_valid` | 1 | An invalid, flushed or killed entry cannot write the register file. |
| `advance_allowed` | 1 | A held entry does not retire, so it cannot write. |
| `reg_write` | 1 | A non-writer retires without a register-file write. |
| `rd` | Not 0 | `x0` has no write target. |

- Retirement is the first two rows, so it depends on validity and advance permission and not on `reg_write`, `wb_src` or the payload.
- A non-writer or a writer to `x0` may retire without a register-file write.
- The register file uses `rf_write_fire` as its write enable and not the raw `reg_write` ([WB-D2](#10-decisions-and-open-items)).
- The semantic `reg_write` stays in the pipeline metadata and qualifies EX forwarding independently of retirement.

## 7. Timing and Control

- The outputs follow the current inputs after combinational settling, with no registered latency and no handshake.
- The core and the register file own setup, hold and rising-edge consumption. Consecutive instructions need no WB-local bubble.
- The timing is a logical contract and not a physical timing claim.
- `advance_allowed` qualifies an event and does not hold pipeline storage ([pipeline-register local control](5-stage-baseline-core.md#pipeline-register-local-control)).

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input, and `wb_data` is not reset or forced to zero. `rf_write_fire` is 0 throughout reset, whatever the stale payload, under the reset assumption of section 8. |
| Stall | None: the block has no stall input. During an unresolved MEM wait `advance_allowed` is 0 (section 8), so `rf_write_fire` is 0, and `wb_data` stays selected and available. |
| Flush | None: the block has no flush input. The core resolves stall, flush and reset before it supplies the current entry and the advance permission. A younger EX redirect does not kill older WB work. |

- Trace: None, because the block has no sequence in time, and its outputs depend on the current inputs alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| `instruction_valid` is 0 and `advance_allowed` is 0 throughout reset after reset propagation | The core and the hazard control unit ([BASE reset contract](5-stage-baseline-core.md#reset-architecture), [HCU-D3](hazard-control-unit.md#10-decisions-and-open-items)); the interface is [WB-D1](#10-decisions-and-open-items) and [WB-D2](#10-decisions-and-open-items) | A stale payload can give `rf_write_fire` 1, because the block has no reset input. |
| `advance_allowed` is 0 while a MEM wait is unresolved, and the core drives the MEM/WB `stall` to retain the entry | The core and the hazard control unit ([BASE architectural side effects](5-stage-baseline-core.md#architectural-side-effects)) | A held entry could retire and write repeatedly. |
| Every input belongs to the same pre-edge MEM/WB instruction, and incoming MEM data does not replace its write data before its retirement edge | The core ([MEM-D2](memory-stage.md#10-decisions-and-open-items)) | A write takes the data or destination of another instruction. |
| The MEM/WB capture enable is not the retirement condition of this block | The core | An incoming instruction cannot replace an invalid entry, and an invalid incoming entry cannot clear the old validity. |
| The decoded fields and the advance permission are legal and consistent with the core state | The environment | The block repairs nothing, and it has no trap, error or checker port. |

| Case | Inputs | Result |
| --- | --- | --- |
| A response releases the MEM wait | `advance_allowed` 1 on the edge of the data response, and a live writer in WB | `rf_write_fire` is 1 for the old WB entry, and the register file consumes the old `wb_data` at that edge. After the edge, the outputs show the newly captured entry. The core adds no release bubble. |
| A younger EX redirect | A live writer in WB, a redirect in EX and `advance_allowed` 1 | The old WB entry is kept and its write is not cancelled. |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_writeback_stage.py` and cocotb module `tb/testcases/writeback_stage_cocotb.py`.
- The module has 2 tests. `test_result_selection` drives 10 selection vectors, and `test_write_qualification` drives the 16 qualification combinations and 3 more vectors.
- Planned checks 1 to 5 are checked by these two tests. Check 6 is outside the leaf, and no test exists for it.
- Expected values are manual literals and never come from the DUT. Stimulus timing follows `tb/README.md`.
- A leaf pass shows only the checked vectors. It does not establish MEM/WB retention and capture, core arbitration, register-file storage and read forwarding, full-pipeline retirement or physical timing.

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Result selection keeps all bits | Distinct EX and load values, zero, high-bit and all-one patterns, and a change of the unselected input | The selected literal appears unchanged, and the unselected input cannot affect the output |
| Valid and advance qualification | A writer to a nonzero `rd` with valid and advance asserted, then each disabled alone | `rf_write_fire` is 0 when either qualifier is 0 |
| Register-file qualification | An eligible write, retirement disabled, a non-writer and an `x0` destination | `rf_write_fire` is 1 only when valid, advance, write intent and a nonzero destination all hold |
| Data independent of retirement | Data and selector held stable while validity and advance permission toggle | `wb_data` stays unchanged while `rf_write_fire` changes |
| Combinational behavior | Selector, values, destination and qualifiers changed in sequence | Every output follows the current inputs, with no state retained from a prior entry |
| Parent integration, outside the leaf | A MEM wait then the response release with distinct old-WB and new-MEM results; reset or a younger redirect | No write during the hold or reset, the old WB entry writes once on the release, and replacement and forwarding keep the correct instruction association |

### Vectors

| Case | Relevant inputs | Expected outputs |
| --- | --- | --- |
| Ordinary writer | `ex_result=0x80000001`, `load_result=0x12345678`, `wb_src=0`, `reg_write=1`, `rd=5` | `wb_data=0x80000001`, `rf_write_fire=1` |
| Signed byte load already formatted in MEM | `ex_result=0x00010003`, `load_result=0xFFFFFF80`, `wb_src=1`, `reg_write=1`, `rd=6` | `wb_data=0xFFFFFF80`, `rf_write_fire=1` |
| Jump link already selected in EX | `ex_result=0x00000024`, `load_result=0xDEADBEEF`, `wb_src=0`, `reg_write=1`, `rd=1` | `wb_data=0x00000024`, `rf_write_fire=1` |
| Held older WB producer | Row 1 with `advance_allowed=0` | `wb_data=0x80000001`, `rf_write_fire=0` |
| Invalid entry | Row 1 with `instruction_valid=0` | `wb_data=0x80000001`, `rf_write_fire=0` |
| Write to `x0` | Row 1 with `rd=0` | `wb_data=0x80000001`, `rf_write_fire=0` |
| Live non-writer | Row 1 with `reg_write=0` | `wb_data=0x80000001`, `rf_write_fire=0` |

- Rows 1 to 3 have `instruction_valid` 1 and `advance_allowed` 1, and each later row changes one input of row 1.

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| WB-D1 | WB receives `instruction_valid` and `advance_allowed`, derives retirement and qualifies the register-file write locally. The core owns the advance arbitration. | It keeps the per-instruction qualification in WB without making WB resolve global reset and stall conditions. The alternative was a core-generated retirement input: it keeps the BASE behavior but moves the local qualification outside WB. |
| WB-D2 | Retirement stays internal, and the block exposes only `wb_data` and `rf_write_fire`. The semantic `reg_write` stays for forwarding, and the register file uses `rf_write_fire` as its write enable. | No BASE consumer needs a separate retirement port. |
| WB-D3 | The selector is named `wb_src`, and its encoding stays 0 for EX and 1 for load. The producer-stage form is `mem_wb_src`. | None recorded. |

- History: 2026-10-24 the Owner accepted the spec after reviewing the block design and confirming that no open decision remained. BASE behavior is inherited, and the `wb_src` naming and the WB-generated retirement were selected locally. The same day the Owner selected the internal retirement qualification with only data and write permission exposed, under the revision label WB D2.
- 2026-11-07 rewritten in the block spec format, with WB-N1 renumbered WB-D3 and the Vectors moved to section 9. The paragraphs on the old `mem_wb_from_mem` name, the RTL mapping paragraph and the closing acceptance remarks went.

| Old ID | New ID | Status |
| --- | --- | --- |
| WB-N1 | WB-D3 | Renumbered |
| WB-D1 | WB-D1 | Kept |
| WB-D2 | WB-D2 | Kept |
| WB D2 (revision label, 2026-10-24; `tb/README.md` cites it) | WB-D1, WB-D2 | Retired as a label: its decisions are WB-D1 and WB-D2, and History carries the date |

- Length: 5 pages, above the 2-4 limit, because the spec has nine ports, two condition tables, six check rows, seven vectors and six assumptions.
- Open items: none.
