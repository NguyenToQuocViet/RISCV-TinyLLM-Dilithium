# Memory Stage

| Field | Value |
| --- | --- |
| Description | Compose data OBI transactions and load/store formatting. |
| Last modified | 2026-11-08 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/memory_stage.sv`, module `memory_stage`, instance name `mem_stage` |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md) (MEM data formatting and MEM/WB boundary, data transaction completion, pipeline-control priority, OBI response validity and reset, reset architecture); [Hazard control unit](hazard-control-unit.md); [Pipeline register](pipeline-register.md); the three leaves ([request formatter](request-formatter.md), [data OBI controller](data-obi-controller.md), [load formatter](load-formatter.md)) |

## 1. Overview

- `memory_stage` is the BASE MEM stage. It formats aligned load and store accesses, manages the data OBI transaction and formats the load response before MEM/WB.
- BASE owns the [memory semantics](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary), the [transaction completion](5-stage-baseline-core.md#data-transaction-completion) and the [pipeline arbitration](5-stage-baseline-core.md#pipeline-control-priority), and this spec refines them without redefining them.
- It consumes the registered EX/MEM instruction, not live combinational EX outputs.
- It composes the three leaves of section 4 and has no logic of its own.
- The current-instruction metadata bypasses it, and the core owns the EX/MEM and MEM/WB registers ([MEM-D2](#10-decisions-and-open-items)).
- It has no stall, flush, completion or output-valid port, and `mem_wait` is its only completion-related output ([MEM-D3](#10-decisions-and-open-items)).
- It does not select the final WB result.
- It has no CPU trap or error port for an invalid memory type ([MEM-D8](#10-decisions-and-open-items)).

## 2. Block Design

```text
                                      clk, rst_n <- core clock and core reset
                                                    |
                                       +-----------------------+
instruction_valid, mem_en, mem_write   |                       | -> load_result (MEM/WB register)
  <- EX/MEM register                   |                       | -> mem_wait (hazard_control_unit)
ex_result, store_data, mem_type        |     memory_stage      | -> req, addr, we, be, wdata, rready (data OBI subordinate)
  <- EX/MEM register                   |                       |
gnt, rvalid, rdata                     |                       |
  <- data OBI subordinate              |                       |
                                       +-----------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | Core clock | Clock of the controller state. |
| `rst_n` | Input | 1 | Core reset | Shared active-low reset, asserted asynchronously and released synchronously. |
| `instruction_valid` | Input | 1 | EX/MEM register | The EX/MEM instruction is live. |
| `ex_result` | Input | `DATA_WIDTH` | EX/MEM register | Effective byte address of a memory instruction. |
| `store_data` | Input | `DATA_WIDTH` | EX/MEM register | Forwarded store value, relevant for a store. |
| `mem_en` | Input | 1 | EX/MEM register | Data-memory access intent. |
| `mem_write` | Input | 1 | EX/MEM register | `0` for a load, `1` for a store. |
| `mem_type` | Input | `mem_type_t` (3) | EX/MEM register | Access width and load signedness. |
| `load_result` | Output | `DATA_WIDTH` | MEM/WB register | Formatted load value. |
| `mem_wait` | Output | 1 | `hazard_control_unit` | The live memory instruction is unresolved. |
| `gnt` | Input | 1 | Data OBI subordinate | Request acceptance, when `req` is 1. |
| `rvalid` | Input | 1 | Data OBI subordinate | Response valid. |
| `rdata` | Input | `DATA_WIDTH` | Data OBI subordinate | Response word. |
| `req` | Output | 1 | Data OBI subordinate | Request presentation. |
| `addr` | Output | `ADDR_WIDTH` | Data OBI subordinate | Request address, meaningful with `req`. |
| `wdata` | Output | `DATA_WIDTH` | Data OBI subordinate | Store payload, meaningful for a store request. |
| `we` | Output | 1 | Data OBI subordinate | Store write enable, meaningful with `req`. |
| `be` | Output | 4 | Data OBI subordinate | Selected byte lanes, meaningful with `req`. |
| `rready` | Output | 1 | Data OBI subordinate | Response readiness. |

- The types come from `riscv_pkg`, and every vector is unsigned.
- The stage has no width parameter, and the supported configuration is `DATA_WIDTH` 32 and `ADDR_WIDTH` 32.

### Width domains

| Domain | Package constant | Signals |
| --- | --- | --- |
| Register and arithmetic datapath | `DATA_WIDTH` | `ex_result`, `store_data`, `rdata`, `wdata`, `load_result` |
| Address | `ADDR_WIDTH` | `addr` |

