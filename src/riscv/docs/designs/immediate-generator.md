# Immediate Generator

| Field | Value |
| --- | --- |
| Description | Reconstruct the canonical immediate from the instruction word. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/immediate_generator.sv`, module `immediate_generator`, instance `id_immediate_generator` in `decode_stage` |
| Parent | [Decode stage](decode-stage.md#leaf-connections) (leaf connections, ID-D5, ID-D6, ID-D7, ID-D11); [BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract), [instruction semantic table](5-stage-baseline-core.md#instruction-semantic-table) and [ID/EX boundary](5-stage-baseline-core.md#idex-boundary) |

## 1. Overview

- `immediate_generator` turns the IF/ID `instruction` into the one canonical `imm` that ID drives to EX.
- For each supported class that uses an immediate, `imm` equals the RV32I immediate of the format of that class.
- It is purely combinational, with no clock, reset or state.
- It does no legality check, because `control_unit` decides whether a word is supported ([ID-D7](decode-stage.md#10-decisions-and-open-items)).
- It has no selector from `control_unit` and no `immediate_kind` output, because it chooses the format from the instruction word alone.
- It defines no value for a word that has no immediate ([IMM-D1](#10-decisions-and-open-items)).

## 2. Block Design

```text
                      +-----------------------+
instruction           |                       |
 <- decode_stage      |  immediate_generator  | -> imm (decode_stage)
                      |                       |
                      +-----------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `instruction` | Input | `INSTR_WIDTH` | `decode_stage` | The IF/ID instruction word. |
| `imm` | Output | `DATA_WIDTH` | `decode_stage` | The canonical immediate of the format of the instruction. |

