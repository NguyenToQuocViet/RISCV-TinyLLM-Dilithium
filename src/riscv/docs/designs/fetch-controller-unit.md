# Fetch Controller Unit

| Field | Value |
| --- | --- |
| Description | Owns next_fetch_pc, the fetch entry ring and lifecycle, kill recovery and the write and read controls of fetch_buffer. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/fetch_controller_unit.sv`, module `fetch_controller_unit`, instance `if_fetch_controller_unit` in `prefetch_unit` |
| Parent | [Fetch stage](fetch-stage.md); [five-stage BASE core](5-stage-baseline-core.md); [Fetch Buffer](fetch-buffer.md); [Fetch OBI Interface](fetch-obi-interface.md); [Redirect Unit](redirect-unit.md) |

## 1. Overview

- The controller is the fetch control plane.
- It owns `next_fetch_pc`, the three slot pointers, the entry lifecycle and the `killed` marks, because they are the fetch control state with a reset.
- It owns all logic on that state: allocation, presentation, response qualification, delivery and recovery at a redirect.
- It drives the write and read slots and enables of `fetch_buffer`, which stores only `pc` and `instruction`.
- It stores no payload.
- It has no OBI signal and no grant input, because `fetch_obi_interface` owns the OBI port.
- It has no hazard or MEM knowledge, because the HCU supplies `fetch_accept` (fetch-stage F-b).
- It does not decode a redirect or check its target, because `redirect_fire` and `redirect_target` arrive qualified.
- It has no allocation pause, so the only capacity rule is a free slot.

## 2. Block Design

```text
                                                    clk             rst_n
                                                     |                |
                                              +------------------------------+
redirect_fire <- redirect_unit                |                              | -> present_valid (fetch_obi_interface)
redirect_target <- redirect_unit              |                              | -> fetch_valid (fetch_stage)
request_fire <- fetch_obi_interface           |                              | -> pc_write (fetch_buffer)
raw_response_transfer <- fetch_obi_interface  |                              | -> pc_write_slot (fetch_buffer)
                                              |    fetch_controller_unit     | -> pc_write_data (fetch_buffer)
                                              |                              | -> instruction_write (fetch_buffer)
                                              |                              | -> instruction_write_slot (fetch_buffer)
                                              |                              | -> present_slot (fetch_buffer)
                                              |                              | -> fetch_slot (fetch_buffer)
                                              +------------------------------+
                                                     ^
                                    fetch_accept <- hazard_control_unit
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | Core clock | Rising-edge clock of the state. |
| `rst_n` | Input | 1 | Core reset | Active-low reset. It asserts asynchronously and releases synchronously. |
| `redirect_fire` | Input | 1 | `redirect_unit` | A taken redirect from EX transfers on this edge. |
| `redirect_target` | Input | `ADDR_WIDTH` | `redirect_unit` | Target address of the redirect. It is valid when `redirect_fire` is high. |
| `fetch_accept` | Input | 1 | `hazard_control_unit` | High lets IF/ID take an entry this edge, if one is valid. Low blocks it. |
| `request_fire` | Input | 1 | `fetch_obi_interface` | The request of the presented entry transfers on this edge. |
| `raw_response_transfer` | Input | 1 | `fetch_obi_interface` | A response transfers on this edge. It is not yet an expected response. |
| `present_valid` | Output | 1 | `fetch_obi_interface` | The entry at `issue_ptr` is presented. |
| `fetch_valid` | Output | 1 | `fetch_stage` | The oldest entry is READY and offered to IF/ID. |
| `pc_write` | Output | 1 | `fetch_buffer` | Write the `pc` of the slot that `pc_write_slot` selects. |
| `pc_write_slot` | Output | 2 | `fetch_buffer` | Slot that `pc_write` writes. |
| `pc_write_data` | Output | `ADDR_WIDTH` | `fetch_buffer` | Fetch address that `pc_write` stores. |
| `instruction_write` | Output | 1 | `fetch_buffer` | Write the instruction word of a response. |
| `instruction_write_slot` | Output | 2 | `fetch_buffer` | Slot that `instruction_write` writes. |
| `present_slot` | Output | 2 | `fetch_buffer` | Slot of the presented entry. |
| `fetch_slot` | Output | 2 | `fetch_buffer` | Slot of the oldest entry. |

