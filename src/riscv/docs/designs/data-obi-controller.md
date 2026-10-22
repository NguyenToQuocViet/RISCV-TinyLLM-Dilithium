# Data OBI Controller — Block Design

**Status:** Accepted by Việt; interface/reset refinement accepted on 2026-10-22.
**Revision:** DOC D2 / 2026-10-22.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [MEM ownership](memory-stage.md#4-controller-state-and-payload-ownership),
[BASE OBI events](5-stage-baseline-core.md#obi-response-validity-and-reset),
[data completion](5-stage-baseline-core.md#data-transaction-completion).
**RTL mapping:** `data_obi_controller` in
[data_obi_controller.sv](../../rtl/data_obi_controller.sv);
RTL is present; full leaf verification remains pending.

## 1. Purpose and boundary

Present the held EX/MEM load/store as one data OBI transaction, suppress
duplicate requests after grant, and release MEM wait only on its expected
response. Both control and payload pass through this leaf. The controller
stores only one `outstanding` bit; EX/MEM retains the instruction and payload.

The request formatter supplies aligned address, byte enables and write data.
The response data passes to the load formatter. Neither formatting nor
instruction decode belongs here. The controller does not contain pipeline
registers, a response buffer, a timeout, cancellation or bus-error handling.

## 2. Interface contract

Port names, payload mappings and local signal equations are accepted. Widths
reuse [riscv_pkg](../../rtl/riscv_pkg.sv); only
`DATA_WIDTH = ADDR_WIDTH = 32` is supported. All scalar ports are 1-bit `logic`;
payload vectors are unsigned. There are no module parameters or new enums.

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `clk` | Input | 1 bit | Core clock; transfers sampled on rising edges |
| `rst_n` | Input | 1 bit | Shared active-low reset |
| `instruction_valid` | Input | 1 bit | Current EX/MEM instruction is live; parent clears it asynchronously during reset |
| `mem_en` | Input | 1 bit | Current instruction requires a data access |
| `mem_write` | Input | 1 bit | Store intent; zero for a load |
| `aligned_address` | Input | `logic [ADDR_WIDTH-1:0]` | Request formatter's aligned byte address |
| `byte_enable` | Input | `logic [3:0]` | Request formatter's selected lanes |
| `write_data` | Input | `logic [DATA_WIDTH-1:0]` | Request formatter's store payload |
| `gnt` | Input | 1 bit | OBI address-phase grant |
| `rvalid` | Input | 1 bit | OBI response valid |
| `rdata` | Input | `logic [DATA_WIDTH-1:0]` | OBI response payload |
| `req` | Output | 1 bit | OBI request presentation |
| `addr` | Output | `logic [ADDR_WIDTH-1:0]` | OBI address, from `aligned_address` |
| `we` | Output | 1 bit | OBI write enable, from `mem_write` |
| `be` | Output | `logic [3:0]` | OBI byte enables, from `byte_enable` |
| `wdata` | Output | `logic [DATA_WIDTH-1:0]` | OBI write data, from `write_data` |
| `rready` | Output | 1 bit | Constant one, including during reset |
| `read_data` | Output | `logic [DATA_WIDTH-1:0]` | Unregistered pass-through of `rdata` to load formatter |
| `mem_wait` | Output | 1 bit | Current live memory instruction is unresolved |

Payload outputs follow their corresponding inputs independently of request or
response qualification. They are not forced to zero or retained when inactive.
Only `req` authorizes address-phase acceptance. During normal operation, a live
memory owner with `mem_wait=0` has its expected response available for the
consuming edge. Parent pipeline control uses this condition and its normal
advance/capture rules to consume a formatted load response; `mem_wait=0` alone
does not indicate completion for an idle or non-memory instruction. There is
no separate completion output. A store ignores response data. No address/data
width conversion occurs inside this leaf.

## 3. Events, state and timing

The interface refines the parent's event definitions as follows.
All expressions use current inputs and pre-edge `outstanding`:

```text
memory_owner = instruction_valid && mem_en
req          = memory_owner && !outstanding
mem_wait     = memory_owner && !(outstanding && rvalid)
```

`req` does not depend on `gnt` or `rvalid`. Outside reset, request acceptance
occurs on an edge with `req && gnt`; expected response acceptance occurs on an
edge with pre-edge `outstanding && rvalid`, because `rready=1`. These retain the
parent's event semantics without requiring named intermediate RTL signals or
a completion port. `mem_wait` is combinational, not a registered notification.
An expected response releases wait on that same edge, without an extra release
cycle. Grant alone never releases wait.

| Pre-edge `outstanding` | Sampled event | Next `outstanding` |
| ---: | --- | ---: |
| 0 | No request transfer | 0 |
| 0 | Request transfer | 1 |
| 1 | No expected response transfer | 1 |
| 1 | Expected response transfer | 0 |

Reset overrides this table. While outstanding, `req=0`; the current memory
instruction remains in EX/MEM. A later memory owner can present its request
after the response edge updates EX/MEM and clears outstanding, not as a second
request on that response edge. Controller state continues progressing during
the global MEM stall; there is no stall input that freezes protocol ownership.

## 4. Environment, reset and unexpected responses

**Design invariant: `instruction_valid` MUST be zero during reset.** It comes
from the asynchronously reset EX/MEM valid bit, not from unreset payload or a
constant. This is a required parent/harness input guarantee, not an optional
optimization; without it this leaf can assert `req` even while `rst_n=0`.

The parent must keep a live memory owner and its complete payload stable until
expected completion. In particular, `req` and address-phase fields remain
stable throughout an ungranted request. Outstanding ownership is not canceled
by pipeline stalls or younger redirects. This leaf has no flush input.

`outstanding` resets asynchronously to zero using the shared
[reset strategy](5-stage-baseline-core.md#reset-architecture). Release is
already synchronized before `rst_n` reaches this leaf; no local synchronizer
is added. The combinational request/wait logic does not use `rst_n`: the parent
must asynchronously clear `instruction_valid` and keep it zero throughout reset.
After reset propagation, this forces `req=0` and `mem_wait=0` regardless of
unreset payload. The standalone leaf harness must supply the same input
guarantee; this leaf does not independently mask a high valid input during reset.
Parent capture/retirement and the OBI subordinate must also obey shared reset,
so no reset edge creates a transaction or consumes a result. Reset-distribution
skew may cause transient combinational outputs; this choice does not guarantee
glitch-free request isolation. Payload wires are not reset. System/harness reset
must also quiesce old bus work; clearing this bit cannot cancel a previously
accepted store or guarantee that a late response belongs to a new transaction.

This implements the parent's reset/valid gating requirement; it does not reset
`mem_en`, `mem_write` or formatter payload. The parent's `data_response_fire`
denotes a sampled completion event, not a required port or stored pulse. With
the retained-owner invariant and reset inactive, it is equivalent to
`memory_owner && !mem_wait`. Parent capture must still obey reset and pipeline
advance rules. Both the controller and EX/MEM must share reset; resetting only
one of them while a transaction is live is outside this boundary.

An unexpected raw response is drained because `rready=1`, but it does not
complete the current instruction or clear wait. If an unexpected response
coincides with the first request grant, the request still establishes
outstanding ownership; the raw response cannot complete that new transaction.
Verification reports the protocol violation. Same-edge response consumption
for a newly granted request is not supported by the parent's pre-edge rule.

Alignment, legal memory types, stable ownership and the OBI environment remain
parent obligations. No hardware checker, trap or recovery is added here. The
guaranteed input domain contains only 0/1; X/Z behavior is outside scope.

## 5. Edge trace and verification boundary

The following load/store trace assumes a valid, stable memory owner and reset
inactive. A store follows the same control sequence as a load.

| Edge | State before | Inputs | `req` / `mem_wait` | State after / parent action |
| --- | ---: | --- | --- | --- |
| A | 0 | `gnt=0`, `rvalid=0` | 1 / 1 | 0; retain owner and request |
| B | 0 | `gnt=1`, `rvalid=0` | 1 / 1 | 1; retain owner while awaiting response |
| C | 1 | `rvalid=0` | 0 / 1 | 1; no duplicate request |
| D | 1 | `rvalid=1` | 0 / 0 | 0; parent advances completed MEM instruction |

Planned leaf checks cover delayed grant/response, payload pass-through, invalid
and non-memory owners, duplicate suppression, unexpected responses including
response-plus-first-grant, reset without a clock edge and reset at transfer
boundaries. Reset checks must clear parent valid and reset subordinate protocol
state as specified above; high valid during reset violates the leaf environment.
Check expected-response wait release combinationally before its edge; do not
mistake the cleared post-edge ownership for a missing completion.
MEM integration separately checks held EX/MEM payload, load-result capture,
store completion, WB retirement and consecutive memory instructions. No test
or verification framework is created by this design document.

## 6. Local decisions

**DOC-D1 — Accepted boundary.** Việt selected control and payload through the
controller, with no private payload storage. Compared with control-only ports,
this gives the leaf one complete OBI boundary at the cost of more pass-through
ports. It does not add a payload register or another cycle of latency.

**DOC-D2 — Accepted interface and timing.** Việt accepted the port names,
direct payload mappings and control equations in sections 2–3 on 2026-10-21.
The inherited one-outstanding ownership, completion, reset and pipeline
behavior were retained; DOC-D3 supersedes the separate completion port and
direct reset gating from that interface.

**DOC-D3 — Completion and reset boundary refinement, accepted 2026-10-22.**
Việt selected `req` and `mem_wait` as the only variable control outputs, removing
`response_fire` and its intermediate event signals from RTL. Parent control
already has the valid/memory intent needed to interpret wait release. Reset
continues to clear `outstanding` asynchronously, while request/wait suppression
relies on the parent's reset valid instead of a combinational reset gate. This
keeps the control structure small, but makes the valid/reset environment
mandatory and does not provide independent glitch-free bus isolation. Revisit
this boundary if valid is no longer reset, the controller is independently
reset, or the receiver cannot obey shared reset. There is no added buffering,
latency or outstanding capacity. No local design decision remains open.
