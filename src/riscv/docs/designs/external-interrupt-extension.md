# External Interrupt Extension

**Status:** Proposed — R2 freeze candidate; owner-selected CPU behavior, final text/snapshot review pending.
**Owner phía CPU:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Contract revision:** R2 / 2026-10-21 (reset-only amendment).
**Parent:** [BASE và profile matrix](5-stage-baseline-core.md#build-profiles-and-contract-composition).
**Composition:** [CI extension](asynchronous-accelerator-control-extension.md).
**Authority:** [AGENT_POLICY](../AGENT_POLICY.md), [PROJECT_MANAGEMENT](../../../../docs/PROJECT_MANAGEMENT.md).

## Purpose, decision and boundary

R1 moves the owner-selected CSR/MRET/IRQ behavior of 2026-10-03 out of BASE.
Việt approved BASE → CI/polling → IRQ and common-top build selection on
2026-10-15. This document owns machine CSR access, interrupt entry/return,
drain/recheck, return-PC tracking and completion notification/driver behavior.
The supported build enabling this feature inherits BASE_CI as specified by the
single parent profile matrix; IRQ-only is not a shipped build.

The added legally encoded operations are CSRRW, CSRRS, CSRRC, CSRRWI, CSRRSI,
CSRRCI and MRET, in M-mode only. CSR accesses are limited to the eight entries
listed below. Unlisted CSR/SYSTEM operations remain outside the supported
profile; no synchronous illegal-instruction or access-fault trap is added.

IRQ is not a CI dependency. CI retains its management ABI/job lifecycle before
and after IRQ is added. Polling and interrupt are firmware completion modes
on the same IRQ-enabled build, chosen once at driver initialization before any
live job/record, and held fixed for that run. No accelerator-management MMIO
frontend, PLIC, new synchronous exception, WFI, counter, nested-handler hardware,
automatic GPR context save or fixed interrupt latency is introduced.

This is intended CPU-boundary behavior and a requirement on a reviewed source
fixture/environment. It does not accept an SoC interrupt topology, real DMA
path, IP descriptor schema or reset-recovery implementation on the team's
behalf. Project/IP review remains required before real integration. Final
owner text/snapshot review and version control precede functional implementation;
AI assistance in extracting/refining the specification is disclosed at PR/commit.

## Clock, reset and feature absence

Use the common rising-edge clk and active-low rst_n with asynchronous assertion
and synchronized release from the [parent reset contract](5-stage-baseline-core.md#reset-architecture).
R2 inherits [RST-D1](../decisions/reset-strategy.md); it does not change CSR/IRQ
semantics outside reset or accept the concrete shared reset implementation.
CPU/manager/adapter/accelerator share that domain in the first integration
profile; any memory-controller bridge must meet its separate platform contract.
The fixed top exposes irq_external in all builds, but BASE/BASE_CI ignore it
and do not instantiate CSR/IRQ/drain/return-PC logic. Masking MIE in an IRQ build
is firmware behavior and does not remove hardware.

The following reset additions apply only when the IRQ feature is present:

On assertion, without requiring a clock edge, reset additionally clears
interrupt-drain and system-instruction ownership, sets `resume_pc = PC_RESET_VEC`,
and clears `mstatus.MIE`, `mstatus.MPIE`, and
`mie.MEIE`. Fixed CSR fields retain the values defined below. CSR address/data
payload (`mtvec.BASE`, `mscratch`, `mepc[31:2]`, and `mcause`) is unspecified
after reset; software must initialize a value before relying on it. In
particular, firmware installs `mtvec` and a valid handler/stack before enabling
interrupts. An asserted IRQ after reset is visible in `mip.MEIP` but cannot
cause entry while masked. Reset suppresses CSR writes, `MRET`, and interrupt
entry on any edge with reset active; it does not acknowledge accelerator
completion or promise rollback of an accepted MMIO store.

## Machine control and interrupt semantics

### CSR profile and WB effects

| CSR | Address | Supported state and write behavior |
| --- | --- | --- |
| `mstatus` | `0x300` | `MIE[3]` and `MPIE[7]` are writable; `MPP[12:11]=2'b11`; all other bits read zero and ignore writes. |
| `mie` | `0x304` | Only `MEIE[11]` is writable; other bits read zero and ignore writes. |
| `mtvec` | `0x305` | Writable `BASE[31:2]`; `MODE[1:0]=0` (Direct), including after writes requesting another mode. |
| `mscratch` | `0x340` | 32-bit software scratch storage. |
| `mepc` | `0x341` | Writable `[31:2]`; `[1:0]=0`; interrupt entry overwrites the saved return PC. |
| `mcause` | `0x342` | 32-bit software-writable storage; external interrupt entry writes `32'h8000_000b`. |
| `mtval` | `0x343` | Reads zero; writes have no effect. |
| `mip` | `0x344` | `MEIP[11]` reflects `irq_external`; all bits ignore software writes, and other bits read zero. |

CSR read/modify/write semantics follow Zicsr. `CSRRW[I]` replaces the writable
state and suppresses the read when `rd=x0`; `CSRRS[I]` sets operand-selected
bits and `CSRRC[I]` clears them. Register-form set/clear suppresses writes
when the encoded `rs1=x0`, not when a nonzero register happens to contain zero;
immediate-form set/clear suppresses writes when `zimm=0`. Immediate operands
are zero-extended five-bit values. Fixed fields apply the masks above.

All CSR reads and writes occur once at the CSR instruction's WB retirement.
The old value observed there supplies `rd` when required; any CSR update and
the permitted RF write occur on that same edge. EX prepares the operand but
does not read or modify CSR state. In particular, a read of `mip` samples the
IRQ level at this WB event. An invalid or held entry performs no CSR effect.
The common WB-to-ID bypass must use this selected CSR old value for a CSR
register result, although serialization prevents a younger consumer from
overlapping the CSR instruction.

`MRET` has no RF or data-port effect. At its WB retirement, it selects the
current aligned `mepc` as the return target, sets `MIE <- MPIE` and `MPIE <- 1`,
keeps `MPP=2'b11`, and redirects the frontend once. It does not use the EX
branch-redirect event. Both CSR and `MRET` are serialized as specified below;
no CSR bypass network, privilege transition, automatic GPR context save, or
hardware nesting stack is required. The IRQ firmware uses non-nested
handlers and keeps `MIE=0` until `MRET`.

### External IRQ and drain boundary

The additional core input `irq_external` is one active-high, level-sensitive
signal synchronous to `clk`. Source capture, synchronization and aggregation
belong to the environment. Completion-source acknowledgement uses the CI
mapping below; no manager MMIO ACK or separate source-mask register is required.
The CPU supplies no
per-accelerator IRQ input or IRQ-acknowledgement output and does not latch a
sticky completion event. In this M-mode-only profile:

```text
irq_eligible = rst_n && irq_external && mstatus.MIE && mie.MEIE
pipeline_empty = !IF/ID.valid && !ID/EX.valid
                 && !EX/MEM.valid && !MEM/WB.valid
```

The core evaluates eligibility each cycle, including while MEM waits, and
uses the CSR state updated by a retiring CSR or `MRET` in the following cycle.
When eligible and not already draining, it starts registered interrupt drain
and suppresses new IF/ID delivery on that edge. It also stops sequential fetch
allocation and first presentation of uncommitted instruction requests. Every
instruction already in IF/ID, ID/EX, EX/MEM, or MEM/WB is preserved by IRQ
recognition. It completes unless an ordinary older branch/jump flushes it;
the existing stall, forwarding, redirect, and serialization rules still apply.

Drain is not a global pipeline freeze. An unresolved data transaction still
holds the pipeline until its expected response, but already-presented
instruction requests and outstanding responses continue their OBI protocol.
An admitted branch/jump may redirect and flush its younger instructions; an
admitted CI/CSR/MRET may finish serialization. Their fresh redirect target may be
allocated while draining, but no target instruction enters IF/ID during drain.

Entry is permitted only when registered drain is active, the pre-edge pipeline
is empty, and no data transaction remains outstanding. It therefore cannot
share an edge with the last instruction's retirement. Eligibility is rechecked
at that boundary:

- If still eligible, `irq_take_fire` saves `mepc <- resume_pc`, writes
  `mcause <- 32'h8000_000b`, sets `MPIE <- MIE`, clears `MIE`, keeps `MPP=2'b11`,
  and redirects to `mtvec.BASE`. It clears drain ownership and creates no
  instruction-retirement event. `mtval` remains zero.
- If no longer eligible, drain is cancelled without CSR changes or trap
  entry. Correct live frontend entries are retained; normal delivery and
  request issue resume in the following cycle. This covers an admitted CSR
  masking IRQ and an admitted CI ACK removing the source.

Every surviving admitted store and MMIO read/write has completed and retired
before entry; flushed wrong-path instructions create no effect. Already
accepted transactions are not cancelled or replayed. This
establishes a precise interrupted-program boundary after drain without making
WB a universal commit point for ordinary stores. Synchronous fault recovery
or interrupt entry before full drain would require a different contract.

There is no fixed interrupt-latency guarantee. Data grant/response delays can
delay drain, and an irrevocable instruction request/response can delay handler
fetch after entry. The environment must eventually complete legal requests;
this profile adds no timeout/abort mechanism to the core. A level still high
when `MRET` restores `MIE` becomes eligible again and may cause another entry
before any instruction at the return target executes.

### Return-PC ownership

`resume_pc` records the next instruction address after the live instructions
admitted to the pipeline; it is not a retire PC or the Prefetch Unit's
`next_fetch_pc`. Its updates use this priority:

1. Reset: `PC_RESET_VEC`.
2. Interrupt entry: `mtvec.BASE`.
3. Retiring `MRET`: its `mepc` return target.
4. EX branch/jump `redirect_fire`: `redirect_target`.
5. A live instruction accepted into IF/ID: that instruction's `pc + 4`.
6. Otherwise hold.

Fetch allocation, grant, and response alone never change `resume_pc`. Redirect
wins over any same-edge candidate IF/ID delivery. During drain, a taken branch
or jump replaces an earlier sequential continuation with its actual target;
otherwise the continuation remains after the last admitted instruction.
Only after the pipeline is empty is this value used as interrupt `mepc`. This
avoids carrying PC/next-PC through MEM/WB and avoids skipping prefetched but
unexecuted instructions.

The architectural definitions referenced by this bounded profile are
[Zicsr 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicsr.html),
[RV32I 2.1 memory ordering](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html),
and Machine-Level ISA 1.13 in the
[privileged manual, release 20260120](https://docs.riscv.org/reference/isa/v20260120/_attachments/riscv-privileged.pdf).
The omitted behavior above prevents a whole-architecture compliance claim.

## Pipeline composition and overrides

### Decode, operand and result extensions

ID remains the only architectural decoder. It produces a distinct CSR kind
with 12-bit CSR address, replace/set/clear operation, read/write intents and
register/immediate source selection, or an MRET kind. Raw instruction/function
bits do not cross ID/EX or get decoded again. Register CSR uses rs1_used=1 and
rs2_used=0; immediate CSR and MRET use neither GPR source. Immediate CSR uses
zero-extended zimm[4:0] in the canonical immediate, not a sign-extended I-immediate.
Encoded-zero write suppression is an intent separate from source qualification.

EX prepares the forwarded rs1 value or zero-extended zimm and carries it with
CSR address/operation/intents through EX/MEM and MEM/WB. EX does not read CSR,
produce a CSR old-value result or redirect MRET. CSR is not an EX/MEM ready
forwarding source. At CSR retirement, old CSR value is an additional late WB
source; RF write still uses parent rd!=x0 gating and selected wb_data.
CI result, CSR old value, load result and ordinary ex_result are mutually
exclusive semantic selections. CSR/MRET never assert ci_cmd_valid or issue a
CPU data request. FENCE remains an ordinary BASE non-writing instruction.

### Shared serialization and priority

CSR/MRET use the [serialized-control protocol](asynchronous-accelerator-control-extension.md#61-serialized-control-protocol)
without a second algorithm or overlapping younger instruction. The protocol
is defined independent of CSR/IRQ; IRQ adds only the completion effects and
frontend rules below. A retiring MRET reads current mepc and updates mstatus
in WB; CI-only WB wait still obeys sole-live/no-data-outstanding ownership.

Effective priority when IRQ is enabled:

1. Reset (asynchronous assertion, synchronized release).
2. irq_take_fire at an empty registered-drain boundary.
3. Retiring MRET and its WB redirect.
4. Unresolved MEM wait from BASE.
5. CI-only WB wait from the CI contract.
6. EX branch/jump redirect_fire.
7. Shared serialized-control admission/progression.
8. BASE load-use hazard.
9. Normal advance and qualified IF availability.

IRQ recognition/drain ownership updates are independent of the hold rows:
MEM wait or CI WB wait must not prevent drain starting. New IF/ID delivery is
suppressed on drain-start and throughout drain, but every surviving admitted
CI/CSR/MRET and ordinary instruction can complete under its own protocol.
Neither a waiting CI nor a waiting CSR/MRET is killed merely by IRQ recognition.
An older ordinary EX redirect may still kill wrong-path waiting work.

| Override / event | Stage/ownership effect | Retirement / externally visible effect |
| --- | --- | --- |
| Reset asserted | Asynchronously clear parent, CI and IRQ validity/control ownership. | No command, RF/CSR write, MRET or IRQ entry on an edge with reset low. |
| irq_take_fire | All pipeline stages already empty; clear drain and freshly select mtvec target. | Trap CSR/PC updates only; no instruction retirement. |
| MRET WB retirement | Serialized owner leaves WB; no younger admission on that edge; freshly select return target. | Exactly one return/CSR effect; no CI command/data access. |
| CI WB wait | Hold only live CI at WB, all other stages invalid; data_outstanding=0. | No CI effect until command_fire; drain can start but not enter. |
| CSR WB retirement | Read/update under decoded intents, selected old value for rd. | Exactly once, no CI command; enables affect eligibility next cycle. |
| Drain proactive freeze | No new sequential allocation, first presentation of uncommitted IF request or IF/ID delivery. | Mandatory existing OBI grant/response progress continues. |
| Qualified EX/MRET/trap redirect while draining | May allocate its fresh target under parent recovery rules; still no new IF/ID delivery. | Redirect does not cancel accepted OBI ownership. |

CI handshake retires the last CI before an IRQ entry is possible. Entry needs
pre-edge empty pipeline, so it cannot share that retirement edge. Its result
and manager side effect occur exactly once, with no replay after MRET. If CI
ACK clears the last source during drain, eligibility recheck may cancel entry;
if another terminal slot remains, entry proceeds normally.

### Frontend and return-PC integration

The parent fresh-target/stale-entry recovery rules apply to EX redirect,
retiring MRET and irq_take_fire. Every pre-redirect fetch entry not admitted
to preserved pipeline work becomes stale regardless of matching PC. Responses
and already-presented requests drain, not cancel; a fresh target is allocated
using the registered PC path, not a combinational trap-to-OBI request path.
No extra next-PC payload must be carried through MEM/WB.

On MRET retirement, serialized ownership releases only for the following cycle;
that cycle can immediately recognize still-eligible IRQ and suppress return-target
admission. MRET/IRQ do not bypass parent fetch capacity, executable-region or
registered-MEM first-presentation restrictions. There is no IRQ-response FIFO
or general decoupled WB mode introduced by this extension.

## Completion source mapping

The authoritative terminal lifecycle/quiescence is the [manager contract](asynchronous-accelerator-control-extension.md#8-manager-adapter-and-concurrent-events).
For each target, SUCCESS or ERROR is persistent until successful ACK:

```text
terminal[i] = slot[i] == SUCCESS || slot[i] == ERROR
manager_irq = terminal[TinyLLM] || terminal[Dilithium]
```

The environment supplies this synchronous level to irq_external. There is no
second independently sticky pending latch or per-target mask in R1. QUERY
identifies sources without clearing; ACK clears only its terminal slot. Two
simultaneous completions must both survive, and ACK of one must not clear the
other. No MMIO source/status/ACK register is required to ship this profile.
Terminal publication must already imply output visibility/quiescence under the
CI memory contract before it can raise a consumable interrupt source.

mip writes cannot clear a source. Propagation can lag ACK; handler re-entry
with no newly terminal target is valid. A QUERY that sees ACTIVE just before
completion does not lose it: persistent terminal level requests service later.
If sources other than these two accelerators are added, the project must define
their identification/service path; QUERY is not a universal interrupt controller.

## Firmware completion modes and ownership

Application uses the same CI driver API and record/buffer lifetime in both
modes. Install stack, GPR-save convention, mtvec and initialized driver records
before enabling MEIE/MIE. Modes are selected only at initialization after
coordinated reset, with no live jobs or completion records:

- POLLING: leave external completion interrupt masked with MEIE=0; collect via
  QUERY/ACK. IRQ hardware/terminal state still exists, and no ISR owns completion.
- INTERRUPT: configure/enable MEIE/MIE after handler/context setup. The driver
  handler owns hardware collection; application consumes software records.

No runtime switch between modes while the run is active, and no feature
discovery CSR is added. A firmware build for BASE_CI never accesses these CSRs.
Mode comparison uses the same IRQ-enabled hardware, clock, manager, adapters,
slot semantics and workload. Hardware cost comparison uses different profiles
and must be reported separately.

### Critical sections and ISR handoff

In IRQ-enabled builds, consistently protect foreground/handler record and CI
bookkeeping with short save/disable/restore MIE sections and compiler barriers.
Restore only the saved MIE bit, not an old entire mstatus word or unconditional
enable; nested sections preserve an originally zero MIE. Handler stays
non-nested, MIE=0 until MRET. Do not poll/retry BUSY or wait for terminal while
interrupts are disabled. Control response is eventually required, not fixed-cycle.

Submit installs context/OWNED before issuing CI, even if job completes before
software next executes. Rejection returns only the newly reserved record to
FREE. ISR collection is strictly:

1. QUERY each target and require terminal observation/acquire before collecting.
2. Copy completion snapshot/class and existing context into the still-OWNED record.
3. ACK hardware; check the returned control status is ACKED.
4. Only then publish record COMPLETED for foreground consumption.

Hardware ACK may make its slot IDLE, but API remains BUSY until application
consumes the old software record. Copy/ACK/publication are software steps;
COMPLETED is not magically stored on the hardware ACK edge. A failed ACK
retains OWNED and prevents consume/new submit; report protocol failure and
follow coordinated recovery, never silently free ownership.

Foreground consume is synchronized and preserves compiler ordering so output
loads cannot move before observing the published completion. The QUERY acquire
performed by ISR must pass through this software handoff; after ACK the
application cannot recover it by querying the now-IDLE hardware slot. volatile
alone is insufficient. BASE_CI's helper has no CSR effects as defined by its
polling driver contract.

A handler services terminal slots it observes and then returns, tolerating
stale IRQ level and subsequent re-entry. It does not ACK ACTIVE/IDLE to force
IRQ low or busy-loop until a delayed IRQ wire drops. Save/restore every GPR
used by the handler; hardware provides no automatic GPR context save.

## Representative traces

- IRQ eligible while CI waits at WB: drain starts and blocks new admission;
  manager eventually responds, CI retires/effects once; only a later empty
  pre-edge can take IRQ after recheck. Job/adapter progress continues throughout.
- CI ACK in drain: ACKED clears last terminal source on its retirement edge;
  the following empty recheck can cancel entry. Another live source preserves
  eligibility. No instruction is replayed or store rolled back.
- Simultaneous target completions: both slots terminal and one aggregate level;
  service/ACK one preserves the other. A stale aggregate level after both ACKs
  may yield another handler entry whose QUERY finds no terminal work.
- ISR snapshot → ACKED → later software publish → foreground consume: record
  remains OWNED until publish and COMPLETED until consume; buffers are not
  reused merely because hardware is IDLE.

## Verification obligations and gate

All checks are planned evidence, not existing test results. Inherit the BASE
objective acceptance/harness evidence rules and CI regression, then add:

1. **CSR and serialized return.** Cover all six CSR instructions on the listed
   supported state, register and immediate operands, encoded-zero versus
   zero-valued-register write suppression, `rd=x0` read suppression, CSR old
   value in `rd`, masks/fixed fields, and read-only external pending state.
   Cover dependencies from older ALU/load producers into CSR operands, waiting
   behind delayed MEM completion and old WB retirement, wrong-path CSR/MRET
   flushing, and the absence of younger admission through WB retirement.
   Check exactly-once atomic CSR/RF updates, back-to-back serialized CSR
   instructions, and MRET's aligned target and MIE/MPIE effects.
2. **External interrupt drain and recovery.** Cover each enable mask, pending
   IRQ before enable, drain with occupied stages, a data grant/response wait,
   and empty pipeline during an instruction-fetch gap. Cover IRQ recognition
   during MEM hold and drain-start suppression of candidate IF/ID delivery.
   Check that a held old WB and an accepted store both finish before entry,
   with no lost or replayed effect. Check drain completion after a taken
   branch/jump, including a redirect on the MEM response edge; `mepc` must use
   the actual continuation rather than the advanced prefetch PC. Cover drain
   cancellation both when IRQ drops and when an admitted CSR masks it;
   admitted CI ACK may also remove pending work. Check trap
   CSR values, no retirement on the entry edge, MRET return, and re-entry with
   IRQ still high before a return-target instruction is admitted. Exercise
   trap/return recovery with READY, OUTSTANDING, presented QUEUED, and
   unpresented QUEUED fetch entries, including simultaneous grant/response
   and no reuse of an entry whose PC happens to match the target.
3. **CI/IRQ composition.** Cover drain starting during CI WB wait, exactly-once
   command/retirement, QUERY observing and ACK clearing a source during drain, eligibility
   cancellation and preserved other-target terminal state. CSR/MRET must never
   issue ci_cmd_valid or data requests. FENCE remains ordinary pipeline flow.
4. **Source and driver races.** Cover masked persistent terminal, immediate
   completion after SUBMIT, simultaneous two-target completion, ACTIVE QUERY
   followed by completion, stale IRQ after ACK, ACK error and protected foreground
   consume. Verify copy-before-ACK and publish-only-after-ACKED, MIE restoration,
   GPR save/restore and compiler handoff in generated firmware.
5. **Configuration and mode checks.** In BASE/BASE_CI, assert irq_external without
   any PC/admission/retirement change and prove IRQ/CSR/resume_pc hardware absent
   at elaboration/synthesis structure. In BASE_CI_IRQ run both polling and IRQ
   firmware modes on the same hardware with identical CI/job semantics. Masking
   interrupts is not evidence of removing feature hardware.
6. **Reset/completion.** Cover reset with CI handshake, CSR/MRET, drain and
   terminal events pending, including assertion between edges or while the
   clock is stopped and synchronized release after restart. Check IRQ enables,
   drain/serialized ownership and resume_pc reset without an edge. Reset wins
   all core effects; source/adapter memory
   recovery and late-epoch traffic obey CI coordinated-reset obligations.

The IRQ/composition gate is cumulative: BASE correctness → CI/polling
correctness → IRQ correctness. Directed tests/checkers derive expectations from
owner-reviewed contracts, not DUT logic. Core-fixture pass is not real IP,
DDR visibility, FPGA timing/resource/power or performance proof.

## Freeze and shared-review boundary

The CPU decisions above are selected, including clock-synchronous level,
drain/recheck, WB CSR/MRET and resume_pc. No manager MMIO frontend or unselected
interrupt controller is implied. Final owner text/snapshot review is pending;
this document records decisions rather than independently accepting a spec.
After freeze, semantic changes require owner approval, a bundle revision
update and matching regression obligations.

The project must still accept concrete source wiring, real-IP descriptors,
shared-memory publication, clock/reset distribution and old-epoch recovery.
The common-clock profile does not itself prove DDR-bridge visibility or reset
quiescence. These are integration gates, not reasons to add IRQ back to BASE
or require CI to use CSR before the IRQ feature exists.
