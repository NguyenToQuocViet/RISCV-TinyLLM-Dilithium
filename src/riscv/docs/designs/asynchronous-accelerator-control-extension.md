# Asynchronous Accelerator Control Extension — Contract and Roadmap

**Status:** Proposed — R2 freeze candidate; owner-selected CPU/ABI decisions, final text/snapshot review pending.
**CPU owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Contract revision:** R2 / 2026-10-21 (reset-only amendment; ABI v1 unchanged).
**Parent:** [BASE and profile matrix](5-stage-baseline-core.md#build-profiles-and-contract-composition).
**IRQ composition:** [External Interrupt Extension](external-interrupt-extension.md).
**Authority:** [AGENT_POLICY](../AGENT_POLICY.md), [PROJECT_MANAGEMENT](../../../../docs/PROJECT_MANAGEMENT.md).

Việt selected ABI v1 on 2026-10-13 and approved the R1 restructuring on 2026-10-15:
BASE without IRQ → CI operating through polling → IRQ addition. This decision
supersedes the 2026-10-03 assumption that the baseline already includes CSR/IRQ.
The CPU contract and ABI choices are owner-selected; final document/snapshot
review remains pending. Manager, adapter and platform requirements do not by
themselves constitute an accepted SoC architecture. AI assisted reasoning,
drafting and review; disclose this assistance in the PR/commit under AGENT_POLICY.

R2 inherits the owner-selected [RST-D1 reset amendment](../decisions/reset-strategy.md):
asynchronous assertion, synchronized release and unchanged selective reset.
The amendment does not accept shared SoC implementation or the rest of this
Proposed extension independently of its final review.

## 1. Objectives and limits

CI manages asynchronous jobs: SUBMIT accepts or rejects work, QUERY observes
state, and ACK reclaims a terminal completion. After acceptance, the accelerator
runs independently; a management instruction does not wait for compute runtime.
The management ISA is shared, while each accelerator has its own descriptor/output
ABI. BASE_CI requires no CSR, MRET, external IRQ, drain or resume_pc mechanism.

Profiles and operation counts are defined only by the parent matrix. BASE_CI
uses polling. BASE_CI_IRQ uses the same CI semantics and lets firmware choose
polling or interrupt completion at driver initialization. The mode remains fixed
throughout the run; there is no runtime feature discovery. Shipping CI does not
require a manager MMIO frontend.

Assumptions: RV32 little-endian, single-hart bare-metal, without caches/coherence.
There is one hardware slot and one software completion record per target; both
targets may run concurrently. CPU, manager, adapters and accelerators share one
clock domain in the initial profile. A memory-controller bridge in a separate
clock domain must satisfy the platform contract. No frequency or fixed latency
is promised.

Out of scope: compute-kernel CI, OoO/ROB, multiple jobs per target, hardware
handles, software FIFO/scheduler, per-job abort/watchdog, OS/multihart, compiler
backend, automatic offload, new synchronous CPU traps, RoCC/XIF compatibility,
and performance superiority. Dual CI/MMIO ingress and runtime frontend switching
have not been selected.

## 2. Authority and environment

The CPU owner owns decode, serialization, prepared operands, WB handshake/result
and feature absence under the parent profiles. The command port is a CPU-boundary
requirement; an independent fixture can implement this contract to verify the CPU.
SoC manager/adapter implementation, memory map, DMA/error policy, per-IP ABI,
clock/reset and visibility proof require project/IP-owner review before real
integration. Project-level documents will own accepted shared designs; reference
them instead of maintaining a second normative copy in this subtree.

## 3. Decision ledger and consequences

Q1–Q27 record owner selections from 2026-10-13. R1, dated 2026-10-15, supersedes
the feature split in Q3/Q7/Q25: BASE has no IRQ/CSR; CI operates before IRQ;
serialization does not depend on CSR; MIE critical sections apply only to an
IRQ-enabled build. The table records current choices and their consequences;
shared implementation still requires review.

| Q | Choice | Consequence / trade-off |
| --- | --- | --- |
| 1 | CI manages asynchronous jobs. | Instruction runtime is a control transaction, not compute runtime. |
| 2 | Shared management ISA; accelerator-specific descriptors. | Microarchitecture changes need not change the ISA if descriptor ABI and semantics are preserved. |
| 3 | BASE → CI/polling → IRQ addition; firmware selects completion mode. | Separates command/completion correctness from interrupt races. |
| 4 | One live slot per accelerator; both accelerators may run concurrently. | No multi-job queue; memory bandwidth may still cause contention between the IPs. |
| 5 | Try-submit returns BUSY without job side effects. | Software retries outside the critical section; the instruction does not wait for a free slot. |
| 6 | Two GPRs: accelerator ID and descriptor pointer. | No dependence on configuration from a previous CI; requires shared-memory/lifetime contracts. |
| 7 | Serialize every CI independently of CSR/IRQ; result/effect at WB. | Simplifies exactly-once proof; adds control overhead and temporarily blocks admission. |
| 8 | Use accelerator ID, without a hardware handle. | No token distinguishes stale jobs; the driver must exclusively own the lifecycle. |
| 9 | Non-destructive QUERY; separate ACK. | Supports repeated observation/debugging; releasing a slot requires an additional operation. |
| 10 | The driver owns jobs; the ISR saves completion before ACK. | Applications do not issue raw ACK; context/record must be protected. |
| 11 | API remains BUSY until the application consumes the previous completion. | Hardware may be IDLE while the driver remains busy; no software FIFO is needed. |
| 12 | ACCEPTED receives a pointer/reserves a slot; descriptor validation is asynchronous. | ACCEPTED does not guarantee a valid job; later errors still produce a completion requiring ACK. |
| 13 | Each adapter fetches/validates its own descriptor. | The manager does not know the IP's descriptor format or native control. |
| 14 | Manager in the SoC; generic command port on the core. | The core holds no long-running job state; the shared interface requires team review. |
| 15 | SUBMIT release; terminal QUERY acquire. | Compiler and platform share ordering obligations; FENCE does not complete DMA. |
| 16 | CI first; MMIO later for comparison. | No assumption of simultaneous ingress or runtime switching. |
| 17 | Argument/state errors return status, without new CPU traps. | Distinguishes pre-acceptance control errors from post-acceptance job errors. |
| 18 | Coordinated reset; handle old transactions before restart. | Old jobs are discarded without rolling back partial writes; CPU-only reset with a live job is out of scope. |
| 19 | Borrow descriptors/buffers until the application consumes completion. | No copying; the caller is responsible for lifetime, access rights and aliasing. |
| 20 | C API with centralized inline-asm bindings. | No compiler backend changes; generated code and compiler barriers must be checked. |
| 21 | No per-job watchdog/abort initially. | A hung job must not be reported as terminal; recovery depends on actual quiescence. |
| 22 | IRQ is the OR of terminal slots; QUERY/ACK through CI. | Slot state is the sticky source; no separate pending latch requires another ACK. |
| 23 | One synchronous handshake at WB. | Manager effect and CI retirement occur at the same edge; BUSY also retires without accepting a job. |
| 24 | Shared clock in the initial profile. | Reduces CDC work; frequency is constrained by shared timing; separate clocks require a new contract. |
| 25 | Only IRQ-enabled builds use save/disable/restore MIE; CI-only firmware emits no CSR instructions. | Prevents ISR interference with bookkeeping; no waiting for a job/BUSY with interrupts disabled. |
| 26 | `rd` contains common status/state/error class; IP details remain in memory. | Querying a failed job may still be a successful control operation; the ISA is independent of IP payload. |
| 27 | Separate emulated-control and real-IP/FPGA gates. | CPU development is independent; fixture proof does not replace real-system proof. |

## 4. Composition and data paths

```text
Application → C API / driver → CI binding
                              ↓
Five-stage CPU → WB control port → SoC job manager
                                      ├→ TinyLLM adapter → TinyLLM
                                      └→ Dilithium adapter → Dilithium
CPU OBI data path ───────────→ shared-memory/interconnect ← adapter memory paths
```

The command port carries only operation, ID, pointer and control result.
Descriptors, inputs and outputs use memory paths; tensors and keys do not pass
through this port. The CPU does not provide a new DMA engine. The manager owns
slot state and dispatch ownership; each adapter owns native configuration,
descriptor fetch/validation and all memory accesses belonging to its job.

An ACTIVE slot includes waiting for dispatch, descriptor fetch/validation and
computation. The two adapters have independent lifecycles; shared-memory
arbitration and ordering belong to the interconnect. Slot count alone does not
establish concurrent throughput.

## 5. Binary ABI v1 — selected by the RISC-V owner

Việt selected the complete ABI in this section on 2026-10-13: three operations
and a simple layout give bindings and decode a clear contract before
implementation. The ABI carries no IP-specific payload; the driver accepts
serialization overhead and separate QUERY/ACK operations. ID mapping,
descriptor-memory accessibility and adapter error mapping require shared review
for SoC use; the concrete address map remains undecided. Changes to these
encodings, layouts or semantics must return to the owner before implementation.

### 5.1 Instruction encoding and arguments

The ABI uses three R-type instructions in `custom-0 = 7'b0001011 = 0x0b`, with
`funct7=0`. RISC-V reserves custom-0/custom-1 for custom extensions; the R-type
layout follows the [RISC-V opcode map](https://docs.riscv.org/reference/isa/v20240411/unpriv/rv-32-64g.html).
The names below are semantic names, not yet toolchain-supported mnemonics.

| Operation | `funct3` | `rs1` value | `rs2` | `rd` |
| --- | --- | --- | --- | --- |
| `ACC_SUBMIT` | `000` | 32-bit unsigned accelerator ID | Value is a 32-bit byte-address descriptor pointer. | Result word |
| `ACC_QUERY` | `001` | 32-bit unsigned accelerator ID | Encoded register must be `x0`; no second operand is used. | Result word |
| `ACC_ACK` | `010` | 32-bit unsigned accelerator ID | Encoded register must be `x0`; no second operand is used. | Result word |

IDs are `0 = TinyLLM` and `1 = Dilithium`; all other values return BAD_ID.
Compare all 32 bits; do not truncate an ID so it aliases a valid target.
`rs1=x0` supplies ID 0. `rd` may alias `rs1`/`rs2`: operands are prepared before
WB writes the result. `rd=x0` suppresses only the RF write; the command and
ordering still occur. The driver uses a real destination to determine whether
submission succeeded.

Other opcode/function patterns, including QUERY/ACK with encoded `rs2 != x0`,
are outside ABI v1 and must not decode as management commands. This contract
adds no illegal-instruction trap. CPU behavior outside supported encodings
remains subject to the baseline's limits.

Cheap pointer check: the descriptor must be 4-byte aligned and its first word
must lie entirely within platform-permitted shared descriptor memory. Range
checking must not overflow. The concrete address map/range requires project
review. The adapter checks additional descriptor alignment or content after
acceptance. A rejected SUBMIT must not fetch a descriptor, read input or cause
native IP side effects.

### 5.2 Result word

The result always contains a **pre-edge** target snapshot and operation status:

| Bits | Field | Meaning |
| --- | --- | --- |
| `[7:0]` | `control_status` | Result of SUBMIT/QUERY/ACK. |
| `[15:8]` | `job_state` | Slot state before the command edge; UNAVAILABLE for an invalid ID. |
| `[23:16]` | `completion_class` | NONE unless state is ERROR; a common error class for ERROR. |
| `[31:24]` | Reserved | Hardware returns zero; software assigns no other meaning in v1. |

| Field | ABI v1 values |
| --- | --- |
| `control_status` | `OK=0`, `ACCEPTED=1`, `ACKED=2`, `BUSY=3`, `BAD_ID=4`, `BAD_PTR=5`, `NOT_READY=6`, `EMPTY=7` |
| `job_state` | `IDLE=0`, `ACTIVE=1`, `SUCCESS=2`, `ERROR=3`, `UNAVAILABLE=255` |
| `completion_class` | `NONE=0`, `DESCRIPTOR=1`, `MEMORY_ACCESS=2`, `EXECUTION=3`, `OTHER=255` |

ERROR must have a class other than NONE; SUCCESS must have NONE. The error
class remains available even when an invalid descriptor/output prevents writing
detailed metadata to memory. MEMORY_ACCESS does not require an additional CPU
OBI error pin or invent fault detection absent from the platform; it is used
only when the adapter/platform actually detects and safely handles that error.
Per-IP details and partial-output validity belong to the separate
descriptor/output ABI.

QUERY on an ERROR slot returns `control_status=OK`, `job_state=ERROR`: state
observation succeeds, while the job failed. SUCCESS means the operation completed
under the IP contract; for example, verify-false may be valid output from a
SUCCESS job. Numeric codes do not represent cycle counts, job handles or
hardware revisions.

### 5.3 Operations and state transitions

SUBMIT checks in this order: **ID → occupied slot → cheap pointer → acceptance**.
All results use pre-edge state; the table lists post-edge state separately.

| Operation / precondition | `control_status` | Post-edge state | Job side effect |
| --- | --- | --- | --- |
| Any operation, nonexistent ID | BAD_ID | Unchanged | None; result state UNAVAILABLE, class NONE. |
| SUBMIT, target ACTIVE/SUCCESS/ERROR | BUSY | Unchanged | Neither accept nor retain the request for later. |
| SUBMIT, IDLE, pointer check fails | BAD_PTR | IDLE | None. |
| SUBMIT, IDLE, valid pointer | ACCEPTED | ACTIVE | Latch pointer, reserve slot, assume responsibility for the job. |
| QUERY, valid ID | OK | Unchanged | Read state/class; terminal observation has acquire semantics. |
| ACK, ACTIVE | NOT_READY | Unchanged by ACK | No cancellation/abort. |
| ACK, IDLE | EMPTY | IDLE | None. |
| ACK, SUCCESS/ERROR | ACKED | IDLE | Reclaim terminal completion and release the hardware slot. |

Successful SUBMIT returns pre-state IDLE although next-state is ACTIVE.
Successful ACK returns pre-state SUCCESS/ERROR although next-state is IDLE.
Only a QUERY returning terminal state provides the job's acquire semantics;
state/class observed in another operation's result does not replace the
driver's QUERY before reclaiming output.

Firmware and hardware must select the same ABI v1 at build time. There is no
discovery, version negotiation or runtime encoding change. Changes to the binary
ABI/ID mapping require review and corresponding binding updates.

## 6. CPU pipeline refinement

### 6.1 Serialized-control protocol

This is the sole definition of the CI serialization protocol; the IRQ extension
references the same protocol for CSR/MRET. It requires no CSR or IRQ state in
BASE_CI.

A live serialized instruction in IF/ID blocks new IF/ID delivery. Hold it there
while older ID/EX, EX/MEM or MEM/WB stages remain valid; older work progresses
under the parent rules. When the parent allows pipeline advance but the
serialized owner cannot yet issue, ID/EX receives an invalid bubble rather than
a duplicate instruction. MEM wait retains the previous stages at higher
priority. An older EX branch/jump may flush a wrong-path owner; that flush
releases ownership without effects.

Issue into ID/EX only when all three older stages are empty pre-edge. At the
issue edge, IF/ID becomes invalid and accepts no replacement instruction.
Ownership blocks younger instructions through WB retirement; admission may
resume only from the following cycle. Neither the Fetch Buffer nor instruction
OBI must be empty; prefetch follows capacity and BASE MEM rules. All
already-presented requests/responses continue progressing; serialization does
not freeze the memory fabric or adapters. IRQ-specific admission/redirect
exceptions, when the feature is present, are defined in the IRQ contract.

### 6.2 Decode, operands and WB

ID is the only decoder and produces semantic operation/source/destination/result
intent. SUBMIT has rs1_used=1, rs2_used=1; QUERY/ACK have rs1_used=1, rs2_used=0.
EX prepares the forwarded target/pointer. Prepared operation, operands, rd and
write intent travel through EX/MEM and MEM/WB to WB; do not carry/re-decode the
raw instruction. CI issues no OBI data request, causes no EX redirect and has
no RF result ready in EX/MEM.

WB selects ci_cmd_result only at the command handshake. rf_write requires a
destination other than x0; a held owner does not write, retire or forward a
valid CI result. rd may alias a source because operands are retained before
writeback. CI does not redirect PC; IRQ return-PC tracking is absent in BASE_CI.

### 6.3 Pipeline overrides

The rows below extend BASE arbitration: reset, MEM wait and older EX redirect
retain parent priority; serialized control precedes load-use/ordinary admission.
CI-only WB wait precedes ordinary advance. It cannot coexist with a MEM owner
or EX redirect because the CI must be the sole live instruction.

| Event | MEM/WB next | EX/MEM next | ID/EX next | IF/ID next | CI retirement |
| --- | --- | --- | --- | --- | --- |
| Waiting serialized control, older work still live | BASE older progression | BASE older progression | Invalid bubble | Hold owner | No CI at WB |
| Issue, older stages empty pre-edge | Invalid | Invalid | Capture decoded owner | Invalid | 0 |
| Serialized owner still in EX/MEM, not yet owning WB | Capture current MEM output | Capture current EX output | Invalid | Invalid | Per live WB owner |
| CI at WB, ready=0 | Hold CI | Invalid | Invalid | Invalid | 0 |
| CI at WB, ready=1, reset inactive | Invalid | Invalid | Invalid | Invalid | ci_cmd_fire |

A CI at WB must be the sole live instruction, with data_outstanding=0. This is
a limited WB-backpressure exception, not a general WB stall alongside a MEM
owner. Keep data_rready=1; no additional data-response buffer is needed. BASE
ordinary data-response/retirement behavior is unchanged. Reset clears
serialization/command ownership and wins over command fire; inactive payloads
need not be reset.

## 7. Native CPU–manager control port

The port uses a common rising edge and active-low `rst_n` with asynchronous
assertion and synchronized release under the [BASE reset contract](5-stage-baseline-core.md#reset-architecture).
The CPU-boundary manager fixture must share this conditioned reset; the real
manager/adapter reset distribution remains subject to project/IP-owner review.
It is the profile's native port and claims no RoCC/XIF compatibility. There is one control
transaction at a time, without request/response queues or a separate commit phase.

| Signal | Direction relative to CPU | Width | Validity / meaning |
| --- | --- | --- | --- |
| `ci_cmd_valid` | Out | 1 | A live CI owns WB and is eligible to progress apart from manager readiness. |
| `ci_cmd_op` | Out | 2 | SUBMIT=0, QUERY=1, ACK=2; 3 is invalid. |
| `ci_cmd_target` | Out | 32 | Prepared accelerator ID; meaningful when valid. |
| `ci_cmd_desc` | Out | 32 | Prepared pointer for SUBMIT; zero for QUERY/ACK. |
| `ci_cmd_ready` | In | 1 | The manager can return a result and perform the operation at this edge. |
| `ci_cmd_result` | In | 32 | Section 5 result; meaningful when valid && ready, sampled at the edge. |

```text
ci_cmd_fire          = rst_n && ci_cmd_valid && ci_cmd_ready
CI_wb_retire_fire    = ci_cmd_fire
CI_rf_write_fire     = ci_cmd_fire && rd != x0
job_accept_fire      = ci_cmd_fire && op == SUBMIT && status == ACCEPTED
job_ack_fire         = ci_cmd_fire && op == ACK && status == ACKED
```

The CPU must not make `valid` depend on `ready`, `ci_cmd_fire` or the CI's own
retirement result. The manager does not require prior CPU retirement before
asserting ready. While valid && !ready, the CPU holds valid/op/target/desc and
the WB owner stable until handshake or coordinated reset. The manager has no
command side effect before fire. The result may change before readiness as the
slot progresses; it must reflect pre-edge state at the handshake, without
requiring a response latched from the first cycle.

A control fire returning BUSY/BAD_ID/BAD_PTR/NOT_READY/EMPTY still retires the CI
exactly once. It does not imply job acceptance. The manager must not wait for
compute completion, a free slot or software ACK to respond to a rejected control
operation. The control implementation and environment must guarantee eventual
response; no cycle count is fixed. Valid control/publication backpressure must
not become blocking for accelerator runtime. A hung port may hang the CPU;
this violates the progress obligation, and no hardware watchdog hides it.

CI command side effects occur only at `ci_cmd_fire`; they do not wait for the
application to read `rd`. The manager also progresses independently through
start, terminal and reset events. Ordinary instructions retain the baseline
retirement contract.

## 8. Manager, adapter and concurrent events

### State ownership and adapter boundary

Each target has slot state, a descriptor pointer, dispatch ownership and a
terminal class. State/control ownership resets to IDLE/not dispatched; pointers
and payloads need not be reset if validity gating prevents their use.
SUCCESS/ERROR remain stable until ACK; QUERY does not clear them. Neither ACTIVE
nor terminal slots may be reused.

The manager retains the pointer at accepted SUBMIT, even before the adapter
accepts start. An adapter that is not ready does not make the CPU wait for
computation: the slot is already reserved and dispatch progresses independently.
The proposed boundary for each adapter is:

| Channel | Payload / transfer | Obligation |
| --- | --- | --- |
| Start | `start_valid`, `start_ready`, 32-bit descriptor pointer; handshake for an ACTIVE slot not yet dispatched. | Manager holds pointer/valid while waiting; adapter accesses descriptor/input only after start acceptance. |
| Terminal | `terminal_valid`, `terminal_ready`, SUCCESS/ERROR and generic class; handshake for a dispatched ACTIVE slot. | Adapter holds terminal payload while waiting; exactly one terminal per job, only after quiescence/publication. |

Channel names describe a proposed interface, not an existing RTL mapping. The
manager records dispatch ownership at the start handshake; start is not replayed.
Terminal may be accepted only when the pre-edge slot is ACTIVE and dispatch
occurred at an earlier edge. A fixture/native adapter finishing immediately on
start acceptance must retain completion until ownership allows the manager to
accept it at a later edge; do not publish terminal with accepted SUBMIT.

Late/duplicate terminal events and old-job memory accesses after terminal are
forbidden. There is no token to distinguish an old event from a new job after
ACK/reuse. An unexpected terminal is an adapter protocol violation, not a
completion for a new job. Monitoring must report failure; no CPU trap is added
for a protocol violation.

Terminal SUCCESS/ERROR means the adapter has stopped using every job buffer,
all relevant memory accesses have completed/become quiescent, and valid
outputs/metadata under the IP contract are visible to the CPU. Native `done`
or DMA request acceptance is insufficient. ERROR may leave invalid partial
output; there is no rollback.

### Concurrent-event rules

All command results use pre-edge state. Completions for the two targets may be
accepted at the same edge; ACK of one target must not lose the other's terminal.

| Pre-edge state | Events at the same edge | Command result / effect | Next state |
| --- | --- | --- | --- |
| ACTIVE | QUERY + terminal | QUERY OK/ACTIVE; completion is retained. | SUCCESS/ERROR |
| ACTIVE | ACK + terminal | ACK NOT_READY; does not clear the new completion. | SUCCESS/ERROR |
| ACTIVE | SUBMIT + terminal | SUBMIT BUSY; no new pointer is accepted. | SUCCESS/ERROR |
| SUCCESS/ERROR | ACK | ACKED; reclaim the old completion. | IDLE |
| IDLE | Valid SUBMIT | ACCEPTED; reserve pointer, not yet terminal. | ACTIVE |
| One target terminal, the other ACTIVE | ACK terminal target + terminal for the other target | ACK the first target; retain the second target's completion. | IDLE + SUCCESS/ERROR |
| Any | Reset asserted, including an edge with command/start/terminal signals high | Reset wins asynchronously for control ownership; no fire, retirement or publication on an edge with reset low. | Control ownership idle |

An adapter terminal while IDLE or after terminal was already accepted is a
protocol violation. Do not add a terminal FIFO or clear-versus-set latch to
legitimize events that violate the lifecycle.

## 9. Memory semantics, descriptors and lifetime

**SUBMIT release:** prior CPU publication of descriptors/inputs must be visible
before any adapter read triggered by the accepted job. The binding prevents
the compiler from moving stores after SUBMIT. CPU serialization completes older
instructions, but an OBI response that orders only against a subsequent CPU data
transaction is insufficient by itself for the new CI control path. The platform
must close the visibility obligation across both paths, for example through
stronger store-response completion or a reviewed ordering mechanism. This
contract does not preselect a bridge/AXI fence implementation. SUBMIT must not
retire before the profile's release obligation is met; rejection still grants
no descriptor-read permission and creates no job.

**Terminal QUERY acquire:** when QUERY observes SUCCESS/ERROR, subsequent CPU
reads may observe outputs/metadata published under the IP ABI. The adapter/memory
path must ensure publication before terminal state; CI serialization blocks
younger accesses and the binding prevents compiler hoisting. QUERY ACTIVE does
not permit output consumption. ACK does not replace QUERY/acquire. CPU FENCE
does not complete DMA or independently solve posted writes, coherence or CDC
in a different system.

Each IP owner must select descriptor schema, version, minimum/full size,
additional alignment, buffer ranges, operation, tensor layout/quantization, PQC
parameters/results and DMA access widths. The manager checks only ID/cheap
pointer validity; it neither parses a common header nor assumes identical
formats. The adapter validates the full descriptor and all ranges before native
effects that require those fields. Post-acceptance errors become safe ERROR
and still require QUERY/ACK. Detection of every hardware fault is not promised.

The application keeps descriptor, input, output and metadata storage valid
from before SUBMIT until the API returns completion to the application. Do not
modify descriptors or inputs being read by a job, read/modify outputs before
acquire/consumption, or use pointers to expired stack frames. Sharing read-only
input between jobs is allowed if the IP contracts permit it; mutable overlap
between jobs or CPU/job is forbidden without a separate contract. The manager
cannot check every alias by itself.

Hardware ACK ends slot ownership, not API lifetime. The driver retains
record/context and API BUSY until application consumption. Only after consumption
may the caller reuse storage according to the IP contract's result/validity rules.

## 10. IRQ composition — reference

CI lifecycle and polling require no IRQ or CSR. When the IRQ feature is enabled,
completion sources, CSR/drain, handlers, MIE critical sections and related races
are defined solely in the [IRQ contract](external-interrupt-extension.md).
Terminal state remains available for QUERY/ACK even without interrupt logic.

## 11. C API and polling driver

One driver exclusively owns SUBMIT/QUERY/ACK. Applications call the semantic
APIs try-submit(ID, descriptor, context) and try-collect(ID), without raw asm/ACK.
C symbol names/signatures are not prescribed yet; the return semantics and
ownership below form the API contract. There is no compiler kernel auto-detection
for offload.

Each target has a FREE/OWNED/COMPLETED record. try-submit returns BUSY while the
record is OWNED or COMPLETED, even if hardware is IDLE after ACK. try-collect
returns NOT_READY without terminal completion, or returns completion/context
and buffer ownership to the caller on successful consumption. There is no
software FIFO or hardware token. The API checks ID before indexing a record;
rejection does not discard an existing record.

BASE_CI has one foreground caller and no ISR. Its critical-section helper reads
or writes no CSR/MIE, but still maintains required compiler memory ordering.
On IRQ-enabled builds, use the helper and synchronization in the IRQ contract;
do not copy the MIE/ISR algorithm into the polling contract.

| Event | Driver action |
| --- | --- |
| Submit | Check FREE, install context and reserve OWNED before CI. ACCEPTED retains OWNED; rejection discards temporary context and returns the newly reserved record to FREE. |
| Collect terminal | QUERY/acquire; copy snapshot/class/context into the OWNED record; ACK; verify ACKED before publishing COMPLETED. Do not loop waiting for terminal/BUSY inside the helper. |
| Consume | Observe COMPLETED with compiler ordering, copy completion/context, mark FREE; output loads must not be hoisted before successful consumption. |
| ACK/protocol error | Retain OWNED and snapshot; publish no consumable completion and accept no new job; use coordinated recovery if ownership cannot be restored. |

Hardware ACK does not end application buffer lifetime. The record retains
context until consumption; status/class does not guarantee valid partial output
for an ERROR job. A volatile flag alone does not ensure compiler handoff;
inspect generated code for publication/acquire/consumption and profile legality.

### Toolchain boundary

Use centralized inline-asm bindings with side-effect-preserving volatile,
correct register constraints and compiler memory effects for release/acquire.
GCC describes a memory clobber as a compiler read/write barrier, not hardware
ordering ([GCC Extended Asm](https://gcc.gnu.org/onlinedocs/gcc/Extended-Asm.html)).
Use .insn r as described by the [GNU assembler](https://sourceware.org/binutils/docs/as/RISC_002dV_002dFormats.html);
this document-freeze task neither selects a toolchain version nor creates binding
source. The gate checks encoding, operand aliasing, rd result, optimized polling
that is neither removed nor hoisted, output handoff, and absence of CSR/MRET
instructions in BASE_CI firmware.

## 12. Errors, progress and coordinated reset

Pre-acceptance control rejection changes no slot/adapter/job ownership. After
acceptance, the adapter must reach SUCCESS or safe ERROR for valid work in an
environment that guarantees progress. Invalid descriptors report ERROR only
after safe handling; emitting ERROR while continuing DMA is forbidden.

There is no hardware watchdog or per-job abort. A software timeout is an
observation, not a terminal event; the slot, driver record and buffers remain
owned by the job. Hung memory/IP has no latency or self-recovery guarantee.
Reset recovery is effective only if the platform can actually stop/drain/quiesce
old transactions; otherwise recovery may be blocked. “Coordinated reset” is
not evidence of quiescence.

CPU, manager and adapters/accelerators reset together. CPU-only reset with a
live job or unconsumed completion is unsupported in the initial profile.
Before firmware restart and memory reuse, eliminate all late effects from the
old epoch: DMA reads/writes, start/terminal/control events and bridge ownership
pending at reset. Reset neither rolls back accepted writes nor restores
pre-job memory contents.

Reset assertion clears required slot/control ownership and terminal state
without waiting for a clock edge, according to the inherited reset contract.
At an edge sampling `rst_n=0`, command/start/terminal fire and CI retirement/RF
write are all zero. Payload reset is not required to establish validity.
Software restarts and initializes records before accepting jobs; IRQ-specific startup belongs
to the IRQ contract. Old jobs are discarded in the reset epoch; normal
completion for the previous application is not promised.

The platform may need to isolate ingress, stop/drain memory paths and hold
reset until quiescence; the clock/reset/interconnect owner selects the concrete
sequence. Do not clear bookkeeping and restart firmware while old DMA can still
write memory.

## 13. Traces to predict before implementation

| Edge / step | Pre-state | Event / observation | Post-state / conclusion |
| --- | --- | --- | --- |
| A | Slot IDLE, CPU CI at WB | valid=1, ready=0 | No retirement/effect; command remains stable. |
| B | As A | valid=1, ready=1, valid SUBMIT | rd ACCEPTED/IDLE, slot ACTIVE; CPU retires once. |
| C or later | ACTIVE, not dispatched | Start handshake | Adapter receives pointer; CPU may perform independent work. |
| D | ACTIVE, dispatched | QUERY concurrent with adapter terminal SUCCESS | rd OK/ACTIVE; slot SUCCESS is retained after the edge. |
| E | SUCCESS | QUERY | rd OK/SUCCESS; acquire for valid output, state is not cleared. |
| F | SUCCESS, software OWNED with snapshot | ACK | rd ACKED/SUCCESS; slot IDLE, software remains OWNED. |
| After F (software) | Hardware IDLE, software OWNED | Driver verifies ACKED result | Publish software COMPLETED; do not assume publication at the ACK edge. |
| G | Hardware IDLE, software COMPLETED | Application attempts submit before consumption | API BUSY; no raw SUBMIT is issued. |
| H | Software COMPLETED | Application consumes successfully | Software FREE; buffer ownership returns to caller, a new job may be accepted. |

Error trace: SUBMIT ACCEPTED → adapter detects an invalid descriptor → quiesce
all related accesses → ERROR/DESCRIPTOR → QUERY/acquire snapshot → ACK → app
consumption. The caller must not treat ACCEPTED as successful validation or read
partial output without permission from the IP contract.

## 14. Verification obligations — no execution results yet

Expected behavior must derive from the owner-approved contract, not from a
copied DUT decoder, FSM or model used as an oracle. Emulated adapters have
controllable delay/backpressure/errors and must be independently defined.
The items below specify planned evidence, not tests already written or passed.

Each fixture test records finite command-ready, adapter-start/terminal delay
and total-cycle bounds in version-controlled configuration, alongside the
parent's OBI bounds. The harness watchdog reports failure when a bound is
exceeded; it is neither a hardware watchdog nor a fixed-latency promise for
the core/accelerator.

| Boundary | Scenario that can falsify the contract | Expected observation |
| --- | --- | --- |
| Encoding / operands | Three operations, x0, rd aliasing a source, ID with nonzero high bits, unused-field patterns | Legal binding decodes correctly; full IDs do not alias; x0 discards the result but retains effects; unsupported patterns produce no CI command. |
| Serialization | CI after ALU/load/store with delayed response; older branch flushes CI; back-to-back CI | Older instructions retire before issue; no younger admission until the cycle after CI retirement; no wrong-path dispatch. |
| WB handshake | ready low for multiple cycles, reset between clock edges and at the handshake edge, BUSY and argument errors | Stable command; exactly-once retirement/effect; CI wait is sole-live with no data outstanding; asynchronous reset clears ownership and wins over fire. |
| Progress / overlap | Accepted SUBMIT followed by delayed terminal; occupied slot; adapter not start-ready | CPU performs independent work; BUSY returns before terminal; no rejected request retained for later execution. |
| Slot lifecycle | Submit to ACTIVE/terminal slot, repeated QUERY/ACK, asynchronous descriptor failure | One job per target; QUERY does not clear; safe ERROR retained; only terminal ACK releases. |
| Concurrent events | ACTIVE + terminal with QUERY/ACK/SUBMIT; two completions at one edge; ACK one target | Pre-edge results match the table; new/other-target completions are not lost. |
| Adapter ownership | Duplicate/late terminal, buffer access after terminal, reset/reuse epoch | Monitor reports violations; old events do not complete a new job. |
| Release/acquire | Delayed CPU publication through memory, command through another path; output write not yet visible | No stale adapter input reads; no terminal or consumable QUERY before output publication/quiescence. |
| BASE_CI polling driver | Immediate completion, rejection after context reservation, ACK error, hardware IDLE with record COMPLETED | No CSR/MIE access; correct context/record ownership; publish only after ACKED; API BUSY until consumption, no output hoisting. |
| Error / reset | Safe error with partial output, hung job, reset with active/terminal/command pending | No premature reuse; timeout does not release; restart only after old-epoch quiescence, no rollback claim. |
| Regression | BASE with CI logic absent and CI pins inert, extended profile running ordinary programs | Baseline contract/test boundary preserved; appropriate instruction/OBI/FENCE regression. |

Emulated memory-ordering checks prove the model/harness contract, not AXI/DDR
visibility on the board. Real adapters require evidence from the real memory
path. Compiler/assembler checks do not prove RTL; simulation does not prove
FPGA timing, power or actual throughput.

## 15. Roadmap and acceptance gates

These are internal gates, not project versions/releases. The root
[ROADMAP](../../../../docs/ROADMAP.md) must define milestone scope/acceptance
before functional feature implementation. Branch/owner review follows project
workflow; core RTL remains human-authored unless separately delegated.

| Gate | Required work / evidence | Claim boundary |
| --- | --- | --- |
| G0 — Contract freeze | Final owner text review, ABI v1 preservation, profile/dependency/link checks and an R2 version-controlled snapshot including RST-D1. | Does not accept shared SoC design or authorize RTL implementation. |
| G1 — BASE | Pass BASE regression, harness and objective acceptance gate. | Correct baseline CPU behavior in the harness; no CI/IRQ. |
| G2 — CI/polling | Add decode/serialize/WB command, an independent manager fixture, two emulated adapters and polling binding/driver; retain BASE regression. | Correct control boundary, independent CPU work, BUSY without waiting for jobs, target overlap, ordering and generated-code evidence. |
| G3 — IRQ/composition | Add CSR/MRET/drain/entry and terminal notification/ISR; retain G1/G2 and IRQ-contract gates. | The same IRQ-enabled hardware runs polling and interrupt firmware; not yet real-IP/FPGA proof. |
| G4 — Real-IP/FPGA | Close per-IP descriptor/golden behavior and platform visibility/reset; integrate TinyLLM/Dilithium and ZCU102. | Separate golden/simulation and board gates; fixture passes do not replace them. |
| G5 — MMIO frontend | After G3, add a frontend for the same manager/adapter/descriptor/API; may run alongside G4 after shared review. | Select map and ingress/build ownership then; no dual ingress/runtime switching yet. |
| G6 — Exploration | Control comparison after G3/G5; workload/board claims after corresponding G4 evidence. Humans select methodology before measurement. | Same IP/data path/slot/clock/workload; same completion mode for CI/MMIO comparison; same IRQ-enabled build for polling/IRQ comparison. |

Fixture memory paths must share backing data storage with the CPU responder
and preserve BASE address/alignment/reset/TEST_STATUS obligations. Test-local
descriptor/buffer layouts belong to an independent fixture contract, not the
real-IP ABI. Selecting real tensor/PQC schemas is unnecessary for designing
and verifying the core command boundary.

## 16. Freeze boundary and integration dependencies

R2 preserves the owner-selected CPU/ISA choices from R1: profile
selection, command ABI, stage ownership/handshake and disabled-feature behavior.
The final text still requires owner review and a Git snapshot; intent is not
hardware proof. Post-freeze semantic changes require owner approval, a bundle
revision update and corresponding regression obligations; do not change them
unilaterally based on DUT/test behavior.

| Dependency | Owner / condition before the corresponding gate |
| --- | --- |
| Shared manager/adapter implementation | Project/IP owners review dispatch/terminal protocol and CPU-boundary mapping. An independent core fixture may satisfy this contract. |
| Real descriptor/output ABI | IP owner selects schema/version, ranges/alignment, tensor/quantization/PQC parameters, validation and golden behavior before G4. |
| Memory / reset / clock | SoC/interconnect owners select map, publication across the CI path, DMA/error/progress and old-epoch quiescence before real integration. |
| Workflow / implementation | Root milestone, owner/reviewer and implementation delegation follow project policy; no commit/merge or RTL implementation in this documentation task. |

Integration requirements constrain the CPU-boundary environment; they are not
an accepted system-level implementation. Keep shared designs under project-level
authority once accepted by the team, referencing them rather than creating
competing copies.
