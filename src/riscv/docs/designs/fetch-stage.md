# Fetch Stage

| Field | Value |
| --- | --- |
| Description | IF stage boundary; connects its ports to prefetch_unit by name. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/fetch_stage.sv`, module `fetch_stage`, instance `if_stage` in the core; `rtl/prefetch_unit.sv`, module `prefetch_unit`, instance `if_prefetch_unit` in `fetch_stage` |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md); [Hazard Control Unit](hazard-control-unit.md); [Fetch Controller Unit](fetch-controller-unit.md); [Fetch Buffer](fetch-buffer.md); [Fetch OBI Interface](fetch-obi-interface.md) |

## 1. Overview

- `fetch_stage` is the BASE IF stage ([instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization)).
- It turns the sequential and redirected address stream into the instruction stream offered to the IF/ID register: the `pc` and `instruction` of the oldest READY entry.
- It owns the instruction-side OBI port.
- It takes `redirect_fire` and `redirect_target` raw from EX, because inside IF a redirect only changes the fetch address and the entries (IF-D4).
- It has no hazard, MEM, load-use or pipeline-occupancy signal, because the HCU resolves global events, which reach it only as `fetch_accept` low (IF-D2, BASE IF-A1).
- It has no branch prediction, because the BASE baseline has none.
- It has no IF/ID register, because the core owns it (IF-D1).
- It does not throttle fetch for data traffic, because the ports are independent and a later shared path arbitrates through `gnt` (IF-D5).
- It does not decode instructions or check their legality, because ID owns decode.
- It has no bus-error, illegal-instruction or exception output, because BASE has none at this boundary.
- It checks no address range, because the code-region precondition belongs to the harness and the test program.
- It holds no logic of its own. The leaves own it: [Fetch Controller Unit](fetch-controller-unit.md), [Fetch Buffer](fetch-buffer.md) and [Fetch OBI Interface](fetch-obi-interface.md).

## 2. Block Design

```text
                                             clk             rst_n
                                              |                |
                                       +------------------------------+
redirect_fire <- redirect_unit         |                              | -> req (instruction OBI subordinate)
redirect_target <- redirect_unit       |                              | -> addr (instruction OBI subordinate)
gnt <- instruction OBI subordinate     |                              | -> we (instruction OBI subordinate)
rvalid <- instruction OBI subordinate  |                              | -> be (instruction OBI subordinate)
rdata <- instruction OBI subordinate   |         fetch_stage          | -> wdata (instruction OBI subordinate)
                                       |                              | -> rready (instruction OBI subordinate)
                                       |                              | -> fetch_valid (IF/ID register)
                                       |                              | -> fetch_pc (IF/ID register)
                                       |                              | -> fetch_instruction (IF/ID register)
                                       +------------------------------+
                                              ^
                             fetch_accept <- hazard_control_unit
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | Core clock | Rising-edge clock of the fetch state. |
| `rst_n` | Input | 1 | Core reset | Active-low reset. It asserts asynchronously and releases synchronously. |
| `fetch_accept` | Input | 1 | `hazard_control_unit` | High lets IF/ID take an entry this edge, if one is valid. Low blocks it. |
| `redirect_fire` | Input | 1 | `redirect_unit` | A taken redirect from EX transfers on this edge. |
| `redirect_target` | Input | `ADDR_WIDTH` | `redirect_unit` | Target address of the redirect. It is valid when `redirect_fire` is high. |
| `gnt` | Input | 1 | Instruction OBI subordinate | Grant of the request that `req` raises. |
| `rvalid` | Input | 1 | Instruction OBI subordinate | A response is valid. |
| `rdata` | Input | `INSTR_WIDTH` | Instruction OBI subordinate | Instruction word of the response. |
| `req` | Output | 1 | Instruction OBI subordinate | Instruction request for the presented entry. |
| `addr` | Output | `ADDR_WIDTH` | Instruction OBI subordinate | Request address, the `pc` of the presented entry. |
| `we` | Output | 1 | Instruction OBI subordinate | Write enable of the read-only port. |
| `be` | Output | 4 | Instruction OBI subordinate | Byte enable. |
| `wdata` | Output | `DATA_WIDTH` | Instruction OBI subordinate | Write data. |
| `rready` | Output | 1 | Instruction OBI subordinate | Response ready. |
| `fetch_valid` | Output | 1 | IF/ID register | The oldest entry is READY and offered to IF/ID. |
| `fetch_pc` | Output | `ADDR_WIDTH` | IF/ID register | The `pc` of that entry. |
| `fetch_instruction` | Output | `INSTR_WIDTH` | IF/ID register | The instruction word of that entry. |