### Width crossings

| Boundary | Source | Destination |
| --- | --- | --- |
| Address use of `ex_result` | `ex_result`: `DATA_WIDTH` | The effective address input of each formatter: `ADDR_WIDTH` |

- The crossing keeps all 32 bits before the word alignment, and only the request formatter clears the low address bits.
- The load formatter receives the original address, so it keeps the lane selection information.
- Unequal widths have no defined conversion.

## 4. Internal Structure

| Module | Instance | File | Spec |
| --- | --- | --- | --- |
| `memory_stage` | `mem_stage` | `rtl/memory_stage.sv` | This spec |
| `request_formatter` | `mem_req_formatter` | `rtl/request_formatter.sv` | [request-formatter.md](request-formatter.md) |
| `data_obi_controller` | `mem_obi_controller` | `rtl/data_obi_controller.sv` | [data-obi-controller.md](data-obi-controller.md) |
| `load_formatter` | `mem_load_formatter` | `rtl/load_formatter.sv` | [load-formatter.md](load-formatter.md) |

### Internal nets

| Net | Width | Driver | Consumers |
| --- | --- | --- | --- |
| `aligned_address` | `ADDR_WIDTH` | `mem_req_formatter`, port `aligned_address` | `mem_obi_controller` port `aligned_address` |
| `byte_enable` | 4 | `mem_req_formatter`, port `byte_enable` | `mem_obi_controller` port `byte_enable` |
| `write_data` | `DATA_WIDTH` | `mem_req_formatter`, port `write_data` | `mem_obi_controller` port `write_data` |
| `read_data` | `DATA_WIDTH` | `mem_obi_controller`, port `read_data` | `mem_load_formatter` port `read_data` |

- The stage instantiates the three leaves, one each, and has no other logic.
- `ex_result` connects to the effective address port of both formatters.
- Every other leaf port connects to the stage port or net of the same name.
- `mem_type` fans out to both formatters.

## 5. State

- None, because the stage holds no register.
- The only storage in the hierarchy is the outstanding bit of the controller, and [data-obi-controller.md](data-obi-controller.md) owns its state, update and reset.
- The core owns the EX/MEM and MEM/WB registers.

## 6. Behavior

### Output table

