# Memory Stage — Decomposition and Ownership Contract

**Status:** Composition, metadata routing, memory-type encoding, formatter
fallbacks and controller ownership accepted by Nguyễn Tô Quốc Việt on 2026-10-21.
Leaf contracts are accepted; the completion/reset boundary was refined by Việt
on 2026-10-22. Exact wrapper ports and pipeline-register implementation remain deferred.
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Design revision:** MEM D2 / 2026-10-22; refines BASE R2.
**Parent contract:** [Five-stage BASE core](5-stage-baseline-core.md).
**RTL mapping:** The three leaves have RTL; `memory_stage` composition remains
planned. This document does not establish functional verification.

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
inputs. It produces load data, WB source selection, MEM-wait control and the
data OBI outputs. Exact ports are deferred to the local designs.

As in EX, current-instruction metadata bypasses the wrapper: the core routes
`rd` and `reg_write` directly from EX/MEM toward MEM/WB. `ex_result` also
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

## 2. Selected decomposition

| Module | Responsibility | Storage |
| --- | --- | --- |
| `memory_stage` | Compose the leaves and derive WB source selection | No additional transaction or payload storage |
| `request_formatter` | Form aligned address, byte enables and replicated store data | Combinational |
| `load_formatter` | Select the response lane and sign/zero-extend load data | Combinational |
| `data_obi_controller` | Own request issue, outstanding state, expected completion and MEM-wait control | One `outstanding` bit |

Request formatting serves both loads and stores. The controller does not
interpret access width or load signedness; the formatters do not own
transaction state. Byte-lane and extension equations remain in the parent.

## 3. Shared memory-type encoding and fallback

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

## 4. Controller state and payload ownership

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

## 5. Deferred local decisions

Leaf port tables and behavior are owned by the accepted
[request formatter](request-formatter.md), [load formatter](load-formatter.md)
and [data OBI controller](data-obi-controller.md) contracts. Exact wrapper ports
and composition implementation still require their own design/implementation
step; leaf acceptance does not imply wrapper or full-pipeline verification.

Pipeline-register implementation remains deferred until its downstream payload
requirements are resolved. This document does not change the accepted reset,
stall/flush priority, OBI protocol, ISA scope or core arbitration.
