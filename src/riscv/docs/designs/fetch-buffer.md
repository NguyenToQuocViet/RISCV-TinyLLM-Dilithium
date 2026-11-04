# Fetch Buffer — Block Design

**Status:** Accepted by Việt on 2026-11-04
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner. The decisions FB-O1..FB-O7 in section 9 are
the Owner's of 2026-11-04.
**Parent contract:** [Fetch stage](fetch-stage.md) (§2 timing, §3 leaf responsibilities, §4 state,
§5 behavior and the four redirect cases, §6 reset, §7 traces, §8 obligations; O2 and O3 are resolved
here), [Fetch OBI interface](fetch-obi-interface.md) (buffer-side ports; FOI-O2, FOI-O3, FOI-O5), and
the [five-stage BASE core](5-stage-baseline-core.md): line 579 (Fetch Controller Unit role),
[instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization),
[instruction fetch capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states),
[stale instruction responses after redirect](5-stage-baseline-core.md#stale-instruction-responses-after-redirect),
[OBI response validity and reset](5-stage-baseline-core.md#obi-response-validity-and-reset) and
[reset architecture](5-stage-baseline-core.md#reset-architecture).
Layout precedent: [data-obi-controller.md](data-obi-controller.md).
**RTL mapping:** `rtl/fetch_buffer.sv`. Module `fetch_buffer`, file `fetch_buffer.sv`, instance `if_fetch_buffer` inside `prefetch_unit` (fetch-stage §3).
The RTL is written by Việt (F-d). This document is neither implementation nor verification evidence.

## 1. Purpose and boundary

`fetch_buffer` holds the `FETCH_DEPTH = 3` entries of the instruction frontend (BASE
[instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization)). It keeps each
entry's lifecycle, `pc`, `instruction` and killed marker, and it keeps the allocation order. It presents
the oldest `QUEUED` entry to the instruction OBI leaf, qualifies the response, delivers the oldest
`READY` entry to IF/ID, and applies the redirect kill to the entries it holds.

Non-goals:

- No PC arithmetic and no choice of the next address. The Fetch Controller Unit owns `next_fetch_pc`
  (BASE line 579; FB-O1).
- No OBI signals beyond those in section 2. The leaf drives them (fetch-obi-interface.md).
- No hazard or MEM knowledge. The HCU supplies `fetch_accept` (fetch-stage F-b).
- No IF/ID register (fetch-stage F-a).
- No outstanding counter (FB-O3), no unexpected-response port (FOI-O3), no per-entry age field (FB-O2).

Observable success criterion: each delivery on `fetch_fire` returns the `pc` and word of the oldest live
entry in allocation order; no entry killed at a redirect edge is delivered; at most one entry is
`OUTSTANDING` at any time (BASE capacity and transaction states; fetch-stage §1 criterion).

## 2. Interface contract

### Clock, reset and configuration

`clk` is the rising-edge clock of the state in section 3. `rst_n` is asynchronous assert, synchronized
release (BASE [reset architecture](5-stage-baseline-core.md#reset-architecture); fetch-stage N3). The
buffer has `FETCH_DEPTH = 3` slots, indexed `0..2` (fetch-stage N2; FB-O6). `ADDR_WIDTH` and
`INSTR_WIDTH` come from `riscv_pkg`, both `32`.

### Ports and payloads

All ports are individual signals, no packed struct. There are 9 inputs and 6 outputs. Names of the leaf
side match [fetch-obi-interface.md](fetch-obi-interface.md) §2 exactly. Controller-side names follow
FB-O1.

| Signal | Direction | Type / width | Meaning | Valid when | Source |
| --- | --- | --- | --- | --- | --- |
| `clk` | Input | 1-bit `logic` | Rising-edge clock of the state | Always | Reset architecture |
| `rst_n` | Input | 1-bit `logic` | Active-low reset, async clear of the state | Always | Reset architecture; fetch-stage N3 |
| `kill` | Input | 1-bit `logic` | Redirect edge; the controller's broadcast, equal to `redirect_fire` | Each edge | FB-O1; fetch-stage §3 |
| `alloc_valid` | Input | 1-bit `logic` | Controller asks to allocate `alloc_pc` this edge on a non-kill edge. Ignored on a kill edge (FB-O7). Does not depend on `alloc_fire` | Each edge | FB-O1; FB-O7 |
| `alloc_pc` | Input | `logic [ADDR_WIDTH-1:0]` | `redirect_target` on a kill edge, otherwise `next_fetch_pc` | When `alloc_valid = 1` or `kill = 1` | FB-O1; FB-O7; fetch-stage §4 |
| `fetch_accept` | Input | 1-bit `logic` | HCU: IF/ID takes an instruction this edge. `fetch_fire = fetch_valid && fetch_accept` | Each edge | fetch-stage F-b, O5 |
| `request_fire` | Input | 1-bit `logic` | Request transfer of the presented entry: `rst_n && req && gnt` | Each edge | [FOI-O4](fetch-obi-interface.md#6-owner-decisions) (leaf output) |
| `raw_response_transfer` | Input | 1-bit `logic` | Raw response transfer: `rst_n && rvalid && rready`, with `rready = 1` (constant on the instruction side). Not yet an expected response | Each edge | FOI-O2, FOI-O4 (leaf output) |
| `response_data` | Input | `logic [INSTR_WIDTH-1:0]` | Pass-through of `rdata` | Meaningful when `raw_response_transfer = 1` | FOI-O6 (leaf output) |
| `alloc_fire` | Output | 1-bit `logic` | Allocation performed this edge: `1` on a kill edge; otherwise `alloc_valid && (!full || tail_free)`. Goes only to the `next_fetch_pc` register | Computed from the pre-edge state and the inputs | FB-O1; FB-O7 |
| `present_valid` | Output | 1-bit `logic` | The entry at `issue` is `QUEUED` | From flops only | FB-O4; FOI-O1 (leaf input) |
| `present_pc` | Output | `logic [ADDR_WIDTH-1:0]` | `pc` of the entry at `issue` | From flops only | FOI-O1 (leaf input) |
| `fetch_valid` | Output | 1-bit `logic` | The entry at `tail` is `READY` | From flops only | fetch-stage §2; FB-O5 |
| `fetch_pc` | Output | `logic [ADDR_WIDTH-1:0]` | `pc` of the entry at `tail` | From flops only | fetch-stage §2 |
| `fetch_instruction` | Output | `logic [INSTR_WIDTH-1:0]` | `instruction` of the entry at `tail` | From flops only | fetch-stage §2 |

The buffer does not receive `redirect_fire` or `redirect_target`. Only `kill` and `alloc_pc` carry them,
through the controller (FB-O1).

### Transfer and timing rules

- The outputs `present_valid`, `present_pc`, `fetch_valid`, `fetch_pc` and `fetch_instruction` are
  functions of the state flops only. No output depends combinationally on an input (fetch-stage §2; BASE
  [capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states),
  "the presented request exists in registered Fetch Buffer state").
- The only output computed from inputs is `alloc_fire`. It feeds only the controller's `next_fetch_pc`
  register (FB-O1). Next-state values never reach the read path.
- A delivery waits: `fetch_valid`, `fetch_pc` and `fetch_instruction` show the same entry until
  `fetch_fire` or a kill frees it (fetch-stage §2).

## 3. State, derived signals and invariants

### State

| State | Width / type | Reset | Meaning | Updated by |
| --- | --- | --- | --- | --- |
| `life[s]`, `s = 0..2` | `FREE`, `QUEUED`, `OUTSTANDING`, `READY` | `FREE` | Lifecycle of slot `s` (BASE lifecycle) | Allocation, request, response, delivery, kill |
| `killed[s]` | 1 bit | `0` | Wrong-path marker (fetch-stage §4) | Kill (set); freeing or allocation (cleared) |
| `head` | 2-bit slot index | `0` | Next slot to allocate (write end) | Allocation; kill |
| `issue` | 2-bit slot index | `0` | Oldest `QUEUED` entry, the presented one; the first `QUEUED` slot, or `head` when none | Request; kill |
| `tail` | 2-bit slot index | `0` | Oldest entry (read end) | Delivery; killed drain; kill |
| `pc[s]` | `ADDR_WIDTH` | not reset | Fetch address of slot `s` | Allocation |
| `instruction[s]` | `INSTR_WIDTH` | not reset | Payload of slot `s`; meaningful only as `READY` | Response (captured) |

`pc` and `instruction` are not reset (BASE [reset architecture](5-stage-baseline-core.md#reset-architecture);
fetch-stage §4).

RTL names: `head`, `issue` and `tail` are `head_ptr`, `issue_ptr` and `tail_ptr`; `next` and `prev` are
`next_slot` and `prev_slot`; lifecycle values are `LIFE_FREE`, `LIFE_QUEUED`, `LIFE_OUTSTANDING` and
`LIFE_READY` of `life_t`, which `riscv_pkg` defines with `FETCH_DEPTH` (fetch-stage N2).

### Derived signals (from state only)

- `prv = prev(issue)`; `outst = (life[prv] == OUTSTANDING)`. This is the outstanding count (FB-O3).
- `full = (life[head] != FREE)`. This resolves `head == tail` (FB-O2). If `head != tail`, slot `head` is
  past the youngest entry and therefore `FREE`.
- `present_valid = (life[issue] == QUEUED)`; `present_pc = pc[issue]`.
- `fetch_valid = (life[tail] == READY)`; `fetch_pc = pc[tail]`; `fetch_instruction = instruction[tail]`.
- Pointer helpers (FB-O6): `next(s) = (s == 2) ? 0 : s + 1`; `prev(s) = (s == 0) ? 2 : s - 1`. Value `3` is
  unused and cannot be reached from reset.

### Structural invariants

These hold after every edge. Each one is checked by the traces in section 5.

- **I1. Occupancy.** The slots from `tail` up to `head - 1` (in ring order) are occupied. All other slots are
  `FREE`. The buffer is full when `life[head] != FREE`.
- **I2. Order.** Walking from `tail`: `READY` entries first, then at most one `OUTSTANDING` entry at `prv`,
  then `QUEUED` entries up to `head - 1`. `issue` is the first `QUEUED` slot, or `head` if there is none.
- **I3. Killed.** A killed entry is never `READY`. A killed `OUTSTANDING` entry is always at `tail`. This
  holds because a `request_fire` needs the older outstanding entry gone, or answered on the same edge
  (BASE capacity and transaction states: the subordinate holds `gnt = 0` until it can accept). So at most
  one outstanding entry exists, and it is the oldest.
- **I4. Ambiguous full case.** When `full` and `issue == tail`: if `life[tail] == QUEUED`, all three
  entries are `QUEUED`; otherwise all three are issued (`READY` or `OUTSTANDING`).

## 4. Behavioral and next-state rules

### 4.1 Events (pre-edge)

- `F = fetch_valid && fetch_accept` (`fetch_fire`; fetch-stage O5).
- `P = outst && raw_response_transfer` (`response_fire`; FB-O3, FOI-O2).
- `Q = request_fire` (the leaf asserts it only while `present_valid = 1`).
- `K = kill`.
- `killed_resp = P && killed[prv]`.
- `tail_free = F || killed_resp` (no kill). Both cases free slot `tail`: a killed `OUTSTANDING` entry is at
  `tail` (I3).
- `A = alloc_fire`: with `K = 0`, `A = alloc_valid && (!full || tail_free)`. With `K = 1`, `A = 1` and
  `alloc_valid` is ignored (FB-O7).

### 4.2 Rules without a kill (`K = 0`)

- **P (response).** `life[prv] := killed[prv] ? FREE : READY`. When not killed, `instruction[prv] := response_data`
  (fetch-stage §5.3; BASE capacity and transaction states, "a live `OUTSTANDING` entry captures `rdata`").
- **Q (request).** `life[issue] := OUTSTANDING`; `issue := next(issue)`. The killed flag is unchanged.
  Non-killed entries follow BASE capacity and transaction states.
- **Delivery / killed drain (`tail_free`).** `life[tail] := FREE`; `killed[tail] := 0`; `tail := next(tail)`.
- **A (allocation).** `life[head] := QUEUED`; `pc[head] := alloc_pc`; `killed[head] := 0`;
  `head := next(head)`. When `full`, `head == tail`, and the slot is reused only if `tail_free` freed it on
  this edge (BASE capacity and transaction states, same-edge reuse).

Combined: `tail' = tail + tail_free`, `head' = head + A`, `issue' = issue + Q`.

### 4.3 Rules on a kill edge (`K = 1`)

All values come from the pre-edge state.

- `kept_out = outst && !P`: the outstanding entry at `prv` is kept as killed. A response on the kill edge
  discards it instead (BASE stale-response section, second bullet).
- `kept_q = (life[issue] == QUEUED)`: the entry at `issue` is kept as killed. By FB-O4 it is committed and
  presented, so it is the committed entry of BASE's stale-response rule.
- Every `READY` entry is freed. Its delivery on `fetch_accept` is ignored: `F` does not apply on a kill
  edge (fetch-stage §5.2, first rule).
- Every `QUEUED` entry beyond `issue` is freed. These are uncommitted (FB-O4).
- `tail' = kept_out ? prv : issue`.
- `t = kept_q ? next(issue) : issue`: the target slot. It is never a kept slot.
- `t` is free when the kill completes: it is not a kept slot, and every slot other than the kept ones is freed.
  So the allocation always succeeds, and `alloc_fire = 1` on a kill edge (FB-O7).
- `life[t] := QUEUED`; `pc[t] := alloc_pc`; `killed[t] := 0`; `head' = next(t)`.
- `killed[prv] := 1` if `kept_out`; `killed[issue] := 1` if `kept_q`.
- `issue' = Q ? next(issue) : issue`. If `Q = 1` the killed entry at `issue` becomes `OUTSTANDING` and
  `issue` moves to the target.
- Every slot not named above becomes `FREE` with `killed = 0`.

### 4.4 Same-edge combinations

| Combination | Result |
| --- | --- |
| `F` and `P` | `tail` is freed; `prv` becomes `READY`. Allowed. Slot `tail` can be reused by `head` when full (trace A). |
| `Q` and `P` | Count stays `1`: `prv` (old outstanding) becomes `READY`; `issue` becomes `OUTSTANDING`; the new `prv` is the old `issue`. |
| `Q` with an outstanding entry and no `P` | Outside the contract (section 6). |
| `F` with `K = 1` | `F` is ignored. Every `READY` is freed; the HCU flush discards the IF/ID capture (fetch-stage §5.2). |
| `P` with `K = 1` | The response is discarded and `prv` is `FREE` (BASE, second case of the stale-response section). |
| `Q` with `K = 1` | The killed entry at `issue` becomes killed `OUTSTANDING`; `issue` moves to the target (trace D). |
| `killed_resp` with `A` when full | The killed drain frees `tail`, which `head` reuses (trace W, edge 4). |
| Empty buffer, `A` | `issue == head`: the new `QUEUED` entry is `issue` and is presented from the next cycle. |
| Raw response with `outst = 0` | No state change (BASE OBI response validity and reset; FOI-O3). |

### 4.5 Redirect cases

The four BASE cases (BASE stale-response section; fetch-stage §5.2) and the two cases that keep an entry:

| BASE case | Entry before the edge | Rule |
| --- | --- | --- |
| 1. Wrong-path `READY` freed | `READY` | Freed by the kill. `tail` moves past it (`tail' = kept_out ? prv : issue`). |
| 2. Outstanding entry with a response on the redirect edge | `OUTSTANDING` at `prv`, `P = 1` | Freed by `P`. Not kept (`kept_out = 0`). |
| 3. Committed `QUEUED` granted on the redirect edge | `QUEUED` at `issue`, `Q = 1` | Kept as killed. Becomes killed `OUTSTANDING`. `issue` moves to the target. |
| 4. Unpresented `QUEUED` freed | `QUEUED` beyond `issue` | Freed. `head := next(t)` rewinds over them. |
| Kept: outstanding entry without a response | `OUTSTANDING` at `prv`, `P = 0` | Kept as killed. `tail := prv`. It is drained, never `READY` (BASE). |
| Kept: committed `QUEUED` not granted | `QUEUED` at `issue`, `Q = 0` | Kept as killed. `issue` stays, so the entry stays presented with stable `req` (BASE). |

BASE says the target "remains queued" until the stale outstanding entry drains (BASE stale-response
section). Here it is at `issue` and presented, but `gnt` stays `0` until the stale response is taken. This
is the presented-while-outstanding case of BASE capacity and transaction states, so it is not a conflict.

### 4.6 Pointer encoding

Each pointer is a 2-bit slot index. `next` and `prev` wrap `2 -> 0` and `0 -> 2` (FB-O6). Value `3` is
never written. Reset sets all three pointers to `0`.

## 5. Representative traces

Each row is one edge. Pointers are shown after the edge. `life` lists slots `0 / 1 / 2`. The `pc` is
written in hex and the `killed` flag is shown as `(k)`.

### Trace A: steady state, same-edge reuse when full (fetch-stage Trace A)

Pre-edge: `head = 0`, `issue = 2`, `tail = 0`; `life = READY 0x08 / OUTSTANDING 0x0C / QUEUED 0x10`
(full). `fetch_accept = 1`, `kill = 0`, `request_fire = 1` (`gnt = 1`), `raw_response_transfer = 1`
(`rvalid = 1`), `response_data = I2`, `alloc_valid = 1`, `alloc_pc = 0x14`.

| Edge | Events | `head / issue / tail` | `life 0 / 1 / 2` | Notes |
| --- | --- | --- | --- | --- |
| E | `F = 1` (frees `0`); `P = 1` (`outst = life[1]`); `Q = 1`; `A = 1` (`head = 0` reused) | `1 / 0 / 1` | `QUEUED 0x14 / READY 0x0C / OUTSTANDING 0x10` | Slot 0 is `issue`, so it is presented from the next cycle. Its `QUEUED` entry is committed (FB-O4). Matches fetch-stage Trace A except for this label. |

### Trace B: redirect with a committed wrong-path entry not yet granted (fetch-stage Trace B)

Pre-edge: `head = 0`, `issue = 2`, `tail = 0`; `life = READY 0x1C / OUTSTANDING 0x20 / QUEUED 0x24`
(presented, full). `kill = 1`, `alloc_valid` ignored (FB-O7), `alloc_pc = 0x100`, `fetch_accept = 0`, `gnt = 0`,
`rvalid = 0`.

| Edge | Events | `head / issue / tail` | `life 0 / 1 / 2` | Notes |
| --- | --- | --- | --- | --- |
| R | `K = 1`; `P = 0`; `Q = 0`; `kept_out = 1`; `kept_q = 1`; `t = next(2) = 0` | `1 / 2 / 1` | `QUEUED 0x100 / OUTSTANDING 0x20 (k) / QUEUED 0x24 (k)` | `fetch_valid = 0` (`life[1]` is `OUTSTANDING`). `present_valid = 1` on slot 2, with `req` stable. `outst = life[1] == OUTSTANDING`. |

Afterwards, slot 2 waits for `gnt`. The target at slot 0 is not presented while slot 2 is pending: `issue`
stays on slot 2. When slot 2 is granted (after the stale response on slot 1), it becomes killed
`OUTSTANDING`, and its response is drained to `FREE` (trace D shows the same-edge version).

### Trace D: redirect with a grant and the older response on the same edge

Pre-edge: as trace B. `kill = 1`, `alloc_valid` ignored (FB-O7), `alloc_pc = 0x100`, `gnt = 1` (grants slot 2),
`rvalid = 1` (answers slot 1), `fetch_accept = 0`.

| Edge | Events | `head / issue / tail` | `life 0 / 1 / 2` | Notes |
| --- | --- | --- | --- | --- |
| R | `K = 1`; `P = 1` (slot 1 freed, response discarded); `Q = 1` (slot 2 killed `OUTSTANDING`); `kept_out = 0`; `tail' = issue = 2`; `t = next(2) = 0` | `1 / 0 / 2` | `QUEUED 0x100 / FREE / OUTSTANDING 0x24 (k)` | `outst = life[2] == OUTSTANDING` (killed). The target is `issue`, presented from the next cycle, with `gnt = 0` until the killed response. A killed `OUTSTANDING` at `tail` (I3). |

Next edge (not shown): `rvalid` answers slot 2, `P = 1` with `killed[2] = 1`, so `killed_resp = 1`. Slot 2
becomes `FREE`, `tail := 0`. The target is then granted (BASE capacity and transaction states).

### Trace W: pointer wrap past the third slot

Start: empty, `head = issue = tail = 2`. Inputs per edge: `alloc_valid = 1` on E1..E6, `fetch_accept = 1`
on E4..E6, `gnt = 1` on E2..E6 when `issue` is `QUEUED`, `rvalid = 1` on E3..E6 for the outstanding entry.
`alloc_pc = 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34` on E1..E6.

| Edge | Events | `head / issue / tail` | `life 0 / 1 / 2` | Wrap |
| --- | --- | --- | --- | --- |
| E1 | `A`: slot 2 gets `0x20`; `head` `2 -> 0` | `0 / 2 / 2` | `FREE / FREE / QUEUED 0x20` | `head` wraps |
| E2 | `Q` on slot 2 (`issue` `2 -> 0`); `A`: slot 0 gets `0x24` | `1 / 0 / 2` | `QUEUED 0x24 / FREE / OUTSTANDING 0x20` | `issue` wraps |
| E3 | `P` on slot 2 (`READY`); `Q` on slot 0; `A`: slot 1 gets `0x28` | `2 / 1 / 2` | `OUTSTANDING 0x24 / QUEUED 0x28 / READY 0x20` | Full (`life[2] = READY`) |
| E4 | `F` frees slot 2 (`tail` `2 -> 0`); `P` on slot 0; `Q` on slot 1 (`issue` `1 -> 2`); `A` reuses slot 2 (`head` `2 -> 0`) | `0 / 2 / 0` | `READY 0x24 / OUTSTANDING 0x28 / QUEUED 0x2C` | `head` and `tail` wrap. Full: `life[0] = READY` |
| E5 | `F` frees slot 0 (`tail` `0 -> 1`); `P` on slot 1; `Q` on slot 2 (`issue` `2 -> 0`); `A` reuses slot 0 (`head` `0 -> 1`) | `1 / 0 / 1` | `QUEUED 0x30 / READY 0x28 / OUTSTANDING 0x2C` | `issue` wraps |
| E6 | `F` frees slot 1 (`tail` `1 -> 2`); `P` on slot 2; `Q` on slot 0 (`issue` `0 -> 1`); `A` reuses slot 1 (`head` `1 -> 2`) | `2 / 1 / 2` | `OUTSTANDING 0x30 / QUEUED 0x34 / READY 0x2C` | Delivery order `0x20, 0x24, 0x28` follows allocation order |

Every invariant in section 3 holds after each edge. The three pointer values are always consistent with the
lifecycle state, which is the check on FB-O2.

## 6. Reset, cancellation and environment

**Reset.** On `rst_n = 0`, the state becomes `life = FREE`, `killed = 0`, `head = issue = tail = 0`. This
is asynchronous: the outputs reach their reset values after reset propagation, without a clock edge
(BASE [reset architecture](5-stage-baseline-core.md#reset-architecture)). So `present_valid = 0` and
`fetch_valid = 0` then, and `req` falls as FOI-O5(a) assumes. No edge with `rst_n = 0` counts a request,
response, delivery or allocation (BASE OBI response validity and reset). `pc` and `instruction` are not
reset. After release, the subordinate returns no response for a pre-reset transaction (BASE OBI response
validity and reset).

**Cancellation.** A kill is the only cancellation inside the buffer (section 4.3, fetch-stage §6). A
committed entry is never removed before its `gnt`; it is kept as killed (BASE capacity and transaction
states).

**Environment preconditions.**

- A `request_fire` requires that no older outstanding entry remains after the edge: either `outst = 0`, or
  `P = 1` on the same edge. This is the subordinate's obligation (BASE capacity and transaction states:
  `gnt = 0` until capacity; `OBI_OUTSTANDING_MAX = 1`). The buffer does not guard it. A violation makes two
  entries `OUTSTANDING`, which is outside the contract.
- `kill` may be asserted only on an edge where `rst_n = 1`. Outside reset, `kill` equals `redirect_fire`
  (FB-O1).
- Inputs are `0` or `1` only (fetch-stage O4).
- A raw unexpected response (`raw_response_transfer && !outst`) changes no state (section 4.4; FOI-O3).

## 7. Verification obligations

No fetch-buffer test exists (`tb/runners/` has no fetch runner, checked 2026-11-04). The following are
planned. Expected values come from section 4, not from the DUT.

| Requirement / invariant | Stimulus or scenario | Expected observation |
| --- | --- | --- |
| Steady state and same-edge reuse (fetch-stage Trace A) | Trace A | Pointers `1 / 0 / 1`; `life` as in section 5 |
| Redirect with a committed entry not granted (fetch-stage Trace B) | Trace B | `issue` stays on the killed entry; `req` stable; `fetch_valid = 0` |
| Redirect with grant and response on one edge | Trace D | Response discards slot 1; slot 2 becomes killed `OUTSTANDING`; target at `issue` |
| Four redirect cases (section 4.5) | One stimulus per case | Each case gives the stated `life` result |
| Pointer wrap (trace W) | Six allocations and deliveries from `head = 2` | Pointers wrap as shown; delivery order is allocation order |
| Full / empty by `life[head]` (I1, I4) | Full with all `QUEUED`; full with all issued; empty | `full` and `issue` as stated; no ambiguity |
| Delivery ignored on kill (fetch-stage §5.2) | `fetch_accept = 1` on a kill edge with a `READY` tail | Tail `READY` freed; no delivery effect |
| Kill with `alloc_valid = 0` (FB-O7) | Trace B with `alloc_valid = 0` | Target still allocated at `t`; `alloc_fire = 1`; `head` as in trace B |
| Killed drain at `tail` (I3) | Killed `OUTSTANDING` answered | Entry `FREE`; never `READY` |
| Reset (section 6) | Reset with entries in every state | All `FREE`; pointers `0`; `present_valid = 0` after propagation |
| Unexpected response (section 4.4) | Raw response with no outstanding entry | No state change |

## 8. Open items

No open items. The gap found while checking the rules, `alloc_valid` on a kill edge, is settled as FB-O7
in section 9.

## 9. Rationale and decisions

Each decision below is the Owner's, dated 2026-11-04. Each one is written as settled.

**FB-O1. Controller boundary.** Decision (Việt, 2026-11-04): the controller drives `alloc_valid`,
`alloc_pc` (`ADDR_WIDTH`) and `kill`; the buffer returns `alloc_fire`. `alloc_pc` is `redirect_target` on a
redirect edge, otherwise `next_fetch_pc`. `kill` equals `redirect_fire`, a single broadcast. The buffer
applies the four redirect cases per entry (section 4.5) and chooses the presented entry, always the oldest
`QUEUED`. The controller reads no per-entry state and has no `gnt` input. `alloc_valid` must not depend on
`alloc_fire`; `alloc_fire` goes only to the `next_fetch_pc` register. On a kill edge, `alloc_valid` is
ignored and the target is always allocated with `alloc_fire = 1` (FB-O7).

**FB-O2. Age order (fetch-stage O3).** Decision (Việt, 2026-11-04): a ring over the three slots with three
pointers, in the Owner's naming. `head` is the write end, the next slot to allocate. `tail` is the oldest
entry. `issue` is the oldest `QUEUED` entry. Allocation writes at `head`, then `head + 1`. `request_fire`
moves the entry at `issue` to `OUTSTANDING`, then `issue + 1`. Delivery or a killed drain frees the entry at
`tail`, then `tail + 1`. There is no count; the per-slot lifecycle stays. `head == tail` is resolved by
`life[head]`: `FREE` means empty, otherwise full. On a redirect edge: `tail = (an OUTSTANDING entry is kept) ?
issue - 1 : issue`; the target goes to `t = (life[issue] == QUEUED) ? issue + 1 : issue`; `head = t + 1`;
`issue` changes only through `request_fire`. ("Kept" means not answered on the same edge; section 4.3.)

**FB-O3. Outstanding (fetch-stage O2).** Decision (Việt, 2026-11-04): derived, not stored:
`outstanding = life[issue - 1] == OUTSTANDING`. `response_fire = outstanding && raw_response_transfer`, and
the response lands in slot `issue - 1`.

**FB-O4. Committed.** Decision (Việt, 2026-11-04): derived, not stored: the entry at `issue` is committed when
`life[issue] == QUEUED`. Every other `QUEUED` entry is uncommitted. This realises BASE's conceptual
`protocol_committed`. Consequence: `present_valid` equals `life[issue] == QUEUED`. An entry is presented from the first cycle in
which it is `QUEUED` at `issue`, not one cycle later. Uncommitted entries are never at `issue`.

**FB-O5. Killed.** Decision (Việt, 2026-11-04): one bit per entry. Set on the redirect edge for each kept
entry. Cleared when the slot is freed or allocated, and on reset. Only the response path reads it.
`fetch_valid = life[tail] == READY`, because a killed `READY` entry never exists.

**FB-O6. Pointer encoding.** Decision (Việt, 2026-11-04): each pointer is a 2-bit slot index, with `next`
and `prev` helpers that wrap `2 -> 0` and `0 -> 2`. Value `3` is unused and unreachable from reset.

**FB-O7. `alloc_valid` on a kill edge.** Decision (Việt, 2026-11-04): (b). On a kill edge the buffer ignores
`alloc_valid`, always allocates the target and drives `alloc_fire = 1`. The alternative was (a): the controller
asserts `alloc_valid = 1` on every kill edge, which makes a controller-side contract. Under (b) the free slot for
the target is guaranteed by section 4.3, so the controller needs no contract on `alloc_valid` for kill edges.

Reasons, as recorded for the Owner. FB-O1 keeps the controller free of per-entry state, so the controller
stays one module. FB-O2 and FB-O3 remove the count and the age field, so there is one source of truth for
order (ring) and one for outstanding (`life`). FB-O4 removes a stored `protocol_committed` state and realises
it by position. FB-O5 keeps the killed marker to the one path that reads it.

### Dependencies

- `fetch_controller_unit` can be drafted against FB-O1: its inputs are `redirect_fire`, `redirect_target`,
  `alloc_fire`; its outputs are `kill`, `alloc_valid`, `alloc_pc` and the `next_fetch_pc` register. On a
  kill edge it sets `alloc_valid` to any value, since the buffer ignores it (FB-O7), and `next_fetch_pc`
  advances from `alloc_fire = 1`.
- The HCU design (fetch-stage D-3) must still drive `fetch_accept` and the IF/ID `stall` and `flush`
  consistently with the kill rule of section 4.3.
- The RTL is written by Việt after acceptance (fetch-stage F-d).
