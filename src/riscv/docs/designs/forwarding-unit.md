# Forwarding Unit

| Field | Value |
| --- | --- |
| Description | Combinational register-source forwarding with MEM over WB priority. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/forwarding_unit.sv`, module `forwarding_unit`, instance `ex_forwarding` in `execute_stage` |
| Parent | [Execute stage](execute-stage.md#4-internal-structure) ([class-to-operand table](execute-stage.md#class-to-operand-table)); [BASE forwarding rules](5-stage-baseline-core.md#forwarding-and-load-use-hazards) |

## 1. Overview

- `forwarding_unit` selects the current value of each register source, `rs1` and `rs2`, independently.
- For each source it takes an older pipeline producer before the value carried in ID/EX.
- The outputs feed operand selection, branch comparison and store data, and the forwarded `rs1` also supplies the JALR base through operand selection. The execute stage owns the composition.
- The block includes the selection and the data muxing.
- It does no instruction decode, register-file read, ALU operand choice, load formatting, jump-link reconstruction or stall generation.
- ID load-use detection and the parent MEM interlock are outside the block.
- BASE owns forwarding eligibility, and this spec refines the local interface.
- It is purely combinational, with no clock, reset, storage, handshake or private hold state.

## 2. Block Design

```text
rs1_id, rs2_id, rs1_value, rs2_value <- ID/EX register    +------------------+
mem_rd, mem_result, mem_valid,                            |                  | -> fwd_rs1 (operand_mux, branch_comparator)
 mem_reg_write, mem_wb_src <- EX/MEM register             | forwarding_unit  |
wb_rd, wb_valid, wb_reg_write <- MEM/WB register          |                  | -> fwd_rs2 (operand_mux, branch_comparator,
wb_data <- writeback_stage                                +------------------+              execute_stage store_data)
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `rs1_id` | Input | 5 | ID/EX register | Register identifier of the first source. |
| `rs2_id` | Input | 5 | ID/EX register | Register identifier of the second source. |
| `rs1_value` | Input | `DATA_WIDTH` | ID/EX register | Register value of the first source carried in ID/EX, after the WB bypass in ID. |
| `rs2_value` | Input | `DATA_WIDTH` | ID/EX register | Register value of the second source carried in ID/EX, after the WB bypass in ID. |
| `mem_rd` | Input | 5 | EX/MEM register | Destination register of the EX/MEM producer. |
| `mem_result` | Input | `DATA_WIDTH` | EX/MEM register | Selected EX result of the EX/MEM producer, including the jump link. |
| `mem_valid` | Input | 1 | EX/MEM register | The EX/MEM producer is live. |
| `mem_reg_write` | Input | 1 | EX/MEM register | The EX/MEM producer has semantic register-write intent. |
| `mem_wb_src` | Input | 1 | EX/MEM register | The architectural result of the EX/MEM producer comes from memory. |
| `wb_rd` | Input | 5 | MEM/WB register | Destination register of the MEM/WB producer. |
| `wb_data` | Input | `DATA_WIDTH` | `writeback_stage` | Selected architectural writeback value of the MEM/WB producer, including formatted load data. |
| `wb_valid` | Input | 1 | MEM/WB register | The MEM/WB producer is live. |
| `wb_reg_write` | Input | 1 | MEM/WB register | The MEM/WB producer has semantic register-write intent. |
| `fwd_rs1` | Output | `DATA_WIDTH` | `operand_mux`, `branch_comparator` | Selected value of the first register source. |
| `fwd_rs2` | Output | `DATA_WIDTH` | `operand_mux`, `branch_comparator`, `execute_stage` | Selected value of the second register source, also the stage output `store_data`. |

