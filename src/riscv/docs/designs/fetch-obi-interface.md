# Fetch OBI Interface — Block Design

**Status:** Accepted by Việt on 2026-11-01
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Parent contract:** [Fetch stage](fetch-stage.md), in particular §3 (hierarchy, leaf
responsibilities), §4 (state ownership), §5.3 (protocol events) and §6 (reset); and the
[five-stage BASE core](5-stage-baseline-core.md): [OBI baseline configuration](5-stage-baseline-core.md#obi-baseline-configuration),
[OBI response validity and reset](5-stage-baseline-core.md#obi-response-validity-and-reset),
[instruction fetch capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states),
[stale instruction responses after redirect](5-stage-baseline-core.md#stale-instruction-responses-after-redirect)
and [reset architecture](5-stage-baseline-core.md#reset-architecture).
Layout precedent: [data-obi-controller.md](data-obi-controller.md).
**RTL mapping:** `rtl/fetch_obi_interface.sv` exists (commit `04f4535`). Module
`fetch_obi_interface`, file `fetch_obi_interface.sv`, instance `if_fetch_obi_interface` inside
`prefetch_unit` (fetch-stage §3, fetch-stage N1). The RTL is written by Việt (F-d).
**Amendment (accepted by Việt on 2026-11-04; IF-A3 wording accepted by Việt on 2026-11-06):** the fetch controller keeps the
presented entry ([fetch-controller-unit.md](fetch-controller-unit.md), FCU-O9, FCU-O13); the
[Fetch Buffer](fetch-buffer.md) stores the `pc` only. Wording below follows it; the port list is unchanged.
This document is neither implementation nor verification evidence.

## 1. Purpose and boundary

`fetch_obi_interface` is the instruction-port OBI leaf of the Prefetch Unit. It presents the
entry at `issue` that the Fetch Controller Unit presents (FCU-O9, FCU-O13) as the protocol signals of the
instruction port, and it reports the request and response transfers to the Fetch Controller Unit
(fetch-stage §3, leaf responsibilities). It drives the constant port fields of the read-only
instruction port (fetch-stage F-c; BASE
[OBI baseline configuration](5-stage-baseline-core.md#obi-baseline-configuration)).

Non-goals:

- No entry lifecycle and no `protocol_committed` storage: the Fetch Controller Unit owns them. No `pc` or
  `instruction` storage: the Fetch Buffer owns them (fetch-stage §4).
- No outstanding count. Its owner is the Fetch Controller Unit (FCU-O8; fetch-stage O2).
- No entry selection and no allocation. The Fetch Controller Unit presents the entry at `issue` (FCU-O13) and
  allocates.
- No instruction capture. The response is written into the Fetch Buffer as payload on the controller's qualified
  response event (`instruction_write`)
  (BASE [capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states)).
- No flush, kill or redirect input. A redirect reaches this leaf only through the Fetch Controller Unit
  and Fetch Controller (fetch-stage §5.2).
- No bus-error, timeout or address-range check. BASE has none at this boundary (BASE
  [OBI baseline configuration](5-stage-baseline-core.md#obi-baseline-configuration); fetch-stage §1).

Observable success criterion: whenever `req = 1`, `addr` is the `pc` of the presented entry; `req`
and `addr` do not change before that entry's `gnt`; the constant fields have their fixed values;
and each `request_fire` and `raw_response_transfer` it reports equals the BASE definition on
that edge (sections 2 and 3).

## 2. Interface contract

### Clock, reset and configuration

The leaf has no clock. It holds no state (FOI-O1), so no sampled register exists in it. `rst_n` is
an input only for event qualification (section 3). Reset effects on `req` come from the Fetch Controller Unit
(section 4; FOI-O5).

Constants and parameters: `ADDR_WIDTH`, `DATA_WIDTH` and `INSTR_WIDTH` from `riscv_pkg`, all `32`
in the supported configuration (`rtl/riscv_pkg.sv`). `DATA_WIDTH` sets the `wdata` width.
`PC_RESET_VEC` is not used by this leaf. The constant port values are the BASE read-only full-word
contract (`we=0`, `be=4'b1111`, `wdata=0`, `rready=1`), as fetch-stage F-c states.

### Ports and payloads

All ports are individual signals, with no packed struct. There are 6 inputs and 9 outputs.
Instruction-port names are the plain names of `rtl/memory_stage.sv` (fetch-stage F-c); the stage
adds the `instr_` prefix. Leaf-to-buffer names are defined in this document.

| Signal | Direction | Type / width | Meaning | Valid when | Source |
| --- | --- | --- | --- | --- | --- |
| `rst_n` | Input | 1-bit `logic` | Active-low reset, qualifies the events in section 3 | Always | [Reset architecture](5-stage-baseline-core.md#reset-architecture); fetch-stage N3 |
| `gnt` | Input | 1-bit `logic` | Instruction OBI grant, sampled with `req` | Each edge | [OBI baseline](5-stage-baseline-core.md#obi-baseline-configuration); F-c |
| `rvalid` | Input | 1-bit `logic` | Instruction OBI response valid | Each edge; with `rready = 1` a raw transfer | [OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset); F-c |
| `rdata` | Input | `logic [INSTR_WIDTH-1:0]` | Instruction word returned by the port | Meaningful when `raw_response_transfer = 1` | OBI response validity; F-c |
| `present_valid` | Input | 1-bit `logic` | A presented entry exists: the entry at `issue` is `QUEUED`. Held until that entry's `request_fire` (section 3). Derived only from registered Fetch Controller Unit state, never combinationally from `gnt`, `rvalid` or `rdata` | Registered state | [Capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states) ("the presented request exists in registered fetch-entry state"); FCU-O9 |
| `present_pc` | Input | `logic [ADDR_WIDTH-1:0]` | `pc` of the presented entry | When `present_valid = 1`; registered, as `present_valid` | Fetch-stage §3 wiring (`fetch_buffer -> presented entry pc`) |
| `req` | Output | 1-bit `logic` | Instruction request for the presented entry | `= present_valid` (section 3) | [Capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states); F-c |
| `addr` | Output | `logic [ADDR_WIDTH-1:0]` | `pc` of the presented entry | When `req = 1` | Capacity and transaction states; F-c |
| `we` | Output | 1-bit `logic` | Constant `0` (read-only port) | Always | OBI baseline; F-c |
| `be` | Output | `logic [3:0]` | Constant `4'b1111` (full word) | Always | OBI baseline; F-c |
| `wdata` | Output | `logic [DATA_WIDTH-1:0]` | Constant `0` | Always | OBI baseline; F-c |
| `rready` | Output | 1-bit `logic` | Constant `1`; a killed expected response is drained | Always, including reset | [OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset) (constant port fields keep their values during reset); F-c |
| `request_fire` | Output | 1-bit `logic` | BASE request event, to the Fetch Controller Unit | Each edge (section 3) | [OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset); FOI-O4 |
| `raw_response_transfer` | Output | 1-bit `logic` | BASE raw response transfer, to the Fetch Controller Unit. Not yet an expected response (FOI-O2) | Each edge (section 3) | OBI response validity; FOI-O2, FOI-O4 |
| `response_data` | Output | `logic [INSTR_WIDTH-1:0]` | Pass-through of `rdata` to the Fetch Buffer | Meaningful when `raw_response_transfer = 1` | Fetch-stage §3 wiring (`gnt, rvalid, rdata -> fetch_obi_interface -> fetch_buffer`); FOI-O6 |

The leaf does not generate `response_fire`, `outstanding` or `unexpected` signals. Their
qualification is in the Fetch Controller Unit (FOI-O2, FOI-O3). `response_data` is `rdata` unchanged; it is
a port only because of the fetch-stage wiring (FOI-O6).

### Transfer and timing rules

- `req` and `addr` are functions of `present_valid` and `present_pc` only. They are not
  combinational from `gnt`, `rvalid`, `rdata` or `rst_n` (fetch-stage §2; BASE
  [capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states),
  `RESPONSE_BYPASS=0`). The leaf adds no `req` gating on any input (FOI-O5).
- `req` does not depend on `outstanding`. The BASE capacity rule allows the next queued entry to
  be presented while one older instruction transaction is `OUTSTANDING`; the subordinate holds
  `gnt = 0` until it can accept (BASE capacity and transaction states, paragraph beginning "The
  next queued entry may be presented"). The one-outstanding limit therefore comes from `gnt`, not
  from this leaf.
- Instruction responses are never backpressured: `rready` is constant `1` (fetch-stage §2; BASE
  [OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset)).

## 3. Internal organization, events and hold rule

The leaf is combinational. It contains one pass-through and one qualification:

```text
req                   = present_valid
addr                  = present_pc
rready                = 1
request_fire          = rst_n && req && gnt
raw_response_transfer = rst_n && rvalid && rready        (rready = 1, so rst_n && rvalid)
response_data         = rdata
```

These are the BASE definitions of `request_fire` and `raw_response_transfer` (BASE
[OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset)). Their
`outstanding` term, which gives `response_fire`, is applied in the Fetch Controller Unit (FOI-O2).

**Hold rule.** Once `req = 1` for an entry, `present_valid` and `present_pc` stay on that entry
until its `request_fire`. The Fetch Controller Unit keeps that entry at `issue` until its `request_fire` moves
`issue` (fetch-controller-unit.md FCU-O7, FCU-O9). Neither a younger queued entry nor a redirect target may bypass or
replace it (BASE capacity and transaction states, paragraph beginning "Once a queued entry has
been presented"; BASE stale-response section, "protocol-committed queued request"). An entry is protocol-committed from the first cycle in which it drives `req = 1`, not from the
following edge (BASE capacity and transaction states, "Once `req` has been asserted"). A redirect on
that first edge therefore keeps the entry. The leaf does
not enforce this rule by itself (FOI-O1). Its effect on the port is that `req` and `addr` cannot
change while `gnt = 0` unless the Fetch Controller Unit changes `present_valid` or the Fetch Buffer changes `present_pc`.

**No bubble.** After `request_fire` for one entry, the next presented entry may drive `req = 1` in
the following cycle without an intervening `req = 0` cycle (BASE capacity and transaction states,
paragraph beginning "No deasserted-`req` bubble"). The leaf adds no cycle of its own.

**Event boundary.** `request_fire` moves the presented entry to `OUTSTANDING` in the Fetch Controller Unit
(fetch-stage §5.3). `raw_response_transfer` and `response_data` are consumed there: the Fetch
Controller Unit's `response_fire` gates the write of `response_data` into the Fetch Buffer, so the buffer captures it as
an entry's instruction only when that `response_fire` holds
(fetch-stage §5.3; BASE capacity and transaction states, paragraph beginning "When
`instr_response_fire` occurs").

## 4. Reset, unexpected responses and environment

**Reset.** On `rst_n = 0`, `request_fire` and `raw_response_transfer` are `0` on every edge, even
if the subordinate shows `gnt = 1` or `rvalid = 1`. BASE gives reset priority over those
transfers (BASE [OBI response validity](5-stage-baseline-core.md#obi-response-validity-and-reset),
"On an edge sampling `rst_n=0`"). `req` falls after reset propagation, without a clock edge,
under FOI-O5(a): the Fetch Controller Unit clears presentation state asynchronously (fetch-stage §6; BASE
[reset architecture](5-stage-baseline-core.md#reset-architecture)). `rready` stays `1` during
reset (BASE OBI response validity, constant port fields keep their values). After release, the
subordinate must not return a response for a pre-reset transaction (BASE OBI response validity and
reset, paragraph beginning "On reset assertion").

**Unexpected responses.** `rvalid` with no `OUTSTANDING` entry is drained, because `rready = 1`.
It changes no state and is reported as a protocol violation by verification (BASE OBI response
validity and reset, "An unexpected response is"; fetch-stage §5.3). The leaf cannot tell an
unexpected response from an expected one without the outstanding count, so it reports neither
(FOI-O3). Detection is in the Fetch Controller Unit and in verification (section 5).

**Environment.** The inputs are `0` or `1` only (fetch-stage O4, Owner decision). A reset edge
with a raised `req` is a defined case (section 5, edge 5). A subordinate that responds to a
pre-reset transaction is outside the contract (BASE OBI response validity and reset).

## 5. Edge trace and verification boundary

The trace uses one sequence with three scenarios: a grant held low for two cycles with `req`
stable; a grant and an older expected response on the same edge; and reset during a raised `req`.
The fetch-entry state is in the comments of the first column, and the leaf outputs are in the
columns for `req` and `addr`.

Pre-trace: entry `S2` is `OUTSTANDING` with `pc = 0x0C`. Entry `S3` is `QUEUED`, presented from
cycle c1 with `pc = 0x10`. `S2`'s response has not yet arrived. `present_valid` and `present_pc`
are the registered controller state (fetch-controller-unit.md, FCU-O9); their timing belongs to that
design.

| Cycle / edge | `present_valid`, `present_pc` | `gnt`, `rvalid`, `rdata` | `req`, `addr`, `rready` | `request_fire`, `raw_response_transfer`, `response_data` | Fetch Controller Unit and buffer effect at the edge |
| --- | --- | --- | --- | --- | --- |
| c1 / edge 1 | 1, `0x10` | 0, 0, — | 1, `0x10`, 1 | 0, 0, — | None. `S3` stays protocol-committed; `S2` stays `OUTSTANDING`. |
| c2 / edge 2 | 1, `0x10` | 0, 0, — | 1, `0x10`, 1 | 0, 0, — | None. `req` and `addr` unchanged while waiting for grant. |
| c3 / edge 3 | 1, `0x10` | 1, 1, `I2` (word at `0x0C`) | 1, `0x10`, 1 | 1, 1, `I2` | `S2` `response_fire` (`outstanding = 1`, raw = 1): `S2` becomes `READY` with `I2`. `S3` `request_fire`: `S3` becomes `OUTSTANDING`. Count `1 + 1 - 1 = 1`. |
| c4 / edge 4 | 1, `0x14` (`S4`) | 0, 0, — | 1, `0x14`, 1 | 0, 0, — | None. `S4` is presented while `S3` is `OUTSTANDING`; `gnt = 0` holds `S4` back. |
| c5 (reset asserted mid-cycle) / edge 5 (`rst_n = 0`) | 1 before assertion, 0 after propagation, `0x14` | 0, 0, — | `req` 1 before assertion, 0 after propagation; `rready` 1 | 0, 0, — | Reset: all entries `FREE`, count `0`, `next_fetch_pc = PC_RESET_VEC`. The pending `S3` response and `S4` request are dropped. |
| c6 / edge 6 | 0 | 0, 0, — | 0, —, 1 | 0, 0, — | None. `rst_n` released (synchronized); nothing presented. |

Reading the trace:

- Edges 1 and 2: the request is raised and held. `req` and `addr` are the same on every cycle until
  `gnt`, as section 3 requires.
- Edge 3: the grant and the older response fire on the same edge. This is the case BASE allows: the
  subordinate may assert `gnt` on the edge the older expected response fires. The response
  qualification uses the pre-edge `outstanding = 1` (FOI-O2).
- Edge 5: `request_fire` and `raw_response_transfer` are zero on the reset edge. In this trace `gnt`
  and `rvalid` are already zero, so the `rst_n` term is not exercised here. The leaf check in
  section 5 uses `gnt = 1` and `rvalid = 1` on the reset edge to exercise it.

**Leaf-level checks** (no leaf test exists; `tb/runners/` has no fetch runner, checked 2026-11-05).
The leaf is combinational, so each check is a single-cycle vector driven by the testbench, which
also drives `present_valid` and `present_pc`:

| Requirement | Stimulus | Expected leaf observation |
| --- | --- | --- |
| Pass-through (section 2) | Set `present_valid`, `present_pc`, toggle `rdata` | `req = present_valid`; `addr = present_pc` when `req = 1`; `response_data = rdata` |
| No combinational path (fetch-stage §2) | Toggle `gnt`, `rvalid`, `rdata` and `rst_n` within a cycle with `present_valid` constant | `req` and `addr` do not change |
| `req` independent of `outstanding` (section 2) | `present_valid = 1` with `gnt = 0` | `req = 1`; the leaf has no count input to change it |
| Event equations (section 3) | All combinations of `rst_n`, `req`, `gnt`, `rvalid` with `rready = 1` | `request_fire` and `raw_response_transfer` match the BASE equations |
| Grant and response on one edge (trace edge 3) | `present_valid = 1`, `gnt = 1`, `rvalid = 1` | `request_fire = 1`; `raw_response_transfer = 1`; `response_data = rdata` |
| Reset edge (section 4) | `rst_n = 0` with `present_valid = 1`, `gnt = 1` and `rvalid = 1` | `request_fire = 0`; `raw_response_transfer = 0` |
| Constant fields (F-c) | Any input | `we = 0`, `be = 4'b1111`, `wdata = 0`, `rready = 1` |
| Unexpected response (section 4) | `rvalid = 1` with no entry presented | `raw_response_transfer = 1`; `request_fire` unchanged |

A pass of these checks shows the leaf's combinational behavior for these vectors. It does not show
the Fetch Controller Unit's lifecycle, the entry selection at `issue`, OBI compliance of the subordinate, or
whole-core fetch behavior.

**Composition-level checks** (planned at stage level in [fetch-stage.md](fetch-stage.md) §8, not in the leaf).
These depend on the fetch-entry state (controller and payload) that the leaf test drives by proxy:

- Reset: `req` is `0` after reset propagation because the controller clears `present_valid` (FOI-O5(a));
  all entries `FREE`; the outstanding count is `0`.
- Unexpected response: `raw_response_transfer && !response_fire` is the violation, observed on the
  controller side with no leaf port (FOI-O3).
- Hold rule: `present_valid` and `present_pc` stay on the committed entry until its `request_fire`
  (section 3); the Fetch Controller Unit keeps that entry at `issue` (fetch-controller-unit.md).
- Trace edges 1–6: entry states, `req` and reset, as in the table above. The table has no `next_fetch_pc`
  column; `next_fetch_pc` appears there only at reset (edge 5).

## 6. Owner decisions

Việt decided FOI-O1..FOI-O6 on 2026-11-01. Each item keeps its options as the record. Numbers are
local to this document (FOI-*); fetch-stage decisions and open items are cited as "fetch-stage O1" and so on.

**FOI-O1. Does the leaf hold any state?**
- Options:
  - (a) Stateless. `req = present_valid` and `addr = present_pc`. The hold rule (section 3)
    is a condition on the Fetch Controller Unit's presentation state (FCU-O7, FCU-O9). The leaf
    has no `clk` port.
  - (b) A one-bit `req_held` register. `req` stays `1` while held, which needs `addr` to stay stable.
    The leaf would then need a latched address of `ADDR_WIDTH` bits, or a guarantee from the buffer
    that `present_pc` is stable. A latch duplicates the entry `pc` that the buffer already holds.
- Decision (Việt, 2026-11-01): (a). The leaf cannot enforce address stability alone without
  duplicating the buffer's `pc` storage, and a second record of the pending request would give
  `protocol_committed` a second owner. The hold obligation sits with the Fetch Controller Unit (section 3;
  fetch-controller-unit.md FCU-O7, FCU-O9, FCU-O13); fetch-stage §3 is refined to say so.

**FOI-O2. Where is `response_fire` qualified by `outstanding`?**
- Options:
  - (a) In the Fetch Controller Unit. The leaf outputs `raw_response_transfer`; the controller
    computes `response_fire = outstanding && raw_response_transfer`.
  - (b) In the leaf. The buffer supplies `outstanding` as an input, so the leaf depends on where the
    count is kept (fetch-stage §4; resolved in the controller design, FCU-O8, as fetch-stage O2).
- Decision (Việt, 2026-11-01): (a). It makes this leaf's ports independent of the outstanding-count decision,
  which is decided in the controller design (FCU-O8). Under (a) the leaf's port list is fixed whichever way
  that decision goes.

**FOI-O3. Where is an unexpected `rvalid` observed?**
- Options:
  - (a) No port in the leaf. The unexpected event is `raw_response_transfer && !response_fire`,
    derived from the controller's qualified event. Verification observes it there.
  - (b) A leaf output `unexpected_response = raw_response_transfer && !outstanding`. This needs the
    count as an input, which conflicts with FOI-O2(a).
- Decision (Việt, 2026-11-01): (a). BASE requires only that an unexpected response is drained and reported by
  verification (BASE OBI response validity and reset). A port is not needed for that.

**FOI-O4. Which events are leaf outputs: `request_fire` and `response_fire`?**
- Options:
  - (a) `request_fire` and `raw_response_transfer` are leaf outputs. `response_fire`
    is in the controller (FOI-O2(a)).
  - (b) Both `request_fire` and `response_fire` are leaf outputs. This needs the outstanding count
    as an input (FOI-O2(b)).
  - (c) No event outputs. The fetch control takes `req`, `gnt` and `rvalid` directly. This adds
    ports to the fetch control and duplicates the `req` and `gnt` path.
- Decision (Việt, 2026-11-01): (a), the same choice as FOI-O2(a). It keeps the leaf's events to the two that depend
  only on its own inputs.

**FOI-O5. Is `req` gated by `rst_n` inside the leaf?**
- Options:
  - (a) No. `req = present_valid`, and `present_valid` is reset state in the Fetch
    Controller Unit, cleared asynchronously. `req` falls after reset propagation, without a clock edge
    (fetch-stage §6; BASE reset architecture, "reset control state drives core `req=0`"). Event
    qualification keeps `rst_n` (section 3).
  - (b) Yes. `req = rst_n && present_valid`. This makes the leaf self-contained for reset, at the
    cost of one gate on a port path. It differs from the data-port precedent, where reset gating was
    deliberately left to the parent valid (data-obi-controller DOC-D3).
- Decision (Việt, 2026-11-01): (a). It follows the BASE reset wording and keeps the port path free of a reset
  term. The Fetch Controller Unit design must state that `present_valid` is cleared asynchronously.

**FOI-O6. Does `rdata` pass through the leaf (`response_data`)?**
- Options:
  - (a) Keep the pass-through, as the accepted fetch-stage wiring routes it. The leaf
    has one extra port with no logic, and the stage wiring is unchanged.
  - (b) Connect the stage `rdata` directly to the Fetch Buffer. The leaf loses `response_data`.
    This has no behavioral effect, but it changes the accepted fetch-stage §3 wiring and port list
    of the leaf.
- Decision (Việt, 2026-11-01): (a). It avoids editing an accepted parent document for a port with
  no logic.

## 7. Dependencies

- Depends on the controller design for the presentation state (`present_valid`) and for the qualification of
  `response_fire` (FOI-O2), both decided in [fetch-controller-unit.md](fetch-controller-unit.md); and on the
  [Fetch Buffer](fetch-buffer.md) for `present_pc`. The leaf's ports do not depend on fetch-stage O2 or O3 (outstanding
  count and age encoding; FCU-O8 and FCU-O7; fetch-stage §9). Either outcome leaves this port list unchanged.
- The presentation choice is in the `fetch_controller_unit` (FCU-O13, FCU-O9). The Fetch Buffer does not choose
  the presented entry.
- Package dependency: `ADDR_WIDTH`, `DATA_WIDTH` and `INSTR_WIDTH` from `riscv_pkg`, all `32`. The
  `wdata` port uses `DATA_WIDTH`. `PC_RESET_VEC` is resolved in the package (fetch-stage D-1) and is
  not used here.
