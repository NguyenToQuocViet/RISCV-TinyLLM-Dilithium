# Fetch Controller Unit — Block Design

**Status:** Accepted by Việt on 2026-11-05
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner. The decisions FCU-O1..FCU-O6 in section 9 are the
Owner's of 2026-11-05. The amendment they depend on, BASE IF-A2, was accepted by Việt on the same date.
**Parent contract:** [Fetch stage](fetch-stage.md) (§2 boundary, §3 leaf responsibilities, §4 `next_fetch_pc`,
§5.2 redirect, §7 Trace B), [Fetch buffer](fetch-buffer.md) (FB-O1 amended, FB-O7 replaced, §4.1, §4.3, §4.5,
§5), and the [five-stage BASE core](5-stage-baseline-core.md): [instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization) (Fetch Controller Unit role), the IF-A2
amendment, [stale instruction responses after redirect](5-stage-baseline-core.md#stale-instruction-responses-after-redirect)
and [reset architecture](5-stage-baseline-core.md#reset-architecture).
Producer of `redirect_fire` and `redirect_target`: [redirect unit](redirect-unit.md).
Layout precedent: [fetch-buffer.md](fetch-buffer.md), [fetch-obi-interface.md](fetch-obi-interface.md).
**RTL mapping:** `rtl/fetch_controller_unit.sv`. Module `fetch_controller_unit`, instance
`if_fetch_controller_unit` inside `prefetch_unit` (fetch-stage §3). The RTL is written by Việt (F-d). This document
is neither implementation nor verification evidence.

## 1. Purpose and boundary

`fetch_controller_unit` is the instruction-fetch control plane of the baseline (BASE [instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization)). It owns the
registered `next_fetch_pc`: it advances it by `+4` on each allocation, loads `redirect_target` on a redirect edge,
and drives the allocation and kill commands to `fetch_buffer`. The buffer holds the entries; this unit holds one
address.

Non-goals:

- No per-entry state and no entry choice. `fetch_buffer` chooses the presented entry, the oldest `QUEUED`
  (FB-O1). The unit reads no `life`, `issue` or `tail`.
- No OBI signals and no `gnt`. The OBI leaf and the buffer own them (fetch-obi-interface.md).
- No hazard or MEM knowledge. The HCU drives `fetch_accept` (fetch-stage F-b).
- No redirect decoding and no target checking. `redirect_fire` and `redirect_target` arrive already qualified
  by EX advance (redirect-unit.md). Misaligned targets are outside BASE and outside this unit (section 5).
- No allocation pause. `alloc_valid` is tied to `1` (FCU-O3). The seam stays in the port list, but pausing is a
  later decision.

Observable success criterion: after reset the allocated addresses start at `PC_RESET_VEC` and step by `+4` for each
allocation. After a redirect edge the first allocated address is the redirect target, allocated on the following edge
(IF-A2), not on the redirect edge itself.

## 2. Interface contract

### Clock, reset and configuration

`clk` is the rising-edge clock of `next_fetch_pc`. `rst_n` is asynchronous assert, synchronized release (BASE
[reset architecture](5-stage-baseline-core.md#reset-architecture); fetch-stage N3). `ADDR_WIDTH = 32` from
`riscv_pkg`. `PC_RESET_VEC` is defined in `riscv_pkg` (fetch-stage D-1, resolved).

### Ports

All ports are individual signals. There are 5 inputs and 3 outputs. The names of the `fetch_buffer` side match
[fetch-buffer.md](fetch-buffer.md) §2 exactly.

| Signal | Direction | Type / width | Meaning | Valid when | Source |
| --- | --- | --- | --- | --- | --- |
| `clk` | Input | 1-bit `logic` | Rising-edge clock of `next_fetch_pc` | Always | Reset architecture |
| `rst_n` | Input | 1-bit `logic` | Active-low reset; async clear to `PC_RESET_VEC` | Always | Reset architecture; fetch-stage N3 |
| `redirect_fire` | Input | 1-bit `logic` | EX taken redirect on this edge, raw from EX | Each edge | [redirect-unit.md](redirect-unit.md) output `redirect_fire`; fetch-stage §2 (F-e) |
| `redirect_target` | Input | `logic [ADDR_WIDTH-1:0]` | Redirect target address | When `redirect_fire = 1` | [redirect-unit.md](redirect-unit.md) output `redirect_target`; fetch-stage §2 |
| `alloc_fire` | Input | 1-bit `logic` | Buffer allocated `alloc_pc` on this edge. On a kill edge it is a don't-care (FCU-O6) | Each edge | [fetch-buffer.md](fetch-buffer.md) output `alloc_fire` (FB-O1, FB-O7) |
| `kill` | Output | 1-bit `logic` | Redirect edge broadcast to the buffer; equal to `redirect_fire` | Each edge | FCU-O2; fetch-buffer §2 `kill` (FB-O1) |
| `alloc_valid` | Output | 1-bit `logic` | Constant `1`: `alloc_pc` is valid and asks for a slot | Always | FCU-O3; fetch-buffer §2 `alloc_valid` (FB-O7: ignored on a kill edge) |
| `alloc_pc` | Output | `logic [ADDR_WIDTH-1:0]` | `next_fetch_pc`, on every cycle | Meaningful when `alloc_valid = 1` | FCU-O4; fetch-buffer §2 `alloc_pc` (IF-A2) |

The unit has no `gnt`, no per-entry input and no presentation output (FCU-O1). `redirect_target` reaches only the
`next_fetch_pc` register (section 4.1). It does not reach `alloc_pc` or any buffer port.

### Transfer and timing rules

- `alloc_pc` and `alloc_valid` are functions of the `next_fetch_pc` register and a constant only. No output depends
  combinationally on an input, so no input reaches the buffer's read path. This also means `redirect_target`
  never reaches a `pc` slot combinationally (IF-A2).
- `kill` is a pass-through of `redirect_fire`. It affects only next-state values in `fetch_buffer`, and the buffer
  state is not on any request path (fetch-buffer §2).
- `alloc_fire` is used only for the `next_fetch_pc` next state (FB-O1).
- Inputs are sampled at the rising edge (fetch-stage §2).

## 3. State and invariants

### State

| State | Width / type | Reset | Meaning | Updated by |
| --- | --- | --- | --- | --- |
| `next_fetch_pc` | `logic [ADDR_WIDTH-1:0]` | `PC_RESET_VEC` (`riscv_pkg`) | Address of the next allocation (BASE [capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states): ownership passes to the entry on allocation) | Redirect edge (loads `redirect_target`); allocation (`+4`); reset |

This is the only state register of the unit. It is the registered `next_fetch_pc` of fetch-stage §4. No other
state is stored: no lifecycle, no killed bit, no outstanding count, no pending-target flag (IF-A2: "The baseline has
no `redirect_pending` state", BASE [stale instruction responses after redirect](5-stage-baseline-core.md#stale-instruction-responses-after-redirect)).

### Derived signals

None. `alloc_valid` is a constant, `alloc_pc` is the register, and `kill` is `redirect_fire`.

### Invariants

- **I1. Address ownership.** Each allocation takes the current `next_fetch_pc`, and the register then advances by
  `+4`. A redirect edge replaces the register by `redirect_target` and allocates nothing on that edge (IF-A2).
- **I2. Hold.** `next_fetch_pc` changes only on a reset, a redirect edge or an allocation. While the buffer is full
  (`alloc_fire = 0`) it holds (fetch-stage §4).

## 4. Behavioral rules

### 4.1 Next-state priority (FCU-O5)

| Priority | Condition (pre-edge) | `next_fetch_pc` after the edge |
| --- | --- | --- |
| 1 | `rst_n = 0` (asynchronous) | `PC_RESET_VEC` |
| 2 | `kill = 1` (`= redirect_fire`) | `redirect_target` |
| 3 | `alloc_fire = 1` | `next_fetch_pc + 4` |
| 4 | none of the above | `next_fetch_pc` (hold) |

Priority 2 beats priority 3, so the value of `alloc_fire` on a redirect edge is never used (FCU-O6). The register
has one adder, for `+4`. The redirect target is one mux input at the register's D input. It has no path to
`alloc_pc` and no path through the adder. This is the point of IF-A2: the EX branch-resolve path no longer reaches
the `pc` slots or a `+4` adder (section 9).

### 4.2 Output values

- `kill = redirect_fire` (FCU-O2).
- `alloc_valid = 1` (FCU-O3). The buffer's `full` is the only capacity check.
- `alloc_pc = next_fetch_pc` on every cycle, with no redirect mux (FCU-O4).

### 4.3 The four redirect cases

The controller acts the same way in all four BASE cases: it loads `redirect_target` into `next_fetch_pc` and
allocates nothing on the redirect edge. The four cases differ only in the buffer. Each case maps to one rule of
[fetch-buffer.md](fetch-buffer.md) §4.5:

| BASE case | Buffer rule (fetch-buffer §4.5) | Controller action on the redirect edge |
| --- | --- | --- |
| 1. Wrong-path `READY` | Freed by the kill | `next_fetch_pc := redirect_target` |
| 2. Outstanding with response on the edge | Freed by `P`, not kept | `next_fetch_pc := redirect_target` |
| 3. Committed `QUEUED` granted on the edge | Kept as killed; `issue` moves to `restart` | `next_fetch_pc := redirect_target` |
| 4. Unpresented `QUEUED` | Freed; `head := restart` | `next_fetch_pc := redirect_target` |

Kept entries after a redirect edge are at most two: one `OUTSTANDING` and one committed `QUEUED`. So the buffer has a
free slot at `restart` (fetch-buffer §4.3). Under IF-A2 the target is allocated into that slot on the following edge
(section 4.4), so no redirect case has to wait for a second free slot.

### 4.4 Target allocation one edge later (IF-A2)

On the redirect edge `k`, `next_fetch_pc` takes `T = redirect_target`. On edge `k+1`, with `alloc_valid = 1` and a
non-full buffer, `alloc_fire = 1` and the buffer allocates `T` at `head`. `next_fetch_pc` becomes `T + 4`. The target
is therefore visible as a `QUEUED` entry after edge `k+1`, and its `req` starts in the cycle after that (section 6,
Trace 2).

A second redirect on edge `k+1` is a new kill edge. The buffer allocates nothing on it, and `next_fetch_pc` takes the
new target. The first target `T` is never allocated, which is correct because it was wrong-path work.

## 5. Reset, cancellation and environment

**Reset.** With `rst_n = 0`, `next_fetch_pc` becomes `PC_RESET_VEC` asynchronously, without a clock edge (BASE
[reset architecture](5-stage-baseline-core.md#reset-architecture)). `alloc_pc` follows the register. `alloc_valid`
stays `1`, but the buffer clears its state under reset and counts no allocation in an edge with `rst_n = 0`
(fetch-buffer §6).

**Cancellation.** The unit cancels no entry. Its part of a redirect is only that the wrong-path allocation does not
happen: the priority of section 4.1 replaces `next_fetch_pc`, and the buffer's kill rules handle the entries
(fetch-buffer §4.3).

**Environment preconditions:**

- Misaligned redirect targets are outside BASE, and [redirect-unit.md](redirect-unit.md) keeps them outside its
  contract. This unit passes `redirect_target` through unchanged and does not check its alignment.
- `next_fetch_pc + 4` wraps modulo `2^32`. Fetch addresses stay in the code region (fetch-stage §6, BASE
  [stale instruction responses](5-stage-baseline-core.md#stale-instruction-responses-after-redirect)).
- Inputs are `0` or `1` only (fetch-stage O4).

## 6. Representative traces

Each row is one edge. `next_fetch_pc` is written in hex. The buffer columns use the notation of
[fetch-buffer.md](fetch-buffer.md) §5: pointers `head / issue / tail`, and `life 0 / 1 / 2`. The `(k)` flag marks a
killed entry.

### Trace 1: sequential allocation with a full buffer holding `next_fetch_pc`

Pre-edge: `next_fetch_pc = 0x14`. Buffer full, as in fetch-buffer Trace A: `head = 0`, `issue = 2`, `tail = 0`;
`life = READY 0x08 / OUTSTANDING 0x0C / QUEUED 0x10`. `alloc_valid = 1` (FCU-O3). `redirect_fire = 0`.

| Edge | Inputs | `next_fetch_pc` | Buffer events | Buffer after: `head / issue / tail`; `life 0 / 1 / 2` |
| --- | --- | --- | --- | --- |
| E0 | `fetch_accept = 0`, `gnt = 0`, `rvalid = 0` | `0x14` (hold) | `alloc_fire = 0`: full, no `tail_free` | `0 / 2 / 0`; `READY 0x08 / OUTSTANDING 0x0C / QUEUED 0x10`, unchanged |
| E1 | `fetch_accept = 1`, `gnt = 0`, `rvalid = 0` | `0x18` (`+4`) | `F = 1` frees slot 0; `alloc_fire = 1` reuses `head = 0` with `alloc_pc = 0x14` | `1 / 2 / 1`; `QUEUED 0x14 / OUTSTANDING 0x0C / QUEUED 0x10` (full: `life[1] != FREE`) |
| E2 | `fetch_accept = 0`, `gnt = 1`, `rvalid = 1` | `0x18` (hold) | `P = 1` (slot 1 `READY`); `Q = 1` (slot 2 `OUTSTANDING`); `alloc_fire = 0`: full, `tail_free = 0` | `1 / 0 / 1`; `QUEUED 0x14 / READY 0x0C / OUTSTANDING 0x10` |

E0 and E2 hold because the buffer is full. E1 allocates `0x14` while the buffer frees and reuses the same slot on one
edge (BASE same-edge reuse). `next_fetch_pc` then moves to `0x18`, and that address waits for the next free slot.

### Trace 2: redirect, target allocation one edge later, and its first `req`

Pre-edge: `next_fetch_pc = 0x2C`. Buffer full and stalled (`fetch_accept = 0`, as in fetch-stage Trace C):
`head = issue = tail = 0`; `life = READY 0x20 / READY 0x24 / READY 0x28`. `alloc_valid = 1`. Edge R is the edge
sampling `redirect_fire = 1`, with `redirect_target = 0x100`, `gnt = 0`, `rvalid = 0`. All three entries are
wrong-path `READY` entries.

Cycle numbering: cycle R is the cycle in which `redirect_fire = 1`. The first `req` for the target is asserted in
cycle R+2, two cycles after the redirect cycle.

| Edge | Inputs | `next_fetch_pc` | Buffer events | Buffer after: `head / issue / tail`; `life 0 / 1 / 2` |
| --- | --- | --- | --- | --- |
| R | `redirect_fire = 1`, `redirect_target = 0x100` | `0x2C` → `0x100` (`kill`, priority 2) | `kill = 1`: all three `READY` entries are freed; nothing kept; `tail' = issue = 0`, `restart = 0`; `alloc_fire` is a don't-care and is not used | `0 / 0 / 0`; `FREE / FREE / FREE` (empty) |
| R+1 | `redirect_fire = 0`, `alloc_valid = 1` | `0x100` → `0x104` (`alloc_fire = 1`) | Not full (`life[0] = FREE`); `alloc_fire = 1`; slot 0 allocated with `alloc_pc = 0x100` as `QUEUED` | `1 / 0 / 0`; `QUEUED 0x100 / FREE / FREE`. `present_valid = 1` from the cycle after this edge |
| R+2 | `gnt = 1` (`request_fire`), `alloc_valid = 1` | `0x104` → `0x108` (`alloc_fire = 1`) | `Q = 1`: slot 0 `OUTSTANDING`, `issue` moves to slot 1; not full (`life[1] = FREE`), so slot 1 allocated with `0x104` | `2 / 1 / 0`; `OUTSTANDING 0x100 / QUEUED 0x104 / FREE` |

The pre-state is reachable: it is the full, stalled state of fetch-stage Trace C, with the entries `READY`. The
target's `req` is asserted in cycle R+2 (the cycle after edge R+1), and it is granted on edge R+2. The redirect
cycle is R, so the first `req` is two cycles after it, the earliest that IF-A2 allows.

## 7. Verification obligations

No test for this unit exists (`tb/runners/` has no fetch runner, checked 2026-11-05). The following are planned.
Expected values come from section 4 and from [fetch-buffer.md](fetch-buffer.md), not from the DUT. Each check is
observable at the unit's ports and at the buffer side named in the table.

| Requirement / invariant | Stimulus or scenario | Expected observation |
| --- | --- | --- |
| Reset (section 5) | `rst_n` asserted with `next_fetch_pc` at another value | `alloc_pc = PC_RESET_VEC` after propagation, without an edge |
| Sequential `+4` (I1) | `alloc_fire = 1` for three consecutive edges from `PC_RESET_VEC` | `alloc_pc` takes `0x0, 0x4, 0x8` in order |
| Hold on full (I2, Trace 1) | `alloc_fire = 0` for several edges | `alloc_pc` unchanged |
| Redirect loads target (FCU-O5) | `redirect_fire = 1` with `alloc_fire = 1` | `next_fetch_pc` takes `redirect_target`, not `redirect_target + 4` |
| Redirect edge: no allocation (IF-A2) | Trace 2, edge R | `alloc_fire` ignored; the buffer allocates nothing; `next_fetch_pc = 0x100` |
| Target allocated one edge later (Trace 2) | Trace 2, edges R+1 and R+2 | Buffer allocates `0x100` at R+1 and `0x104` at R+2 |
| `req` timing (IF-A2) | Trace 2 | First `req` for `0x100` in cycle R+2, not in cycle R+1 |
| Back-to-back redirect (section 4.4) | Redirect on edges R and R+1 | Target from R is never allocated; `next_fetch_pc = second target` after R+1 |
| No combinational path from redirect to `alloc_pc` (IF-A2) | Toggle `redirect_target` while `redirect_fire = 0` | `alloc_pc` and `next_fetch_pc` unchanged within the cycle |
| `alloc_valid` tie-off (FCU-O3) | Any stimulus | `alloc_valid = 1` in every cycle |
| `kill` broadcast (FCU-O2) | Any stimulus | `kill` equals `redirect_fire` in every cycle |

## 8. Open items

Each item is a gap found while drafting. The Owner decides; each has a recommendation.

1. **BASE wording on controller issue policy (already flagged in the 2026-11-04 round).** The
   [Instruction-fetch organization](5-stage-baseline-core.md#instruction-fetch-organization) section gives the
   controller "issue policy". FB-O1 gives the presented-entry choice to the buffer, which the
   [capacity and transaction states](5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states)
   section already describes.
   - (a) Reword the controller role at the next BASE amendment so the buffer chooses the presented entry.
     **Recommendation.**
   - (b) Keep the wording and read "issue policy" as the buffer's presentation rule.
   This document follows FB-O1 and does not edit that section.
2. **Drain and redirect allocation (external-interrupt-extension.md line 247).** Under IF-A2 the redirect target is
   allocated on the edge after the redirect. If that edge is in a drain freeze, the freeze must still allow this one
   target allocation. The extension document says it may allocate its fresh target while draining, but it does not
   say which edge. This is a follow-up for that document's owner, not a change to this one.

## 9. Rationale and decisions

Each decision below is the Owner's, dated 2026-11-05, and is written as settled. The amendment IF-A2 is in BASE,
accepted, and is the reason for FCU-O4 and FCU-O5.

**IF-A2. Delayed redirect target (BASE amendment, accepted 2026-11-05).** Decision (Việt, 2026-11-05): the redirect edge does not
allocate the target. On that edge the buffer applies the four redirect cases, and `next_fetch_pc` takes
`redirect_target`. The target is allocated through the ordinary allocation path on a later edge, the next edge in the
baseline. Reason: `redirect_target` no longer reaches the three `pc` slots or a `+4` adder after the EX branch-resolve
path, and the controller loses a mux and an adder. Cost: one more cycle per redirect; the address reaches the bus two
cycles after the redirect cycle at the earliest, not one. No synthesis numbers exist, so no timing gain is claimed.
Still no `redirect_pending` state: `next_fetch_pc` holds the target, and a free slot exists after the redirect edge
because at most two entries are kept.

**FCU-O1. Ports.** Decision (Việt, 2026-11-05): inputs `clk`, `rst_n`, `redirect_fire`, `redirect_target`,
`alloc_fire`; outputs `kill`, `alloc_valid`, `alloc_pc`. No `gnt` and no per-entry state. Reason: FB-O1 keeps the
controller free of per-entry state, so the unit depends only on the EX redirect and the buffer's allocation result.

**FCU-O2. `kill`.** Decision (Việt, 2026-11-05): `kill = redirect_fire`. One broadcast to the buffer, as FB-O1
states.

**FCU-O3. `alloc_valid`.** Decision (Việt, 2026-11-05): constant `1`. Meaning: `alloc_pc` is valid and asks for a slot.
The baseline has no reason to stop fetch, and the buffer's `full` handles capacity. The port stays as the seam for
pausing allocation later. This is a contract with a tie-off, not an invariant of the design: a later pause would set
it from a condition, and that would be a new decision.

**FCU-O4. `alloc_pc`.** Decision (Việt, 2026-11-05): `alloc_pc = next_fetch_pc` on every cycle, with no redirect mux.
The target reaches the buffer only through the `next_fetch_pc` register, one edge later (IF-A2). This is what
removes the mux that the 2026-11-04 wording needed on `alloc_pc`.

**FCU-O5. `next_fetch_pc`.** Decision (Việt, 2026-11-05): the name stays, meaning the next PC to fetch. Priority:
reset takes `PC_RESET_VEC`; else `kill` takes `redirect_target`; else `alloc_fire` adds `4`; else it holds. One adder.

**FCU-O6. `alloc_fire` on a kill edge.** Decision (Việt, 2026-11-05): `alloc_fire` on a kill edge is a don't-care. The
controller gives `kill` priority, so no `!kill` term is added, and `kill` leaves the `alloc_fire` path. The buffer
allocates nothing on a kill edge (FB-O7, replaced), so the value of `alloc_fire` there is never used.

### Dependencies

- `fetch_buffer` (fetch-buffer.md): the port table of section 2 must match. On a kill edge the buffer ignores
  `alloc_valid` (FB-O7) and allocates nothing. Its RTL (`rtl/fetch_buffer.sv`) implements this rule.
- `redirect_unit` (redirect-unit.md): supplies `redirect_fire` and `redirect_target`, already qualified by EX advance.
- HCU design (fetch-stage D-3): drives `fetch_accept` and IF/ID control. This unit does not depend on it.
- RTL is written by Việt (fetch-stage F-d).
