# Fetch Stage — Block Design

**Status:** Accepted by Việt on 2026-11-01
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Parent contract:** [Five-stage BASE core](5-stage-baseline-core.md), in particular
[instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization),
[IF/ID boundary](5-stage-baseline-core.md#ifid-boundary),
[pipeline-control priority](5-stage-baseline-core.md#pipeline-control-priority) (including the
frontend amendment IF-A1),
[instruction fetch capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states),
[stale instruction responses after redirect](5-stage-baseline-core.md#stale-instruction-responses-after-redirect),
[OBI baseline configuration](5-stage-baseline-core.md#obi-baseline-configuration),
[OBI response validity and reset](5-stage-baseline-core.md#obi-response-validity-and-reset) and
[reset architecture](5-stage-baseline-core.md#reset-architecture);
[memory-stage.md](memory-stage.md) and [decode-stage.md](decode-stage.md) for port and layout precedent.
**RTL mapping:** The three leaves exist in `rtl/`: `fetch_obi_interface` (`04f4535`), `fetch_buffer`
(`2a8d0bf`, its latest commit) and `fetch_controller_unit` (`d985318`). `prefetch_unit` and `fetch_stage` exist
too (`4f2135c`; checked 2026-11-05). Names are fixed in section 3 (N1, N4). The RTL for the IF-A3 move is delegated
(F-d); the leaf commits above predate it.
This document is neither implementation nor verification evidence.

**Amendment IF-A3 (accepted by Việt on 2026-11-06).** All fetch control state moves to the
[Fetch Controller Unit](fetch-controller-unit.md) (FCU-O13); the [Fetch Buffer](fetch-buffer.md) stores `pc` and
`instruction` payload only (FB-O8, FB-O9). Behavior is unchanged. The 2026-11-04 buffer decisions are
mapped to their new IDs in those two documents. The RTL for this move is delegated (F-d).

**Amendment IF-A2 (accepted by Việt on 2026-11-05).** The redirect edge does not allocate the EX
redirect target. `next_fetch_pc` takes `redirect_target` on that edge, and the target is allocated as a fresh
`QUEUED` entry on the following edge. The rows below that describe the redirect edge are worded for it.
See [fetch-controller-unit.md](fetch-controller-unit.md) and BASE IF-A2.

## 1. Purpose and boundary

`fetch_stage` is the BASE IF stage. It turns the sequential, redirected instruction-address
stream into the instruction stream offered to the core IF/ID register: the `pc` and
`instruction` of the oldest live `READY` fetch entry, payload held in the Fetch Buffer (BASE
[instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization);
[IF/ID boundary](5-stage-baseline-core.md#ifid-boundary)). It also owns the instruction-side
OBI port.

Observable success criterion: every instruction delivered on `fetch_fire` has the `pc` and word
that the instruction port returned for that address; deliveries follow allocation order, not
numerical PC order; and no entry that was wrong-path at a redirect edge can be delivered
afterwards (BASE
[capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states),
[stale instruction responses](5-stage-baseline-core.md#stale-instruction-responses-after-redirect)).

The stage sees exactly two control sources (F-e):

- **EX redirect, raw.** `redirect_fire` and `redirect_target` come straight from the EX
  `redirect_unit`. Inside IF, a redirect only changes the fetch PC and the fetch entries. The
  flush of IF/ID and ID/EX that the same redirect causes is the Hazard Control Unit's job, not IF's.
- **Global events, through the Hazard Control Unit (HCU).** Load-use and the unresolved MEM wait
  reach IF only as `fetch_accept = 0`, meaning IF/ID does not take an instruction this edge. IF
  receives no MEM, load-use or pipeline-occupancy signal (BASE IF-A1).

Non-goals:

- No branch prediction. The BASE baseline has no predictor (BASE instruction-fetch organization).
- No IF/ID register. It is core-owned (F-a).
- No hazard knowledge and no MEM signal. The HCU resolves global events (F-b, F-e).
- No fetch throttling for data traffic. The ports are independent; a later shared memory path
  arbitrates through `gnt` (BASE IF-A1; BASE integration obligations).
- No instruction decode and no legality check. ID owns decode (BASE IF/ID boundary).
- No bus-error, illegal-instruction or exception output. BASE has none (BASE
  [OBI baseline configuration](5-stage-baseline-core.md#obi-baseline-configuration)).
- No address-range checking. The code-region precondition belongs to the harness and test
  program (BASE [stale instruction responses](5-stage-baseline-core.md#stale-instruction-responses-after-redirect)).
- No leaf internals. The leaf designs own them: [fetch-buffer.md](fetch-buffer.md),
  [fetch-controller-unit.md](fetch-controller-unit.md) and [fetch-obi-interface.md](fetch-obi-interface.md).

Producers and consumers at the stage boundary:

- `fetch_accept`: the core-level HCU (F-b).
- `redirect_fire`, `redirect_target`: the EX `redirect_unit`, already qualified by EX advance
  (BASE [redirect event](5-stage-baseline-core.md#redirect-event-and-pipeline-recovery)). The HCU
  also consumes `redirect_fire` for its own flush decisions.
- Delivery outputs: the core IF/ID register.
- Instruction-memory subordinate: the instruction OBI port.

Inherited by reference, not restated: the BASE fetch organization, capacity and lifecycle, stale
response rules, pipeline-control priority, OBI rules and reset architecture. Local refinements are
the names, the interface table and the decisions in section 9.

## 2. Interface contract

### Clock, reset and configuration

`clk` is the rising-edge clock for the Fetch Controller and Fetch Buffer state. `rst_n` is the
core's active-low reset: asserted asynchronously, released synchronized (BASE
[reset architecture](5-stage-baseline-core.md#reset-architecture)). On assertion, the Fetch
Controller's `next_fetch_pc` takes `PC_RESET_VEC`, and the control state is cleared (section 6).

Constants and parameters:

- `PC_RESET_VEC = 32'h0000_0000` is a BASE constant defined in the RISC-V package (BASE
  [purpose and boundary](5-stage-baseline-core.md#purpose-and-boundary)). It is defined in
  `rtl/riscv_pkg.sv` (dependency D-1, resolved 2026-11-01).
- `FETCH_DEPTH = 3` (BASE instruction-fetch organization), defined in `rtl/riscv_pkg.sv` (N2).
- `OBI_OUTSTANDING_MAX = 1` is a link contract on the instruction port, not an OBI property and not
  a port (BASE [OBI baseline configuration](5-stage-baseline-core.md#obi-baseline-configuration)).

The supported configuration is `DATA_WIDTH = ADDR_WIDTH = INSTR_WIDTH = 32`.

### Ports and payloads

All ports are individual signals; no packed payload struct. Types refer to `riscv_pkg`. There are
8 inputs and 9 outputs. Instruction-port names are the plain names of `rtl/memory_stage.sv`
(F-c); the core adds the `instr_` prefix.

| Signal | Direction | Type / width | Meaning | Valid when | Source |
| --- | --- | --- | --- | --- | --- |
| `clk` | Input | 1-bit `logic` | Rising-edge clock | Always | Reset architecture |
| `rst_n` | Input | 1-bit `logic` | Active-low reset, async assert, synchronized release | Always | Reset architecture; N3 |
| `fetch_accept` | Input | 1-bit `logic` | HCU: IF/ID may take an instruction on this edge. A delivery happens only on `fetch_fire = fetch_valid && fetch_accept` | Each cycle; `0` under load-use and unresolved MEM wait; may be `1` while `fetch_valid = 0` | [Pipeline-control priority](5-stage-baseline-core.md#pipeline-control-priority); F-b, O5 |
| `redirect_fire` | Input | 1-bit `logic` | EX taken control-flow redirect on this edge, raw from `redirect_unit` | Each cycle; already `0` while EX cannot advance | [Redirect event](5-stage-baseline-core.md#redirect-event-and-pipeline-recovery); F-e |
| `redirect_target` | Input | `logic [ADDR_WIDTH-1:0]` | Redirect target address | When `redirect_fire = 1` | Redirect event; F-e |
| `gnt` | Input | 1-bit `logic` | Instruction OBI grant | Sampled at the rising edge with `req` | [OBI baseline](5-stage-baseline-core.md#obi-baseline-configuration); F-c |
| `rvalid` | Input | 1-bit `logic` | Instruction OBI response valid | Raw response transfer with `rready` | [OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset); F-c |
| `rdata` | Input | `logic [INSTR_WIDTH-1:0]` | Instruction word returned by the port | When `rvalid && rready`; captured only for an expected response | OBI response validity; F-c |
| `req` | Output | 1-bit `logic` | Instruction request for the presented entry | From first presentation until that entry's `gnt`; stable while asserted | [Capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states); F-c |
| `addr` | Output | `logic [ADDR_WIDTH-1:0]` | The `pc` of the presented entry | When `req = 1` | Capacity and transaction states; F-c |
| `we` | Output | 1-bit `logic` | Constant `0` (read-only port) | Always | [OBI baseline](5-stage-baseline-core.md#obi-baseline-configuration); F-c |
| `be` | Output | `logic [3:0]` | Constant `4'b1111` (full word) | Always | OBI baseline; F-c |
| `wdata` | Output | `logic [DATA_WIDTH-1:0]` | Constant `0` | Always | OBI baseline; F-c |
| `rready` | Output | 1-bit `logic` | Constant `1`: every expected response is accepted; a killed one is drained | Always | [OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset); F-c |
| `fetch_valid` | Output | 1-bit `logic` | An oldest live `READY` entry exists | From registered fetch-entry state | Capacity and transaction states; F-b |
| `fetch_pc` | Output | `logic [ADDR_WIDTH-1:0]` | `pc` of that entry | When `fetch_valid = 1` | [IF/ID boundary](5-stage-baseline-core.md#ifid-boundary) |
| `fetch_instruction` | Output | `logic [INSTR_WIDTH-1:0]` | `instruction` payload of that entry | When `fetch_valid = 1` | IF/ID boundary; capacity and transaction states |

The core connects `fetch_valid`, `fetch_pc` and `fetch_instruction` to the IF/ID register inputs
(`valid_i` and payload, BASE
[pipeline-register local control](5-stage-baseline-core.md#pipeline-register-local-control)). The
HCU drives that register's `stall` and `flush` and drives `fetch_accept` so that IF frees an entry
exactly when IF/ID captures it. The HCU rule is not part of this document (D-3).

Width domains: `pc` and addresses are `ADDR_WIDTH`; the instruction word is `INSTR_WIDTH` (the
32-bit base encoding, not ILEN). `be` is the OBI byte-enable field, not a datapath vector.

### Transfer and timing rules

- `fetch_valid`, `fetch_pc`, `fetch_instruction`, `req` and `addr` are functions of registered
  fetch-entry (controller and payload) state only. They are not combinational from `gnt`, `rvalid`,
  `rdata`, `fetch_accept` or `redirect_*` (BASE
  [capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states),
  `RESPONSE_BYPASS=0`). The stage takes no data-port signal, so no path from the data port to `req`
  exists (BASE IF-A1).
- `fetch_accept`, `redirect_fire` and `redirect_target` are sampled at the rising edge with the
  other inputs. An edge with `rst_n = 0` has no transfer, delivery or allocation effect (BASE
  [reset architecture](5-stage-baseline-core.md#reset-architecture)).
- A delivery waits: `fetch_valid`, `fetch_pc` and `fetch_instruction` keep showing the same entry
  until `fetch_fire` or a redirect frees it.
- Instruction responses are never backpressured. `rready` is constant `1`, and every
  `OUTSTANDING` entry reserved its storage before it was granted (BASE
  [OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset)).

## 3. Internal organization

### Hierarchy and naming (N1)

The BASE hierarchy is `core -> IF -> Prefetch Unit -> {Fetch Controller Unit, Fetch Buffer, OBI Interface}`
(BASE instruction-fetch organization). `fetch_stage` is the IF stage. It contains one child,
`prefetch_unit`, which contains three leaves. Module and file names have no `riscv_` prefix.
Instance names follow the `id_<module>` pattern of
[decode-stage.md](decode-stage.md#hierarchy-and-naming-d1).

| Module | File basename | Instance name | Instantiated by |
| --- | --- | --- | --- |
| `fetch_stage` | `fetch_stage.sv` | `if_stage` | Core |
| `prefetch_unit` | `prefetch_unit.sv` | `if_prefetch_unit` | `fetch_stage` |
| `fetch_controller_unit` | `fetch_controller_unit.sv` | `if_fetch_controller_unit` | `prefetch_unit` |
| `fetch_buffer` | `fetch_buffer.sv` | `if_fetch_buffer` | `prefetch_unit` |
| `fetch_obi_interface` | `fetch_obi_interface.sv` | `if_fetch_obi_interface` | `prefetch_unit` |

```text
if_stage : fetch_stage
  if_prefetch_unit : prefetch_unit
    if_fetch_controller_unit : fetch_controller_unit
    if_fetch_buffer          : fetch_buffer
    if_fetch_obi_interface   : fetch_obi_interface
```

### Wiring

```text
redirect_fire, redirect_target, fetch_accept, rst_n, clk
    -> fetch_controller_unit  (all fetch control state; FCU-O13)
         -> pc_write, pc_write_slot, pc_write_data           -> fetch_buffer (pc array)
         -> instruction_write, instruction_write_slot        -> fetch_buffer (instruction array)
         -> present_slot, fetch_slot                         -> fetch_buffer (read addresses)
         -> present_valid                                    -> fetch_obi_interface
         -> fetch_valid                                      -> fetch stage output (O5: fetch_fire)
fetch_buffer -> present_pc (pc[present_slot])                -> fetch_obi_interface
fetch_buffer -> fetch_pc, fetch_instruction (slot fetch_slot) -> fetch stage output
request_fire, raw_response_transfer -> fetch_controller_unit (from fetch_obi_interface)
fetch_obi_interface -> response_data -> fetch_buffer.instruction_write_data
fetch_obi_interface -> req, addr, we, be, wdata, rready        (instruction port out)
gnt, rvalid, rdata -> fetch_obi_interface                      (grant and response in)
```

### Prefetch Unit wrapper and internal nets (N4)

Owner decision, 2026-11-05. `prefetch_unit` has the same 17 ports as `fetch_stage` (8 inputs, 9 outputs;
section 2), with the same names and widths. `fetch_stage` has one child, so it connects them by name with no
logic and no internal nets. `prefetch_unit` has no logic of its own and gets no separate `prefetch-unit.md`:
this section specifies it.

`clk` goes to `fetch_controller_unit` and `fetch_buffer` only; `fetch_obi_interface` has no `clk`
([fetch-obi-interface.md](fetch-obi-interface.md) FOI-O1). `rst_n` goes to `fetch_controller_unit` and `fetch_obi_interface`; the payload array has no reset.

The twelve nets inside `prefetch_unit` are the leaf port names below (IF-A3, FCU-O13). Widths are checked against the
leaf port lists in `rtl/`. `kill`, `alloc_fire` and `next_fetch_pc` are internal to `fetch_controller_unit` and are not nets.

| Net | Width | Driver | Load |
| --- | --- | --- | --- |
| `pc_write` | 1-bit `logic` | `fetch_controller_unit` (= `alloc_fire`, FCU-O4) | `fetch_buffer` |
| `pc_write_slot` | `logic [1:0]` | `fetch_controller_unit` (= `head_ptr`) | `fetch_buffer` |
| `pc_write_data` | `logic [ADDR_WIDTH-1:0]` | `fetch_controller_unit` (= `next_fetch_pc`, FCU-O4) | `fetch_buffer` |
| `instruction_write` | 1-bit `logic` | `fetch_controller_unit` (= `response_fire`) | `fetch_buffer` |
| `instruction_write_slot` | `logic [1:0]` | `fetch_controller_unit` (= `prv`) | `fetch_buffer` |
| `present_slot` | `logic [1:0]` | `fetch_controller_unit` (= `issue_ptr`) | `fetch_buffer` |
| `fetch_slot` | `logic [1:0]` | `fetch_controller_unit` (= `tail_ptr`) | `fetch_buffer` |
| `present_valid` | 1-bit `logic` | `fetch_controller_unit` (entry at `issue` is `QUEUED`) | `fetch_obi_interface` |
| `present_pc` | `logic [ADDR_WIDTH-1:0]` | `fetch_buffer` (`pc[present_slot]`) | `fetch_obi_interface` |
| `request_fire` | 1-bit `logic` | `fetch_obi_interface` | `fetch_controller_unit` |
| `raw_response_transfer` | 1-bit `logic` | `fetch_obi_interface` | `fetch_controller_unit` |
| `response_data` | `logic [INSTR_WIDTH-1:0]` | `fetch_obi_interface` (`rdata` pass-through, FOI-O6) | `fetch_buffer` |

### Leaf responsibilities

- **`fetch_controller_unit`** — the instruction-fetch control plane (FCU-O13; BASE
  [instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization)). It owns every
  control state element with a reset: `next_fetch_pc`, the entry lifecycle `FREE`/`QUEUED`/`OUTSTANDING`/`READY`,
  the killed marks and the three slot pointers, with all logic on them: allocation, presentation of the entry at
  `issue`, response qualification, delivery and kill recovery. It drives the write enables, write addresses and read
  addresses of `fetch_buffer`. It has no `gnt` input. Its encoding is in
  [fetch-controller-unit.md](fetch-controller-unit.md).
- **`fetch_buffer`** — payload only (FB-O8, FB-O9): the `pc` and `instruction` of the `FETCH_DEPTH = 3` slots,
  as indexed arrays with no reset, and the read muxes that present `pc[present_slot]`, `pc[fetch_slot]` and
  `instruction[fetch_slot]`. It has no lifecycle, no pointers and no kill logic. Its encoding is in
  [fetch-buffer.md](fetch-buffer.md).
- **`fetch_obi_interface`** — presents the chosen entry as protocol signals and drives the constant
  port fields (F-c). It is stateless ([fetch-obi-interface.md](fetch-obi-interface.md) FOI-O1): the
  OBI hold, stability and no-withdrawal rules of BASE instruction-fetch organization are met at the
  port because the controller keeps the entry at `issue` `QUEUED` until its `request_fire`, and the buffer
  keeps its `pc` (FCU-O9, FB-O8).

Pipeline-register ownership: the IF/ID register is core-owned, outside this stage (F-a).

## 4. State and ownership

| State/storage | Meaning and owner | Update event | Hold rule | Reset value or no-reset rationale |
| --- | --- | --- | --- | --- |
| `next_fetch_pc` (`ADDR_WIDTH`) | Next address to allocate; `fetch_controller_unit` | Each allocation: `+4`; redirect edge: `redirect_target`, with no allocation on that edge (IF-A2) | Holds when nothing is allocated, including while the ring is full | `PC_RESET_VEC` (BASE reset architecture) |
| Entry lifecycle (`FREE`, `QUEUED`, `OUTSTANDING`, `READY`) | Entry validity and lifecycle; `fetch_controller_unit` (FCU-O13) | Allocation, grant, response, `fetch_fire`, redirect | Per the BASE lifecycle | `FREE` (BASE reset architecture: entry-valid and lifecycle state) |
| Entry `protocol_committed` (derived) | Request ownership; `fetch_controller_unit`, derived as `life[issue] == QUEUED` (FCU-O9) | The entry at `issue` is presented from the first cycle in which it is `QUEUED` at `issue`; a redirect on that edge keeps it (BASE capacity and transaction states) | Holds until the entry's own `gnt`, which moves `issue` (FCU-O7) | None stored; derived from `life`, which resets to `FREE` |
| Entry `killed` | Wrong-path marker; `fetch_controller_unit` (FCU-O10) | Redirect edge, for each kept entry | Set until the entry is drained or freed (BASE stale-response section) | `0` (control-plane state) |
| Entry `pc` (`ADDR_WIDTH`) | Fetch address and delivered `fetch_pc`; payload in `fetch_buffer`, written by the controller | Allocation (`pc_write`) | Holds for the entry's life; stable while `req` is asserted | Not reset; meaningful only while the entry is valid (BASE reset architecture) |
| Entry `instruction` (`INSTR_WIDTH`) | Payload of a `READY` entry; payload in `fetch_buffer`, written by the controller | Expected response for a live `OUTSTANDING` entry (`instruction_write`) | Holds while `READY` | Not reset (BASE reset architecture) |
| Outstanding count (`0` or `1`) | Derived, not stored: `life[issue - 1] == OUTSTANDING` (FCU-O8) | `request_fire`, `response_fire` | Derived | No state; `life` resets to `FREE` (BASE OBI response validity and reset) |
| Allocation order | Three-slot ring: `head_ptr`, `issue_ptr`, `tail_ptr` (FCU-O7) | Allocation, `request_fire`, delivery, redirect | Holds | `head = issue = tail = 0` |

Ownership rules: the presented request's payload is the entry's `pc`; `addr` and `req` do not
change before the matching `gnt` (BASE capacity and transaction states). A `FREE` entry's payload
has no meaning and cannot authorize a delivery or a request. `fetch_valid` comes from lifecycle
state, not from payload.

## 5. Behavioral and next-state rules

### 5.1 Definitions (pre-edge state)

- **Live `READY`**: an entry in `READY` that is not killed. A redirect frees every `READY` entry on
  its edge (BASE stale-response section), so a killed `READY` entry never persists.
- **Delivery event**: `fetch_fire = fetch_valid && fetch_accept` (O5). It frees the oldest live
  `READY` entry; the core IF/ID captures that entry on the same edge.
- **Presentable**: the entry at `issue`, when it is `QUEUED` (FCU-O9). It is always committed, so no
  uncommitted entry is presented. An older `OUTSTANDING` entry does not block presentation; the subordinate
  holds `gnt = 0` until it can accept (BASE capacity and transaction states).
- **Allocation**: a `FREE` entry, counting entries freed on this edge, receives `next_fetch_pc` as a
  new `QUEUED` entry. There is no other allocation condition (BASE IF-A1), and a redirect edge allocates nothing (IF-A2). A full buffer stops
  allocation by capacity alone.

### 5.2 Concurrent-event rules

| Condition | Events on this edge | Actions | Next state |
| --- | --- | --- | --- |
| `rst_n = 0` | Any | No request, transfer, delivery or allocation (BASE reset architecture) | `next_fetch_pc = PC_RESET_VEC`; control state reset (section 6) |
| `redirect_fire = 1` | Grant and response events on this edge still apply | Every `READY` entry is freed, whatever `fetch_accept` is; an `OUTSTANDING` entry is killed and kept, or freed if its `response_fire` occurs; a protocol-committed `QUEUED` entry is killed and kept, and becomes killed `OUTSTANDING` if granted on this edge; an uncommitted `QUEUED` entry is freed; the target is not allocated on this edge; it is allocated as a fresh uncommitted `QUEUED` entry on the following edge (IF-A2; BASE stale-response section, four cases) | `next_fetch_pc = redirect_target` |
| No redirect, `fetch_fire = 1` | Delivery; grant and response events; allocation | The oldest live `READY` entry is freed; that slot may be allocated on the same edge (BASE capacity and transaction states, one-edge example) | As the events dictate |
| No redirect, `fetch_fire = 0` (HCU stall, or nothing `READY`) | Grant and response events; allocation | No delivery. Allocation and presentation continue until every entry is occupied (BASE IF-A1) | As the events dictate |

Rules that hold in every row:

- On a redirect edge the IF/ID register is flushed by the HCU, not by IF. IF frees its `READY`
  entries on that edge whatever `fetch_accept` is, so no wrong-path entry survives in IF (BASE
  stale-response section, first bullet).
- A response and a grant on the same edge keep the outstanding count at one (BASE capacity and
  transaction states, `A`/`B` example).
- Allocation may reuse a slot freed on the same edge (BASE capacity and transaction states; BASE
  stale-response section, "reclaimed from stale `READY`").

### 5.3 Protocol events

Using the BASE event definitions (BASE OBI response validity and reset):

```text
request_fire  = rst_n && req && gnt
response_fire = outstanding && rst_n && rvalid && rready        (rready = 1)
```

- `request_fire` moves the presented `QUEUED` entry to `OUTSTANDING`. The outstanding count follows
  `next = current + request_fire - response_fire` and never exceeds `OBI_OUTSTANDING_MAX = 1`.
- `response_fire` on a live `OUTSTANDING` entry captures `rdata` and moves the entry to `READY`; on a
  killed `OUTSTANDING` entry it discards the response and frees the entry (BASE capacity and
  transaction states).
- `rvalid` with no `OUTSTANDING` entry is an unexpected response: drained, no state change, no
  `READY` entry, reported as a protocol violation by verification (BASE OBI response validity and reset).

### 5.4 Derived outputs

- `fetch_valid = 1` iff a live `READY` entry exists. `fetch_pc` and `fetch_instruction` are the
  payload of the oldest one in allocation order, not the numerically lowest PC.
- `req = 1` iff an entry is presented and not yet granted; `addr` is that entry's `pc`.

## 6. Reset, cancellation and exceptional conditions

**Reset.** On `rst_n = 0`, after reset propagation and without a clock edge, the stage drives
`req = 0`; `next_fetch_pc` takes `PC_RESET_VEC`; every entry becomes `FREE`; `killed`,
`protocol_committed` and the outstanding count are cleared. Entry `pc` and `instruction` are not
reset (BASE reset architecture; BASE OBI response validity and reset). No edge sampling `rst_n = 0`
counts a request, response or delivery. After release, the instruction subordinate must not return
a response for a pre-reset transaction (BASE OBI response validity and reset).

**Redirect as cancellation.** A redirect is the only cancellation of wrong-path work inside IF. The
four cases and the target allocation are in section 5.2 and the BASE stale-response section. A
protocol-committed entry is never retracted (BASE capacity and transaction states).

**Environment preconditions** (harness and test program; BASE stale-response section):

- Every instruction request address is in the code region, including speculative and wrong-path
  fetches. The frontend can request up to `FETCH_DEPTH` words beyond the instruction in IF/ID, so
  test images end with safe terminal control flow (for example `j .`) followed by NOP padding
  that keeps those requests in range. This bound comes from capacity, not from IF-A1; the BASE
  padding rule is unchanged.
- Inputs are `0` or `1` only (O4).

**Outside the contract.** Unexpected responses are drained and reported (section 5.3). Instruction
bus errors do not exist at this boundary (BASE OBI baseline). The stage has no error output, flag or
default vector.

## 7. Representative examples or cycle traces

### Trace A: steady state with response, grant and delivery on one edge

Pre-edge: `next_fetch_pc = 0x14`. S1 `READY` (`pc=0x08`, `I1`); S2 `OUTSTANDING` (`pc=0x0C`); S3
`QUEUED`, committed, `req=1` (`pc=0x10`). Inputs: `fetch_accept=1`, `redirect_fire=0`, `gnt=1`,
`rvalid=1`, `rdata=I2` (word at `0x0C`).

| Edge | Events | State before | Action | State after |
| --- | --- | --- | --- | --- |
| E | `fetch_fire=1`; `request_fire` for S3; `response_fire` for S2 | S1 `READY` `0x08`; S2 `OUTSTANDING` `0x0C`; S3 `QUEUED` committed `0x10`; outstanding `1` | IF/ID captures `{0x08, I1}`; S1 freed and reallocated with `0x14`; S2 captures `I2`; S3 granted | S1 `QUEUED` `0x14` committed (at `issue`, FCU-O9); S2 `READY` `0x0C`; S3 `OUTSTANDING` `0x10`; `next_fetch_pc=0x18`; outstanding `1` |

After E: `fetch_valid=1` with `{0x0C, I2}`. `0x14` is presentable in the next cycle because S3 is
no longer waiting for `gnt`. One instruction per cycle is sustained (BASE capacity and transaction
states).

### Trace B: redirect with a committed wrong-path entry not yet granted

Pre-edge: `next_fetch_pc = 0x28`. S1 `READY` (`0x1C`); S2 `OUTSTANDING` (`0x20`); S3 `QUEUED`,
committed, `req=1` (`0x24`). Inputs: `redirect_fire=1`, `redirect_target=0x100`, `fetch_accept=0`,
`gnt=0`, `rvalid=0`.

| Edge | Events | State before | Action | State after |
| --- | --- | --- | --- | --- |
| R | Redirect to `0x100` | As above | S1 freed; S2 killed and kept; S3 killed and kept, `req` stays `1`; no allocation on this edge | S1 `FREE`; S2 `OUTSTANDING` killed; S3 `QUEUED` committed killed, `req=1`; `fetch_valid=0`; `next_fetch_pc=0x100` |
| R+1 | Target allocation (IF-A2) | As after R; no grant or response | S1 allocated with `0x100` (uncommitted) | S1 `QUEUED` `0x100` uncommitted; S3 still waits for `gnt` with `req=1`; `next_fetch_pc=0x104` |

Afterwards: `0x100` is not presented while S3 waits for `gnt`. When S3 is granted it becomes killed
`OUTSTANDING`, and its response and S2's are drained to `FREE`, never `READY`. `0x100` is then
presented and delivered after its own response (BASE stale-response section).

### Trace C: HCU stall, the buffer fills and allocation stops by capacity

The HCU holds IF/ID (for example during a MEM wait), so `fetch_accept=0` on edges 1 and 2.
`redirect_fire=0`. The instruction memory responds one cycle after grant.

| Edge | Events | State before | Action | State after |
| --- | --- | --- | --- | --- |
| 1 | `response_fire` for S2, `request_fire` for S3 | S1 `READY` `0x08`; S2 `OUTSTANDING` `0x0C`; S3 `QUEUED` committed `0x10`; `next_fetch_pc=0x14` | No delivery; S2 `READY`; S3 `OUTSTANDING`; no `FREE` entry, so no allocation | S1 `READY` `0x08`; S2 `READY` `0x0C`; S3 `OUTSTANDING` `0x10`; `next_fetch_pc=0x14` |
| 2 | `response_fire` for S3 | As after edge 1 | S3 `READY`; nothing to present | Three `READY` entries; `req=0`; `next_fetch_pc=0x14` |
| 3 | `fetch_accept=1` (stall released) | As after edge 2 | `fetch_fire` delivers `0x08`; S1 reallocated with `0x14` | S1 `QUEUED` `0x14`; S2, S3 `READY`; `next_fetch_pc=0x18` |

`fetch_valid` stays `1` with `{0x08, I1}` through the stall. After release the frontend delivers
`0x0C` and `0x10` on the next two edges without waiting for memory, which is the benefit of IF-A1.

## 8. Verification obligations

Planned checks. No fetch test exists (`tb/runners/` has no fetch runner, checked 2026-11-05).
Expected values come from the BASE rules cited and the traces in section 7, not from the DUT.
Leaf-level checks are in the leaf designs; the rows below are the stage (composition) checks.

| Requirement/invariant | Stimulus or scenario | Expected observation |
| --- | --- | --- |
| Steady state (BASE capacity and transaction states) | Trace A | One delivery per edge; outstanding count stays `1` |
| No combinational path to `req` (BASE capacity; IF-A1) | Toggle `gnt`, `rvalid`, `fetch_accept`, `redirect_fire` within a cycle | `req`, `addr` and the delivery outputs change only after an edge |
| Oldest-first delivery (BASE capacity and transaction states) | Entries allocated in order with decreasing numeric PC after a redirect | Delivery follows allocation order |
| Redirect, `READY` entry (BASE stale-response section) | Redirect with `fetch_accept=1` and a `READY` entry | Entry freed; never delivered |
| Redirect, outstanding without response | Trace B | Entry killed, kept until drained, never delivered |
| Redirect, outstanding with response | Response on the redirect edge | Response discarded; entry `FREE` |
| Redirect, committed and granted | Grant on the redirect edge | Entry becomes killed `OUTSTANDING`; its response is drained |
| Redirect, committed not granted | Trace B | `req` and `addr` stay stable; not replaced or bypassed |
| Redirect, unpresented | Redirect with an uncommitted `QUEUED` entry | Entry freed; never presented |
| Redirect target | Redirect edge, then the following edge (Trace B) | No allocation on the redirect edge; target allocated as `QUEUED` on the following edge (IF-A2); its `req` starts two cycles after the redirect cycle at the earliest |
| HCU stall (IF-A1) | Trace C | Delivery held; buffer fills to three entries; allocation stops; no entry lost or reordered after release |
| `fetch_accept` without `fetch_valid` (O5) | `fetch_accept=1` while no entry is `READY` | No entry freed; state unchanged by the accept |
| Unexpected response (BASE OBI response validity and reset) | `rvalid` with no outstanding entry | No state change; reported as violation |
| Reset (BASE reset architecture) | `rst_n` asserted with entries in every state | `req=0` after propagation; `next_fetch_pc=PC_RESET_VEC`; entries `FREE`; payload not checked |
| Wrap (FCU-O7) | Many allocations through the three slots ([fetch-controller-unit.md](fetch-controller-unit.md) Trace W) | Ordering holds across slot reuse |
| Hold rule (fetch-obi-interface §3, §5) | Committed entry first presented with `redirect_fire=1` on that edge, then `gnt=0` for several edges, with a younger `QUEUED` entry behind it | `present_valid` and `present_pc` (so `req` and `addr`) stay on the committed entry until its `request_fire`; the redirect keeps it, and the younger entry is not presented |
| Composition trace (fetch-obi-interface §5, edges 1–6) | Replay that §5 sequence through this stage: `S2` outstanding; `S3` presented from edge 1 and granted with `S2`'s response on edge 3; `S4` queued; reset on edge 5; release on edge 6 | Edge 3: `S2` `READY` with `0x0C`, `S3` `OUTSTANDING`, one outstanding; edge 4: `req=1`, `addr=0x14` with `gnt=0`; edge 5: every entry `FREE`, `next_fetch_pc=PC_RESET_VEC`, `req=0` after propagation; edge 6: nothing presented. The fetch-obi table has no `next_fetch_pc` column, so `next_fetch_pc` is checked at reset only |

## 9. Rationale and open decisions

### Decisions recorded for acceptance (Owner, 2026-11-01)

| Id | Decision | Reason |
| --- | --- | --- |
| F-a | The IF/ID register is core-owned, outside `fetch_stage` | EX/MEM precedent ([memory-stage.md](memory-stage.md)); BASE IF/ID boundary |
| F-b | The HCU supplies the one global control, `fetch_accept`; outputs are `fetch_valid`, `fetch_pc`, `fetch_instruction` (oldest live `READY`). IF has no hazard or MEM knowledge | BASE PR-D1: parent resolves arbitration; IF stays free of hazard logic |
| F-c | Instruction OBI ports use the plain names of `rtl/memory_stage.sv`; `fetch_obi_interface` drives `we=0`, `be=4'b1111`, `wdata=0`, `rready=1`; the core adds the `instr_` prefix | Precedent and BASE constant port fields |
| F-d | Việt writes all IF RTL (leaves and wrapper). For the IF-A3 move (control to the controller, payload only in the buffer), the RTL is delegated and this document does not state that it is written by Việt | Learning-critical block (F-d original); delegation recorded for the IF-A3 move (Owner, 2026-11-06) |
| F-e | `redirect_fire` and `redirect_target` come raw from EX, because inside IF a redirect only changes the fetch PC and the entries. Global events (load-use, MEM wait, flushes of other stages) go through the HCU and reach IF only as `fetch_accept` | Owner principle: local effect stays direct, global effects go through the HCU |
| F-f | No MEM-wait freeze and no MEM-occupancy rule for the frontend; the BASE amendment IF-A1 records it. Fetch continues during any stall until the buffer is full | Two independent ports and memory models: withholding fetch protects nothing; a later shared path arbitrates through `gnt` |
| N1 | Names and instances of section 3 | `id_<module>` pattern; `fetch_obi_interface` avoids the `obi_interface` ambiguity |
| N2 | `FETCH_DEPTH = 3` and the entry lifecycle type `life_t` are defined in `riscv_pkg` (Owner, 2026-11-04); `OBI_OUTSTANDING_MAX` is not a port | Owner placed them in the package when writing `fetch_buffer` |
| N3 | `rst_n` is a stage input | BASE reset architecture |
| N4 | `prefetch_unit` has the same 17 ports as `fetch_stage` (8 inputs, 9 outputs), same names and widths. `fetch_stage` connects them by name with no logic and no internal nets. No separate `prefetch-unit.md` | Owner, 2026-11-05. A wrapper with no logic is specified by section 3 |
| O1 | Amended by FCU-O13 (IF-A3, accepted 2026-11-06, [fetch-controller-unit.md](fetch-controller-unit.md)): `fetch_controller_unit` presents the entry at `issue` (the oldest `QUEUED`) and drives the payload read addresses; `fetch_buffer` stores payload only; `fetch_obi_interface` presents only that entry and keeps it stable | Owner decision 2026-11-04, moved 2026-11-06; BASE [OBI-side selection](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states) already gives the oldest eligible `QUEUED` entry to the OBI side |
| O4 | Inputs are `0` or `1` only; X and Z are outside the contract | Accepted EX and WB precedent |
| O5 | `fetch_fire = fetch_valid && fetch_accept` is the only event that delivers and frees the oldest live `READY` entry | Standard valid/accept; no extra HCU gating |
| IF-A2 | Accepted 2026-11-05 (BASE amendment): the redirect edge loads `redirect_target` into `next_fetch_pc` without allocating it; the target is allocated on the following edge | The EX branch-resolve path no longer reaches the `pc` slots or a `+4` adder; the controller loses a mux and an adder. Cost: one more cycle per redirect. No synthesis numbers exist |
| IF-A3 | Accepted by Việt on 2026-11-06 (BASE amendment): all fetch control state moves to `fetch_controller_unit` (FCU-O13); `fetch_buffer` stores `pc` and `instruction` only (FB-O8, FB-O9). Behavior is unchanged; `alloc_valid` is removed (FCU-O3) | Owner decision 2026-11-06: one module owns ordering and lifecycle; the buffer is an indexed payload array because entries are allocated before data arrives and a kill reloads the pointers |

### Dependencies

- **D-1.** Resolved 2026-11-01: Việt added `PC_RESET_VEC` (`ADDR_WIDTH`, value `'0`) to
  `rtl/riscv_pkg.sv`, as with `INSTR_WIDTH` and `opcode_t` (commit `aedcead`).
- **D-2.** Resolved 2026-11-01: BASE amendment IF-A1 (`5-stage-baseline-core.md`) was accepted by
  Việt together with this document. It also drops one clause in `external-interrupt-extension.md` (Proposed) that cited the
  removed first-presentation rule.
- **D-3.** The HCU design must drive `fetch_accept` consistently with the IF/ID `stall` and `flush` it
  drives, so that IF frees an entry exactly when IF/ID captures it. Resolved by
  [hazard-control-unit.md](hazard-control-unit.md) (HCU-D4), accepted by Việt on 2026-11-05.

### Open items resolved in the controller design

They do not change the `fetch_stage` interface.

**O2. Outstanding count: stored or derived.** Resolved in [fetch-controller-unit.md](fetch-controller-unit.md) (FCU-O8):
derived, `outstanding = life[issue - 1] == OUTSTANDING`.

**O3. Age encoding for oldest-first order.** Resolved in [fetch-controller-unit.md](fetch-controller-unit.md) (FCU-O7): a
three-slot ring with `head` (write end), `issue` (oldest `QUEUED`) and `tail` (oldest entry). The redirect
rule, and the wrap, empty and full conditions, are in that document.

### What can proceed and what stays blocked

- Done: `fetch_obi_interface` (`04f4535`) is committed. Leaf RTL for the pre-IF-A3 split is committed for
  `fetch_buffer` (`2a8d0bf`) and `fetch_controller_unit` (`d985318`). The IF-A3 move (designs
  [fetch-controller-unit.md](fetch-controller-unit.md) and [fetch-buffer.md](fetch-buffer.md)) is accepted, and its RTL is
  delegated (F-d). D-1 and D-2 are resolved.
- Done: the two wrappers, `prefetch_unit` (N4) and `fetch_stage`, are committed (`4f2135c`).
- Done: the HCU design (D-3), [hazard-control-unit.md](hazard-control-unit.md).
- Verification of this stage is not established by this document; section 8 lists obligations only.
