# Writeback Stage — Block Design

**Status:** Accepted by Nguyễn Tô Quốc Việt on 2026-10-24 after reviewing the
block design and confirming that no open decisions remain. BASE behavior is
inherited; `wb_src` naming and WB-generated retirement are selected locally.
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Design revision:** WB D2 / 2026-10-24; Việt selected internal retirement
qualification with only data and RF-write permission exposed.
**Parent contract:** [BASE result selection](5-stage-baseline-core.md#exmem-boundary-and-data-request-ownership),
[MEM/WB payload](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary),
[architectural side effects](5-stage-baseline-core.md#architectural-side-effects),
and [MEM routing](memory-stage.md#3-internal-organization-and-wiring).
**RTL mapping:** Leaf `writeback_stage` in [rtl/writeback_stage.sv](../../rtl/writeback_stage.sv);
instance `wb_stage` belongs to future core integration. Việt created the initial
module and result mux, then delegated the internal-retirement/RF-write update
on 2026-10-24. This mapping is not functional verification evidence.

## 1. Purpose and boundary

Select the current MEM/WB instruction's architectural result and qualify its
register-file write. The selected decomposition is one combinational leaf,
without a separate wrapper, mux leaf or write-control leaf.

BASE owns result semantics, retirement and interlock rules. This document
refines the local WB interface; it does not move instruction decode, arithmetic,
load formatting, pipeline storage or arbitration into WB. CI, CSR/MRET and IRQ
are outside this BASE leaf. No extension result inputs are reserved.

RF owns storage, read ports and read-port forwarding. EX's forwarding unit owns
producer matching and operand selection. WB supplies the selected `wb_data`;
neither forwarding function is part of this leaf.

## 2. Interface contract

### Clock, reset and configuration

Combinational; no clock, reset, storage, local stall or flush ports. Data vectors
use `riscv_pkg::DATA_WIDTH`; the supported BASE configuration is
`DATA_WIDTH = ADDR_WIDTH = 32`. There are no module width parameters or width
conversions. All vectors are unsigned bit patterns.

### Ports

This table applies the owner-selected WB-D2 interface from section 9.
There are seven inputs and two outputs.

| Port | Direction | Type / width | Meaning and validity |
| --- | --- | --- | --- |
| `ex_result` | Input | `logic [DATA_WIDTH-1:0]` | MEM/WB EX result; architectural value when a live writer selects `wb_src=0` |
| `load_result` | Input | `logic [DATA_WIDTH-1:0]` | MEM/WB formatted load value; architectural value when a live load selects `wb_src=1` |
| `wb_src` | Input | 1-bit `logic` | ID-decoded selector retained in MEM/WB: `0` selects EX, `1` selects load; meaningful for a live writer |
| `rd` | Input | `logic [4:0]` | MEM/WB destination; meaningful for a live writer |
| `reg_write` | Input | 1-bit `logic` | MEM/WB semantic register-write intent; consumed for write qualification only when retirement is permitted |
| `instruction_valid` | Input | 1-bit `logic` | Current MEM/WB entry is live; zero throughout reset after reset propagation |
| `advance_allowed` | Input | 1-bit `logic` | Core permits WB to advance at the next rising edge; zero during active reset or unresolved MEM wait |
| `wb_data` | Output | `logic [DATA_WIDTH-1:0]` | Selected data; usable by forwarding for an eligible live producer even when it cannot retire; consumed by RF for a write only with `rf_write_fire` |
| `rf_write_fire` | Output | 1-bit `logic` | Permission for RF to write the current `rd` with `wb_data` at the rising edge |

No shared WB-selector enum currently exists in `riscv_pkg`. This design keeps
the already selected one-bit encoding and introduces no new type or package edit.

### Timing and consumption

Outputs follow current inputs after combinational settling; there is no
additional registered latency or transaction handshake. Core and RF own
setup/hold and rising-edge consumption. Consecutive instructions require no
WB-local bubble. This is a logical contract, not a physical timing claim.

The core routes MEM/WB `rd`, `valid` and `reg_write` directly to their consumers.
RF receives the destination directly; EX forwarding receives producer metadata
directly. This design adds no pass-through ports for those fields.

## 3. Internal organization

One two-input data mux and register-write qualification implement the selected
leaf. `wb_retire_fire` is an internal combinational signal, not an output port
or stored state. BASE has no separately identified functional consumer requiring
a public retirement port. Selection preserves every data bit without arithmetic or sign conversion.
JAL/JALR's `pc + 4` has already been selected into `ex_result` in EX; no PC,
`pc_plus_4` input or third WB data source is needed.

## 4. State and ownership

The leaf owns no state. The core owns MEM/WB validity, payload retention,
replacement and permission to advance. The selected WB interface combines that
permission with current validity to form internal retirement qualification; it does
not arbitrate reset or memory wait. RF owns the architectural registers
and read-port forwarding. The core must associate every input with the same
pre-edge MEM/WB instruction; incoming MEM data does not replace that current
instruction's write data before its retirement edge.

`advance_allowed` qualifies an event; it does not hold pipeline storage.
The core must separately drive MEM/WB's `stall` input to retain its entry and
deny WB advance while the BASE interlock applies. EX already uses the same
valid/advance distinction to qualify redirect. MEM instead emits `mem_wait`;
its OBI controller continues mandatory grant/response progress while pipeline
registers are held. These stage-specific interfaces do not replace the
[pipeline-register stall contract](5-stage-baseline-core.md#pipeline-register-local-control).

## 5. Behavioral rules

Inherited BASE selection, using the owner's new selector name:

```text
wb_data = wb_src ? load_result : ex_result
```

Both binary selector values are defined. ALU/LUI/AUIPC and jump-link writers
select `0`; loads select `1`. Branches, stores and FENCE retire with
`reg_write=0`. Unused data is not required to be zero, including during bubbles.

Under the owner-selected WB-D2 interface, internal event qualification is:

```text
wb_retire_fire = instruction_valid && advance_allowed
rf_write_fire = wb_retire_fire && reg_write && (rd != 0)
```

Retirement is distinct from RF write. A non-writer or a writer to x0 may retire
without an RF write. Retirement depends on validity and advance permission,
not `reg_write`, `wb_src` or payload values. RF uses `rf_write_fire` as its write
enable instead of raw `reg_write`. Semantic `reg_write` remains in the pipeline
metadata and qualifies EX forwarding independently of retirement.

Do not use internal retirement as the MEM/WB capture enable: parent controls
must also permit an incoming instruction to replace an invalid WB entry and
allow an invalid incoming entry to clear old validity.

During an unresolved MEM wait, parent control retains MEM/WB and supplies
`advance_allowed=0`, so `wb_retire_fire=0`. `wb_data` remains selected and
available; do not gate or zero it with retirement or RF write permission.
EX forwarding eligibility remains
the separate BASE rule `valid && reg_write && rd != 0`.

On a valid memory-response release edge, old WB may retire and write RF while
the completed MEM instruction replaces it in MEM/WB. RF consumes the old WB
value at that edge; combinational WB outputs then reflect the newly captured
entry. Parent control adds no release bubble and preserves old WB on a younger
EX redirect. [BASE arbitration](5-stage-baseline-core.md#pipeline-control-priority)
owns these concurrent events.

## 6. Reset, cancellation and exceptional conditions

The leaf has no private reset or cancellation mechanism. Parent reset clears
MEM/WB valid asynchronously and forbids retirement under the
[BASE reset contract](5-stage-baseline-core.md#reset-architecture). Under WB-D2,
the core must therefore clear `instruction_valid` and hold `advance_allowed=0`
throughout reset after reset propagation. The leaf's qualification then
suppresses retirement and RF writes regardless of stale payload. `wb_data`
is not reset or forced to zero.

Parent control resolves stall/flush/reset before supplying the current entry
and advance permission. A younger EX redirect does not kill older WB work.
RF retains the inherited x0 and selective-reset behavior; those storage rules
are not implemented by this leaf.

The guaranteed input domain contains only 0/1. X/Z behavior is outside scope.
Illegal decode and inconsistent parent advance permission are environment
violations, not errors this leaf repairs. No trap, error or checker port is added.

## 7. Representative examples

The data examples apply the inherited mux. Write-enable examples assume the
owner-selected WB-D2 interface. The first three rows use `instruction_valid=1` and
`advance_allowed=1`; expected values are explicit literals.

| Case | Relevant inputs | Expected outputs |
| --- | --- | --- |
| Ordinary writer | `ex_result=0x80000001`, `load_result=0x12345678`, `wb_src=0`, `reg_write=1`, `rd=5` | `wb_data=0x80000001`, `rf_write_fire=1` |
| Signed byte load already formatted in MEM | `ex_result=0x00010003`, `load_result=0xFFFFFF80`, `wb_src=1`, `reg_write=1`, `rd=6` | `wb_data=0xFFFFFF80`, `rf_write_fire=1` |
| Jump link already selected in EX | `ex_result=0x00000024`, `load_result=0xDEADBEEF`, `wb_src=0`, `reg_write=1`, `rd=1` | `wb_data=0x00000024`, `rf_write_fire=1` |
| Held older WB producer | First row with `advance_allowed=0` | `wb_data=0x80000001`, `rf_write_fire=0`; eligible EX forwarding may still use the data |
| Invalid entry | First row with `instruction_valid=0` | Data follows selector, `rf_write_fire=0` |
| Write to x0 | First row with `rd=0` | Data unchanged, `rf_write_fire=0` |
| Live non-writer | First row with `reg_write=0` | Data follows selector, `rf_write_fire=0` |

## 8. Verification obligations

These obligations derive from BASE and the accepted interface. They do not
constitute an approved executable test plan or observed results. Use the owner-readable
[testbench conventions](../../tb/README.md#testbench-conventions) when a plan is
approved; directed expected data must be supplied as manual literals.

| Obligation | Scenario | Expected observation |
| --- | --- | --- |
| Result selection preserves all bits | Distinct EX/load values, zero, high-bit and all-one patterns; change unselected input | Selected literal appears unchanged; unselected input cannot affect output |
| Valid/advance qualification | A writer to nonzero rd with valid and advance asserted, then each disabled independently | RF write is suppressed when either qualifier is zero; inspect no private signal to establish this |
| RF qualification | Eligible write, retirement disabled, non-writer, x0 destination | Write permitted only when retirement, write intent and nonzero destination all hold |
| Data independent of retirement | Keep data/selector stable while toggling validity and advance permission | `wb_data` stays unchanged while RF write permission changes |
| Combinational behavior | Consecutively change selector, values, destination and qualifiers | Every output follows the current inputs without retained prior-entry state |
| Parent integration, outside leaf evidence | MEM wait then response release with distinct old-WB/new-MEM results; reset or younger redirect | No write during hold/reset; old WB writes once on release; replacement and forwarding retain correct instruction association |

Leaf checks cannot establish actual MEM/WB retention/capture, core arbitration,
RF storage/read forwarding, full-pipeline retirement or physical timing.

## 9. Rationale and open decisions

The inherited two-source selection and RF-write rule fit one combinational
leaf; separate mux/control leaves would add hierarchy without separating an
independent storage or protocol responsibility. The owner-selected decisions
are recorded below.

| ID | Decision / authority | Selected choice and rationale |
| --- | --- | --- |
| WB-N1 | Naming, selected by Việt on 2026-10-24 | Use `wb_src` with unchanged `0=EX`, `1=load` encoding. The producer-stage form is `mem_wb_src`. |
| WB-D1 | Retirement qualification, selected by Việt on 2026-10-24 | WB receives `instruction_valid` and `advance_allowed`, derives retirement and qualifies RF write locally. Core owns advance arbitration. This keeps per-instruction qualification in WB without making it resolve global reset/stall conditions. The considered alternative was a core-generated retirement input; it preserves BASE behavior but moves that local qualification outside WB. |
| WB-D2 | Retirement visibility, selected by Việt on 2026-10-24 | Keep `wb_retire_fire` internal; expose only `wb_data` and `rf_write_fire`. No BASE consumer needs a separate retirement port. Keep semantic `reg_write` for forwarding; use the fully qualified `rf_write_fire` at the RF write-enable port. |

Existing EX RTL/tests still use `mem_wb_from_mem`; current contracts use
`mem_wb_src` under the owner's naming amendment. RTL/test/diagram migration is
outside this WB update. No material open decisions remain within the
accepted leaf boundary. Acceptance defines intended behavior; it is not
implementation or verification evidence. No WB RTL, package type or test code
is authorized by document acceptance alone. Functional implementation remains
human-authored unless explicitly delegated under AGENT_POLICY.