- The block accepts any `instruction` value in any cycle.
- The port names equal the `decode_stage` names, so the stage only wires them ([decode-stage leaf connections](decode-stage.md#leaf-connections)).
- The block has no module parameter. The supported configuration is `INSTR_WIDTH` 32 and `DATA_WIDTH` 32 ([ID-D11](decode-stage.md#10-decisions-and-open-items)).

## 4. Internal Structure

- None, because the block has no sub-blocks.
- It is one selection on `instruction[6:2]` followed by one field copy per format, with no arithmetic. Equivalent coding styles are free.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

- `imm` is an unsigned bit pattern, and the Field layout table is its one width crossing from the instruction fields ([decode-stage width domains](decode-stage.md#width-domains)).
- The layouts follow the [BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract).
- Selection examines the full `instruction[6:2]` of each supported class ([IMM-D2](#10-decisions-and-open-items)), and the class names follow the [BASE instruction semantic table](5-stage-baseline-core.md#instruction-semantic-table).

### Format selection

| Class | `instruction[6:2]` | Format |
| --- | --- | --- |
| `LUI` | `01101` | U |
| `AUIPC` | `00101` | U |
| `JAL` | `11011` | J |
| `JALR` | `11001` | I |
| LOAD | `00000` | I |
| OP-IMM, including `SLLI`, `SRLI` and `SRAI` | `00100` | I |
| STORE | `01000` | S |
| BRANCH | `11000` | B |
| OP (`01100`), MISC-MEM and `FENCE` (`00011`), every other value | none | No format, and `imm` is any ([IMM-D1](#10-decisions-and-open-items)) |

### Field layout

| Format | Layout of `imm`, from the most significant side |
| --- | --- |
| I | `[31:11]` from `instruction[31]`, `[10:5]` from `instruction[30:25]`, `[4:1]` from `instruction[24:21]`, `[0]` from `instruction[20]` |
| S | `[31:11]` from `instruction[31]`, `[10:5]` from `instruction[30:25]`, `[4:1]` from `instruction[11:8]`, `[0]` from `instruction[7]` |
| B | `[31:12]` from `instruction[31]`, `[11]` from `instruction[7]`, `[10:5]` from `instruction[30:25]`, `[4:1]` from `instruction[11:8]`, `[0]` is 0 |
| U | `[31:12]` from `instruction[31:12]`, `[11:0]` is 0 |
| J | `[31:20]` from `instruction[31]`, `[19:12]` from `instruction[19:12]`, `[11]` from `instruction[20]`, `[10:1]` from `instruction[30:21]`, `[0]` is 0 |

- A range of `imm` bits that comes from one instruction bit repeats that bit, which is the sign extension.
- `SLLI`, `SRLI` and `SRAI` use the I layout unchanged. So `imm[11:5]` stays as in the word, `0x00` for `SLLI` and `SRLI` and `0x20` for `SRAI`, and `imm[4:0]` is the shift amount.
- The block does not mask the shift amount, because EX uses only `imm[4:0]` ([BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract)).

## 7. Timing and Control

- `imm` is a combinational function of `instruction` alone, so the block has no latency, no handshake and no dependence on any other signal.
- The block does not know whether IF/ID is valid, because ID/EX handles an invalid entry ([ID-D8](decode-stage.md#10-decisions-and-open-items)).

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no state or control input. |
| Stall | None: the block has no state or control input. |
| Flush | None: the block has no state or control input. |

- Trace: None, because the block has no sequence in time, and `imm` depends on the current `instruction` alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every `instruction` bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| An unsupported or no-immediate word causes no side effect through `imm` | `control_unit` blocks the side effects of an unsupported word ([ID-D5](decode-stage.md#10-decisions-and-open-items)) | The block cannot prevent it, because it has no error output, default vector or legality flag ([ID-D6](decode-stage.md#10-decisions-and-open-items)). |

| Case | Inputs | Result |
| --- | --- | --- |
| Unsupported word that shares a supported `instruction[6:2]` | `LD`, which is LOAD with `funct3` `011` | `imm` has the I value, which is still any and never an oracle ([IMM-D1](#10-decisions-and-open-items)). |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_immediate_generator.py` and cocotb module `tb/testcases/immediate_generator_cocotb.py`.
- The module has 7 tests: `test_i_format`, `test_s_format`, `test_b_format`, `test_u_format`, `test_j_format`, `test_shift_immediates` and `test_selection_other_classes`.
- Each planned check below has one test in the module.
- Expected values are the literals of the Vectors table, or follow from the Field layout table, and never come from the DUT. Stimulus timing follows `tb/README.md`.
- A leaf pass shows only the checked vectors, not decode integration, control selection or whole-core behavior. The immediate checks through the stage are in [decode-stage.md](decode-stage.md#planned-checks).

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| I format | The two I words of the Vectors table | `imm` equals the listed value, at sign bit 0 and 1 |
| S format | The two S words | The fields `[31:25]` and `[11:7]` are rejoined correctly |
| B format | The two B words | `instruction[7]` is at `imm[11]`, and the low bit is 0 |
| U format | The two U words | `imm[31:12]` equals `instruction[31:12]`, with twelve low zeros |
| J format | The two J words | `instruction[20]` is at `imm[11]`, and the low bit is 0 |
| Shifts | `SLLI x1, x2, 31` and `SRAI x1, x2, 3` | `imm[11:5]` stays as in the word, and `imm[4:0]` is the shift amount |
| Selection, other classes | One word each of `JALR`, LOAD and `AUIPC` | The I value for `JALR` and LOAD, and the U value for `AUIPC` |

### Vectors

| Format | Assembly | `instruction` | Expected `imm` |
| --- | --- | --- | --- |
| I | `ADDI x1, x2, 1365` | `0x5551_0093` | `0x0000_0555` |
| I | `ADDI x1, x2, -1366` | `0xAAA1_0093` | `0xFFFF_FAAA` |
| S | `SW x6, 1365(x2)` | `0x5461_2AA3` | `0x0000_0555` |
| S | `SW x6, -1366(x2)` | `0xAA61_2523` | `0xFFFF_FAAA` |
| B | `BEQ x1, x2, +2730` | `0x2A20_85E3` | `0x0000_0AAA` |
| B | `BNE x1, x2, -2732` | `0xD420_9A63` | `0xFFFF_F554` |
| U | `LUI x5, 0x55555` | `0x5555_52B7` | `0x5555_5000` |
| U | `LUI x5, 0xAAAAA` | `0xAAAA_A2B7` | `0xAAAA_A000` |
| J | `JAL x1, +699050` | `0x2ABA_A0EF` | `0x000A_AAAA` |
| J | `JAL x1, -699052` | `0xD545_50EF` | `0xFFF5_5554` |
| Shift | `SLLI x1, x2, 31` | `0x01F1_1093` | `0x0000_001F` |
| Shift | `SRAI x1, x2, 3` | `0x4031_5093` | `0x0000_0403` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| IMM-D1 | `imm` for OP, MISC-MEM (`FENCE`) and every opcode outside the supported set stays any. No value is fixed, no oracle may use it, and the RTL author chooses it. | The stage adds no logic beyond safety, and nothing needs guaranteeing ([ID-D5](decode-stage.md#10-decisions-and-open-items), [ID-D6](decode-stage.md#10-decisions-and-open-items)). |
| IMM-D2 | Format selection matches the full `instruction[6:2]` of each supported class. `instruction[1:0]`, `funct3` and `funct7` are not examined. | It maps 1:1 to the BASE opcode table for review, and legality belongs to `control_unit` ([ID-D7](decode-stage.md#10-decisions-and-open-items)). |
| IMM-D3 | The Vectors table gives two words per format, with sign bit 0 and 1 and complementary immediate bit patterns, and two shift words. | A bit-swizzle error becomes visible, and `imm[11:5]` stays as in the word. |

- History: 2026-10-29 the Owner stated I1 to I4 and accepted the spec. The same day the Owner accepted the amendment that gives `instruction` the type `INSTR_WIDTH` (O7-R), under the revision label IMM D2.
- 2026-11-07 rewritten in the block spec format, with IDs renumbered and the vectors moved to section 9. The RTL mapping paragraph and the closing remarks went.

| Old ID | New ID | Status |
| --- | --- | --- |
| I1 | IMM-D1 | Kept |
| I2 | IMM-D2 | Kept |
| I3 | IMM-D3 | Kept |
| I4 | none | Retired: it records who writes the RTL, not a design choice |
| D6 (carried from the decode stage) | ID-D6 | Not an ID of this file: linked from IMM-D1 and section 8 |
| IMM D2 (revision label, 2026-10-29; `tb/README.md` cites it) | none | Retired as a label: History carries the date. It is not decision I2. |

- Length: 4 pages, above the 2-3 limit, because the spec holds five field layouts, seven planned checks, twelve vectors and a six-row map.
- Open items: none.
