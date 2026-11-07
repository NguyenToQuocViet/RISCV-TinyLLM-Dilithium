# Data OBI Controller

| Field | Value |
| --- | --- |
| Description | Data OBI request, transaction ownership and MEM-wait control. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/data_obi_controller.sv`, module `data_obi_controller`, instance `mem_obi_controller` in `memory_stage` |
| Parent | [Memory stage](memory-stage.md) (controller ownership, MEM-D4 and MEM-D5); [Five-stage BASE core](5-stage-baseline-core.md) (OBI response validity and reset, data transaction completion, reset architecture) |

## 1. Overview

- `data_obi_controller` presents the held EX/MEM load or store as one data OBI transaction. It suppresses duplicate requests after grant and releases `mem_wait` only on its expected response.
- Control and payload both pass through it, so it forms one complete OBI boundary ([DOC-D1](#10-decisions-and-open-items)).
- It does no formatting and no instruction decode.
- It has no pipeline register, response buffer, timeout, cancellation or bus-error handling.
- It adds no buffering, no latency and no outstanding capacity beyond one transaction ([DOC-D3](#10-decisions-and-open-items)).
- It has no separate completion port, because `req` and `mem_wait` are its only variable control outputs ([DOC-D3](#10-decisions-and-open-items)).

## 2. Block Design

```text
                                    clk, rst_n <- core clock and core reset
                                                  |
                                     +-----------------------+
instruction_valid, mem_en,           |                       | -> mem_wait (memory_stage)
  mem_write <- memory_stage          |                       | -> read_data (load_formatter)
aligned_address, byte_enable,        |  data_obi_controller  | -> req, addr, we, be, wdata, rready (data OBI subordinate)
  write_data <- request_formatter    |                       |
rdata, gnt, rvalid                   |                       |
  <- data OBI subordinate            |                       |
                                     +-----------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | Core clock | Clock of the ownership state. |
| `rst_n` | Input | 1 | Core reset | Shared active-low reset. |
| `instruction_valid` | Input | 1 | `memory_stage` | The current EX/MEM instruction is live. |
| `mem_en` | Input | 1 | `memory_stage` | The current instruction requires a data access. |
| `mem_write` | Input | 1 | `memory_stage` | Store intent, `0` for a load. |
| `aligned_address` | Input | `ADDR_WIDTH` | `request_formatter` | Aligned byte address of the access. |
| `byte_enable` | Input | 4 | `request_formatter` | Selected byte lanes. |
| `write_data` | Input | `DATA_WIDTH` | `request_formatter` | Store payload. |
| `read_data` | Output | `DATA_WIDTH` | `load_formatter` | Response payload for the load formatter. |
| `mem_wait` | Output | 1 | `memory_stage` | The current live memory instruction is unresolved. |
| `req` | Output | 1 | Data OBI subordinate | OBI request presentation. |
| `addr` | Output | `ADDR_WIDTH` | Data OBI subordinate | OBI address. |
| `we` | Output | 1 | Data OBI subordinate | OBI write enable. |
| `be` | Output | 4 | Data OBI subordinate | OBI byte enables. |
| `wdata` | Output | `DATA_WIDTH` | Data OBI subordinate | OBI write data. |
| `rready` | Output | 1 | Data OBI subordinate | OBI response readiness. |
| `rdata` | Input | `DATA_WIDTH` | Data OBI subordinate | OBI response payload. |
| `gnt` | Input | 1 | Data OBI subordinate | OBI address-phase grant. |
| `rvalid` | Input | 1 | Data OBI subordinate | OBI response valid. |

- The payload vectors are unsigned, and the block has no module parameter and no enum.
- The widths come from `riscv_pkg`, and the supported configuration is `DATA_WIDTH` 32 and `ADDR_WIDTH` 32.

### Width domains

| Domain | Package constant | Signals |
| --- | --- | --- |
| Register and arithmetic datapath | `DATA_WIDTH` | `write_data`, `read_data`, `wdata`, `rdata` |
| Address | `ADDR_WIDTH` | `aligned_address`, `addr` |

- No address or data width conversion occurs in the block.

## 4. Internal Structure

- None, because the block has no sub-blocks.

## 5. State

| Register | Reset value | Updater |
| --- | --- | --- |
| `outstanding` | 0, cleared asynchronously by `rst_n` | The rising edge of `clk`, as the Ownership table shows |