- `ADDR_WIDTH` is 32, `FETCH_DEPTH` is 3 with slots 0 to 2, and `PC_RESET_VEC` is the reset address, all from `riscv_pkg`.

## 4. Internal Structure

- None, because the unit is one state group with its next-state logic and has no sub-blocks.

## 5. State

| Register | Reset value | Updater |
| --- | --- | --- |
| `next_fetch_pc`, `ADDR_WIDTH` bits | `PC_RESET_VEC` | Redirect loads `redirect_target`; allocation adds 4 |
| `life`, one per slot | FREE | Allocation, request, response, delivery, killed drain, redirect |
| `killed`, one bit per slot | 0 | Redirect sets it for each kept entry; freeing the slot clears it |
| `head_ptr`, 2 bits | 0 | Allocation, redirect |
| `issue_ptr`, 2 bits | 0 | Request |
| `tail_ptr`, 2 bits | 0 | Delivery, killed drain, redirect |

- `head_ptr` is the next slot to allocate, and `tail_ptr` is the oldest entry.
- `issue_ptr` is the oldest QUEUED entry, or `head_ptr` when none is QUEUED.
- The entry at `issue_ptr` is committed when it is QUEUED, and it is the presented entry.
- Every other QUEUED entry is uncommitted.
- `life` holds the BASE lifecycle states FREE, QUEUED, OUTSTANDING and READY ([capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states)).
- `killed` marks wrong-path work (fetch-stage §4).
- The pointers are 2-bit slot indices. After slot 2 comes slot 0, before slot 0 comes slot 2, and value 3 is never reached from reset.
- These are the only state elements. No outstanding count and no pending-target flag exist, because BASE has no `redirect_pending` state.
- I1, occupancy: the slots from `tail_ptr` up to the slot before `head_ptr` are occupied, and all others are FREE.
  - Every slot is occupied when the slot at `head_ptr` is not FREE.
- I2, order: from `tail_ptr`, READY entries come first, then at most one OUTSTANDING entry at the slot before `issue_ptr`, then QUEUED entries.
- I3, killed: a killed entry is never READY.
  - A killed OUTSTANDING entry is always at `tail_ptr`, because a request needs the older outstanding entry gone or answered on the same edge (BASE).
- I4, ambiguous case: when every slot is occupied and `issue_ptr` equals `tail_ptr`, the slot at `tail_ptr` decides.
  - If it is QUEUED, all three entries are QUEUED. Otherwise all three are issued, READY or OUTSTANDING.

## 6. Behavior

| Event | Condition | Effect after an edge with `redirect_fire` low |
| --- | --- | --- |
| Response | The slot before `issue_ptr` is OUTSTANDING and `raw_response_transfer` is high | `instruction_write` writes the word. The slot becomes READY unless its entry is killed. |
| Request | `request_fire` is high | The slot at `issue_ptr` becomes OUTSTANDING, and `issue_ptr` moves to the next slot. `killed` is unchanged. |
| Delivery | `fetch_valid` and `fetch_accept` are high | The slot at `tail_ptr` becomes FREE with `killed` 0, and `tail_ptr` moves to the next slot. |
| Killed drain | A response for an entry with `killed` 1, which is at `tail_ptr` (I3) | The same as a delivery. |

- Events on one edge apply together from the pre-edge state.

| Output | Value |
| --- | --- |
| `present_valid` | High when the slot at `issue_ptr` is QUEUED |
| `present_slot` | Equals `issue_ptr` |
| `fetch_valid` | High when the slot at `tail_ptr` is READY |
| `fetch_slot` | Equals `tail_ptr` |
| `pc_write` | High when the slot at `head_ptr` is FREE, or when a delivery or a killed drain occurs, with or without a redirect |
| `pc_write_slot` | Equals `head_ptr` |
| `pc_write_data` | Equals `next_fetch_pc`, with no redirect mux |
| `instruction_write` | High when the slot before `issue_ptr` is OUTSTANDING and `raw_response_transfer` is high |
| `instruction_write_slot` | The slot before `issue_ptr` |

- An allocation is a `pc_write` edge with `redirect_fire` low.
- An allocation makes the slot at `head_ptr` QUEUED and moves `head_ptr` to the next slot.
- A slot freed on an edge may be allocated on that edge ([BASE same-edge reuse](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states)).
- A free slot always has `killed` 0, so allocation needs no clear.

