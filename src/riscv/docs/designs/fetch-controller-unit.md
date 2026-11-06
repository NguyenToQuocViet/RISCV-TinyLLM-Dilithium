# Fetch Controller Unit — Block Design

**Status:** Accepted by Việt on 2026-11-06 (IF-A3: FCU-O1, FCU-O4, FCU-O7..FCU-O13, and the retirement of FCU-O3).
The remaining decisions were accepted on 2026-11-05 (IF-A2).
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner. Decisions are in section 9: FCU-O1..FCU-O6 of 2026-11-05,
FCU-O7..FCU-O13 of 2026-11-06.
**Parent contract:** [Fetch stage](fetch-stage.md) (§2 boundary, §3 leaves, §4 state, §5.2 redirect, §7 traces) and
the [five-stage BASE core](5-stage-baseline-core.md): [instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization)
(IF-A2, IF-A3), [instruction fetch capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states),
[stale instruction responses after redirect](5-stage-baseline-core.md#stale-instruction-responses-after-redirect) and
[reset architecture](5-stage-baseline-core.md#reset-architecture). Payload storage: [Fetch Buffer](fetch-buffer.md).
Producer of `redirect_fire` and `redirect_target`: [redirect unit](redirect-unit.md).
**RTL mapping:** `rtl/fetch_controller_unit.sv`, module `fetch_controller_unit`, instance `if_fetch_controller_unit`
inside `prefetch_unit` (fetch-stage §3). The RTL for the IF-A3 move is delegated (fetch-stage F-d). This document is
neither implementation nor verification evidence.

## 1. Purpose and boundary

`fetch_controller_unit` is the instruction-fetch control plane (BASE
[instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization)). It owns every fetch control
state element with a reset: `next_fetch_pc`, the three slot pointers, the per-entry lifecycle and the killed marks. It
owns all logic on them: allocation, presentation, response qualification, delivery and kill recovery. It drives the
write and read addresses and enables of the [Fetch Buffer](fetch-buffer.md), which stores only `pc` and `instruction`.
Internal names are unchanged (FCU-O13).

Non-goals: no payload storage; no OBI signals and no `gnt` ([fetch-obi-interface.md](fetch-obi-interface.md)); no
hazard or MEM knowledge (the HCU drives `fetch_accept`, fetch-stage F-b); no redirect decoding or target checking
(`redirect_fire` and `redirect_target` arrive qualified, [redirect-unit.md](redirect-unit.md); misaligned targets are
outside BASE, §6); no allocation pause (FCU-O3, retired).

Observable success criterion: after reset the allocated addresses start at `PC_RESET_VEC` and step by `+4`. After a
redirect edge the first allocated address is the redirect target, allocated on the following edge (IF-A2). Deliveries
follow allocation order, and no entry killed at a redirect edge is delivered (fetch-stage §1).

## 2. Interface contract

### Clock, reset and configuration

`clk` is the rising-edge clock of the state in section 4. `rst_n` is asynchronous assert, synchronized release (BASE
[reset architecture](5-stage-baseline-core.md#reset-architecture); fetch-stage N3). `ADDR_WIDTH = 32`.
`PC_RESET_VEC` is defined in `riscv_pkg` (fetch-stage D-1). `FETCH_DEPTH = 3`, slots `0..2`.

### Ports

There are 7 inputs and 9 outputs. Output names match the input names of [fetch-buffer.md](fetch-buffer.md) §2.

| Signal | Direction | Type / width | Meaning | Valid when | Source |
| --- | --- | --- | --- | --- | --- |
| `clk` | Input | 1-bit `logic` | Rising-edge clock of the state | Always | Reset architecture |
| `rst_n` | Input | 1-bit `logic` | Active-low reset; async clear | Always | Reset architecture; fetch-stage N3 |
| `redirect_fire` | Input | 1-bit `logic` | EX taken redirect on this edge | Each edge | [redirect-unit.md](redirect-unit.md); fetch-stage F-e |
| `redirect_target` | Input | `logic [ADDR_WIDTH-1:0]` | Redirect target address | When `redirect_fire = 1` | [redirect-unit.md](redirect-unit.md) |
| `fetch_accept` | Input | 1-bit `logic` | HCU: IF/ID takes an entry this edge; `fetch_fire = fetch_valid && fetch_accept` | Each edge | fetch-stage F-b, O5 |
| `request_fire` | Input | 1-bit `logic` | Request transfer of the presented entry: `rst_n && req && gnt` | Each edge | [FOI-O4](fetch-obi-interface.md#6-owner-decisions) |
| `raw_response_transfer` | Input | 1-bit `logic` | `rst_n && rvalid && rready`, `rready = 1`; not yet an expected response | Each edge | FOI-O2, FOI-O4 |
| `present_valid` | Output | 1-bit `logic` | The entry at `issue` is `QUEUED` | From flops only | OBI leaf (FOI-O1); FCU-O9 |
| `fetch_valid` | Output | 1-bit `logic` | The entry at `tail` is `READY` | From flops only | Fetch stage output |
| `pc_write` | Output | 1-bit `logic` | Write `pc[pc_write_slot]` on this edge (`= alloc_fire`) | Each edge | FCU-O4 |
| `pc_write_slot` | Output | `logic [1:0]` | `head_ptr` | From flops only | FCU-O4, FCU-O7 |
| `pc_write_data` | Output | `logic [ADDR_WIDTH-1:0]` | `next_fetch_pc` | Meaningful when `pc_write = 1` | FCU-O4 |
| `instruction_write` | Output | 1-bit `logic` | Write `instruction[instruction_write_slot]` (`= response_fire`) | Each edge | FCU-O4 |
| `instruction_write_slot` | Output | `logic [1:0]` | `prv` | Each edge | FCU-O4, FCU-O7 |
| `present_slot` | Output | `logic [1:0]` | `issue_ptr` | From flops only | FCU-O9 |
| `fetch_slot` | Output | `logic [1:0]` | `tail_ptr` | From flops only | FCU-O7 |

Internal signals, not ports: `kill` (= `redirect_fire`, FCU-O2) and `alloc_fire` (FCU-O6). There is no `gnt`, no
per-entry input and no `alloc_valid` port (FCU-O3, retired).

### Transfer and timing rules

- `present_valid`, `fetch_valid`, `present_slot`, `fetch_slot`, `pc_write_slot` and `pc_write_data` are functions of
  registered state only.
- `pc_write` and `instruction_write` are combinational from the inputs (`pc_write` through `fetch_accept` and the
  response path; `instruction_write` through `response_fire`). They are sampled at the edge into the payload array and
  this unit's state. They never reach `req`, `addr`, `present_valid` or `fetch_valid`.
- `redirect_target` reaches only the `next_fetch_pc` register (section 5.1), never `pc_write_data` within a cycle (IF-A2).

## 3. Internal organization

The unit is one state group (section 4) and its next-state logic. It has no child blocks. Derived signals are
combinational functions of that state: `prv = prev(issue_ptr)`, `outst`, `full`, `present_valid`, `fetch_valid` and
`alloc_fire` (section 5.2 and 5.3). Pointer helpers `next` and `prev` are in FCU-O11.

## 4. State and ownership

| State | Width / type | Reset | Meaning | Updated by |
| --- | --- | --- | --- | --- |
| `next_fetch_pc` | `logic [ADDR_WIDTH-1:0]` | `PC_RESET_VEC` | Address of the next allocation; ownership passes to the entry on allocation | Redirect edge (`redirect_target`); allocation (`+4`); reset |
| `life[s]`, `s = 0..2` | `FREE`, `QUEUED`, `OUTSTANDING`, `READY` (`life_t`) | `FREE` | Lifecycle of slot `s` (BASE lifecycle) | Allocation, request, response, delivery, kill |
| `killed[s]` | 1 bit | `0` | Wrong-path marker (fetch-stage §4) | Kill (set); freeing or allocation (cleared) |
| `head_ptr` | 2-bit slot index | `0` | Next slot to allocate (write end) | Allocation; kill |
| `issue_ptr` | 2-bit slot index | `0` | Oldest `QUEUED` entry, the presented one; `head_ptr` when none | Request; kill |
| `tail_ptr` | 2-bit slot index | `0` | Oldest entry (read end) | Delivery; killed drain; kill |

These are the only state elements of the unit. No outstanding count and no pending-target flag exist (BASE
stale-response section, "no `redirect_pending` state"). The `pc` and `instruction` payload in the
[Fetch Buffer](fetch-buffer.md) is not reset.

RTL names: `head_ptr`, `issue_ptr`, `tail_ptr` (`head`, `issue`, `tail` in prose); `next_slot` and `prev_slot`; values
`LIFE_FREE`, `LIFE_QUEUED`, `LIFE_OUTSTANDING`, `LIFE_READY` of `life_t`, which `riscv_pkg` defines with `FETCH_DEPTH`
(fetch-stage N2).

Invariants, checked by the traces in section 7:

- **I1. Occupancy.** The slots from `tail` up to `head - 1` (ring order) are occupied; all others are `FREE`. The ring
  is full when `life[head] != FREE`.
- **I2. Order.** Walking from `tail`: `READY` entries, then at most one `OUTSTANDING` entry at `prv`, then `QUEUED`
  entries up to `head - 1`. `issue` is the first `QUEUED` slot, or `head` if there is none.
- **I3. Killed.** A killed entry is never `READY`. A killed `OUTSTANDING` entry is always at `tail`: a `request_fire`
  needs the older outstanding entry gone or answered on the same edge (BASE capacity and transaction states). So at
  most one outstanding entry exists, and it is the oldest.
- **I4. Ambiguous full case.** When `full` and `issue == tail`: if `life[tail] == QUEUED`, all three entries are
  `QUEUED`; otherwise all three are issued (`READY` or `OUTSTANDING`).

## 5. Behavioral and next-state rules

### 5.1 Next-state priority of `next_fetch_pc` (FCU-O5)

| Priority | Condition (pre-edge) | `next_fetch_pc` after the edge |
| --- | --- | --- |
| 1 | `rst_n = 0` (asynchronous) | `PC_RESET_VEC` |
| 2 | `kill = 1` (`= redirect_fire`) | `redirect_target` |
| 3 | `alloc_fire = 1` | `next_fetch_pc + 4` |
| 4 | none of the above | `next_fetch_pc` (hold) |

Priority 2 beats 3, so `alloc_fire` on a redirect edge is never used (FCU-O6). The redirect target is one mux input at
the register's D input; it has no path through the `+4` adder.

### 5.2 Derived signals and outputs

- `prv = prev(issue_ptr)`; `outst = (life[prv] == OUTSTANDING)` (FCU-O8).
- `full = (life[head_ptr] != FREE)` (FCU-O7). `present_valid = (life[issue_ptr] == QUEUED)`; `present_slot = issue_ptr`.
- `fetch_valid = (life[tail_ptr] == READY)`; `fetch_slot = tail_ptr`.
- `kill = redirect_fire` (FCU-O2).
- `alloc_fire = !full || tail_free`, with no kill term (FCU-O6, FCU-O12). It drives `pc_write` and the `next_fetch_pc`
  next state; on a kill edge its value is not used by `next_fetch_pc`.
- `pc_write = alloc_fire`, `pc_write_slot = head_ptr`, `pc_write_data = next_fetch_pc` on every cycle, with no redirect
  mux (FCU-O4).
- `instruction_write = response_fire`, `instruction_write_slot = prv` (FCU-O4). A killed response is written too and is
  then discarded by the lifecycle rules.

### 5.3 Events (pre-edge)

- `F = fetch_valid && fetch_accept` (`fetch_fire`; fetch-stage O5).
- `P = outst && raw_response_transfer` (`response_fire`; FCU-O8).
- `Q = request_fire` (the leaf asserts it only while `present_valid = 1`).
- `K = kill`; `killed_resp = P && killed[prv]`.
- `tail_free = F || killed_resp` (no kill). Both free slot `tail`: a killed `OUTSTANDING` entry is at `tail` (I3).
- `A = alloc_fire`. On a kill edge the unit allocates nothing (FCU-O12).

### 5.4 Rules without a kill (`K = 0`)

- **P (response).** `life[prv] := killed[prv] ? FREE : READY`. The payload `instruction[prv]` is written on every
  `response_fire`; a killed entry never becomes `READY`, so its payload is never read (fetch-stage §5.3).
- **Q (request).** `life[issue] := OUTSTANDING`; `issue := next(issue)`. The killed flag is unchanged.
- **Delivery / killed drain (`tail_free`).** `life[tail] := FREE`; `killed[tail] := 0`; `tail := next(tail)`.
- **A (allocation).** `life[head] := QUEUED`; `pc[head]` takes `next_fetch_pc` (through `pc_write`); `killed[head] := 0`;
  `head := next(head)`. When `full`, `head == tail`, and the slot is reused only if `tail_free` frees it on this edge
  (BASE same-edge reuse).

Combined: `tail' = tail + tail_free`, `head' = head + A`, `issue' = issue + Q`.

### 5.5 Rules on a kill edge (`K = 1`)

All values come from the pre-edge state.

- `kept_out = outst && !P`: the outstanding entry at `prv` is kept as killed. A response on the kill edge discards it
  instead (BASE stale-response section).
- `kept_q = (life[issue] == QUEUED)`: the entry at `issue` is kept as killed. It is committed and presented (FCU-O9).
- Every `READY` entry is freed. Its delivery on `fetch_accept` is ignored (fetch-stage §5.2).
- Every `QUEUED` entry beyond `issue` is freed; these are uncommitted (FCU-O9).
- `tail' = kept_out ? prv : issue`.
- `restart = kept_q ? next(issue) : issue`: the first free slot after the kept entries, never a kept slot. At most two
  entries are kept (one `OUTSTANDING`, one committed `QUEUED`), so `restart` is free and the target can be allocated on
  the next edge (IF-A2).
- `head' = restart`. No slot becomes `QUEUED` (FCU-O12).
- `killed[prv] := 1` if `kept_out`; `killed[issue] := 1` if `kept_q` (FCU-O10).
- `issue' = Q ? next(issue) : issue`. If `Q = 1` the killed entry at `issue` becomes `OUTSTANDING`, and `issue` moves to
  `next(issue)`, which is `restart`.
- Every slot not named above becomes `FREE` with `killed = 0`. With nothing kept, `tail' = head' = issue`.
- **pc write.** `pc[head]` takes `next_fetch_pc` whenever `pc_write = 1`, with no kill condition (FCU-O12). This is safe:
  on a kill edge the written slot is `FREE` or freed on that edge, so no kept entry changes. If not `full`, `head` is
  `FREE`. If `full`, `head = tail`; a kept `tail` is `OUTSTANDING` with `P = 0` or `QUEUED` with `P = 0` (I4), and in
  both cases `alloc_fire = 0`. A freed `tail` (`READY`, or an `OUTSTANDING` answered on this edge) may be written.

### 5.6 Same-edge combinations

| Combination | Result |
| --- | --- |
| `F` and `P` | `tail` is freed; `prv` becomes `READY`. Slot `tail` can be reused by `head` when full (fetch-stage Trace A). |
| `Q` and `P` | Count stays `1`: `prv` becomes `READY`; `issue` becomes `OUTSTANDING`; the new `prv` is the old `issue`. |
| `Q` with an outstanding entry and no `P` | Outside the contract (section 6). |
| `F` with `K = 1` | `F` is ignored; every `READY` is freed; the HCU flush discards the IF/ID capture (fetch-stage §5.2). |
| `P` with `K = 1` | The response is discarded and `prv` is `FREE` (BASE stale-response section). |
| `Q` with `K = 1` | The killed entry at `issue` becomes killed `OUTSTANDING`; `issue` moves to `restart` (Trace D). |
| `killed_resp` with `A` when full | The killed drain frees `tail`, which `head` reuses (Trace W, edge 4). |
| Empty ring, `A` | `issue == head`: the new `QUEUED` entry is `issue` and is presented from the next cycle. |
| Raw response with `outst = 0` | No state change (BASE OBI response validity and reset; FOI-O3). |

### 5.7 The four redirect cases

The unit acts the same way in all four BASE cases: it loads `redirect_target` into `next_fetch_pc` and allocates nothing.
The entries follow section 5.5:

| BASE case | Entry before the edge | Rule |
| --- | --- | --- |
| 1. Wrong-path `READY` freed | `READY` | Freed by the kill; `tail` moves past it. |
| 2. Outstanding with a response on the edge | `OUTSTANDING` at `prv`, `P = 1` | Freed by `P`; not kept. |
| 3. Committed `QUEUED` granted on the edge | `QUEUED` at `issue`, `Q = 1` | Kept as killed; becomes killed `OUTSTANDING`; `issue` moves to `restart`. |
| 4. Unpresented `QUEUED` freed | `QUEUED` beyond `issue` | Freed; `head := restart` rewinds over them. |
| Kept: outstanding without a response | `OUTSTANDING` at `prv`, `P = 0` | Kept as killed; `tail := prv`; drained, never `READY`. |
| Kept: committed `QUEUED` not granted | `QUEUED` at `issue`, `Q = 0` | Kept as killed; `issue` stays, so the entry stays presented with stable `req`. |

### 5.8 Target allocation one edge later (IF-A2)

On redirect edge `k`, `next_fetch_pc` takes `T = redirect_target`. On edge `k+1`, with a non-full ring, `alloc_fire = 1`
and `T` is allocated at `head`; `next_fetch_pc` becomes `T + 4`. The target is `QUEUED` after edge `k+1`, and its `req`
starts in the following cycle (section 7, Trace 2). A second redirect on edge `k+1` is a new kill edge; the first target
is never allocated, because it was wrong-path work. BASE's "remains queued" wording is met because `issue` reaches the
target only after the stale outstanding entry drains, and `gnt` stays `0` until then.

## 6. Reset, cancellation, and exceptional conditions

**Reset.** On `rst_n = 0`, `life = FREE`, `killed = 0`, `head_ptr = issue_ptr = tail_ptr = 0` and
`next_fetch_pc = PC_RESET_VEC`, asynchronously (BASE [reset architecture](5-stage-baseline-core.md#reset-architecture)).
So `present_valid = 0` and `fetch_valid = 0` after propagation, and `pc_write_data` follows the register. `req` falls as
FOI-O5(a) assumes. `pc_write` may be 1 in reset (every entry is `FREE`, so `alloc_fire = 1`); the Fetch Buffer write is
then clocked, but no entry becomes valid. No edge with `rst_n = 0` counts a request, response, delivery or allocation.
After release, the subordinate returns no response for a pre-reset transaction (BASE OBI response validity and reset).

**Cancellation.** A kill is the only cancellation of wrong-path work (section 5.5, fetch-stage §6). A committed entry is
never removed before its `gnt`; it is kept as killed (BASE capacity and transaction states). The unit's part of a
redirect is that the wrong-path allocation does not happen: section 5.1 replaces `next_fetch_pc`.

**Environment preconditions:**

- A `request_fire` requires that no older outstanding entry remains after the edge (`outst = 0`, or `P = 1` on the same
  edge). This is the subordinate's obligation (BASE capacity and transaction states, `OBI_OUTSTANDING_MAX = 1`). The unit
  does not guard it; a violation is outside the contract.
- `kill` may be asserted only on an edge with `rst_n = 1`.
- Misaligned redirect targets are outside BASE, and [redirect-unit.md](redirect-unit.md) keeps them outside its contract.
  The unit passes `redirect_target` through and does not check alignment.
- `next_fetch_pc + 4` wraps modulo `2^32`. Fetch addresses stay in the code region (fetch-stage §6).
- Inputs are `0` or `1` only (fetch-stage O4). A raw unexpected response changes no state (section 5.6; FOI-O3).

## 7. Representative examples or cycle traces

Each row is one edge. Pointers are `head / issue / tail` after the edge, `life 0 / 1 / 2` lists the slots, `(k)` marks a
killed entry. Traces A and B of [fetch-stage.md](fetch-stage.md) §7 cover the steady-state and redirect cases; they are
not repeated here.

### Trace 1: sequential allocation with a full ring holding `next_fetch_pc`

Pre-edge: `next_fetch_pc = 0x14`. Ring full: `head = 0`, `issue = 2`, `tail = 0`; `life = READY 0x08 / OUTSTANDING 0x0C /
QUEUED 0x10`. `redirect_fire = 0`.

| Edge | Inputs | `next_fetch_pc` | Ring events | Ring after; `life 0 / 1 / 2` |
| --- | --- | --- | --- | --- |
| E0 | `fetch_accept = 0`, `gnt = 0`, `rvalid = 0` | `0x14` (hold) | `alloc_fire = 0`: full, no `tail_free` | `0 / 2 / 0`; unchanged |
| E1 | `fetch_accept = 1`, `gnt = 0`, `rvalid = 0` | `0x18` (`+4`) | `F = 1` frees slot 0; `alloc_fire = 1` reuses `head = 0`, `pc[0] := 0x14` | `1 / 2 / 1`; `QUEUED 0x14 / OUTSTANDING 0x0C / QUEUED 0x10` |
| E2 | `fetch_accept = 0`, `gnt = 1`, `rvalid = 1` | `0x18` (hold) | `P = 1`; `Q = 1`; `alloc_fire = 0`: full, `tail_free = 0` | `1 / 0 / 1`; `QUEUED 0x14 / READY 0x0C / OUTSTANDING 0x10` |

E0 and E2 hold because the ring is full. E1 allocates `0x14` while the ring frees and reuses the same slot on one edge.

### Trace 2: redirect, target allocation one edge later, and its first `req`

Pre-edge: `next_fetch_pc = 0x2C`. Ring full and stalled (`fetch_accept = 0`, as in fetch-stage Trace C): `head = issue =
tail = 0`; `life = READY 0x20 / READY 0x24 / READY 0x28`. Edge R samples `redirect_fire = 1`, `redirect_target = 0x100`,
`gnt = 0`, `rvalid = 0`. All three entries are wrong-path `READY` entries. Cycle R is the cycle with `redirect_fire = 1`.

| Edge | Inputs | `next_fetch_pc` | Ring events | Ring after; `life 0 / 1 / 2` |
| --- | --- | --- | --- | --- |
| R | `redirect_fire = 1`, `redirect_target = 0x100` | `0x2C` → `0x100` (priority 2) | `kill = 1`: all `READY` freed; nothing kept; `tail' = issue = 0`; no allocation | `0 / 0 / 0`; all `FREE` |
| R+1 | `redirect_fire = 0` | `0x100` → `0x104` (`alloc_fire = 1`) | Not full; slot 0 allocated: `pc[0] := 0x100`, `QUEUED` | `1 / 0 / 0`; `QUEUED 0x100 / FREE / FREE`; `present_valid = 1` from the next cycle |
| R+2 | `gnt = 1` (`request_fire`) | `0x104` → `0x108` (`alloc_fire = 1`) | `Q = 1`: slot 0 `OUTSTANDING`; slot 1 allocated with `pc[1] := 0x104` | `2 / 1 / 0`; `OUTSTANDING 0x100 / QUEUED 0x104 / FREE` |

The first `req` for the target is in cycle R+2, two cycles after the redirect cycle, the earliest IF-A2 allows.

### Trace D: redirect with a grant and the older response on the same edge

Pre-edge: `head = 0`, `issue = 2`, `tail = 0`; `life = READY 0x1C / OUTSTANDING 0x20 / QUEUED 0x24` (presented, full). `kill = 1`; `gnt = 1` (grants slot 2); `rvalid = 1` (answers slot 1); `fetch_accept = 0`.

| Edge | Events | `head / issue / tail`; `life 0 / 1 / 2` | Notes |
| --- | --- | --- | --- |
| R | `K = 1`; `P = 1` (slot 1 freed, response discarded); `Q = 1` (slot 2 killed `OUTSTANDING`); `kept_out = 0`; `tail' = issue = 2`; `restart = 0`; no allocation | `0 / 0 / 2`; `FREE / FREE / OUTSTANDING 0x24 (k)` | A killed `OUTSTANDING` at `tail` (I3). `issue = head`: `present_valid = 0`. `next_fetch_pc := 0x100`. |
| R+1 | No kill; not full; `alloc_fire = 1` | `1 / 0 / 2`; `QUEUED 0x100 / FREE / OUTSTANDING 0x24 (k)` | Target allocated at slot 0; `gnt = 0` until the killed response on slot 2 is taken (`OBI_OUTSTANDING_MAX = 1`). |

Next edge (not shown): `rvalid` answers slot 2 (`killed_resp = 1`); slot 2 becomes `FREE` and `tail := 0`. The target at
slot 0 can be granted on that edge.

### Trace W: pointer wrap past the third slot

Start: empty, `head = issue = tail = 2`. Per edge: `fetch_accept = 1` on E4..E6; `gnt = 1` on E2..E6 when `issue` is
`QUEUED`; `rvalid = 1` on E3..E6 for the outstanding entry. An allocation happens on every edge with a free slot, with
`next_fetch_pc = 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34` on E1..E6.

| Edge | Events | `head / issue / tail` | `life 0 / 1 / 2` | Wrap |
| --- | --- | --- | --- | --- |
| E1 | `A`: slot 2 gets `0x20`; `head` `2 -> 0` | `0 / 2 / 2` | `FREE / FREE / QUEUED 0x20` | `head` wraps |
| E2 | `Q` on slot 2 (`issue` `2 -> 0`); `A`: slot 0 gets `0x24` | `1 / 0 / 2` | `QUEUED 0x24 / FREE / OUTSTANDING 0x20` | `issue` wraps |
| E3 | `P` on slot 2 (`READY`); `Q` on slot 0; `A`: slot 1 gets `0x28` | `2 / 1 / 2` | `OUTSTANDING 0x24 / QUEUED 0x28 / READY 0x20` | Full |
| E4 | `F` frees slot 2 (`tail` `2 -> 0`); `P` on slot 0; `Q` on slot 1; `A` reuses slot 2 (`head` `2 -> 0`) | `0 / 2 / 0` | `READY 0x24 / OUTSTANDING 0x28 / QUEUED 0x2C` | `head` and `tail` wrap |
| E5 | `F` frees slot 0 (`tail` `0 -> 1`); `P` on slot 1; `Q` on slot 2 (`issue` `2 -> 0`); `A` reuses slot 0 (`head` `0 -> 1`) | `1 / 0 / 1` | `QUEUED 0x30 / READY 0x28 / OUTSTANDING 0x2C` | `issue` wraps |
| E6 | `F` frees slot 1 (`tail` `1 -> 2`); `P` on slot 2; `Q` on slot 0 (`issue` `0 -> 1`); `A` reuses slot 1 (`head` `1 -> 2`) | `2 / 1 / 2` | `OUTSTANDING 0x30 / QUEUED 0x34 / READY 0x2C` | Delivery order `0x20, 0x24, 0x28` follows allocation order |

## 8. Verification obligations

No test for this unit exists (`tb/runners/` has no fetch runner, checked 2026-11-06). Planned checks; expected values come
from section 5 and [fetch-buffer.md](fetch-buffer.md), not from the DUT. Stage-level checks are in
[fetch-stage.md](fetch-stage.md) §8.

| Requirement / invariant | Stimulus or scenario | Expected observation |
| --- | --- | --- |
| Reset (section 6) | `rst_n` asserted with `next_fetch_pc` at another value | `pc_write_data = PC_RESET_VEC` after propagation, without an edge |
| Sequential `+4` (I1) | `alloc_fire = 1` for three consecutive edges from `PC_RESET_VEC` | Allocated `pc` takes `0x0, 0x4, 0x8` in order |
| Hold on full (I2, Trace 1) | `alloc_fire = 0` for several edges | `pc_write_data` unchanged; `pc_write = 0` |
| Redirect loads target (FCU-O5) | `redirect_fire = 1` with `alloc_fire = 1` | `next_fetch_pc` takes `redirect_target`, not `redirect_target + 4` |
| Redirect edge: no allocation (IF-A2, FCU-O12) | Trace 2, edge R | No live entry written; `next_fetch_pc = 0x100` |
| Target allocated one edge later (Trace 2) | Trace 2, edges R+1 and R+2 | `0x100` written at R+1 and `0x104` at R+2 |
| `req` timing (IF-A2) | Trace 2 | First `req` for `0x100` in cycle R+2 |
| Back-to-back redirect (section 5.8) | Redirect on edges R and R+1 | Target from R is never allocated |
| No combinational path from redirect to `pc_write_data` (IF-A2) | Toggle `redirect_target` while `redirect_fire = 0` | `pc_write_data` and `next_fetch_pc` unchanged within the cycle |
| Write enables off the request path (section 2) | Toggle `fetch_accept`, `raw_response_transfer` within a cycle | `req`, `present_valid`, `fetch_valid` unchanged until the edge |
| `kill` broadcast (FCU-O2) | Any stimulus | `kill` equals `redirect_fire` in every cycle |
| Four redirect cases (section 5.7) | One stimulus per case | Each case gives the stated `life` result |
| Pointer wrap (Trace W) | Six allocations and deliveries from `head = 2` | Pointers wrap as shown; delivery order is allocation order |
| Full / empty by `life[head]` (I1, I4) | Full with all `QUEUED`; full with all issued; empty | `full` and `issue` as stated |
| Delivery ignored on kill (fetch-stage §5.2) | `fetch_accept = 1` on a kill edge with a `READY` tail | Tail `READY` freed; no delivery |
| Killed drain at `tail` (I3) | Killed `OUTSTANDING` answered | Entry `FREE`; never `READY` |
| Unexpected response (section 5.6) | Raw response with no outstanding entry | No state change |

## 9. Rationale and open decisions

### Open items

1. **Controller issue policy (resolved by IF-A3, 2026-11-06).** The issue policy belongs to this unit: it presents the
   oldest `QUEUED` entry ([BASE](5-stage-baseline-core.md#instruction-fetch-organization)).
2. **Drain and redirect allocation (external-interrupt-extension.md line 247).** Under IF-A2 the redirect target is
   allocated on the edge after the redirect. If that edge is in a drain freeze, the freeze must still allow this one
   target allocation. The extension document does not say which edge. This is a follow-up for that document's owner.

### Decisions

**IF-A2. Delayed redirect target (BASE amendment, accepted 2026-11-05).** The redirect edge loads the target into
`next_fetch_pc` without allocating it; the target is allocated on the next edge. Reason: `redirect_target` no longer
reaches the `pc` slots or a `+4` adder, and the controller loses a mux and an adder. Cost: one more cycle per redirect.
No synthesis numbers exist, so no timing gain is claimed.

**IF-A3. Control moves to the controller (BASE amendment, accepted by Việt on 2026-11-06).** Decision FCU-O13. Behavior is
unchanged.

**FCU-O13. The cut (2026-11-06).** The controller owns every state element with a reset and all logic on them. The
[Fetch Buffer](fetch-buffer.md) owns only `pc[]` and `instruction[]` (FB-O8). Both module names stay, and internal names
move unchanged. Read muxes stay in the buffer (FB-O9). Reason: entries are allocated before data arrives and a kill
reloads the pointers, so ordering and lifecycle belong in one module. This supersedes the 2026-11-04 controller
boundary (decision map, section 9). `alloc_valid` is removed (FCU-O3); `kill` and `alloc_fire` become internal.

**FCU-O1. Ports (rewritten 2026-11-06).** Inputs `clk`, `rst_n`, `redirect_fire`, `redirect_target`, `fetch_accept`,
`request_fire`, `raw_response_transfer`; outputs as in section 2. No `gnt`, no `alloc_valid`.

**FCU-O2. `kill` (internal, kept).** `kill = redirect_fire`, an internal signal (2026-11-05).

**FCU-O3. `alloc_valid` (retired 2026-11-06).** Allocation is requested on every edge; the ring's `full` is the only
capacity rule. A pause would need a new decision.

**FCU-O4. Buffer write and read addresses (rewritten 2026-11-06).** `pc_write = alloc_fire`, `pc_write_slot = head_ptr`,
`pc_write_data = next_fetch_pc` with no redirect mux; `instruction_write = response_fire`, `instruction_write_slot = prv`;
`present_slot = issue_ptr`; `fetch_slot = tail_ptr`.

**FCU-O5. `next_fetch_pc` (kept, 2026-11-05).** Priority: reset, then kill (`redirect_target`), then `alloc_fire` (`+4`),
then hold. One adder.

**FCU-O6. `alloc_fire` on a kill edge (kept, 2026-11-05).** A don't-care for `next_fetch_pc`; `kill` has priority, so no
`!kill` term is added. Section 5.5 shows that its `pc_write` effect is safe.

**FCU-O7. Age order (2026-11-04).** A ring of three slots with `head_ptr` (write end), `issue_ptr` (oldest `QUEUED`)
and `tail_ptr` (oldest entry). Allocation writes at `head` then advances it; `request_fire` moves `issue`; delivery or a
killed drain frees `tail`. `head == tail` is resolved by `life[head]`. On a redirect edge `tail = kept_out ? issue - 1 :
issue` and `head = restart`; `issue` changes only through `request_fire`.

**FCU-O8. Outstanding (2026-11-04).** Derived: `outstanding = life[issue - 1] == OUTSTANDING`; `response_fire =
outstanding && raw_response_transfer`, landing in slot `issue - 1`.

**FCU-O9. Committed (2026-11-04).** Derived: the entry at `issue` is committed when `life[issue] == QUEUED`. Every other
`QUEUED` entry is uncommitted. `present_valid` equals that condition; an entry is presented from its first `QUEUED`
cycle at `issue`.

**FCU-O10. Killed (2026-11-04).** One bit per entry, set on the redirect edge for each kept entry, cleared when the slot
is freed or allocated, and on reset. Only the response path reads it.

**FCU-O11. Pointer encoding (2026-11-04).** 2-bit slot indices; `next` and `prev` wrap `2 -> 0` and `0 -> 2`. Value `3`
is unused and unreachable from reset.

**FCU-O12. Kill edge allocates nothing (2026-11-05).** No slot becomes `QUEUED` on a kill edge. `pc_write` may still
assert there, and the slot it writes is free or freed on that edge (section 5.5). The target is allocated on the next edge.

### Decision map

The map from the 2026-11-04 IDs to the new IDs is the only one in this set of documents.

| Old ID (2026-11-04) | New ID | Status |
| --- | --- | --- |
| FB-O1. Controller boundary | FCU-O13 (the cut) | Superseded by IF-A3 |
| FB-O2. Age order | FCU-O7 | Moved |
| FB-O3. Outstanding | FCU-O8 | Moved |
| FB-O4. Committed | FCU-O9 | Moved |
| FB-O5. Kill marks | FCU-O10 | Moved |
| FB-O6. Pointer encoding | FCU-O11 | Moved |
| FB-O7. Kill edge allocates nothing | FCU-O12 | Moved; the write goes through `pc_write` |
| FCU-O3. `alloc_valid` | retired | Removed by FCU-O13 |
