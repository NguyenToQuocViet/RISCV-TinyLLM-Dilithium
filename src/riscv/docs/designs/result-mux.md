# Result Mux

| Field | Value |
| --- | --- |
| Description | Combinational selection of the ALU result or jump-link value. |
| Last modified | 2026-11-08 |
| Status | Accepted by Việt on 2026-11-08 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/result_mux.sv`, module `result_mux`, instance `ex_result_mux` in `execute_stage` |
| Parent | [Execute stage](execute-stage.md#4-internal-structure) ([result row](execute-stage.md#6-behavior)) |

## 1. Overview

- `result_mux` selects the EX result from the ALU result and the jump-link value.
- The [ALU](alu.md) supplies the ALU result, the [link adder](link-adder.md) supplies the jump-link value, and ID supplies the selector.
- The result feeds the EX/MEM register through the execute stage.
- The block is purely combinational, with no clock, reset, storage, handshake or stall input.
- It decodes no instruction, calculates no link and handles no jump target. It formats no load response, selects no final writeback value and controls no architectural side effect.
- It does no arithmetic, signed conversion, alignment correction or JALR target masking, and the jump target stays separate from the link value.
- The execute stage owns the composition, and this block owns the selection.

## 2. Block Design

```text
alu_result <- alu                                       +--------------+
pc_plus_4 <- link_adder                                 |              | -> result (EX/MEM register)
result_src <- ID/EX register                            |  result_mux  |
                                                        |              |
                                                        +--------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `alu_result` | Input | `DATA_WIDTH` | `alu` | ALU result or effective byte address. |
| `pc_plus_4` | Input | `ADDR_WIDTH` | `link_adder` | Jump-link address. |
| `result_src` | Input | `result_src_t` (1) | ID/EX register | Source selector of the EX result. |
| `result` | Output | `DATA_WIDTH` | EX/MEM register | Selected EX result. |

- The selector type comes from `riscv_pkg`, and every vector is unsigned.
- `result_src` is separate from `wb_src`, which controls the final writeback selection outside EX.
- `pc_plus_4` belongs to the address domain and the other vectors to the datapath domain ([width domains](execute-stage.md#width-domains)). Selecting `pc_plus_4` is a crossing that keeps every bit ([width crossings](execute-stage.md#width-crossings)).

### Selector encoding

| Member | Code |
| --- | --- |
| `RESULT_ALU` | `1'b0` |
| `RESULT_PC_PLUS_4` | `1'b1` |

- Both codes of `result_src` are assigned.

## 4. Internal Structure

- The block has no sub-module and no internal net, and one case on `result_src` selects the result.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

### Selection

| `result_src` | `result` equals |
| --- | --- |
| `RESULT_ALU` | `alu_result`, all 32 bits |
| `RESULT_PC_PLUS_4` | `pc_plus_4`, all 32 bits |

- A branch and FENCE need no meaningful EX result, and the block still follows its selector and does not force zero ([RM-D1](#10-decisions-and-open-items)).

## 7. Timing and Control

- The output follows the current inputs after combinational settling.
- The block has no latency, no handshake and no registered output, and the parent pipeline control owns the capture and hold of the inputs.

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
| JAL and JALR select `RESULT_PC_PLUS_4` even when the destination is x0. Every other instruction that has an EX result selects `RESULT_ALU`, including a load or store address | The [control unit](control-unit.md#class-table) in ID | `result` is not the value that the [execute stage](execute-stage.md#6-behavior) states for the class. |
| The result of an unsupported word or an invalid entry authorizes no side effect | The core, which uses a result only for a valid instruction that needs it ([execute stage](execute-stage.md#8-assumptions-and-corner-cases)) | An arbitrary payload could cause a side effect. |

- Corner cases: None, because the block has no state and `result` depends on the selector and the selected input alone (section 6).

## 9. Verification

- No test of `result_mux` exists in `tb/`: it has no runner and no cocotb module.
- The `execute_stage` runner compiles the block as part of the stage, and the `execute_stage_cocotb` module drives both codes of `result_src` through the stage. The [execute stage](execute-stage.md#9-verification) owns those tests.
- Expected values would come from the selection table of section 6, never from the DUT.

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Result from the ALU | `RESULT_ALU` with `alu_result` values `0x80000000`, `0xFFFFFFFF` and `0x00000001`, and `pc_plus_4` different | `result` equals `alu_result` in all 32 bits | none |
| Result from the link | `RESULT_PC_PLUS_4` with `pc_plus_4` values `0x80000000`, `0xFFFFFFFF` and `0x00000004`, and `alu_result` different | `result` equals `pc_plus_4` in all 32 bits | none |
| Unselected input ignored | Each code with the other data input at zero, then at all ones | `result` is the same in both | none |
| Full-width data | A single set bit walked through the 32 positions of each data input, with its selector chosen | `result` shows the same bit position | none |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| RM-D1 | The block follows `result_src` for a branch and FENCE and does not force zero. | A branch and FENCE require no meaningful EX result. |

- History: 2026-10-19 the Owner accepted the spec, under the revision label RM D2. The old file also records, with no date, a width clarification that the Owner accepted.
- 2026-11-08 rewritten in the block spec format, with an ID for the decision that the old file stated in prose.
- Open items: none.