| Priority | Condition | `next_fetch_pc` after the edge |
| --- | --- | --- |
| 1 | `rst_n` low (asynchronous) | `PC_RESET_VEC` |
| 2 | `redirect_fire` high | `redirect_target` |
| 3 | An allocation occurs | The value plus 4 |
| 4 | None of the above | Unchanged |

| Slot role on a redirect edge | Pre-edge state and same-edge event | Slot `life` after the redirect edge | Slot `killed` after the redirect edge | Pointers after |
| --- | --- | --- | --- | --- |
| Slot before `issue_ptr` | READY; a delivery on this edge is ignored | FREE | 0 | `tail_ptr` becomes `issue_ptr` |
| Slot before `issue_ptr` | OUTSTANDING, response on this edge, which is discarded | FREE | 0 | `tail_ptr` becomes `issue_ptr` |
| Slot before `issue_ptr` | OUTSTANDING, no response | OUTSTANDING | 1 | `tail_ptr` becomes this slot |
| Slot before `issue_ptr` | QUEUED (only when all three entries are QUEUED, I4), or FREE | FREE | 0 | `tail_ptr` becomes `issue_ptr` |
| Slot at `issue_ptr` | QUEUED, no request on this edge | QUEUED | 1 | `issue_ptr` unchanged; `head_ptr` becomes the slot after `issue_ptr` |
| Slot at `issue_ptr` | QUEUED, request on this edge | OUTSTANDING | 1 | `issue_ptr` and `head_ptr` become the slot after `issue_ptr` |
| Slot at `issue_ptr` | FREE, or READY when every slot is occupied and all are issued (I4) | FREE | 0 | `issue_ptr` unchanged; `head_ptr` becomes `issue_ptr` |
| Slot after `issue_ptr` | FREE, uncommitted QUEUED or READY | FREE | 0 | None |