| Output | Equals | Rule owner |
| --- | --- | --- |
| `req` | 1 for a live memory instruction that has no accepted transaction, held until grant | [data-obi-controller.md](data-obi-controller.md) |
| `mem_wait` | 1 for a live memory instruction until its expected response, and 0 otherwise | [data-obi-controller.md](data-obi-controller.md), [BASE data transaction completion](5-stage-baseline-core.md#data-transaction-completion) |
| `addr` | The effective address with the low two bits cleared | [request-formatter.md](request-formatter.md) |
| `we` | `mem_write` | [data-obi-controller.md](data-obi-controller.md) |
| `be` | The byte lanes of the access | [request-formatter.md](request-formatter.md) |
| `wdata` | The store value, replicated over the access width | [request-formatter.md](request-formatter.md) |
| `rready` | 1, including reset | [data-obi-controller.md](data-obi-controller.md) |
| `load_result` | The response word, with the lane selected and extended by `mem_type` and the original address | [load-formatter.md](load-formatter.md) |

- With a live memory owner retained and reset inactive, `mem_wait` 0 means the expected response is available for this edge.
- `mem_wait` 0 alone does not indicate completion, because a bubble or a non-memory instruction also has `mem_wait` 0.
- The core combines the wait release with its valid and advance rules to capture a load into MEM/WB or to advance a completed store.
- The BASE event `data_response_fire` is a semantic name, and no RTL signal of that name is required.
- A store ignores the response data.
- `load_result` does not authorize capture ([MEM-D9](#10-decisions-and-open-items)).

### mem_type_t table

| Member | Encoding | Operations |
| --- | --- | --- |
| `MEM_BYTE` | `000` | LB, SB |
| `MEM_HALF` | `001` | LH, SH |
| `MEM_WORD` | `010` | LW, SW |
| `MEM_BYTE_U` | `100` | LBU |
| `MEM_HALF_U` | `101` | LHU |
| Unassigned | `011`, `110`, `111` | None: the request formatter gives byte enable `0000` and write data zero with the normal aligned address, and the load formatter gives `32'hDEAD_BEEF` ([MEM-D7](#10-decisions-and-open-items)) |

- ID supplies the semantic selector, and a matching `funct3` value does not authorize downstream raw decode.
- `mem_write` distinguishes a load from a store, and the unsigned-load types are not legal store types.

### Bypass paths

| Producer | Consumer |
| --- | --- |
| EX/MEM `ex_result` | MEM/WB `ex_result`, unchanged, in parallel with its branch into the stage |
| EX/MEM `rd`, `reg_write`, `wb_src` | The corresponding MEM/WB fields, unchanged |

## 7. Timing and Control

- Completion adds no pipeline cycle, because an expected response releases `mem_wait` before the edge that consumes it.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | `rst_n` reaches the controller unchanged, and neither formatter has a reset port. Reset generation and synchronization belong to the core and system boundary. |
| Stall | None: the stage has no stall input. The core must keep the owner and the payload until the expected completion ([MEM-D4](#10-decisions-and-open-items)). |
| Flush | None: the stage has no flush input. A younger redirect does not cancel an accepted transaction ([data-obi-controller.md](data-obi-controller.md)). |

- Trace: None, because the stage adds no sequence of its own, and the edge trace of [data-obi-controller.md](data-obi-controller.md) covers the transaction sequence.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment, as in each leaf spec | X and Z behavior is unspecified and untested. |
| `instruction_valid` is 0 throughout reset | The core ([MEM-D5](#10-decisions-and-open-items)) | The controller can assert `req` while `rst_n` is 0, because it does not gate its outputs with `rst_n`. |
| The core retains the live memory owner and its complete payload in EX/MEM until the expected completion | The core ([MEM-D4](#10-decisions-and-open-items)) | The request fields change while the request waits for grant or response. |
| The core keeps `rd`, `reg_write` and `wb_src` associated with their instruction under stall, capture and flush | The core ([MEM-D2](#10-decisions-and-open-items)) | A load result enters MEM/WB with the metadata of another instruction. |
| The core consumes `load_result` only at the expected load completion, and never for a bubble, a non-memory instruction or a store | The core ([MEM-D9](#10-decisions-and-open-items)) | Arbitrary load data is taken as a load result. |
| The core presents aligned accesses and legal memory types, and the OBI subordinate follows the BASE OBI configuration | The core and the subordinate ([BASE](5-stage-baseline-core.md#obi-response-validity-and-reset)) | A misaligned access has no specified recovery. |

| Case | Inputs | Result |
| --- | --- | --- |
| Invalid type on a live instruction | A valid memory instruction with an unassigned type, or a store with an unsigned-load type | The controller still presents the request, and the formatters give the fallbacks of the `mem_type_t` table. |
| Response edge with the next instruction | The expected response arrives and the core replaces the EX/MEM instruction at the edge | `load_result` is available before the edge for MEM/WB capture, and the next request appears after the edge, not on it ([data-obi-controller.md](data-obi-controller.md)). |

## 9. Verification

- A directed test exists: runner `tb/runners/test_memory_stage.py` runs the top `memory_stage` with Verilator and cocotb.
  - The module `memory_stage_cocotb` has 3 tests: `test_access_paths`, `test_wait_and_successors` and `test_idle_and_reset`.
- The tests cover the legal-access, delayed-handshake, successor, bubble and reset-with-pending-load stimuli. They do not cover the unexpected response, the reset with a stopped clock or the memory-type checker.
- The wrapper checks target wiring and coordination, and they do not repeat the transition table and the edge trace of [data-obi-controller.md](data-obi-controller.md).
- Expected values come from the BASE rules and the leaf contracts.
- The core-level harness must model the EX/MEM retention and the MEM/WB capture, and it must not replace the held payload when the grant arrives.
- The alignment, memory-type and unexpected-response checkers of the parent remain required ([MEM-D8](#10-decisions-and-open-items)).
- A pass shows only wrapper wiring and coordination under the supplied core and bus obligations, not full-pipeline, system-reset or physical timing correctness.

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Legal access | A legal byte, halfword and word load or store at supported offsets | The OBI address is aligned. The byte enable and the store payload match the request formatting. The load lane uses the original address, with the correct extension. |
| Delayed grant and response | A delayed grant and a delayed response | The core retains the EX/MEM payload. The request stays stable until grant and never repeats after grant. The wait releases only for the expected response. |
| Expected response and next instruction | An expected response, then a next memory instruction | As the section 8 row "Response edge with the next instruction". A store ignores the response data. |
| Unexpected response | A response with no outstanding transaction, including on the first grant | The response is drained, without completing the new request or releasing its wait. |
| Bubble, non-memory or store | A bubble, a non-memory instruction or a store, with arbitrary load data | The load data is never consumed as a valid load result. The core-carried WB selection stays associated with its instruction. |
| Shared reset | A shared reset during a pending transaction, including a stopped clock | The EX/MEM valid and the controller ownership clear asynchronously, and the payload need not clear. No capture or acceptance occurs during reset under the shared-reset contract. |
| Type checker ([MEM-D8](#10-decisions-and-open-items)) | A valid memory instruction with an unassigned type, or a store with an unsigned-load type | Checker FAIL |
| Checker scope (MEM-D8) | A bubble or a non-memory instruction, with any type | No checker FAIL |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| MEM-D1 | MEM has three leaves: the request formatter, the load formatter and the data OBI controller. | None recorded. |
| MEM-D2 | `rd`, `reg_write` and `wb_src` go around the stage, and the core routes them from EX/MEM to MEM/WB. `ex_result` also continues unchanged to MEM/WB, in parallel with its branch into the stage. ID decodes `wb_src`, and the stage does not regenerate it from `mem_en` and `mem_write`. | The core owns the pipeline-register validity and the capture, and the stage holds no EX/MEM or MEM/WB storage, as in EX. |
| MEM-D3 | The ports are individual signals. The stage adds no completion port, WB-selector port, packed payload, stall or flush input or output-valid port. | The stage reuses the leaf boundaries and adds no new protocol. |
| MEM-D4 | The controller owns the transaction state, one outstanding bit. The EX/MEM register retains the complete payload throughout the grant and response waits, and the controller keeps no private copy. A core stall does not freeze the controller. | Waiting for grant needs no separate stored state, because EX/MEM retains the owner. |
| MEM-D5 | `instruction_valid` is the EX/MEM valid bit. The core clears it asynchronously on shared reset and keeps it 0 throughout reset, and the controller does not gate its outputs with `rst_n`. | None recorded. |
| MEM-D6 | The shared memory-type encoding is the `mem_type_t` table. | None recorded. |
| MEM-D7 | The unassigned `mem_type` codes give deterministic formatter fallbacks, and the fallbacks are no access suppression and no recovery. | Zero byte enables do not guarantee harmless MMIO behavior. |
| MEM-D8 | At MEM integration, a valid memory instruction with an unassigned type, or a store with an unsigned-load type, must cause a checker FAIL. A bubble or a non-memory instruction does not. No CPU trap or error port is added. | None recorded. |
| MEM-D9 | `load_result` stays combinational, and the stage neither zeroes nor registers it when unavailable. The core qualifies its consumption. | None recorded. |

- Revisit: independent backpressure, cancellation or payload replacement needs a new decision on the ownership boundary of MEM-D4.
- History: 2026-10-21 the Owner accepted the composition, the metadata routing, the memory-type encoding, the formatter fallbacks and the controller ownership.
- 2026-10-22 the Owner refined the completion and reset boundary. The Owner confirmed the ID-owned `wb_src` with its external bypass, which superseded the earlier MEM-derived selector. The Owner also authored the wrapper and requested its commit, which confirmed the corrected wrapper interface and composition. That revision is MEM D3, which extends MEM D2 and refines BASE R2 without changing its behavior.
- 2026-10-24 the WB naming clarification renamed the ID-owned selector to `wb_src`, with encoding and routing unchanged.
- 2026-11-07 rewritten in the block spec format, with IDs added. The "Pipeline-register implementation remains deferred" note, the RTL mapping paragraph and the readiness remarks went.
- 2026-11-08 the Owner chose the instance name `mem_stage`, following `ex_stage` and `id_stage`. The RTL has no instantiation of the stage yet.

| Old ID | New ID | Status |
| --- | --- | --- |
| MEM D2 (revision label; BASE cites "MEM D2 / 2026-10-22") | MEM-D1, MEM-D2, MEM-D4, MEM-D5 | Retired as a label: its requirements (three-leaf decomposition, metadata bypass, state ownership, reset invariant) are those decisions, and History carries the date |
| MEM D3 (revision label, 2026-10-22; `tb/README.md` cites it) | MEM-D2, MEM-D3 | Retired as a label: its decisions are the metadata bypass with the ID-owned `wb_src`, and the flat wrapper interface; History carries the date |

- Length: 7 pages, above the 2-4 limit, because the spec has 19 ports, four nets, an encoding table, 8 check rows and 9 decisions.
- Open items: none.