- `ADDR_WIDTH`, `DATA_WIDTH` and `INSTR_WIDTH` are all 32, from `riscv_pkg`.
- The instruction word is the 32-bit base encoding, not ILEN.
- `FETCH_DEPTH` is 3, and `PC_RESET_VEC` is 0, both from `riscv_pkg` ([BASE purpose and boundary](5-stage-baseline-core.md#purpose-and-boundary)).
- `OBI_OUTSTANDING_MAX` is 1 on the instruction port. It is a link contract, not an OBI property and not a port ([BASE OBI baseline](5-stage-baseline-core.md#obi-baseline-configuration)).

## 4. Internal Structure

- The BASE hierarchy is core, IF, Prefetch Unit and three leaves ([instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization)).
- `fetch_stage` has one child, `prefetch_unit`, which has the three leaves.
- Module names have no `riscv_` prefix, and a file is the module name with `.sv`.
- Instance names take the stage prefix, the pattern of [decode-stage.md](decode-stage.md#hierarchy-and-naming-d1) (IF-D6).
- `fetch_stage` connects its 17 ports to `prefetch_unit` by name, with no logic and no internal nets.
- `prefetch_unit` has the same 17 ports with the same names and widths and no logic of its own, so it has no separate spec (IF-D9).

| Module | Instance name | Instantiated by | Role |
| --- | --- | --- | --- |
| `fetch_stage` | `if_stage` | Core | IF stage boundary |
| `prefetch_unit` | `if_prefetch_unit` | `fetch_stage` | Connects the three leaves |
| `fetch_controller_unit` | `if_fetch_controller_unit` | `prefetch_unit` | Fetch control state and logic ([spec](fetch-controller-unit.md)) |
| `fetch_buffer` | `if_fetch_buffer` | `prefetch_unit` | `pc` and `instruction` payload ([spec](fetch-buffer.md)) |
| `fetch_obi_interface` | `if_fetch_obi_interface` | `prefetch_unit` | Instruction OBI port, stateless ([spec](fetch-obi-interface.md)) |

| Leaf | Takes from the stage ports | Drives to the stage ports |
| --- | --- | --- |
| `fetch_controller_unit` | `clk`, `rst_n`, `redirect_fire`, `redirect_target`, `fetch_accept` | `fetch_valid` |
| `fetch_buffer` | `clk` | `fetch_pc`, `fetch_instruction` |
| `fetch_obi_interface` | `rst_n`, `gnt`, `rvalid`, `rdata` | `req`, `addr`, `we`, `be`, `wdata`, `rready` |

| Net | Width | Driver | Load |
| --- | --- | --- | --- |
| `pc_write` | 1 | `fetch_controller_unit` | `fetch_buffer` |
| `pc_write_slot` | 2 | `fetch_controller_unit` | `fetch_buffer` |
| `pc_write_data` | `ADDR_WIDTH` | `fetch_controller_unit` | `fetch_buffer` |
| `instruction_write` | 1 | `fetch_controller_unit` | `fetch_buffer` |
| `instruction_write_slot` | 2 | `fetch_controller_unit` | `fetch_buffer` |
| `present_slot` | 2 | `fetch_controller_unit` | `fetch_buffer` |
| `fetch_slot` | 2 | `fetch_controller_unit` | `fetch_buffer` |
| `present_valid` | 1 | `fetch_controller_unit` | `fetch_obi_interface` |
| `present_pc` | `ADDR_WIDTH` | `fetch_buffer` | `fetch_obi_interface` |
| `request_fire` | 1 | `fetch_obi_interface` | `fetch_controller_unit` |
| `raw_response_transfer` | 1 | `fetch_obi_interface` | `fetch_controller_unit` |
| `response_data` | `INSTR_WIDTH` | `fetch_obi_interface` | `fetch_buffer` |

## 5. State

- None, because the stage is a wrapper with no logic.
- The controller owns the control state ([fetch-controller-unit.md](fetch-controller-unit.md) section 5).
- The buffer owns the payload ([fetch-buffer.md](fetch-buffer.md) section 5).
- The OBI leaf is stateless ([fetch-obi-interface.md](fetch-obi-interface.md) section 5).

## 6. Behavior

- The stage offers the oldest READY entry to IF/ID, and a redirect cancels wrong-path work without retracting a presented request.

| Output | Value |
| --- | --- |
| `fetch_valid` | High when the oldest entry is READY, which the lifecycle decides, not the payload |
| `fetch_pc`, `fetch_instruction` | The `pc` and instruction of the oldest READY entry in allocation order, not the lowest PC |
| `req` | High when an entry is presented and not yet granted |
| `addr` | The `pc` of that entry |
| `we`, `be`, `wdata`, `rready` | Constant: `we` 0, `be` all four bytes, `wdata` 0, `rready` 1, so every response is accepted and a killed one is drained |

| Condition | Effect at the stage ports | Effect on the entries |
| --- | --- | --- |
| Reset (`rst_n` low) | `req` and `fetch_valid` fall after reset propagation, without a clock edge. No request, response, delivery or allocation counts. | Every entry is FREE. The first address allocated after release is `PC_RESET_VEC`. |
| Redirect (`redirect_fire` high, `rst_n` high) | No delivery, whatever `fetch_accept` is, and `fetch_valid` is low after the edge. A presented entry keeps `req` and `addr` stable until its grant. | The four BASE cases apply ([stale responses](5-stage-baseline-core.md#stale-instruction-responses-after-redirect); [slot-role table](fetch-controller-unit.md)). The target is allocated on the next edge as a fresh QUEUED entry (IF-A2). |
| Delivery (`rst_n` high, `redirect_fire` low, `fetch_valid` and `fetch_accept` high) | IF/ID captures `fetch_pc` and `fetch_instruction`. | The delivered entry is freed, and its slot may be allocated on the same edge (BASE). |
| No delivery (`rst_n` high, `redirect_fire` low, `fetch_valid` or `fetch_accept` low) | While `fetch_valid` is high, `fetch_valid`, `fetch_pc` and `fetch_instruction` keep showing the same entry until a delivery or a redirect frees it. | No READY entry is freed. Allocation and presentation continue until every entry is occupied (BASE IF-A1). |

- An older OUTSTANDING entry does not block presentation, because the subordinate holds `gnt` low until it can accept (BASE).
- The request and response transfers follow the [BASE event definitions](5-stage-baseline-core.md#obi-response-validity-and-reset).

## 7. Timing and Control

- `fetch_valid`, `fetch_pc`, `fetch_instruction`, `req` and `addr` depend on registered state only.
- No path from `gnt`, `rvalid`, `rdata`, `fetch_accept`, `redirect_fire` or `redirect_target` reaches them within a cycle, because BASE forbids a response bypass ([capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states)).
- The stage takes no data-port signal, so no path from the data port to `req` exists (BASE IF-A1).
- The edge samples `fetch_accept`, `redirect_fire` and `redirect_target` with the other inputs.
- Responses are never back-pressured, because `rready` is constant 1 and an OUTSTANDING entry reserved its storage before its grant.

### When valid

| Signal group | When valid |
| --- | --- |
| `fetch_valid` | Every cycle, from registered state |
| `fetch_pc`, `fetch_instruction` | When `fetch_valid` is high |
| `req` | Every cycle. Once high, it stays high until the grant of that entry or reset |
| `addr` | When `req` is high. It is stable until the grant of that entry or reset |
| `we`, `be`, `wdata`, `rready` | Always, including reset |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset (`rst_n` low) | As in the Reset row of section 6. |
| Stall | The stage has no stall input. A low `fetch_accept` holds the delivery, and fetch continues as in the No delivery row of section 6 (IF-D5). |
| Flush | The stage has no flush input. A redirect is the only cancellation of wrong-path work, and the IF/ID flush is the HCU's. |

- Before edge E, S1 is READY with `pc` 0x08 and I1, and S2 is OUTSTANDING with `pc` 0x0C.
- S3 is QUEUED and presented with `pc` 0x10, and the next allocation address is 0x14.

| Cycle / edge | Stage inputs | Stage outputs | Effect |
| --- | --- | --- | --- |
| Cycle before E | `fetch_accept` high, `gnt` high, `rvalid` high with `rdata` I2, the word at 0x0C | `fetch_valid` high with 0x08 and I1; `req` high with `addr` 0x10 | Nothing changes until the edge. |
| Edge E | The inputs of the cycle before E | IF/ID captures 0x08 and I1 | S1 is delivered and freed, and reallocated with 0x14. S2 receives I2 and becomes READY. S3 is granted and becomes OUTSTANDING. One entry stays outstanding. |
| Cycle after E | None | `fetch_valid` high with 0x0C and I2; `req` high with `addr` 0x14 | S3 no longer waits for a grant, so 0x14 is presented. |

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every request address is in the code region, including speculative and wrong-path fetches. Test images end with safe control flow and NOP padding, because the frontend may request `FETCH_DEPTH` words beyond the instruction in IF/ID. | The harness and the test program ([BASE stale responses](5-stage-baseline-core.md#stale-instruction-responses-after-redirect)) | Outside the contract. The stage checks no address range. |
| The HCU drives `fetch_accept` consistently with the IF/ID stall and flush, so the stage frees an entry exactly when IF/ID captures it | `hazard_control_unit` ([HCU-D4](hazard-control-unit.md)) | An entry is lost or delivered twice. |
| The subordinate holds `gnt` low until it can accept, and returns no response for a pre-reset transaction after release | The instruction OBI subordinate (BASE) | Outside the contract. |
| `redirect_fire` is already low while EX cannot advance | `redirect_unit` ([BASE redirect event](5-stage-baseline-core.md#redirect-event-and-pipeline-recovery)) | Outside the contract. |
| Every input is 0 or 1 | The environment (IF-D10) | Outside the contract. |

| Case | Inputs | Result |
| --- | --- | --- |
| Unexpected response | `rvalid` high with no OUTSTANDING entry | The response is drained with no state change and no READY entry, and verification reports a protocol violation |
| Accept without a valid entry | `fetch_accept` high with `fetch_valid` low | `fetch_accept` has no effect on that edge |

## 9. Verification

- No test for the stage exists, so every check is planned.
- Expected values come from the BASE rules cited and the trace in section 7, not from the DUT.
- Leaf-level checks are in the leaf specs ([controller](fetch-controller-unit.md), [buffer](fetch-buffer.md), [OBI leaf](fetch-obi-interface.md)).

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Steady state ([BASE](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states)) | The trace of section 7 | One delivery per edge, and one entry stays outstanding |
| No combinational path to `req` (section 7) | Toggle `gnt`, `rvalid`, `rdata`, `fetch_accept`, `redirect_fire` and `redirect_target` within a cycle | `req`, `addr` and the delivery outputs change only after an edge |
| Oldest-first delivery (section 6) | Entries allocated in order with decreasing numeric PC after a redirect | Delivery follows allocation order |
| Redirect, READY entry (section 6) | A redirect with a READY entry and `fetch_accept` high | The entry is freed and never delivered |
| Redirect, response on the edge (section 6) | A redirect with an OUTSTANDING entry and a response on the edge | The response is discarded and the entry is FREE |
| Redirect, presented entry granted on the edge (section 6) | A redirect with a presented entry and a grant on the edge | The entry becomes killed OUTSTANDING, and its response is drained |
| Redirect, unpresented entry (section 6) | A redirect with an unpresented QUEUED entry | The entry is freed and never presented |
| Redirect target (section 6) | A redirect with no entry kept, then the next edge | No entry is allocated on the redirect edge, and `fetch_valid` is low after it. The target is allocated on the next edge, and `req` shows it two cycles after the redirect cycle at the earliest |
| Redirect with an OUTSTANDING entry without a response, and with a presented entry not granted (section 6) | Before edge 1: S1 READY (`pc` 0x1C), S2 OUTSTANDING (0x20), S3 QUEUED and presented (0x24). Edge 1: `redirect_fire` high, `redirect_target` 0x100, `fetch_accept` low, `gnt` low, `rvalid` low. Edge 2: no input. Edge 3: `rvalid` high for S2, `gnt` high for S3. Edge 4: `gnt` low, `rvalid` low. Edge 5: `rvalid` high for S3, `gnt` high for the target. Edge 6: `rvalid` high for the target. Edge 7: `fetch_accept` high | Edge 1: S1 is freed, S2 and S3 are kept as killed, `fetch_valid` is low, and `req` stays high with `addr` 0x24. Edge 2: the target 0x100 is allocated as a fresh QUEUED entry, and `req` and `addr` still show S3. Edge 3: S2's response is drained, and S3 is granted and becomes killed OUTSTANDING. From the next cycle `req` is high with `addr` 0x100, so the target is presented while S3 is OUTSTANDING. Edge 4: `gnt` low holds the target back. Edge 5: S3's response is drained, and the target's request transfers on this edge, no earlier. The drained responses leave their entries FREE and never READY, so `fetch_valid` stays low. Edge 6: `fetch_valid` goes high with 0x100 and its word. Edge 7: the target is delivered |
| HCU stall (section 6) | Before edge 1: S1 READY (0x08, I1), S2 OUTSTANDING (0x0C), S3 QUEUED and presented (0x10), next allocation address 0x14. `fetch_accept` low on edges 1 and 2, `redirect_fire` low, and the memory responds one cycle after a grant. Edge 1: `rvalid` high for S2, `gnt` high for S3. Edge 2: `rvalid` high for S3. Edges 3 to 5: `fetch_accept` high | Edge 1: no delivery, S2 READY, S3 OUTSTANDING, no entry FREE so no allocation, and `fetch_valid` stays high with 0x08 and I1. Edge 2: S3 READY, three READY entries, and `req` low. Edge 3: 0x08 and I1 are delivered, S1 is reallocated with 0x14, and `req` shows 0x14 from the next cycle. Edges 4 and 5: 0x0C and 0x10 are delivered on consecutive edges without waiting for memory (IF-A1). No entry is lost or reordered after the release |
| Accept without a valid entry (section 8) | `fetch_accept` high while no entry is READY | `fetch_accept` has no effect on that edge |
| Unexpected response (section 8) | `rvalid` with no OUTSTANDING entry | No state change, and the violation is reported |
| Reset (section 6) | `rst_n` asserted with entries in every state | `req` and `fetch_valid` are low after propagation, every entry is FREE, and the first address presented after release is `PC_RESET_VEC`. Payload is not checked |
| Pointer wrap (BASE capacity) | The two Pointer wrap rows of [fetch-controller-unit.md](fetch-controller-unit.md) section 9, observed at the stage ports | Delivery order is allocation order across slot reuse |
| Hold rule (section 6) | An entry first presented on a redirect edge, then `gnt` low for several edges, with a younger QUEUED entry behind it | `req` and `addr` stay on the presented entry until its grant. The redirect keeps it, and the younger entry is not presented |
| Composition with reset (section 6) | Before edge 1: S2 OUTSTANDING (0x0C), S3 QUEUED and presented (0x10), S4 QUEUED (0x14) behind it. `fetch_accept` is low throughout. Edges 1 and 2: `gnt` low, `rvalid` low. Edge 3: `gnt` high, `rvalid` high with I2. Edge 4: `gnt` low, `rvalid` low. `rst_n` falls between edges 4 and 5, so it is low at edge 5, and it is high again at edge 6 with `gnt` low and `rvalid` low | Edges 1 and 2: `req` high with `addr` 0x10, unchanged. Edge 3: S2 READY with I2, S3 OUTSTANDING, and one entry outstanding. The cycle after edge 3: `req` high with `addr` 0x14 while `gnt` is low. Edge 5: every entry FREE, and `req` and `fetch_valid` low after propagation. Edge 6: `req` is low, and the edge allocates the first entry, so `req` shows `PC_RESET_VEC` from the next cycle |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| IF-D1 | The core owns the IF/ID register, outside `fetch_stage`. | It follows the EX/MEM precedent ([memory-stage.md](memory-stage.md)) and the BASE IF/ID boundary. |
| IF-D2 | The HCU supplies the one global control, `fetch_accept`. The stage outputs are `fetch_valid`, `fetch_pc` and `fetch_instruction`, and the stage has no hazard or MEM knowledge. | The parent resolves arbitration (BASE PR-D1), so IF stays free of hazard logic. |
| IF-D3 | The instruction OBI ports use the plain names of `rtl/memory_stage.sv`, and `fetch_obi_interface` drives the constant fields. The core adds the `instr_` prefix. | It follows the precedent and the BASE constant port fields. |
| IF-D4 | `redirect_fire` and `redirect_target` come raw from EX. Global events reach IF only as `fetch_accept`. | A redirect only changes the fetch address and the entries inside IF, so local effects stay direct and global effects go through the HCU. |
| IF-D5 | The frontend has no MEM-wait freeze and no MEM-occupancy rule (BASE IF-A1). Fetch continues during any stall until every entry is occupied. | The two ports and memory models are independent, so withholding fetch protects nothing, and a later shared path arbitrates through `gnt`. |
| IF-D6 | Module, file and instance names are as in section 4. | Instance names take the stage prefix, and `fetch_obi_interface` avoids the `obi_interface` ambiguity. |
| IF-D7 | `FETCH_DEPTH` 3 and the entry lifecycle type are defined in `riscv_pkg`. `OBI_OUTSTANDING_MAX` is not a port. | The Owner placed them in the package when writing the buffer. |
| IF-D8 | `rst_n` is a stage input. | BASE [reset architecture](5-stage-baseline-core.md#reset-architecture). |
| IF-D9 | `prefetch_unit` has the same 17 ports as `fetch_stage`, and `fetch_stage` connects them by name with no logic and no internal nets. There is no separate `prefetch-unit.md`. | A wrapper with no logic needs no spec of its own, so this spec states it. |
| IF-D10 | Inputs are 0 or 1 only. X and Z are outside the contract. | It follows the accepted EX and WB precedent. |
| IF-D11 | A delivery, with `fetch_valid` and `fetch_accept` high, is the only event that frees the oldest READY entry. | It is the standard valid and accept handshake, so the HCU needs no extra gating. |

- History: 2026-11-01 the Owner accepted F-a to F-f, N1, N3, O4 and O5.
  - 2026-11-01 D-1 and D-2 were resolved: `PC_RESET_VEC` entered the package, and BASE IF-A1 was accepted.
  - 2026-11-04 the Owner settled N2 and O1.
  - 2026-11-05 N4 and IF-A2 were accepted, and HCU-D4 resolved D-3.
  - 2026-11-06 IF-A3 moved the fetch control to the controller, amended O1, and resolved O2 and O3 in the controller design.
  - 2026-11-07 rewritten in the block spec format, IDs renumbered, F-d retired.
  - A claim that the target waits for the stale entry to drain was removed, because BASE presents the target earlier.
- Old ID map:
  - F-a to F-c map to IF-D1 to IF-D3 in order; all kept.
  - F-e and F-f map to IF-D4 and IF-D5; both kept.
  - N1 to N4 map to IF-D6 to IF-D9 in order; all kept.
  - O4 and O5 map to IF-D10 and IF-D11; both kept.
  - F-d is retired, because it recorded who writes the RTL, which is process and not behavior.
  - O1, O2 and O3 moved to FCU-D1, FCU-D6 and FCU-D5, because IF-A3 gave the controller those decisions.
  - IF-A2 and IF-A3 are BASE IDs and are not renumbered.
- Length: this spec runs to 7 pages, above the 2-4 page limit, because it has 17 ports, a twelve-net table and 16 checks. The check rows carry the traces.
- Open items: none.