- The block holds no copy of the instruction or the payload ([DOC-D1](#10-decisions-and-open-items)).
- The `outstanding` bit is 1 from an accepted request until its expected response.

## 6. Behavior

### Control table

| Condition | `req` | `mem_wait` |
| --- | --- | --- |
| `instruction_valid` 0, or `mem_en` 0 | 0 | 0 |
| `instruction_valid` 1, `mem_en` 1 and `outstanding` 0 | 1 | 1 |
| `instruction_valid` 1, `mem_en` 1, `outstanding` 1 and `rvalid` 0 | 0 | 1 |
| `instruction_valid` 1, `mem_en` 1, `outstanding` 1 and `rvalid` 1 | 0 | 0 |

### Payload table

| Output | Equals |
| --- | --- |
| `addr` | `aligned_address` |
| `we` | `mem_write` |
| `be` | `byte_enable` |
| `wdata` | `write_data` |
| `read_data` | `rdata` |
| `rready` | 1, including reset |

### Ownership table

| Pre-edge `outstanding` | Sampled event | Next `outstanding` |
| --- | --- | --- |
| 0 | No request transfer | 0 |
| 0 | Request transfer | 1 |
| 1 | No expected response transfer | 1 |
| 1 | Expected response transfer | 0 |

- `req` does not depend on `gnt` or `rvalid`.
- Outside reset, a request transfer is a rising edge with `req` 1 and `gnt` 1.
- Outside reset, an expected response transfer is a rising edge with `outstanding` 1 and `rvalid` 1 before the edge, because `rready` is 1.
- Only `req` authorizes the address-phase acceptance.
- Grant alone never releases `mem_wait`.
- The payload outputs follow their inputs independently of the request and response qualification, and the block neither zeroes nor retains them when inactive.
- Reset overrides the Ownership table.
- [memory-stage.md](memory-stage.md#6-behavior) states how the core reads `mem_wait`.

## 7. Timing and Control

- `req` and `mem_wait` are combinational functions of the current inputs and of `outstanding` before the edge, and `mem_wait` is not a registered notification.
- The ownership state changes at the rising edge of `clk`, and transfers are sampled on that edge.
- An expected response releases `mem_wait` on the same edge, with no extra release cycle.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | `outstanding` clears asynchronously, without a clock edge. The `req` and `mem_wait` logic does not use `rst_n`, so both are 0 after reset propagation if `instruction_valid` is 0 throughout reset (section 8). `mem_en`, `mem_write` and the payload are not reset. Reset skew may cause transient outputs, so the block gives no glitch-free request isolation. |
| Stall | None: the block has no stall input, and `outstanding` keeps progressing ([MEM-D4](memory-stage.md#10-decisions-and-open-items)). |
| Flush | None: the block has no flush input. A stall or a younger redirect does not cancel an accepted transaction. |

### Trace

- Pre-state: the owner is live and stable, reset is inactive and `outstanding` is 0 before edge A. A store follows the same sequence as a load.

| Edge | `outstanding` before | Inputs | `req` / `mem_wait` | `outstanding` after and core action |
| --- | --- | --- | --- | --- |
| A | 0 | `gnt` 0, `rvalid` 0 | 1 / 1 | 0; the core retains the owner and the request |
| B | 0 | `gnt` 1, `rvalid` 0 | 1 / 1 | 1; the core retains the owner while it awaits the response |
| C | 1 | `rvalid` 0 | 0 / 1 | 1; no duplicate request |
| D | 1 | `rvalid` 1 | 0 / 0 | 0; the core advances the completed MEM instruction |

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment | X and Z behavior is outside scope. |
| `instruction_valid` is 0 throughout reset | The core ([MEM-D5](memory-stage.md#10-decisions-and-open-items)) | The block can assert `req` while `rst_n` is 0, and it does not mask a high `instruction_valid` during reset. |
| `req` and the address-phase fields stay stable throughout an ungranted request | The core ([MEM-D4](memory-stage.md#10-decisions-and-open-items)) | The block has no hardware checker, trap or recovery. |
| Alignment, legal memory types and the OBI environment follow the parent contract | The core and the OBI subordinate | The block has no hardware checker, trap or recovery. |
| The core capture and retirement and the OBI subordinate obey the shared reset | The core and the subordinate ([BASE reset architecture](5-stage-baseline-core.md#reset-architecture)) | A reset edge could create a transaction or consume a result. |
| The block and the EX/MEM register share the reset | The core | Resetting only one of them while a transaction is live is outside this boundary. |
| The reset release is synchronized before `rst_n` reaches the block | The core reset ([BASE reset architecture](5-stage-baseline-core.md#reset-architecture)) | The block adds no local synchronizer. |

| Case | Inputs | Result |
| --- | --- | --- |
| Unexpected response with no outstanding transaction | `rvalid` 1 with `outstanding` 0 | The response is drained because `rready` is 1. It does not complete the current instruction and does not release `mem_wait`. |
| Unexpected response with the first grant | `rvalid` 1 on the edge of the first request transfer | The request still sets `outstanding`, and the raw response cannot complete the new transaction. The parent pre-edge rule does not support same-edge consumption. |
| Next memory instruction on the response edge | The core replaces the EX/MEM instruction at the expected response edge | The next request appears after the edge, because `outstanding` clears at the edge, and it is not a second request on the response edge. |
| Reset with an accepted transaction | `rst_n` low while `outstanding` is 1 | `outstanding` clears, but the clear cannot cancel a previously accepted store or guarantee that a late response belongs to a new transaction. The system or harness reset must quiesce the old bus work. |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_data_obi_controller.py` runs the top `data_obi_controller` with Verilator and cocotb.
  - The module `data_obi_controller_cocotb` has 9 tests: `test_idle_control`, `test_payload_routing`, `test_delayed_grant`, `test_delayed_response`, `test_completion_timing`, `test_consecutive_transactions`, `test_unexpected_response`, `test_reset_during_transaction` and `test_reset_without_clock`.
- The tests cover every planned check below. The unexpected-response test checks the block only, and no test asserts a protocol diagnostic or reads the ownership bit.
- The release of `mem_wait` for an expected response is checked before the edge, because the ownership is already clear after it.
- A reset check clears `instruction_valid` and the subordinate protocol state first, because a high `instruction_valid` during reset violates the environment of the block.
- A leaf pass shows only the checked vectors under the supplied core and bus obligations. The MEM integration checks are in [memory-stage.md](memory-stage.md#9-verification).

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Idle qualification | A bubble and a non-memory instruction, with grant | `req` 0 and `mem_wait` 0, as the first row of the Control table |
| Payload pass-through | Any payload, with and without a live owner | Every Payload table output equals its source |
| Delayed grant and response | A delayed grant, then a delayed response | `req` and the payload stay stable until grant, and `mem_wait` releases only for the response |
| Duplicate suppression | A request after its grant | `req` 0 while `outstanding` is 1 |
| Expected response | A response for the accepted transaction | `mem_wait` 0 before the consuming edge, as the Control table shows |
| Unexpected response | A response with no outstanding transaction, including with the first grant | As the section 8 rows "Unexpected response with no outstanding transaction" and "Unexpected response with the first grant". Verification reports the protocol violation. |
| Reset without a clock edge | `rst_n` low with `instruction_valid` cleared and no clock edge | `req` 0, `mem_wait` 0 and the ownership cleared |
| Reset at transfer boundaries | `rst_n` low on the edge of a request transfer and of a response transfer | No ownership results, because reset overrides the Ownership table |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| DOC-D1 | Control and payload pass through the controller, with no private payload storage. The block adds no payload register and no cycle of latency. | It gives the leaf one complete OBI boundary, at the cost of more pass-through ports than control-only ports. |
| DOC-D2 | The interface has these port names, these direct payload mappings and the control rules of section 6. It keeps the inherited one-outstanding ownership, completion, reset and pipeline behavior. DOC-D3 supersedes the separate completion port and the direct reset gating of that interface. | None recorded. |
| DOC-D3 | `req` and `mem_wait` are the only variable control outputs, and the earlier completion port and its intermediate event signals are removed. `outstanding` clears asynchronously on reset, and the suppression of `req` and `mem_wait` relies on the reset `instruction_valid` of [MEM-D5](memory-stage.md#10-decisions-and-open-items) instead of a combinational reset gate. | Parent control already has the valid and memory intent that it needs to interpret the wait release, and the control structure stays small. |

- Revisit this boundary if valid is no longer reset, the controller is independently reset, or the receiver cannot obey the shared reset.
- History: 2026-10-21 the Owner accepted the port names, the direct payload mappings and the control equations.
- 2026-10-22 the Owner accepted the interface and reset refinement, with the completion and reset boundary (revision DOC D2).
- 2026-11-07 rewritten in the block spec format. The RTL mapping line and the closing remarks went.

| Old ID | New ID | Status |
| --- | --- | --- |
| DOC-D1 | DOC-D1 | Kept |
| DOC-D2 | DOC-D2 | Kept; the control equations of the old sections 2 and 3 are the section 6 tables |
| DOC-D3 | DOC-D3 | Kept; `tb/README.md` and `reset-strategy.md` cite it |
| DOC D2 (revision label, 2026-10-22; `tb/README.md` cites it) | none | Retired as a label: History carries the date, and its decisions are DOC-D2 and DOC-D3 |

- Open items: none.
