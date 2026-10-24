# Memory Stage — Block Design

**Status:** Composition, metadata routing, memory-type encoding, formatter
fallbacks and controller ownership accepted by Nguyễn Tô Quốc Việt on 2026-10-21.
Leaf contracts are accepted; the completion/reset boundary was refined by Việt
on 2026-10-22. ID-owned `wb_src` and its external bypass were confirmed
by Việt on 2026-10-22, superseding the earlier MEM-derived selector. The corrected
wrapper interface/composition is confirmed by Việt's implementation and request
to commit on 2026-10-22. Pipeline-register implementation remains deferred.
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Design revision:** MEM D3 / 2026-10-22, extending accepted MEM D2;
refines BASE R2 without changing its behavior.
**Parent contract:** [Five-stage BASE core](5-stage-baseline-core.md).
**RTL mapping:** The three leaves and `rtl/memory_stage.sv` have RTL. The wrapper
is human-authored. This document does not establish functional verification.

The [2026-10-24 WB naming clarification](5-stage-baseline-core.md) renames the
ID-owned selector to `wb_src` without changing its encoding or routing. Earlier
owner confirmations above retain their dates; the naming amendment is later.

## 1. Purpose and boundary

MEM formats aligned load/store accesses, manages the data OBI transaction and
formats load responses before MEM/WB. The parent owns
[memory semantics](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary),
[transaction completion](5-stage-baseline-core.md#data-transaction-completion)
and [pipeline arbitration](5-stage-baseline-core.md#pipeline-control-priority).
This document records the selected local decomposition without redefining them.

MEM consumes the current registered EX/MEM instruction, not live combinational
EX outputs. The wrapper receives instruction validity, `ex_result`,
`store_data`, `mem_en`, `mem_write`, `mem_type`, clock/reset and the data OBI
inputs. It produces load data, MEM-wait control and the data OBI outputs.
The flat wrapper ports are listed below.

As in EX, current-instruction metadata bypasses the wrapper: the core routes
`rd`, `reg_write` and `wb_src` directly from EX/MEM toward MEM/WB. `ex_result` also
continues unchanged toward MEM/WB, with a branch into MEM for effective-address
processing. The core owns pipeline-register validity and capture decisions;
the wrapper does not contain EX/MEM or MEM/WB storage.

`instruction_valid` is EX/MEM's valid bit. The core must clear it asynchronously
on shared reset and keep it zero throughout reset, even though memory-control
and data payload are not reset. The controller relies on this guarantee rather
than gating its combinational outputs with `rst_n`; see its
[required reset invariant](data-obi-controller.md#4-environment-reset-and-unexpected-responses).

GPR data and `ex_result` use `DATA_WIDTH`; OBI addresses use `ADDR_WIDTH`.
The supported configuration remains `DATA_WIDTH = ADDR_WIDTH = 32`.
Interpreting `ex_result` as an address preserves all 32 bits before the required
word alignment. Unequal-width conversion is not defined.

## 2. Wrapper interface

The interface uses individual ports, as in EX, with no packed payload structure.
Types/constants below belong to `riscv_pkg`; all vectors are unsigned logic.
Only `DATA_WIDTH = ADDR_WIDTH = 32` is supported; no module width parameters
or unequal-width conversion are introduced.

| Group | Port(s) | Direction | Type / width | Meaning and use |
| --- | --- | --- | --- | --- |
| System | `clk` | Input | 1-bit logic | Controller state updates on the rising edge |
| System | `rst_n` | Input | 1-bit logic | Shared active-low, asynchronous-assert/synchronous-release reset |
| EX/MEM | `instruction_valid` | Input | 1-bit logic | Current EX/MEM valid; must be zero throughout reset |
| EX/MEM | `ex_result` | Input | `logic [DATA_WIDTH-1:0]` | Effective byte address for a memory instruction |
| EX/MEM | `store_data` | Input | `logic [DATA_WIDTH-1:0]` | Forwarded store value; relevant for stores |
| EX/MEM | `mem_en`, `mem_write` | Input | 1-bit logic each | Memory intent; write distinguishes store from load when enabled |
| EX/MEM | `mem_type` | Input | `mem_type_t` | Access width and load signedness, meaningful for a live memory instruction |
| Toward MEM/WB | `load_result` | Output | `logic [DATA_WIDTH-1:0]` | Formatted load value; consumed only at expected load completion |
| Pipeline control | `mem_wait` | Output | 1-bit logic | Current live memory instruction is unresolved; not a standalone completion indication |
| Data OBI | `gnt` | Input | 1-bit logic | Request acceptance when `req` is asserted |
| Data OBI | `rvalid` | Input | 1-bit logic | Response presentation; only an outstanding transaction can complete |
| Data OBI | `rdata` | Input | `logic [DATA_WIDTH-1:0]` | Response word; consumed only for an expected load response |
| Data OBI | `req` | Output | 1-bit logic | Request presentation, retained until grant |
| Data OBI | `addr` | Output | `logic [ADDR_WIDTH-1:0]` | Word-aligned byte address, meaningful with `req` |
| Data OBI | `we` | Output | 1-bit logic | Store write enable, meaningful with `req` |
| Data OBI | `be` | Output | `logic [3:0]` | Selected byte lanes, meaningful with `req` |
| Data OBI | `wdata` | Output | `logic [DATA_WIDTH-1:0]` | Replicated store payload, meaningful for a store request |
| Data OBI | `rready` | Output | 1-bit logic | Always one, including reset; readiness is not proof of response ownership |

There are 11 input ports and 8 output ports. Reset generation/synchronization
belongs to the core/system boundary, not this wrapper. `rst_n` reaches the
controller unchanged. Neither formatter has a clock or reset port.

`wb_src` is decoded in ID and carried unchanged through ID/EX, EX/MEM
and MEM/WB. It is neither an input nor an output of this wrapper; MEM does not
regenerate it from `mem_en` and `mem_write`. The core retains its association
with the instruction under stall, capture and flush. `load_result` remains
combinational rather than being zeroed or registered when unavailable. The core
qualifies consumption.

## 3. Internal organization and wiring

| Module | Responsibility | Storage |
| --- | --- | --- |
| `memory_stage` | Compose the request, transaction-control and load-response paths | No additional transaction or payload storage |
| `request_formatter` | Form aligned address, byte enables and replicated store data | Combinational |
| `load_formatter` | Select the response lane and sign/zero-extend load data | Combinational |
| `data_obi_controller` | Own request issue, outstanding state, expected completion and MEM-wait control | One `outstanding` bit |

Request formatting serves both loads and stores. The controller does not
interpret access width or load signedness; the formatters do not own
transaction state. Byte-lane and extension equations remain in the parent.

The wrapper introduces these internal datapath nets:

| Net | Type / width | Producer and consumers |
| --- | --- | --- |
| `aligned_address` | `logic [ADDR_WIDTH-1:0]` | Request formatter to controller |
| `byte_enable` | `logic [3:0]` | Request formatter to controller |
| `write_data` | `logic [DATA_WIDTH-1:0]` | Request formatter to controller |
| `read_data` | `logic [DATA_WIDTH-1:0]` | Controller to load formatter |

Wrapper `ex_result` connects directly to each formatter's `effective_address`
input; no separate address net is required. This is the datapath-to-address
conversion boundary. It preserves all 32 bits; only the request formatter
clears the low address bits. The load formatter receives the original address
so it retains lane selection information.

```text
ex_result -> effective_address ----+---> request_formatter
                                  +---> load_formatter
store_data ---------------------------> request_formatter

request_formatter -- aligned_address, byte_enable, write_data --> data_obi_controller
OBI rdata ----------> data_obi_controller -- read_data ----------> load_formatter
load_formatter ------------------------------------------------> load_result
```

The following table specifies every leaf port. Each pin connects to the
same-named wrapper port or internal net above, except each formatter's
`effective_address`, which connects to wrapper `ex_result`.

| Leaf | Input connections | Output connections |
| --- | --- | --- |
| `request_formatter` | `effective_address`, `store_data`, `mem_type` | `aligned_address`, `byte_enable`, `write_data` |
| `data_obi_controller` | `clk`, `rst_n`, `instruction_valid`, `mem_en`, `mem_write`, `aligned_address`, `byte_enable`, `write_data`, `gnt`, `rvalid`, `rdata` | `read_data`, `mem_wait`, `req`, `addr`, `we`, `be`, `wdata`, `rready` |
| `load_formatter` | `read_data`, `effective_address`, `mem_type` | `load_result` |

`mem_type` fans out to both formatters. Controller `read_data` is the unchanged
OBI response word. `mem_write` drives controller `we`; the wrapper does not
add request gating, formatting or transaction state around the controller.

Core-owned paths bypass the wrapper:

| Producer | Consumer |
| --- | --- |
| EX/MEM `ex_result` | MEM/WB `ex_result`, unchanged, in parallel with its branch into MEM |
| EX/MEM `rd`, `reg_write`, `wb_src` | Corresponding MEM/WB metadata, unchanged |
| Wrapper `load_result` | MEM/WB `load_result` |

Final WB result selection remains outside MEM. No WB mux, pipeline register,
flush/stall input or output-valid port is added to the wrapper.

<a id="3-shared-memory-type-encoding-and-fallback"></a>

## 4. Shared memory-type encoding and fallback

The package defines `riscv_pkg::mem_type_t`, an
`enum logic [2:0]` with these accepted values:

| Member | Encoding | Operations |
| --- | --- | --- |
| `MEM_BYTE` | `000` | LB, SB |
| `MEM_HALF` | `001` | LH, SH |
| `MEM_WORD` | `010` | LW, SW |
| `MEM_BYTE_U` | `100` | LBU |
| `MEM_HALF_U` | `101` | LHU |

ID produces semantic control. Matching instruction `funct3` values does not
authorize downstream raw-instruction decode. `mem_write` distinguishes loads
and stores; unsigned-load types are not legal store types.

For the unassigned binary codes `011`, `110` and `111`, `request_formatter`
returns byte enable `0000` and write data zero while retaining the normal
aligned-address calculation. `load_formatter` returns `32'hDEAD_BEEF`.
These are deterministic formatter fallbacks, not an access-suppression or
recovery mechanism; zero byte enables do not guarantee harmless MMIO behavior.

At MEM integration, a valid memory instruction with an unassigned type, or a
store with an unsigned-load type, must cause checker FAIL. Bubbles and
non-memory instructions do not trigger this check. No CPU trap or error port
is added. The selected binary-input policy excludes X/Z behavior from scope.

<a id="4-controller-state-and-payload-ownership"></a>

## 5. Timing, state and ownership

The controller uses one `outstanding` bit. EX/MEM retains the complete
instruction payload throughout grant and response waits; the controller does
not copy the address, store data or memory type into private payload storage.

| Current ownership | Event | Next `outstanding` |
| --- | --- | ---: |
| No accepted transaction | No request transfer | 0 |
| No accepted transaction | Request transfer | 1 |
| Accepted transaction | No expected response transfer | 1 |
| Accepted transaction | Expected response transfer | 0 |

With no outstanding transaction, a valid memory owner presents its request
until grant. After grant it must not reissue that request. Waiting for grant
needs no separate stored state because EX/MEM retains the owner. Completion
uses pre-edge ownership under the parent's
[response rules](5-stage-baseline-core.md#obi-response-validity-and-reset).
An unexpected response does not release ownership or resolve MEM wait.

The controller exposes `mem_wait`, not a separate completion port. With a live
memory owner retained and reset inactive, `mem_wait=0` means the expected
response is available for this edge. Core control uses wait release with its
normal valid/advance rules to capture a load into MEM/WB or advance a completed
store. A bubble or non-memory instruction also has `mem_wait=0`, so wait alone
is not a completion indication. The parent's `data_response_fire` remains the
semantic event name; it does not require a same-named RTL signal. Formatter
outputs are always combinational and do not authorize capture themselves.

The bit resets to zero under the shared
[reset contract](5-stage-baseline-core.md#reset-architecture). Global pipeline
stall does not freeze mandatory controller protocol progress. Parent control
must retain the owner and payload until expected completion; this controller
is not an independently buffered command interface. Adding independent
backpressure, cancellation or payload replacement requires reconsidering this
ownership boundary.

## 6. Integration verification obligations

These are planned wrapper checks, not recorded results. Child behavior is
checked against the linked contracts; the wrapper checks below target wiring
and coordination rather than duplicating the controller's transition table
and [edge traces](data-obi-controller.md#5-edge-trace-and-verification-boundary).

| Scenario | Required observation |
| --- | --- |
| Legal byte/halfword/word load or store at supported offsets | OBI address is aligned; byte enable and store payload match request formatting; load lane uses the original address and correct extension |
| Delayed grant and response | Parent retains EX/MEM payload; request stays stable until grant, never repeats after grant, and wait releases only for the expected response |
| Expected response and next instruction | Load result is available for MEM/WB capture on the response edge; store ignores response data; no next request is issued on that same edge |
| Unexpected response with no outstanding transaction, including first grant | Response is drained without completing the new request or releasing its wait |
| Bubble, non-memory instruction or store | Arbitrary load data is never consumed as a valid load result; core-carried WB selection remains associated with its instruction |
| Shared reset during a pending transaction, including stopped clock | EX/MEM valid and controller ownership clear asynchronously; payload need not clear; no capture/acceptance during reset under the shared-reset contract |

The core-level harness must model EX/MEM retention and MEM/WB capture, not
replace the held payload early when grant arrives. Completion has no added
pipeline cycle: expected response releases wait combinationally before its
consuming edge. Independent downstream backpressure is outside this contract.
Parent alignment, memory-type and unexpected-response checkers remain required.
Wrapper simulation alone does not establish full-pipeline, system-reset or
physical timing correctness.

## 7. Rationale and open decisions

The three-leaf decomposition, metadata bypass, state ownership and reset
invariant remain accepted MEM D2 requirements. Leaf port tables and behavior
remain owned by the [request formatter](request-formatter.md),
[load formatter](load-formatter.md) and
[data OBI controller](data-obi-controller.md) contracts.

The flat wrapper interface and wiring reuse the leaf boundaries, retain the
ID-owned `wb_src` bypass, and add no completion port, WB-selector port or
new protocol. Việt authored the wrapper and requested its commit on 2026-10-22;
this records that owner confirmation, not functional verification.

No additional behavioral choice is open within this wrapper boundary.
Pipeline-register implementation remains deferred until its downstream payload
requirements are resolved. This document does not change the accepted reset,
stall/flush priority, OBI protocol, ISA scope or core arbitration.