- Data vectors use `DATA_WIDTH`, register identifiers are unsigned 5-bit vectors, and qualifiers are 1-bit. The [stage boundary contract](execute-stage.md#3-interface) applies.
- The names `mem_*` and `wb_*` identify the producer stage and the priority ([FU-D2](#10-decisions-and-open-items)).
- The block has no public mux selector, no consumer-valid input and no source-use input ([FU-D2](#10-decisions-and-open-items)).
- There is no error port and no CPU trap.

## 4. Internal Structure

### Internal nets

| Net | Width | Driver | Consumers |
| --- | --- | --- | --- |
| `mem_eligible` | 1 | Logic from ports `mem_valid`, `mem_reg_write`, `mem_wb_src` and `mem_rd` | The selection of `fwd_rs1` and `fwd_rs2` |
| `wb_eligible` | 1 | Logic from ports `wb_valid`, `wb_reg_write` and `wb_rd` | The selection of `fwd_rs1` and `fwd_rs2` |
| `mem_rs1_match` | 1 | Logic from ports `mem_rd` and `rs1_id` | The selection of `fwd_rs1` |
| `mem_rs2_match` | 1 | Logic from ports `mem_rd` and `rs2_id` | The selection of `fwd_rs2` |
| `wb_rs1_match` | 1 | Logic from ports `wb_rd` and `rs1_id` | The selection of `fwd_rs1` |
| `wb_rs2_match` | 1 | Logic from ports `wb_rd` and `rs2_id` | The selection of `fwd_rs2` |

- The block has no sub-module. It has two eligibility terms, four destination matches and two three-way selections.
- The nets are combinational and hold no state.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

### Producer eligibility

| Condition | EX/MEM producer | MEM/WB producer | Reason |
| --- | --- | --- | --- |
| Live | `mem_valid` is 1 | `wb_valid` is 1 | An invalid producer payload is ignored through its valid qualifier. |
| Writer | `mem_reg_write` is 1 | `wb_reg_write` is 1 | A non-writer cannot override a source. |
| Result available | `mem_wb_src` is 0 | Not used, because `wb_data` already holds the selected architectural value | A load has no data in EX/MEM, and a load address is not load data. |
| Destination | `mem_rd` is not 0 | `wb_rd` is not 0 | A destination x0 cannot override a source. |

### Selection

| Priority | Condition for the source | Selected value |
| --- | --- | --- |
| 1 | The EX/MEM producer is eligible, and `mem_rd` equals the source identifier | `mem_result` |
| 2 | The MEM/WB producer is eligible, and `wb_rd` equals the source identifier | `wb_data` |
| 3 | No eligible producer matches | The carried `rs1_value` or `rs2_value` |

- The selection applies independently to `rs1_id` with `rs1_value` for `fwd_rs1`, and to `rs2_id` with `rs2_value` for `fwd_rs2`.
- Both sources can select the same producer or different producers.
- Every bit of the selected value is kept, with no signed conversion and no arithmetic.
- A source x0 matches no eligible producer, so its output is the carried value through priority 3. The block adds no separate zero override ([FU-D3](#10-decisions-and-open-items)).
- No retirement or register-file write pulse qualifies forwarding, so a held MEM/WB producer remains usable.
- An EX/MEM load stays ineligible even on its response edge, and its completed data is forwarded from MEM/WB.
- The block does not signal readiness to EX and does not repair a missing load-use stall.

## 7. Timing and Control

- Both outputs follow the current inputs after combinational settling, including while EX is held.
- The block has no latency and no handshake.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input and no state. |
| Stall | None: the block has no stall input, and the outputs follow the inputs while EX is held. |
| Flush | None: the block has no flush input, and an invalid producer is ignored through its valid qualifier. |

- Trace: None, because the block has no sequence in time, and its outputs depend on the current inputs alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| The carried value of a consumed source x0 is zero | ID/EX, and standalone tests supply the same ([FU-D3](#10-decisions-and-open-items)) | The block does not repair it, so the output follows the nonzero carried value. |
| The producer stages own the payload stability and the validity of their inputs | The producer stages | The block cannot detect it, because it has no input for either. |
| Parent hazard and interlock control prevents consumption while the nearest older writer of a source is unavailable | Parent hazard and interlock control ([BASE forwarding rules](5-stage-baseline-core.md#forwarding-and-load-use-hazards)) | The block selects an older producer or the carried value, which does not resolve the dependency. |
| Parent control ignores the outputs for an invalid entry or an unused source | Parent control | The block cannot suppress them, because it has no consumer-valid or source-use input ([FU-D2](#10-decisions-and-open-items)). |

| Case | Inputs | Result |
| --- | --- | --- |
| An EX/MEM load matches a source | `mem_valid` 1, `mem_reg_write` 1, `mem_wb_src` 1, and `mem_rd` equal to the source identifier | The EX/MEM result is not used. The output is `wb_data` for an eligible matching MEM/WB producer, and the carried value otherwise. |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_forwarding_unit.py` and cocotb module `tb/testcases/forwarding_unit_cocotb.py`.
- The module has 9 tests, and each planned check below has one test.
- Expected values are literals in the tests and never come from the DUT.
- Integration verification is owned by the [parent EX contract](execute-stage.md#9-verification).

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| EX/MEM match | A matching eligible EX/MEM producer, no live MEM/WB producer, for each source | The source takes `mem_result`, and the other source keeps its carried value | `test_mem_match` |
| MEM/WB match | A matching eligible MEM/WB producer, with an eligible EX/MEM producer that does not match | The source takes `wb_data`, and the other source keeps its carried value | `test_wb_match` |
| No match | A live EX/MEM producer that matches neither source with no live MEM/WB producer, then the reverse | Both sources keep their carried values | `test_no_match` |
| EX/MEM priority | Both producers match one source, then only EX/MEM matches | The source takes `mem_result` in both cases | `test_mem_priority` |
| Destination x0 | Both sources x0, with a producer of destination x0 in turn for EX/MEM and MEM/WB, each carrying nonzero data | Both sources keep the carried zero | `test_zero_destination` |
| EX/MEM eligibility | Each combination of `mem_valid`, `mem_reg_write` and `mem_wb_src`, with and without a live MEM/WB producer | Only live, writer and non-load select `mem_result`, otherwise `wb_data` or the carried value | `test_mem_guards` |
| MEM/WB eligibility | Each combination of `wb_valid` and `wb_reg_write` | Only live and writer select `wb_data` | `test_wb_guards` |
| Both sources at once | Both sources on the same producer, and on different producers | Each source selects independently | `test_simultaneous_sources` |
| Eligibility change | Both identifiers matched while the EX/MEM producer and then the MEM/WB producer become ineligible | The outputs move from `mem_result` to `wb_data` to the carried value | `test_selection_transition` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| FU-D1 | The block receives `mem_wb_src` with the valid, write intent and destination of the EX/MEM producer, and excludes a load of that producer inside the block. The parent supplies decoded semantic facts and not a precomputed availability qualifier. | None recorded. |
| FU-D2 | The interface is the flat ports of section 3, with `mem` and `wb` names that identify the producer stage and the priority. The block returns forwarded data directly, with no public mux selector and no consumer-valid or source-use port. | None recorded. |
| FU-D3 | A consumed source x0 relies on ID/EX supplying zero and takes the ordinary fallback. Every producer with destination x0 is excluded, and the block has no separate zero-selection path. Legal standalone tests supply the same x0 input. | None recorded. |

- History: 2026-10-19 the Owner accepted the spec and the local decisions FU-D1, FU-D2 and FU-D3, under the revision label FU D1.
- 2026-11-07 rewritten in the block spec format, with the selection contract as section 6 and the checks of the nine tests as section 9. The planned-module line and the paragraph on the old `mem_wb_from_mem` name went.

| Old ID | New ID | Status |
| --- | --- | --- |
| FU-D1 | FU-D1 | Kept |
| FU-D2 | FU-D2 | Kept |
| FU-D3 | FU-D3 | Kept |

- Open items: none.
