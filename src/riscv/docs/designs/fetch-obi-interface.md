# Fetch OBI Interface

| Field | Value |
| --- | --- |
| Description | Stateless instruction OBI port for the selected fetch entry, with request and raw response events to the fetch controller. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/fetch_obi_interface.sv`, module `fetch_obi_interface`, instance `if_fetch_obi_interface` in `prefetch_unit` |
| Parent | [Fetch stage](fetch-stage.md); [five-stage BASE core](5-stage-baseline-core.md); [Fetch Controller Unit](fetch-controller-unit.md); [Fetch Buffer](fetch-buffer.md) |

## 1. Overview

- The leaf is the instruction-port OBI block of the Prefetch Unit.
- It turns the entry that `fetch_controller_unit` presents into the OBI request, and it drives the constant read-only port fields.
- It reports the request transfer and the raw response transfer to `fetch_controller_unit`.
- It is stateless and has no clock.
- It owns no entry state, storage, outstanding count or allocation, because the controller and the buffer do.
- It checks no bus error, timeout or address range, because BASE has none at this boundary.

## 2. Block Design

```text
                                                         rst_n
                                                           |
                                              +--------------------------+
present_valid <- fetch_controller_unit        |                          | -> req (instruction OBI subordinate)
present_pc <- fetch_buffer                    |                          | -> addr (instruction OBI subordinate)
gnt <- instruction OBI subordinate            |                          | -> we (instruction OBI subordinate)
rvalid <- instruction OBI subordinate         |                          | -> be (instruction OBI subordinate)
rdata <- instruction OBI subordinate          |   fetch_obi_interface    | -> wdata (instruction OBI subordinate)
                                              |                          | -> rready (instruction OBI subordinate)
                                              |                          | -> request_fire (fetch_controller_unit)
                                              |                          | -> raw_response_transfer (fetch_controller_unit)
                                              |                          | -> response_data (fetch_buffer)
                                              +--------------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `rst_n` | Input | 1 | Core reset | Active-low reset. It qualifies the two events. |
| `gnt` | Input | 1 | Instruction OBI subordinate | Grant of the request that `req` raises. |
| `rvalid` | Input | 1 | Instruction OBI subordinate | A response is valid. |
| `rdata` | Input | `INSTR_WIDTH` | Instruction OBI subordinate | Instruction word of the response. |
| `present_valid` | Input | 1 | `fetch_controller_unit` | A presented entry exists. |
| `present_pc` | Input | `ADDR_WIDTH` | `fetch_buffer` | The `pc` of the presented entry. |
| `req` | Output | 1 | Instruction OBI subordinate | Instruction request for the presented entry. |
| `addr` | Output | `ADDR_WIDTH` | Instruction OBI subordinate | Request address, the `pc` of the presented entry. |
| `we` | Output | 1 | Instruction OBI subordinate | Write enable of the read-only port. |
| `be` | Output | 4 | Instruction OBI subordinate | Byte enable. |
| `wdata` | Output | `DATA_WIDTH` | Instruction OBI subordinate | Write data. |
| `rready` | Output | 1 | Instruction OBI subordinate | Response ready. |
| `request_fire` | Output | 1 | `fetch_controller_unit` | The request of the presented entry transfers on this edge. |
| `raw_response_transfer` | Output | 1 | `fetch_controller_unit` | A response transfers on this edge. It is not yet an expected response. |
| `response_data` | Output | `INSTR_WIDTH` | `fetch_buffer` | The instruction word handed to the buffer. |

- `ADDR_WIDTH`, `DATA_WIDTH` and `INSTR_WIDTH` are all 32, from `riscv_pkg`.

## 4. Internal Structure

- None, because the leaf has no sub-blocks.

## 5. State

- None, because the leaf is stateless (section 1).

## 6. Behavior

| Output | Value |
| --- | --- |
| `req` | Equals `present_valid` |
| `addr` | Equals `present_pc` |
| `we`, `be`, `wdata` | Constant: `we` 0, `be` all four bytes, `wdata` 0 |
| `rready` | Constant 1, so every response is accepted and a killed one is drained |
| `response_data` | Equals `rdata` |

| Condition | `request_fire` | `raw_response_transfer` |
| --- | --- | --- |
| Reset active (`rst_n` low) | 0 | 0 |
| Reset inactive, `req` high, `gnt` high, `rvalid` high | 1 | 1 |
| Reset inactive, `req` high, `gnt` high, `rvalid` low | 1 | 0 |
| Reset inactive, `req` low or `gnt` low, `rvalid` high | 0 | 1 |
| Reset inactive, `req` low or `gnt` low, `rvalid` low | 0 | 0 |