- `tail_ptr` comes from the rows for the slot before `issue_ptr`, and `head_ptr` and `issue_ptr` from the rows for the slot at `issue_ptr`.
- A redirect edge allocates nothing, so no slot becomes QUEUED and the target is allocated on the next edge ([FCU-D10](#10-decisions-and-open-items)).
- At most two entries are kept, one OUTSTANDING and one committed QUEUED, so a free slot remains for the target (IF-A2).
- A kept QUEUED entry stays at `issue_ptr`, so `present_valid` and `present_slot` stay stable until its request transfers.
- A redirect edge may have `pc_write` high, because `pc_write` has no redirect term (FCU-D4).
- That write never changes a kept entry, because it never selects the slot of one.
  - If the slot at `head_ptr` is FREE, it holds no entry.
  - Otherwise `pc_write` high means every slot is occupied, `head_ptr` equals `tail_ptr`, and a delivery or a killed drain frees that slot.
  - A kept entry at `tail_ptr` is OUTSTANDING without a response, or QUEUED (I4), so neither event occurs and `pc_write` is low.

## 7. Timing and Control

- `present_valid`, `fetch_valid`, `present_slot`, `fetch_slot`, `pc_write_slot`, `pc_write_data` and `instruction_write_slot` depend on registered state only.
- `pc_write` and `instruction_write` are combinational from the inputs, and the edge samples them.
- They never reach `present_valid` or `fetch_valid` within a cycle.
- `redirect_target` reaches only `next_fetch_pc`, never `pc_write_data` within a cycle, because it is one input of the register with no path through the adder (IF-A2).
- The target's earliest presentation is two cycles after the redirect cycle (BASE).
- A kept QUEUED entry at `issue_ptr` goes first, so the target waits for that entry's request transfer.
- The target may be presented while a killed entry is OUTSTANDING.
- Its request transfers no earlier than the edge that takes that response, because `OBI_OUTSTANDING_MAX` is 1 (BASE).

### When valid

| Signal group | When valid |
| --- | --- |
| `present_valid`, `fetch_valid`, `present_slot`, `fetch_slot`, `pc_write_slot`, `instruction_write_slot` | Every cycle, from registered state |
| `pc_write`, `instruction_write` | Each edge |
| `pc_write_data` | When `pc_write` is high |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset (`rst_n` low) | All state clears asynchronously (section 5), so `present_valid` and `fetch_valid` fall without a clock edge. `pc_write_data` shows `PC_RESET_VEC`. `pc_write` is high, because every slot is FREE, and no entry becomes valid, because `life` stays FREE. No edge with `rst_n` low counts a request, response, delivery or allocation. |
| Stall | The unit has no stall input. A low `fetch_accept` leaves a READY entry in place, and allocation holds while no slot is free or freed. |
| Flush | The unit has no flush input. A redirect is the only cancellation of wrong-path work, and it never removes a committed entry before its request transfers (section 6). |

- Before edge 1, `head_ptr` is 0, `issue_ptr` is 2 and `tail_ptr` is 0.
- Slot 0 is READY with `pc` 0x1C, slot 1 is OUTSTANDING with 0x20, and slot 2 is QUEUED with 0x24 and presented.
- Every slot is occupied.

| Trace edge | Inputs | Buffer writes | State after: `head_ptr` / `issue_ptr` / `tail_ptr`; slots 0 / 1 / 2 | Notes |
| --- | --- | --- | --- | --- |
| 1 | `redirect_fire` high, `redirect_target` 0x100; `request_fire` high, which grants slot 2; `raw_response_transfer` high, which answers slot 1; `fetch_accept` low | `instruction_write` to slot 1; `pc_write` low | 0 / 0 / 2; FREE / FREE / OUTSTANDING 0x24, killed | Slot 1 is freed and its response is discarded. Slot 0 is freed. Slot 2 is kept at `tail_ptr` (I3). `present_valid` is low, and `next_fetch_pc` is 0x100. |
| 2 | None | `pc_write` high to slot 0 with data 0x100 | 1 / 0 / 2; QUEUED 0x100 / FREE / OUTSTANDING 0x24, killed | The target is allocated, and `next_fetch_pc` is 0x104. `present_valid` is high from the next cycle. |
| 3 | `raw_response_transfer` high, which answers slot 2; `request_fire` high, which grants slot 0 | `instruction_write` to slot 2; `pc_write` high to slot 1 with data 0x104 | 2 / 1 / 0; OUTSTANDING 0x100 / QUEUED 0x104 / FREE | The killed drain frees slot 2 with `killed` 0 and moves `tail_ptr` to slot 0. The target transfers on the drain edge, and `next_fetch_pc` is 0x108. |

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| A request transfer happens only if no older outstanding entry remains after the edge | The subordinate ([BASE](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states), `OBI_OUTSTANDING_MAX` 1) | Outside the contract. The unit does not guard it. |
| `request_fire` is high only while `present_valid` is high | `fetch_obi_interface` | A request would land on a slot that is not QUEUED. |
| `redirect_fire` is high only on an edge with `rst_n` high | The environment | Outside the contract. |
| Redirect targets are aligned | BASE leaves misaligned targets outside, and [redirect-unit.md](redirect-unit.md) keeps them outside | The unit passes the target through and does not check it. |
| `next_fetch_pc` wraps at `ADDR_WIDTH` bits, and fetch addresses stay in the code region | The environment (fetch-stage §6) | Outside the contract. |
| After release, the subordinate returns no response for a pre-reset transaction | The subordinate (BASE) | Outside the contract. |
| Every input is 0 or 1 | The environment (fetch-stage O4) | Outside the contract. |

| Case | Inputs | Result |
| --- | --- | --- |
| Unexpected response | `raw_response_transfer` high while the slot before `issue_ptr` is not OUTSTANDING | No state change, and verification reports it ([FOI-D3](fetch-obi-interface.md)) |
| Back-to-back redirect | `redirect_fire` high on the edge after a redirect edge | The first target is never allocated, because it was wrong-path work, and `next_fetch_pc` takes the second target |

## 9. Verification

- No test for this unit exists, so every check is planned.
- Expected values come from sections 5 to 8 and [fetch-buffer.md](fetch-buffer.md), not from the DUT.
- Stage-level checks are in [fetch-stage.md](fetch-stage.md) §8.

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Reset (section 7) | `rst_n` asserted while `next_fetch_pc` holds another value | `pc_write_data` is `PC_RESET_VEC` after propagation, without an edge |
| Sequential step (section 6) | Three consecutive edges from reset, each with a free slot | The allocated `pc` takes 0x0, 0x4, 0x8 in order |
| Hold when no slot is free (section 6) | Every slot occupied, no delivery or killed drain, several edges | `pc_write` low; `pc_write_data` unchanged |
| Redirect loads the target (section 6) | `redirect_fire` high on an edge where the slot at `head_ptr` is FREE | `next_fetch_pc` takes `redirect_target`, not the target plus 4 |
| Redirect with all entries READY (section 6) | Before edge 1: `next_fetch_pc` 0x2C; all three pointers 0; slots READY 0x20, 0x24, 0x28; `fetch_accept` low. Edge 1: `redirect_fire` high, `redirect_target` 0x100. Edge 2: no input. Edge 3: `request_fire` high | Edge 1: no slot is written, all slots FREE, `next_fetch_pc` 0x100. Edge 2: 0x100 is written to slot 0 as QUEUED, `next_fetch_pc` 0x104, and `present_valid` is high from the next cycle, two cycles after the redirect cycle. Edge 3: slot 0 OUTSTANDING, 0x104 written to slot 1, pointers 2 / 1 / 0, `next_fetch_pc` 0x108 |
| Back-to-back redirect (section 8) | `redirect_fire` high on two consecutive edges | The first target is never allocated |
| No path from redirect to `pc_write_data` (section 7) | Toggle `redirect_target` with `redirect_fire` low | `pc_write_data` and `next_fetch_pc` do not change within the cycle |
| Write enables off the presented path (section 7) | Toggle `fetch_accept` and `raw_response_transfer` within a cycle | `present_valid` and `fetch_valid` do not change until the edge |
| Slot-role table (section 6) | One stimulus per row of the table | Each row gives the stated `life`, `killed` and pointers |
| Trace (section 7) | The three edges of the trace | Each State after column |
| Pointer wrap, fill (section 5) | Empty, all pointers 2, `next_fetch_pc` 0x20. Edges 1 to 3: `request_fire` high from edge 2 whenever `present_valid` is high, `raw_response_transfer` high from edge 3 | Edge 1: 0 / 2 / 2; FREE / FREE / QUEUED 0x20. Edge 2: 1 / 0 / 2; QUEUED 0x24 / FREE / OUTSTANDING 0x20. Edge 3: 2 / 1 / 2; OUTSTANDING 0x24 / QUEUED 0x28 / READY 0x20 |
| Pointer wrap, steady (section 5) | Continue with `fetch_accept` high on edges 4 to 6 | Edge 4: 0 / 2 / 0; READY 0x24 / OUTSTANDING 0x28 / QUEUED 0x2C. Edge 5: 1 / 0 / 1; QUEUED 0x30 / READY 0x28 / OUTSTANDING 0x2C. Edge 6: 2 / 1 / 2; OUTSTANDING 0x30 / QUEUED 0x34 / READY 0x2C. Deliveries come in the order 0x20, 0x24, 0x28 |
| Reuse of a slot freed on the edge (section 6) | Before edge 1: `next_fetch_pc` 0x14; pointers 0 / 2 / 0; slots READY 0x08, OUTSTANDING 0x0C, QUEUED 0x10. Edge 1: all inputs low. Edge 2: `fetch_accept` high. Edge 3: `request_fire` and `raw_response_transfer` high | Edge 1: nothing changes, `pc_write` low. Edge 2: 0x14 is written to slot 0, `next_fetch_pc` 0x18, pointers 1 / 2 / 1. Edge 3: slot 1 READY, slot 2 OUTSTANDING, pointers 1 / 0 / 1, `pc_write` low, `next_fetch_pc` 0x18 |
| Occupied and empty ring (section 5) | `fetch_accept` low. Every slot QUEUED; every slot issued; empty | Every slot QUEUED: `pc_write` low, `present_valid` high, `fetch_valid` low. Every slot issued: `pc_write` low, `present_valid` low. Empty: `pc_write` high, `present_valid` low, `fetch_valid` low |
| Delivery ignored on a redirect (section 6) | `fetch_accept` high on a redirect edge with a READY entry at `tail_ptr` | The entry is freed and not delivered |
| Killed drain (section 6) | A response for a killed OUTSTANDING entry | The entry becomes FREE and never READY |
| Unexpected response (section 8) | `raw_response_transfer` high with nothing OUTSTANDING | No state change |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| FCU-D1 | The controller owns every state element with a reset and all logic on them, and `fetch_buffer` owns only `pc` and `instruction`. | Entries are allocated before data arrives and a redirect reloads the pointers, so ordering and lifecycle belong in one module. |
| FCU-D2 | The controller drives the write slots and enables and the read slots of `fetch_buffer`, and `pc_write_data` is `next_fetch_pc` with no redirect mux. |  |
| FCU-D3 | `next_fetch_pc` takes reset, then the redirect target, then allocation plus 4, then hold. | The target is one mux input, so it has no path through the adder. |
| FCU-D4 | `pc_write` has no redirect term. | The redirect has priority on `next_fetch_pc`, so an extra term adds nothing, and the write is safe (section 6). |
| FCU-D5 | The three slots hold age order with `head_ptr`, `issue_ptr` and `tail_ptr`, and the slot at `head_ptr` tells an occupied ring from an empty one. |  |
| FCU-D6 | The outstanding state is derived from the slot before `issue_ptr`, and it is not stored. |  |
| FCU-D7 | The committed state is derived from the entry at `issue_ptr`, and `present_valid` equals it. |  |
| FCU-D8 | `killed` is one bit per entry. A redirect sets it for each kept entry, freeing the slot and reset clear it, and only the response path reads it. |  |
| FCU-D9 | Slot indices are 2 bits and wrap from 2 to 0 and from 0 to 2. |  |
| FCU-D10 | A redirect edge allocates nothing, and the target is allocated on the next edge. |  |

- History: 2026-11-04 the Owner settled FB-O1 to FB-O7.
  - 2026-11-05 IF-A2 and the remaining decisions were accepted.
  - 2026-11-06 IF-A3 accepted FCU-O1, FCU-O4 and FCU-O7 to FCU-O13, and retired FCU-O3.
  - IF-A3 also resolved the controller issue policy, formerly open item 1.
  - 2026-11-07 rewritten in the block spec format, IDs renumbered.
  - A claim that the target waits for the stale entry to drain was removed, because BASE presents the target earlier.
  - IF-A2 and IF-A3 stay in [BASE](5-stage-baseline-core.md#instruction-fetch-organization).

| Old ID | New ID | Status |
| --- | --- | --- |
| FCU-O13, FB-O1 | FCU-D1 | Kept; FB-O1 superseded by IF-A3 and this decision |
| FCU-O4 | FCU-D2 | Kept |
| FCU-O5 | FCU-D3 | Kept |
| FCU-O6 | FCU-D4 | Kept; an internal name is replaced by allocation |
| FCU-O7, FB-O2 | FCU-D5 | Kept; FB-O2 moved |
| FCU-O8, FB-O3 | FCU-D6 | Kept; FB-O3 moved |
| FCU-O9, FB-O4 | FCU-D7 | Kept; FB-O4 moved |
| FCU-O10, FB-O5 | FCU-D8 | Kept; FB-O5 moved; the clear on allocation is dropped, because a free slot always has the mark at 0 |
| FCU-O11, FB-O6 | FCU-D9 | Kept; FB-O6 moved |
| FCU-O12, FB-O7 | FCU-D10 | Kept; FB-O7 moved, and the write goes through `pc_write` |
| FCU-O1 | None | Retired: it recorded the port list, which section 3 holds, and the removed `alloc_valid` |
| FCU-O2 | None | Retired: it recorded an internal signal that equals `redirect_fire`, so the port event states it |
| FCU-O3 | None | Retired on 2026-11-06 with the removed port `alloc_valid`; section 1 keeps the absence of an allocation pause |

- Length: this spec runs to 8 pages, above the 3-5 page limit, because it has 16 ports, a slot-role table and 17 checks. The check rows carry the traces moved to section 9.
- Open items:
  - Drain and redirect allocation ([external-interrupt-extension.md](external-interrupt-extension.md) line 247): under IF-A2 the target is allocated on the edge after the redirect.
    - If that edge is in a drain freeze, the freeze must still allow this one allocation, but the extension does not say which edge.
    - Until its owner states the edge, the allocation on the edge after a redirect under drain is unspecified.
