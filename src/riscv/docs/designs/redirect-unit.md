# Redirect Unit

| Field | Value |
| --- | --- |
| Description | Qualify branch/jump redirects and form the redirect target. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/redirect_unit.sv`, module `redirect_unit`, instance `ex_redirect` in `execute_stage` |
| Parent | [Execute stage](execute-stage.md#4-internal-structure); [BASE redirect contract](5-stage-baseline-core.md#redirect-event-and-pipeline-recovery) |

## 1. Overview

- `redirect_unit` qualifies a branch or jump redirect and formats its target from an already computed ALU result.
- Instruction decode belongs to ID, target arithmetic belongs to the [ALU](alu.md), and comparison belongs to the [branch comparator](branch-comparator.md).
- The block does not calculate a link value, flush pipeline registers, update the fetch PC or arbitrate extension redirects.
- It is purely combinational, with no clock, reset, storage or private state that remembers a sent redirect.
- Parent control owns the pipeline advance and the suppression of side effects during reset and hold.
- BASE owns the redirect contract, the execute stage owns the composition, and the [hazard control unit](hazard-control-unit.md) owns `advance_allowed`.

## 2. Block Design

```text
alu_result <- alu                                   +-----------------+
branch_condition <- branch_comparator               |                 | -> redirect_fire (fetch_stage,
control_flow, instruction_valid <- ID/EX register   |  redirect_unit  |                   hazard_control_unit)
advance_allowed <- hazard_control_unit              |                 | -> redirect_target (fetch_stage)
                                                    +-----------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `alu_result` | Input | `DATA_WIDTH` | `alu` | ALU result of the instruction in EX, which holds the computed target. |
| `branch_condition` | Input | 1 | `branch_comparator` | Selected comparison result. Only a conditional branch uses it. |
| `control_flow` | Input | `control_flow_t` (2) | ID/EX register | Decoded control-flow intent of the instruction in EX. |
| `advance_allowed` | Input | 1 | `hazard_control_unit` | The parent permits the instruction in EX to leave EX. |
| `instruction_valid` | Input | 1 | ID/EX register | The instruction in EX is live. |
| `redirect_fire` | Output | 1 | `fetch_stage`, `hazard_control_unit` | Qualified redirect event for the consuming edge. |
| `redirect_target` | Output | `ADDR_WIDTH` | `fetch_stage` | Redirect address, meaningful when `redirect_fire` is 1. |

