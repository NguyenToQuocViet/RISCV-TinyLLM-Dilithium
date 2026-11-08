# Link Adder

| Field | Value |
| --- | --- |
| Description | Combinational 32-bit PC increment for the jump return address. |
| Last modified | 2026-11-08 |
| Status | Accepted by Việt on 2026-11-08 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/link_adder.sv`, module `link_adder`, instance `ex_link_adder` in `execute_stage` |
| Parent | [Execute stage](execute-stage.md#4-internal-structure) |

## 1. Overview

- `link_adder` computes the sequential return address of the instruction in EX.
- It does so for JAL and JALR, in parallel with the target calculation in the [ALU](alu.md) ([EX-D4](execute-stage.md#10-decisions-and-open-items)).
- The [result mux](result-mux.md#3-interface) receives the address, selects it and owns the conversion to a GPR result.
- The block is purely combinational, with no clock, reset, storage, handshake or stall input.
- It decodes no instruction, calculates no jump target and selects no result. It writes no register and controls no redirect.

## 2. Block Design

```text
pc <- ID/EX register                                    +--------------+
                                                        |              | -> pc_plus_4 (result_mux)
                                                        |  link_adder  |
                                                        |              |
                                                        +--------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `pc` | Input | `ADDR_WIDTH` | ID/EX register | Byte address of the instruction in EX. |
| `pc_plus_4` | Output | `ADDR_WIDTH` | `result_mux` | Sequential return address. |

- Both vectors are unsigned and belong to the address domain ([width domains](execute-stage.md#width-domains)).

## 4. Internal Structure

- The block has no sub-module and no internal net, and one adder adds the constant 4 to `pc`.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

- `pc_plus_4` is `pc` plus 4, modulo 2^32 ([LA-D1](#10-decisions-and-open-items)).
- The block has no carry or overflow output and no trap.
- The block applies no alignment correction and no target masking.

## 7. Timing and Control

- The output follows the current input after combinational settling.
- The block has no latency, no handshake and no registered output, and the parent pipeline control decides when the result is consumed.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input and no state. |
| Stall | None: the block has no stall input. |
| Flush | None: the block has no flush input. |

- Trace: None, because the block has no sequence in time, and its output depends on the current input alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| `pc` is the PC of the instruction in EX, taken from the ID/EX register, and not the current or next fetch PC of the frontend | The core, which carries the PC in the ID/EX register ([execute stage](execute-stage.md#3-interface)) | `pc_plus_4` is not the return address of the instruction in EX. |
| The result of an unsupported word or an invalid entry authorizes no side effect | The core, which uses a result only for a valid instruction that needs it ([execute stage](execute-stage.md#8-assumptions-and-corner-cases)) | An arbitrary payload could cause a side effect. |

- Corner cases: None, because the block has no state and `pc_plus_4` depends on `pc` alone (section 6).

## 9. Verification

- No test of `link_adder` exists in `tb/`: it has no runner and no cocotb module.
- The `execute_stage` runner compiles the block as part of the stage.
- `test_jump_target_and_link` in the `execute_stage_cocotb` module checks the link of JAL and JALR through the stage, including the wrap at the top of the address range. The [execute stage](execute-stage.md#9-verification) owns those tests.
- Expected values would come from the behavior of section 6, never from the DUT.

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Plain increment | `pc` values `0x00000000` and `0x00001000` | `pc_plus_4` is `0x00000004` and `0x00001004` | none |
| Carry chain | `pc` values `0x0000FFFC` and `0x7FFFFFFC` | `pc_plus_4` is `0x00010000` and `0x80000000` | none |
| Wrap | `pc` values `0xFFFFFFFC` and `0xFFFFFFFF` | `pc_plus_4` is `0x00000000` and `0x00000003` | none |
| No alignment correction | `pc` values `0x00000001`, `0x00000002` and `0x00000003` | `pc_plus_4` is `pc` plus 4 in each case | none |
| Every bit position | A single set bit walked through the 32 positions of `pc` | `pc_plus_4` is `pc` plus 4, modulo 2^32, at each position | none |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| LA-D1 | The increment is a constant four bytes, and it is not derived from the data or address width. | The supported instructions are 32 bits wide. |

- History: 2026-10-19 the Owner accepted the spec, under the revision label LA D2. The old file also records, with no date, a width clarification that the Owner accepted.
- 2026-11-08 rewritten in the block spec format, with an ID for the decision that the old file stated in prose.
- Open items: none.
