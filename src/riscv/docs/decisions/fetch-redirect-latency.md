# IF-A4 — Fetch Redirect Latency: Direct Presentation and Response Bypass

**Status:** Accepted by Việt on 2026-11-23
**Type:** Microarchitecture decision (frontend timing contract).
**Decision owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Author:** Nguyễn Tô Quốc Việt
**Applies to:** BASE instruction frontend: [Fetch Controller Unit](../designs/fetch-controller-unit.md), [Fetch Buffer](../designs/fetch-buffer.md), [Fetch Stage](../designs/fetch-stage.md).
**Supersedes:** The cost statement of IF-A2 and the `RESPONSE_BYPASS=0` rule in BASE.
**Behavioral authority:** [BASE capacity and transaction states](../designs/5-stage-baseline-core.md#instruction-fetch-capacity-and-transaction-states).

## Context: why

The first benchmark run (2026-11-20, ideal one-cycle memory) gave 0.623 / 0.670
CoreMark/MHz and 0.436 DMIPS/MHz. Every taken branch, JAL and JALR cost exactly
5 cycles, and these redirects took 47 % of all CoreMark cycles. A branch that
resolves in EX should cost 2 cycles: the two wrong-path instructions in IF and
ID. The other 3 cycles were in the refetch path.

## How the cause was traced

- **Probe.** Three small assembly loops, one each for BEQ, JAL and JALR. Each
  jumps between two code regions A and B until a counter reaches 10. Every jump
  is always taken, and an `ebreak` after each jump acts as wrong-path poison.
- **Bench.** The Verilator bench logs about 60 control signals of the fetch
  controller, the IF/ID and ID/EX registers and the redirect unit once per
  cycle.
- **Finding.** All 39 redirects in the three probes followed one pattern,
  whatever the jump type. Counting cycles after the redirect cycle N:

| Cycle | What happens to the target | Register it waits in |
| --- | --- | --- |
| N | EX fires the redirect; the target is written to `next_fetch_pc` | `next_fetch_pc` |
| N+1 | The target is allocated into a slot as QUEUED; no request yet | `pc[slot]`, QUEUED |
| N+2 | `req` with the target address | OUTSTANDING |
| N+3 | Response arrives and is written to the slot | READY |
| N+4 | The slot is offered to IF/ID | IF/ID |
| N+5 | ID | ID/EX |
| N+6 | EX | |

Excerpt from the JAL probe (`j c0` at 0xAC jumps to B = 0xC0). Here `life`
lists slots 0, 1, 2 as F free, Q queued, O outstanding, R ready:

| Cycle | `instr_req` / addr | `life` | Fetch out | IF/ID | ID/EX |
| --- | --- | --- | --- | --- | --- |
| 36 | 1 / 0xBC | ROQ | 0xB4 | 0xB0 | 0xAC `j c0`, redirect fires |
| 37 | 0 | FFO | - | - | - |
| 38 | 1 / 0xC0 | QFF | - | - | - |
| 39 | 1 / 0xC4 | OQF | - | - | - |
| 40 | 1 / 0xC8 | ROQ | 0xC0 | - | - |
| 41 | 1 / 0xCC | QRO | 0xC4 | 0xC0 | - |
| 42 | 1 / 0xD0 | OQR | 0xC8 | 0xC4 | 0xC0 |

The two registers that cost the extra cycles were in the contract, not in a bug:

- IF-A2 sent the target through the ordinary allocation path, so a request
  could only come from a QUEUED slot, one cycle after `next_fetch_pc`.
- `RESPONSE_BYPASS=0` made every response become READY before IF/ID could take it.

Discarding the wrong-path work cost nothing: the killed response was drained
in the same cycle as the allocation.

## Decision

1. **Direct presentation.** When the slot at `issue_ptr` is FREE, the controller
   presents `next_fetch_pc` on OBI in the same cycle that it allocates the slot.
   - A grant on that edge makes the slot OUTSTANDING at once.
   - Without a grant, the slot becomes a committed QUEUED entry with the same
     address, so the OBI hold rule still holds.
   - The rule applies to every allocation, not only to a redirect target.
     Otherwise the sequential instruction after the target would still pass
     through QUEUED and leave a bubble.
2. **Response bypass, `RESPONSE_BYPASS=1`.** When the oldest live entry is
   OUTSTANDING and its response arrives, `fetch_valid` rises in that cycle, and
   the buffer offers `rdata` to IF/ID. If IF/ID holds, the entry becomes READY
   as before.
3. **`started` bit.** One register is 0 at reset and 1 from the first edge
   after release. Direct presentation needs it.
   - During reset every slot is FREE, so without this bit `req` would rise
     during reset.
   - The alternative, gating `req` with `rst_n`, was rejected. It would reverse
     FOI-D5 (2026-11-01), put a reset net on the output path of the port, and
     treat reset on the instruction port differently from the data port
     (DOC-D3).
   - With the bit, the reset state itself is quiet, and the first request is
     still in the second cycle after release.
4. **Unchanged.**
   - `redirect_target` still reaches only the `next_fetch_pc` register, so EX
     has no combinational path to the bus.
   - `req` and `addr` depend on registered state only.
   - `OBI_OUTSTANDING_MAX` stays 1, and delivery is still oldest-first.
   - Both muxes are in the fetch buffer, selected by registered controller
     state (`present_direct`, `fetch_bypass`).

The change was made and measured in two steps, so that each step's cost in
timing can be told apart: direct presentation first (expected 4 cycles per
redirect), then the bypass (expected 3 cycles per redirect).

## Alternatives

| Option | Redirect cost | Why not selected |
| --- | --- | --- |
| Keep IF-A2 and `RESPONSE_BYPASS=0` | 5 | Redirects take 47 % of CoreMark cycles. |
| Direct presentation only | 4 | Leaves one register on the most common slow path. The Owner chose to make the common case fast. |
| Combinational path from `redirect_target` to `addr` | 2 | It would extend the existing critical path (EX forwarding into the redirect decision into `next_fetch_pc`) out to the port. IF-A2 was made to avoid exactly that. |

## Consequences

- **New timing paths.**
  - `next_fetch_pc` to the `instr_addr` port, through one 2:1 mux.
  - The `instr_rvalid` and `instr_rdata` ports into the IF/ID register, through
    the `fetch_valid` logic and one 2:1 mux. This path also reaches the
    allocation enables, through delivery and `tail_free`.
  - The out-of-context fmax flow has no I/O constraints, so it does not time
    these port paths. A system-level flow must budget them against the
    memory's output delay.
- **Contracts changed.**
  - BASE: IF-A4 header, capacity section, stale-response section,
    verification list.
  - `fetch-controller-unit.md`: ports, state, behavior, timing, checks,
    FCU-D10 to FCU-D13.
  - `fetch-buffer.md`: two inputs, two muxes, FB-D3.
  - `fetch-stage.md`: outputs, timing, checks.
  - `fetch-obi-interface.md`: wording of one reason only.
- **Tests.** Checks that encoded the old timing (target `req` two cycles after
  the redirect, no response bypass) were updated to the new contract. Checks
  of unchanged rules (OBI stability, one outstanding transaction, kill and
  drain, reset, ISA, benchmark CRCs) must still pass unchanged.
- **Revisit** if the memory's response arrives late in the cycle on the target
  platform, so that the bypass mux limits the system clock. The fallback is to
  drop decision 2 and keep decision 1, at 4 cycles per redirect.

## Results

Measured on 2026-11-23 with the bench and ideal memory of the first run. Full
numbers are in the
[2026-11-23 performance report](../reports/2026-11-23-core-performance-redirect.md)
(local-only).

| Metric | Baseline | Step 1 | Step 2 |
| --- | --- | --- | --- |
| Cycles per redirect | 5.000 | 4.000 | 3.000 |
| Trace milestones (alloc, req, fetch, ID, EX) | 1, 2, 4, 5, 6 | 1, 1, 3, 4, 5 | 1, 1, 2, 3, 4 |
| CoreMark/MHz, flags A / B | 0.623 / 0.670 | 0.688 / 0.737 | 0.768 / 0.818 |
| DMIPS/MHz | 0.436 | 0.470 | 0.510 |
| Tightest period met (OOC, xczu7ev-2) | 3.5 ns | 3.0 ns | 3.0 ns |
| LUT / FF at 3.5 ns | 1129 / 426 | 1141 / 427 | 1157 / 427 |

- **Measured behavior.**
  - The milestones held for all 39 redirects of the probes.
  - Retired instruction counts and redirect counts did not change.
  - CoreMark CRCs and Dhrystone results match the baseline.
  - The critical path is still forwarding into the redirect decision. The new
    paths are not on it, and the port paths are not timed (see Consequences).
- **Tests changed to the new contract.**
  - `fetch_controller_unit_cocotb`:
    - The checks after a redirect expect `present_valid` high, because the
      target is presented directly.
    - The pointer-wrap setup was rewritten, because a second redirect can no
      longer empty the ring.
    - The checks with a live OUTSTANDING oldest entry and a response expect
      `fetch_valid` high.
    - New tests: start after reset, direct presentation with and without a
      grant, redirect with a directly presented slot, response bypass.
  - `fetch_stage_cocotb`:
    - The target `req` is one cycle earlier.
    - After-checks are taken with idle inputs, and before-edge offers are
      checked.
    - The no-path test now allows `rvalid`/`rdata` to reach the delivery
      outputs only.
  - `fetch_buffer_cocotb`: new checks for the direct mux and the bypass mux.
  - `core_instr_obi_cocotb`:
    - G4-08g checks the exact cycle.
    - G4-05 now checks the bypass.
- **Testbench defect exposed.**
  - The exploratory harness timed "response limit" as continuous time with any
    transaction outstanding. Core verification section 7 defines it as response
    latency.
  - The redirect idle cycle had hidden this. With direct presentation, tight
    loops kept the port busy for over 200 cycles and tripped the watchdog.
  - The harness now restarts the age when the oldest transaction is answered.
- **Unchanged rules held without test edits:** OBI stability, one outstanding
  transaction, oldest-first delivery, kill and drain, reset, ISA, benchmark
  CRCs.