- BASE defines both events ([OBI response validity and reset](5-stage-baseline-core.md#obi-response-validity-and-reset)).

## 7. Timing and Control

- Every output is combinational in the same cycle, so the leaf adds no latency.
- No path from `gnt`, `rvalid`, `rdata` or `rst_n` reaches `req` or `addr`, because BASE forbids a response bypass ([capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states)).
- `req` ignores the outstanding entry, so the one-outstanding limit comes from `gnt`.
- After a request transfer, the next presented entry may drive `req` in the next cycle, and the leaf adds no idle cycle.

### When valid

| Signal group | When valid |
| --- | --- |
| `req` | Every cycle |
| `addr` | When `req` is high |
| `we`, `be`, `wdata`, `rready` | Always, including reset |
| `request_fire`, `raw_response_transfer` | Every edge |
| `response_data` | When `raw_response_transfer` is high |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset (`rst_n` low) | Both events are 0 (section 6). `req` falls after reset propagation without a clock edge, because the controller clears `present_valid` asynchronously. `rready` stays 1. |
| Stall | The leaf has no stall input. `req` and `addr` hold while `gnt` is low, as long as the presented entry holds (section 8). |
| Flush | The leaf has no flush, kill or redirect input. A redirect reaches it only through `present_valid` and `present_pc`. |

- Before edge 1, entry `S2` is granted and waits for its response, `S3` is presented with `pc` 0x10, and `S4` follows with `pc` 0x14.
- At edge 3, `gnt` accepts the new request while `rvalid` answers the older one, so the two signals belong to different transactions.

| Cycle / edge | `present_valid`, `present_pc` | `gnt`, `rvalid`, `rdata` | `req`, `addr` | `request_fire`, `raw_response_transfer`, `response_data` | Effect at the controller |
| --- | --- | --- | --- | --- | --- |
| c1 / edge 1 | 1, 0x10 | 0, 0, none | 1, 0x10 | 0, 0, none | None. `S3` waits for its grant and `S2` for its response. |
| c2 / edge 2 | 1, 0x10 | 0, 0, none | 1, 0x10 | 0, 0, none | None. `req` and `addr` are unchanged. |
| c3 / edge 3 | 1, 0x10 | 1, 1, I2 (the word at 0x0C) | 1, 0x10 | 1, 1, I2 | `S2` receives I2, and `S3` is granted. |
| c4 / edge 4 | 1, 0x14 | 0, 0, none | 1, 0x14 | 0, 0, none | None. `S4` is presented, and `gnt` low holds it back. |

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| The presented entry stays on `present_valid` and `present_pc` from its first `req` until its request transfer, even through a redirect | `fetch_controller_unit` keeps the entry presented; `fetch_buffer` keeps its `pc` ([buffer assumption](fetch-buffer.md)) | `req` or `addr` changes before `gnt`, which breaks OBI request stability. |
| `present_valid` and `present_pc` come from registered state only | `fetch_controller_unit` and `fetch_buffer` | A path from `gnt`, `rvalid` or `rdata` to `req` would exist, which BASE forbids. |
| The subordinate holds `gnt` low until it can accept, and returns no response for a pre-reset transaction after release | Instruction OBI subordinate ([BASE](5-stage-baseline-core.md#obi-response-validity-and-reset)) | Outside the contract. |
| Every input is 0 or 1 | The environment (fetch-stage O4) | Outside the contract. |

| Case | Inputs | Result |
| --- | --- | --- |
| Unexpected response | `rvalid` high with no granted request waiting | `raw_response_transfer` high, `request_fire` unchanged; the controller drains it and verification reports it |

## 9. Verification

- No leaf test exists, so every check in the table is planned.
- A pass shows only these vectors, not the controller lifecycle, entry selection, subordinate OBI compliance or whole-core behavior.
- Stage-level checks are in [fetch-stage.md](fetch-stage.md) §8.

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Pass-through (section 6) | Set `present_valid` and `present_pc`, toggle `rdata` | `req` equals `present_valid`; `addr` equals `present_pc` when `req` is high; `response_data` equals `rdata` |
| No combinational path (section 7) | Toggle `gnt`, `rvalid`, `rdata` and `rst_n` within a cycle, with `present_valid` constant | `req` and `addr` do not change |
| Event table (section 6) | All combinations of `rst_n`, `req`, `gnt` and `rvalid` | Both events match the section 6 table |
| Constant fields (section 6) | Any input | `we` 0, `be` all four bytes, `wdata` 0, `rready` 1 |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| FOI-D1 | The leaf is stateless and has no clock. | A held `req` register would need a latched address that copies the buffer's `pc`, and a second record of the pending request would give the committed mark a second owner. |
| FOI-D2 | The controller qualifies the response by the outstanding entry, and the leaf outputs `raw_response_transfer`. | The leaf's ports stay the same wherever the outstanding count lives. |
| FOI-D3 | The leaf has no unexpected-response port. | BASE requires only that an unexpected response is drained and reported by verification, and a port would need the outstanding count as an input. |
| FOI-D4 | The leaf outputs `request_fire` and `raw_response_transfer`. | Both depend only on the leaf's own inputs. |
| FOI-D5 | `req` is not gated by `rst_n`. | The BASE reset wording already drops `req` when the controller clears `present_valid`, and a gate would put a reset term on the port path. |
| FOI-D6 | `rdata` passes through as `response_data`, as the accepted fetch-stage wiring routes it. | It avoids editing an accepted parent document for a port with no logic. |

- History: 2026-11-01 the Owner settled FOI-O1 to FOI-O6; 2026-11-04 and 2026-11-06 the peers moved with IF-A3; 2026-11-07 rewritten in the block spec format, IDs renumbered.
- Old ID map: FOI-O1 to FOI-O6 map to FOI-D1 to FOI-D6 in order; all kept.
- Open items: none.