- The target crosses from the datapath domain to the address domain under the [stage boundary contract](execute-stage.md#3-interface). Every bit is kept except the JALR bit-zero adjustment, and unequal-width conversion is not supported.
- The port names have no EX prefix and no direction suffix. Their producer mapping is an integration concern ([RU-D2](#10-decisions-and-open-items)).
- `branch_kind` and `result_src` keep their separate comparison and result-selection responsibilities.
- There is no error port and no CPU trap.

### Control-flow encoding

| Member | Code | Meaning |
| --- | --- | --- |
| `CF_NONE` | `2'b00` | No control-flow operation. |
| `CF_BRANCH` | `2'b01` | Conditional branch. |
| `CF_JAL` | `2'b10` | Direct jump. |
| `CF_JALR` | `2'b11` | Register-indirect jump. |

- `control_flow_t` is a shared 2-bit enum in `riscv_pkg` ([RU-D1](#10-decisions-and-open-items)).
- All four binary codes are assigned and mutually exclusive.

## 4. Internal Structure

### Internal nets

| Net | Width | Driver | Consumers |
| --- | --- | --- | --- |
| `redirect_req` | 1 | Logic from ports `control_flow` and `branch_condition` | The qualification of `redirect_fire` with ports `instruction_valid` and `advance_allowed` |

- The block has no sub-module. It has one selection on `control_flow`, which sets the request and the target, and one qualification of the request.
- The net is combinational and holds no state.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

### Redirect request and target

| Decoded intent | Redirect requested | `redirect_target` |
| --- | --- | --- |
| No control-flow operation | Never | `alu_result`, unchanged |
| Conditional branch | When `branch_condition` is 1 | `alu_result`, unchanged |
| JAL | Always | `alu_result`, unchanged |
| JALR | Always | `alu_result` with only bit 0 forced to 0 |

- `redirect_fire` is 1 only when a redirect is requested, `instruction_valid` is 1 and `advance_allowed` is 1.
- A jump redirects independently of the comparison result and of the destination register, including x0.
- A non-control-flow instruction never redirects, even when the comparison result is true.
- `redirect_target` does not depend on `instruction_valid`, `advance_allowed`, `branch_condition` or `redirect_fire`. It follows the current datapath even when no redirect fires, with no zero value and no retained previous target ([RU-D3](#10-decisions-and-open-items)).
- JALR clears only bit 0 and keeps bit 1.
- The block tracks no previous event and cancels no outstanding bus transaction.

## 7. Timing and Control

- Both outputs follow the current inputs after combinational settling, and the parent consumes the event at its clock edge.
- The block has no latency, no handshake and no registered pulse.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input and no state. |
| Stall | None: the block has no stall input, and `advance_allowed` 0 keeps `redirect_fire` at 0 for a held instruction. |
| Flush | None: the block has no flush input, and `instruction_valid` 0 keeps `redirect_fire` at 0. |

- Trace: None, because the block has no sequence in time, and its outputs depend on the current inputs alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| `advance_allowed` does not depend on `redirect_fire` in the same cycle | The hazard control unit ([section 7](hazard-control-unit.md#7-timing-and-control)) | The core contains a combinational loop. |
| The parent consumes `redirect_target` only when `redirect_fire` is 1 | Parent control ([RU-D3](#10-decisions-and-open-items)) | The parent takes a target that follows the datapath for an instruction that does not redirect. |
| Parent control owns the suppression of side effects during reset and hold | Parent control | The block cannot suppress them, because it has no reset or hold input. |
| Parent pipeline recovery prevents a replay of a redirect | Parent control ([BASE redirect contract](5-stage-baseline-core.md#redirect-event-and-pipeline-recovery)) | The block reports the same redirect again, because it keeps no memory of a previous event. |
| A redirect target is four-byte aligned | Nothing: BASE leaves a misaligned target outside | The block keeps the target unchanged, and JALR clears only bit 0. |

| Case | Inputs | Result |
| --- | --- | --- |
| A branch or jump is held during an unresolved MEM wait | A requesting `control_flow`, `instruction_valid` 1, `advance_allowed` 0 | `redirect_fire` is 0, and `redirect_target` keeps following the datapath. |
| Parent control permits advance on the memory-response edge | The same inputs with `advance_allowed` 1 | `redirect_fire` is 1, and the held instruction redirects and leaves EX together. |
| A non-control-flow instruction with a true comparison | `CF_NONE` and `branch_condition` 1 | `redirect_fire` is 0. |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_redirect_unit.py` and cocotb module `tb/testcases/redirect_unit_cocotb.py`.
- The module has 5 tests, and each planned check below has one test.
- Expected values are literals in the tests and never come from the DUT.
- Integration verification of redirect, hold and release, and invalid pipeline state is owned by the [parent EX contract](execute-stage.md#9-verification).

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Fire qualification | Every `control_flow` with `branch_condition` 0 and 1, and every combination of `instruction_valid` and `advance_allowed` | `redirect_fire` is 1 only for a branch with a true condition or a jump, with both qualifiers 1, and the target equals the ALU result | `test_redirect_fire` |
| Target kept | `CF_NONE`, `CF_BRANCH` and `CF_JAL` with five ALU results from 0 to `0xFFFFFFFC`, and every qualifier 1 | `redirect_target` equals the ALU result, and `redirect_fire` is 0 for `CF_NONE` and 1 otherwise | `test_target_passthrough` |
| JALR target | `CF_JALR` with five ALU results, odd and even, with bit 1 set and clear, `branch_condition` 0 and both qualifiers 1 | `redirect_fire` is 1, bit 0 of the target is 0, and the other bits equal the ALU result | `test_jalr_target` |
| JALR target without fire | The same five ALU results with `instruction_valid` and `advance_allowed` low in turn and together | `redirect_fire` is 0, and the target has bit 0 cleared | `test_jalr_target_without_fire` |
| Control change | ALU result `0x80000003` with `CF_JALR`, `CF_JAL` and `CF_NONE` in succession | `redirect_fire` is 1, 1 and 0, and the target is `0x80000002`, `0x80000003` and `0x80000003` | `test_target_control_transition` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| RU-D1 | The decoded control flow reaches the block as the shared 2-bit enum of section 3, with explicit semantic intent independent of operand selection. | The selector keeps redirect behavior independent of operand-source encoding. It replaces the proposed separate branch and jump intent flags, so the intent has no second copy. |
| RU-D2 | The port names are those of section 3, with no EX prefix and no direction suffix. Their producer mapping remains an integration concern. | None recorded. |
| RU-D3 | The target follows the datapath independently of `redirect_fire`, as section 6 states. | Parent consumption is qualified by `redirect_fire`, so no extra zero-output selection is required. |

- History: 2026-10-19 the Owner accepted the spec and the local decisions RU-D1, RU-D2 and RU-D3, under the revision label RU D2, with a width clarification.
- 2026-11-07 rewritten in the block spec format, with the redirect behavior as section 6 and the checks of the five tests as section 9. The planned-module line went.

| Old ID | New ID | Status |
| --- | --- | --- |
| RU-D1 | RU-D1 | Kept |
| RU-D2 | RU-D2 | Kept |
| RU-D3 | RU-D3 | Kept |

- Length: 4 pages, above the 2-3 limit, because section 3 holds the encoding table and section 9 has five planned checks.
- Open items: none.
