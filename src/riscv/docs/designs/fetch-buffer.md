# Fetch Buffer

| Field | Value |
| --- | --- |
| Description | Indexed pc and instruction payload array; no reset and no control. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/fetch_buffer.sv`, module `fetch_buffer`, instance `if_fetch_buffer` in `prefetch_unit` |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md#instruction-fetch-organization) (IF-A3); [Fetch stage](fetch-stage.md) §3 and §4; [Fetch Controller Unit](fetch-controller-unit.md) |

## 1. Overview

- The fetch buffer stores the `pc` and the `instruction` of each of the three fetch slots.
- It holds no slot state, pointer, killed mark or choice of slot, because the [Fetch Controller Unit](fetch-controller-unit.md) owns those.
- A read of a slot returns the last value written to that slot on an earlier edge with its write enable high.

## 2. Block Design

```text
                                                              clk
                                                               |
                                                  +--------------------------+
pc_write <- fetch_controller_unit                 |                          | -> present_pc (fetch_obi_interface)
pc_write_slot <- fetch_controller_unit            |                          | -> fetch_pc (fetch_stage)
pc_write_data <- fetch_controller_unit            |                          | -> fetch_instruction (fetch_stage)
instruction_write <- fetch_controller_unit        |       fetch_buffer       |
instruction_write_slot <- fetch_controller_unit   |                          |
instruction_write_data <- fetch_obi_interface     |                          |
present_slot <- fetch_controller_unit             |                          |
fetch_slot <- fetch_controller_unit               |                          |
                                                  +--------------------------+
```

## 3. Interface

- `ADDR_WIDTH` and `INSTR_WIDTH` are both 32, from `riscv_pkg`.
- The slots are numbered 0 to 2.

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | Core clock | Rising-edge clock of the two arrays. |
| `pc_write` | Input | 1 | `fetch_controller_unit` | Write enable of the `pc` array. |
| `pc_write_slot` | Input | 2 | `fetch_controller_unit` | Slot that a `pc_write` writes. |
| `pc_write_data` | Input | `ADDR_WIDTH` | `fetch_controller_unit` | Fetch address that a `pc_write` stores. |
| `instruction_write` | Input | 1 | `fetch_controller_unit` | Write enable of the `instruction` array. |
| `instruction_write_slot` | Input | 2 | `fetch_controller_unit` | Slot that an `instruction_write` writes. |
| `instruction_write_data` | Input | `INSTR_WIDTH` | `fetch_obi_interface` | Instruction word that an `instruction_write` stores. It is the `response_data` of the OBI leaf. |
| `present_slot` | Input | 2 | `fetch_controller_unit` | Slot that `present_pc` reads. |
| `fetch_slot` | Input | 2 | `fetch_controller_unit` | Slot that `fetch_pc` and `fetch_instruction` read. |
| `present_pc` | Output | `ADDR_WIDTH` | `fetch_obi_interface` | The stored `pc` of the slot that `present_slot` selects. |
| `fetch_pc` | Output | `ADDR_WIDTH` | `fetch_stage` | The stored `pc` of the slot that `fetch_slot` selects. |
| `fetch_instruction` | Output | `INSTR_WIDTH` | `fetch_stage` | The stored `instruction` of the slot that `fetch_slot` selects. |

## 4. Internal Structure

- The buffer holds two arrays of three entries: one for `pc` and one for `instruction`.
- It holds three read selectors, one for each output.
- It has no sub-blocks.

## 5. State

| Register | Reset value | Updater |
| --- | --- | --- |
| `pc` array, three entries of `ADDR_WIDTH` bits | None; not reset | `pc_write`, at the rising edge |
| `instruction` array, three entries of `INSTR_WIDTH` bits | None; not reset | `instruction_write`, at the rising edge |

## 6. Behavior

- Each output is the stored value at its read slot, at all times.
- Each array changes only on a rising edge that writes it.

| Condition at the edge | `pc` array after the edge | `instruction` array after the edge |
| --- | --- | --- |
| `pc_write` low, `instruction_write` low | Unchanged | Unchanged |
| `pc_write` high, `instruction_write` low | The slot that `pc_write_slot` selects holds `pc_write_data`; other slots unchanged | Unchanged |
| `pc_write` low, `instruction_write` high | Unchanged | The slot that `instruction_write_slot` selects holds `instruction_write_data`; other slots unchanged |
| `pc_write` high, `instruction_write` high | As in the second row | As in the third row |

- The two writes need no priority, because they touch different arrays and cannot conflict.
- The buffer checks no slot state and accepts a write to any slot.

## 7. Timing and Control

- The arrays are registered storage and the three reads are combinational.
- A written value appears at the outputs after the write edge, with no further delay.
- The outputs depend only on the stored values and the two read slots, which the controller drives from registers.
- Write enables, write slots and write data are sampled only at the edge and reach no output within a cycle ([fetch stage](fetch-stage.md) §2).

### When valid

| Signal group | When valid |
| --- | --- |
| `present_pc` | While `fetch_controller_unit` presents an entry in the selected slot, after that entry's `pc` write edge. It stays valid for a killed entry that is still presented, until its request fires. |
| `fetch_pc`, `fetch_instruction` | While `fetch_controller_unit` reports a deliverable entry in the slot that `fetch_slot` selects. `fetch_instruction` also needs that entry's response written. |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | The arrays are not reset. Writes still follow their enables. A write during reset has no meaning, because the controller holds every entry free and reads no payload. |
| Stall | The buffer has no stall input. A slot holds its value until a write selects it. |
| Flush | The buffer has no flush input and discards nothing. |

- The trace uses the buffer alone, with the controller supplying the slots and enables.
- Before E1, both arrays hold any value, because neither is reset.

| Edge | Inputs | State after | Outputs after the edge |
| --- | --- | --- | --- |
| E1 | `pc_write` high, `pc_write_slot` 2, `pc_write_data` 0x20 | `pc` of slot 2 holds 0x20 | `present_pc` with `present_slot` 2 is 0x20 |
| E2 | `instruction_write` high, `instruction_write_slot` 2, `instruction_write_data` I1 | `instruction` of slot 2 holds I1 | `fetch_pc` and `fetch_instruction` with `fetch_slot` 2 are 0x20 and I1 |

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| The slot ports carry 0, 1 or 2 | `fetch_controller_unit` ([FCU-O11](fetch-controller-unit.md)) | Not specified; the controller never drives it. |
| The write enables, slots and data come from the controller and the OBI leaf only | The wiring in [fetch stage](fetch-stage.md) §3 | The stored values no longer follow the controller's allocation and response events. |
| A `pc_write` never selects the slot of a killed entry that is still presented | `fetch_controller_unit` ([pc write on a redirect](fetch-controller-unit.md)) | `present_pc` changes while the request is held, which breaks the OBI hold rule. |

| Case | Inputs | Result |
| --- | --- | --- |
| Both writes, different slots | `pc_write` and `instruction_write` high, slots differ | Each array captures its own data |
| Both writes, same slot number | `pc_write` and `instruction_write` high, slots equal | Each array captures its own data in that slot |
| Write during reset | `pc_write` high while the core is in reset | The write happens and has no meaning |

## 9. Verification

- No fetch-buffer test exists.
- The checks below are planned.

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Write, then read; enable low (section 6) | `pc_write` to slot `s`, read `s` through `present_slot` or `fetch_slot`; then change the data with the enable low | Read returns the written value; stored value unchanged |
| Independent writes (section 6) | `pc_write` and `instruction_write` on one edge, to different slots | Both arrays capture their own data |
| Combinational read (section 6) | Change a read slot within a cycle | Output follows the array with no edge |
| Reset with enables low (section 7) | Reset asserted with `pc_write` and `instruction_write` held at 0 | Arrays unchanged |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| FB-D1 | The buffer is an indexed payload array with no reset, not a FIFO. | Entries are allocated before their data arrives and a redirect reloads the pointers, so a FIFO does not fit. |
| FB-D2 | The read selectors are in the buffer. | The controller handles only slot numbers, never payload. |

- History: 2026-11-06 decisions settled (IF-A3); rewritten in the block spec format, IDs renumbered.

| Old ID | New ID | Status |
| --- | --- | --- |
| FB-O8 | FB-D1 | Kept |
| FB-O9 | FB-D2 | Kept |

- FB-O1 to FB-O7 are mapped in [fetch-controller-unit.md](fetch-controller-unit.md), because the controller took over those decisions.
- Open items: none.
