# Hazard Control Unit — Block Design

**Status:** Accepted by Việt on 2026-11-05
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Parent contract:** [Five-stage BASE core](5-stage-baseline-core.md), in particular
[pipeline-control priority](5-stage-baseline-core.md#pipeline-control-priority),
[pipeline-register local control](5-stage-baseline-core.md#pipeline-register-local-control) (PR-D1),
[forwarding and load-use hazards](5-stage-baseline-core.md#forwarding-and-load-use-hazards),
[register-file timing and WB-to-ID bypass](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass) (load-use definition) and
[reset architecture](5-stage-baseline-core.md#reset-architecture); [fetch-stage.md](fetch-stage.md) §2
(`fetch_accept`), §5.2 (redirect row) and D-3; [decode-stage.md](decode-stage.md) (`rs1_id`, `rs2_id`,
`rs1_used`, `rs2_used`; decisions D2 and O2); [redirect-unit.md](redirect-unit.md) (`redirect_fire` gated
by `advance_allowed`); [memory-stage.md](memory-stage.md) (`mem_wait`); [writeback-stage.md](writeback-stage.md)
(WB-D2, reset).
**RTL mapping:** `rtl/hazard_control_unit.sv`, module `hazard_control_unit` (HCU-O2). The RTL is written by
Việt (HCU-O2). The instance name belongs to the later core top design.
This document is neither implementation nor verification evidence.

## 1. Purpose and boundary

The HCU is the core-level arbiter for the pipeline-control signals of the five-stage core. It detects
load-use and turns the MEM wait, the EX redirect and load-use into per-register `stall` and `flush`,
and into `advance_allowed` and `fetch_accept`. Its success criterion is that every pipeline register
and the frontend take the next state that the BASE next-state table gives for each condition
([pipeline-control priority](5-stage-baseline-core.md#pipeline-control-priority)), and that `fetch_accept`
is consistent with the IF/ID `stall` and `flush` (fetch-stage D-3).

The HCU is one purely combinational module: no `clk`, no state (HCU-O1).

Non-goals (HCU-O1):

- It does not create `redirect_fire`. The EX `redirect_unit` qualifies it.
- It does not route the redirect to IF. The raw EX redirect goes to IF directly (fetch-stage F-e).
- It does no forwarding. Forwarding is in the EX and register-file paths (BASE forwarding section).
- It produces no `valid_i` for any pipeline register.
- It does not decide the frontend allocation or the Fetch Buffer state. It supplies `fetch_accept` only.

Producers and consumers at the boundary:

- Producers: `memory_stage` (`mem_wait`), `execute_stage` (`redirect_fire`), `decode_stage`
  (`rs1_id`, `rs2_id`, `rs1_used`, `rs2_used`), and the IF/ID and ID/EX pipeline registers (their
  valid and fields; not yet written, see section 2).
- Consumers: `execute_stage` and `writeback_stage` (`advance_allowed`), `fetch_stage` (`fetch_accept`),
  and the four pipeline registers (`stall`, `flush`).

Inherited by reference, not restated: the BASE next-state table, PR-D1, the load-use definition and
reset architecture. Local decisions are in section 9.

## 2. Interface contract

### Clock, reset and configuration

The HCU has no clock. It holds no state, so no sampled register exists in it (HCU-O1). `rst_n` is an
input only so that `advance_allowed = 0` during reset (HCU-O4, WB-D2; BASE
[reset architecture](5-stage-baseline-core.md#reset-architecture)). Reset of the pipeline registers
is handled by those registers (PR-D1, reset has priority 1).

Constants: none. The three 5-bit fields are register identifiers (`logic [4:0]`) and take no
configuration. The supported configuration is the BASE five-stage core.

### Ports and payloads

All ports are individual signals; there is no packed struct. There are 12 inputs and 8 outputs
(20 ports). Every port is 1-bit `logic` except the three 5-bit register-identifier fields.

| Signal | Direction | Type / width | Meaning | Valid when | Source |
| --- | --- | --- | --- | --- | --- |
| `rst_n` | Input | 1-bit `logic` | Active-low core reset | Always | Core reset (core top, not yet written); [reset architecture](5-stage-baseline-core.md#reset-architecture); HCU-O4 |
| `mem_wait` | Input | 1-bit `logic` | Unresolved MEM wait: a live memory owner has not completed | Always | `memory_stage` output `mem_wait` (`rtl/memory_stage.sv`, line 23) |
| `redirect_fire` | Input | 1-bit `logic` | Qualified EX redirect, already gated by `advance_allowed` | Always | `execute_stage` output `redirect_fire` (`rtl/execute_stage.sv`, line 44); [redirect-unit.md](redirect-unit.md) |
| `id_valid` | Input | 1-bit `logic` | The instruction in ID is valid | Always | IF/ID register `valid_o`: not yet written |
| `id_rs1_id` | Input | `logic [4:0]` | Raw `rs1` field of the ID instruction | Qualified by `id_rs1_used` | `decode_stage` output `rs1_id` (`rtl/decode_stage.sv`, line 24) |
| `id_rs2_id` | Input | `logic [4:0]` | Raw `rs2` field of the ID instruction | Qualified by `id_rs2_used` | `decode_stage` output `rs2_id` (`rtl/decode_stage.sv`, line 25) |
| `id_rs1_used` | Input | 1-bit `logic` | ID instruction semantically reads `rs1` | Supported encodings | `decode_stage` output `rs1_used` (`rtl/decode_stage.sv`, line 29) |
| `id_rs2_used` | Input | 1-bit `logic` | ID instruction semantically reads `rs2` | Supported encodings | `decode_stage` output `rs2_used` (`rtl/decode_stage.sv`, line 30) |
| `ex_valid` | Input | 1-bit `logic` | The instruction in EX is valid | Always | ID/EX register `valid_o`: not yet written |
| `ex_mem_en` | Input | 1-bit `logic` | The instruction in EX accesses memory | Always | ID/EX register, from `decode_stage` `mem_en`: not yet written |
| `ex_mem_write` | Input | 1-bit `logic` | The memory access in EX is a store | Qualified by `ex_mem_en` | ID/EX register, from `decode_stage` `mem_write`: not yet written |
| `ex_rd` | Input | `logic [4:0]` | Destination register of the instruction in EX | Qualified by `ex_valid` | ID/EX register `rd`: not yet written |
| `advance_allowed` | Output | 1-bit `logic` | The core permits EX and WB to advance on this edge | Combinational | Consumers: `execute_stage` (`rtl/execute_stage.sv`, line 28), `writeback_stage` (`rtl/writeback_stage.sv`, line 18) |
| `fetch_accept` | Output | 1-bit `logic` | IF/ID may take a frontend entry on this edge (capture mode). A valid entry moves only on `fetch_fire = fetch_valid && fetch_accept` | Combinational | Consumer: `fetch_stage` (`rtl/fetch_stage.sv`, line 14) |
| `if_id_stall` | Output | 1-bit `logic` | Hold the IF/ID register | Combinational | IF/ID register (not yet written) |
| `if_id_flush` | Output | 1-bit `logic` | Invalidate the IF/ID register | Combinational | IF/ID register (not yet written) |
| `id_ex_stall` | Output | 1-bit `logic` | Hold the ID/EX register | Combinational | ID/EX register (not yet written) |
| `id_ex_flush` | Output | 1-bit `logic` | Invalidate the ID/EX register | Combinational | ID/EX register (not yet written) |
| `ex_mem_stall` | Output | 1-bit `logic` | Hold the EX/MEM register | Combinational | EX/MEM register (not yet written) |
| `mem_wb_stall` | Output | 1-bit `logic` | Hold the MEM/WB register | Combinational | MEM/WB register (not yet written) |

Four separate `stall` outputs are used, not one shared signal (HCU-O3). There is no `ex_mem_flush`
and no `mem_wb_flush` output: in BASE the EX/MEM and MEM/WB flush inputs are never 1, and the core top
ties them to 0 (HCU-O3).

Width domains: the three register identifiers are 5-bit architectural register numbers (`x0`..`x31`).
They are compared for equality only. No width conversion exists in this block.

### Transfer and timing rules

- All outputs are combinational functions of the inputs. Each output is defined by the equations below,
  and nothing is registered inside the HCU.
- Equations (HCU-O6, settled by the Owner, 2026-11-05):

  ```systemverilog
  load_use = id_valid && ex_valid && ex_mem_en && !ex_mem_write && (ex_rd != 5'd0)
          && ((id_rs1_used && (id_rs1_id == ex_rd)) || (id_rs2_used && (id_rs2_id == ex_rd)));
  mem_wb_stall    = mem_wait;
  ex_mem_stall    = mem_wait;
  id_ex_stall     = mem_wait;
  if_id_stall     = mem_wait || load_use;
  if_id_flush     = redirect_fire;
  id_ex_flush     = redirect_fire || (load_use && !mem_wait);
  advance_allowed = rst_n && !mem_wait;
  fetch_accept    = !if_id_stall && !if_id_flush;
  ```

- **Timing note (fact, not a target).** The combinational chains that cross the HCU are:
  1. `rvalid` → `mem_wait`: `data_obi_controller` drives `mem_wait = !rvalid` while the memory owner
     has an outstanding request (`rtl/data_obi_controller.sv`, line 64).
  2. `mem_wait` → `if_id_stall` → `fetch_accept` (HCU) → `fetch_fire` (`fetch_valid && fetch_accept`):
     the Fetch Buffer frees its entry and IF/ID captures it, on the same edge, in the frontend next state.
  3. `mem_wait` → `advance_allowed` (HCU) → `redirect_fire` (`rtl/redirect_unit.sv`, line 48) →
     `if_id_flush`, `id_ex_flush` (HCU), and `kill` to `fetch_controller_unit`
     (`rtl/fetch_controller_unit.sv`, line 37); `redirect_fire` → `if_id_flush` → `fetch_accept`.
  4. `mem_wait` → `advance_allowed` → `wb_retire_fire` (`rtl/writeback_stage.sv`, line 27) → the
     register-file write and the WB-to-ID bypass value that feeds ID/EX next state.

  Each chain ends at registers: pipeline-register valid and payload, Fetch Buffer state, or the
  register-file write. No chain reaches `req` or `addr`: the frontend's `req` comes from registered
  Fetch Buffer state only (fetch-stage §2; BASE IF-A1). Section 5 gives the logic values for these
  chains; this note gives no timing number.

- The HCU has no cycle: `advance_allowed` depends only on `rst_n` and `mem_wait`, and `load_use`
  depends only on registers and decode outputs. Neither depends on `redirect_fire`, so the
  `redirect_fire` gating in [redirect-unit.md](redirect-unit.md) is not circular through the HCU.

## 3. Internal organization

The HCU has three groups of logic and no sub-blocks:

- **Hazard detect:** `load_use`, from the ID instruction's used sources and the EX load's destination.
- **MEM wait and redirect decode:** `mem_wait`, `redirect_fire` and `load_use` drive the stall and
  flush equations of section 2. The `!mem_wait` guard on `id_ex_flush` is in section 5.
- **Frontend qualification:** `fetch_accept` is `!if_id_stall && !if_id_flush`, so it is 1 exactly when
  IF/ID is in capture mode (PR-D1). A valid entry moves only on `fetch_fire = fetch_valid && fetch_accept`:
  the Fetch Buffer frees that entry and IF/ID captures it on the same edge (fetch-stage D-3). With
  `fetch_valid = 0`, `fetch_accept` may be 1 and no entry moves.

No width, signedness, extension or overflow semantics apply beyond the 5-bit equality compare.

## 4. State and ownership

The HCU is stateless. It stores nothing and has no reset value. The stored state that it controls
(pipeline-register valid and payload, Fetch Buffer state) belongs to those blocks, under their own
reset and hold rules.

## 5. Behavioral and next-state rules

### 5.1 Preconditions used by the table

The table relies on three facts that the HCU does not check. Each is enforced elsewhere:

- **P1. `redirect_fire = 1` implies `mem_wait = 0` and `rst_n = 1`.** `redirect_fire` is
  `redirect_req && instruction_valid && advance_allowed` (`rtl/redirect_unit.sv`, line 48), and
  `advance_allowed = rst_n && !mem_wait` (HCU). The MEM wait and redirect are therefore never both 1.
- **P2. `redirect_fire = 1` implies `load_use = 0`.** A load in EX has `mem_en = 1` and `mem_write = 0`.
  A control-flow instruction has `mem_en = 0`: `rtl/control_unit.sv` sets `mem_en` only in the load and
  store decode, and clears it for unsupported encodings (line 300). One EX instruction cannot be both.
  This is HCU-O8: "redirect wins" then costs no logic.
- **P3. Pipeline inputs are the stage's own instruction.** `id_*` fields are the ID instruction
  qualified by `id_valid`; `ex_*` fields are the EX instruction qualified by `ex_valid`. These come from
  registers not yet written, so this is a requirement on those registers.

Inputs are `0` or `1` only; X and Z are outside the contract (the same precedent as fetch-stage O4).

### 5.2 BASE next-state rows against the equations

The rows follow the BASE next-state table and its priority (reset > MEM wait > redirect > load-use >
normal). "Hold" is `stall=1`, `flush=0`. PR-D1 gives reset priority over flush and stall.

| BASE row (first applicable) | Input condition | HCU outputs | Pipeline registers under PR-D1 | `wb_retire_fire` |
| --- | --- | --- | --- | --- |
| Reset asserted | `rst_n=0` | `advance_allowed=0`; `fetch_accept` may read `1` (fetch ignores it under reset, fetch-stage §2); stall and flush values are masked | IF/ID, ID/EX, EX/MEM, MEM/WB invalid (reset dominates) | `0` |
| Unresolved MEM wait | `rst_n=1`, `mem_wait=1`, `redirect_fire=0` (P1) | `if_id_stall=1`, `if_id_flush=0`, `id_ex_stall=1`, `id_ex_flush=0` (guard), `ex_mem_stall=1`, `mem_wb_stall=1`, `fetch_accept=0` | All four hold | `0` |
| `redirect_fire` | `rst_n=1`, `mem_wait=0`, `redirect_fire=1`, `load_use=0` (P1, P2) | `if_id_stall=0`, `if_id_flush=1`, `id_ex_stall=0`, `id_ex_flush=1`, `ex_mem_stall=0`, `mem_wb_stall=0`, `fetch_accept=0` | IF/ID invalid; ID/EX invalid; EX/MEM captures EX output; MEM/WB captures MEM output | Current MEM/WB valid |
| Load-use hazard | `rst_n=1`, `mem_wait=0`, `redirect_fire=0`, `load_use=1` | `if_id_stall=1`, `if_id_flush=0`, `id_ex_stall=0`, `id_ex_flush=1`, `ex_mem_stall=0`, `mem_wb_stall=0`, `fetch_accept=0` | IF/ID holds the dependent instruction; ID/EX invalid bubble; EX/MEM captures the load; MEM/WB captures MEM output | Current MEM/WB valid |
| Normal / IF availability | `rst_n=1`, all of the above `0` | All stalls and flushes `0`; `fetch_accept=1` | ID/EX captures ID output; EX/MEM and MEM/WB capture; IF/ID captures the oldest `READY` entry when `fetch_valid=1`, else invalid | Current MEM/WB valid |

### 5.3 Combined cases

| Case | Input condition | Equation result | Matches | Note |
| --- | --- | --- | --- | --- |
| MEM wait with load-use (guard case) | `mem_wait=1`, `load_use=1` | `id_ex_flush = redirect_fire || (1 && !1) = 0`; `id_ex_stall = 1`; `if_id_stall = 1`; all others as the MEM-wait row | Unresolved MEM wait: all hold | Without `!mem_wait`, `id_ex_flush` would be `1` and erase the load in ID/EX, although BASE holds ID/EX (and PR-D1 gives flush priority over stall). See section 5.4 |
| Response plus load-use | `mem_wait=0` on the `data_response_fire` edge, `load_use=1` | Same values as the load-use row | BASE text on the response-plus-load-use edge: MEM/WB takes the completed memory instruction, EX/MEM takes the load, ID/EX takes a bubble, IF/ID holds the dependent instruction | `mem_wait=0` on that edge (`memory-stage.md`: `mem_wait=0` means the expected response is available) |
| Response plus redirect | `mem_wait=0` on the response edge, `redirect_fire=1` | Same values as the redirect row | BASE text on the response-plus-redirect edge: MEM/WB takes the completed memory instruction, EX/MEM takes the redirecting instruction, younger entries invalid | Redirect is allowed on this edge because `advance_allowed` is 1 |

### 5.4 Why the guard, and where it matters

PR-D1 says flush beats stall. Under a MEM wait, ID/EX must hold its load (BASE: the MEM wait holds all
four registers). With the guard, `id_ex_flush` is 0 under a MEM wait, so the MEM-wait row holds.
Without it, a store waiting in MEM, a load in EX and its consumer in ID would clear the load.
Trace 2 (section 7) shows this case.

No other guard is needed (HCU-O8). `redirect_fire` and `mem_wait` are never both 1 (P1), and
`redirect_fire` and `load_use` are never both 1 (P2), so the redirect term in `id_ex_flush` and
`if_id_flush` costs no logic.

### 5.5 Derived properties

Under P1 and P2:

- No register is stalled and flushed in the same cycle. `if_id_flush` is 1 only when `mem_wait` and
  `load_use` are 0, so `if_id_stall` is 0. `id_ex_flush` is 1 only when `id_ex_stall = mem_wait` is 0.
  PR-D1's "simultaneous flush and stall invalidates" case never occurs in BASE.
- `fetch_accept = 1` exactly when IF/ID is in capture mode (not stalled, not flushed). A valid entry moves
  only on `fetch_fire = fetch_valid && fetch_accept`: the Fetch Buffer frees that entry and IF/ID captures
  it on that edge (fetch-stage D-3). With `fetch_valid = 0`, no entry moves.
- `fetch_accept = 0` on every redirect edge (HCU-O5, option A). The Fetch Buffer frees its `READY`
  entries on a redirect whatever `fetch_accept` is (fetch-stage §5.2), so A is a choice that does not
  depend on that detail.

## 6. Reset, cancellation and exceptional conditions

**Reset.** The HCU has no reset state. `rst_n = 0` forces `advance_allowed = 0`, which suppresses
retirement (`wb_retire_fire = 0`, WB-D2) and EX advance. The pipeline registers clear their valid
asynchronously (PR-D1, reset row). `fetch_accept` is not gated by `rst_n` in the HCU: the Fetch Buffer
has no transfer, delivery or allocation effect on an edge with `rst_n = 0` (fetch-stage §2).

**Cancellation.** Two cancellations exist in the HCU:
- The EX redirect flushes IF/ID and ID/EX (`redirect_fire`). IF frees its `READY` entries through the
  Fetch Buffer, not through the HCU.
- The load-use bubble invalidates ID/EX for one cycle (`load_use && !mem_wait`). No instruction is
  discarded: the consumer is held in IF/ID and the load advances.

**Preconditions and their enforcement:**

- P1 (`redirect_fire` implies no MEM wait): enforced by `redirect_unit` gating with `advance_allowed`.
- P2 (`redirect_fire` and `load_use` exclusive): enforced by `control_unit` `mem_en` and `control_flow`
  decode.
- P3 (pipeline inputs are the stage's own instruction): enforced by the IF/ID and ID/EX registers, not
  yet written.

Behavior outside these preconditions is not defined by this document. In particular `redirect_fire = 1`
with `mem_wait = 1` is not a legal input.

## 7. Representative examples or cycle traces

Stimulus notes. The memory of a load or store is modelled as `data_obi_controller` drives it (section 2,
timing note): `mem_wait = 1` while the owner has not been granted, and `mem_wait = !rvalid` while it is
outstanding. In these traces `ID/EX` and `IF/ID` names are the instructions in those registers.
Register values are shown as the instruction name.

### Trace 1: load-use bubble, MEM wait, then release

Pre-edge: IF/ID `C` (`ADD x6, x5, x1`, uses `x5`); ID/EX `Lx` (`LW x5, 0(x2)`); EX/MEM `A` (ALU);
MEM/WB `B` (valid). `fetch_valid=1`: `D`, the oldest live `READY` Fetch Buffer entry, is on the delivery
outputs (`fetch_valid`, `fetch_pc`, `fetch_instruction`).

| Cycle / edge | Inputs (HCU) | State before (IF/ID, ID/EX, EX/MEM, MEM/WB) | Outputs | State after |
| --- | --- | --- | --- | --- |
| 1 | `mem_wait=0` (`Lx` is in EX, no memory owner); `load_use=1` | `C`, `Lx`, `A`, `B` | `if_id_stall=1`; `id_ex_flush=1`; `fetch_accept=0`; `advance_allowed=1`; `B` retires | `C` (held), bubble, `Lx`, `A` |
| 2 | `mem_wait=1` (`Lx` owns MEM, not granted); `load_use=0` (bubble in ID/EX) | `C`, bubble, `Lx`, `A` | All stalls `1`; `fetch_accept=0`; `advance_allowed=0`; no retire | Unchanged |
| 3 | `mem_wait=0` (`rvalid=1`, response available); `load_use=0` | `C`, bubble, `Lx`, `A` | All stalls and flushes `0`; `fetch_accept=1`; `advance_allowed=1`; `A` retires | `C` (ID/EX), `D` (IF/ID), bubble (EX/MEM), `Lx` completed (MEM/WB) |

At edge 3, `Lx` moves to MEM/WB and `C` moves to ID/EX, so `C` reads `x5` through MEM/WB forwarding
in its next EX cycle (BASE forwarding section). The load-use bubble and the MEM wait are separate
mechanisms (BASE register-file timing section).

### Trace 2: load-use behind a MEM wait (guard case), then response

Pre-edge: EX/MEM `S` (store, outstanding, waiting for its response); ID/EX `Lx` (`LW x5, 0(x2)`);
IF/ID `C` (uses `x5`); MEM/WB `B` (valid).

| Cycle / edge | Inputs (HCU) | State before | Outputs | State after |
| --- | --- | --- | --- | --- |
| 1 | `mem_wait=1` (`S` waits, `rvalid=0`); `load_use=1` | `C`, `Lx`, `S`, `B` | `id_ex_flush=0` (guard); all stalls `1`; `fetch_accept=0`; no retire | Unchanged |
| 2 | `mem_wait=0` (`rvalid=1` for `S`); `load_use=1` | `C`, `Lx`, `S`, `B` | `id_ex_flush=1`; `if_id_stall=1`; `fetch_accept=0`; `advance_allowed=1`; `B` retires | `C` (held), bubble (ID/EX), `Lx` (EX/MEM), `S` completed (MEM/WB) |

Cycle 3 continues as Trace 1 from its cycle 2: `Lx` now owns MEM and waits for its own response.

Without the guard, edge 1 would give `id_ex_flush = 1` while `id_ex_stall = 1`. PR-D1 gives flush
priority, so `Lx` would be cleared although BASE holds it. Edge 2 is the response-plus-load-use case
in section 5.3.

### Trace 3: EX redirect

Pre-edge: IF/ID `D1` (wrong-path); ID/EX `Bx` (taken branch, `mem_en = 0`); EX/MEM `A`; MEM/WB `B`
(valid). `fetch_valid=1`.

| Edge | Inputs (HCU) | State before | Outputs | State after |
| --- | --- | --- | --- | --- |
| R | `mem_wait=0`; `redirect_fire=1`; `load_use=0` (P2) | `D1`, `Bx`, `A`, `B` | `if_id_flush=1`; `id_ex_flush=1`; `ex_mem_stall=0`; `mem_wb_stall=0`; `fetch_accept=0`; `advance_allowed=1`; `B` retires | IF/ID invalid; ID/EX invalid; EX/MEM `Bx`; MEM/WB `A` |

No fetch entry is taken on R (`fetch_accept=0`). The Fetch Buffer's own redirect behavior (kill, target
allocation on the next edge) is in [fetch-stage.md](fetch-stage.md) §5.2 and is not part of the HCU.

### Trace 4: response plus redirect on one edge

Pre-edge: EX/MEM `Mx` (memory owner, outstanding); ID/EX `Bx` (taken branch); IF/ID `D1`; MEM/WB `B`.

| Edge | Inputs (HCU) | State before | Outputs | State after |
| --- | --- | --- | --- | --- |
| R | `rvalid=1` → `mem_wait=0`; `redirect_fire=1` (allowed because `advance_allowed=1`); `load_use=0` | `D1`, `Bx`, `Mx`, `B` | `if_id_flush=1`; `id_ex_flush=1`; stalls `0`; `fetch_accept=0`; `B` retires | IF/ID invalid; ID/EX invalid; EX/MEM `Bx`; MEM/WB `Mx` completed |

Without the response in the same cycle, `mem_wait=1`, `advance_allowed=0` and `redirect_fire=0`: the
branch waits in EX. The redirect is taken on the response edge, as BASE requires ("a redirect or
load-use event behind MEM may be processed without an extra release bubble").

## 8. Verification obligations

No HCU test exists. `tb/runners/` has no hazard runner (checked 2026-11-05). The checks below are
planned. Expected values come from the BASE rows and the equations in section 2, not from the DUT.

| Requirement/invariant | Stimulus or scenario | Expected observation |
| --- | --- | --- |
| Reset row (BASE pipeline-control priority) | `rst_n=0` with any other input | `advance_allowed=0`; `wb_retire_fire=0` through the WB leaf (WB-D2) |
| MEM wait row | `mem_wait=1`, `load_use=0`, `redirect_fire=0` | All four stalls `1`; both flushes `0`; `fetch_accept=0`; `advance_allowed=0` |
| Redirect row | `redirect_fire=1`, `mem_wait=0`, `load_use=0` | Both IF/ID and ID/EX flushes `1`; EX/MEM and MEM/WB stalls `0`; `fetch_accept=0`; `advance_allowed=1` |
| Load-use row | `load_use=1`, `mem_wait=0`, `redirect_fire=0` | `if_id_stall=1`; `id_ex_flush=1`; `id_ex_stall=0`; `fetch_accept=0` |
| Normal row | All inputs `0` | All stalls and flushes `0`; `fetch_accept=1`; `advance_allowed=1` |
| MEM wait with load-use (guard) | `mem_wait=1` and `load_use=1` (Trace 2, cycle 1) | `id_ex_flush=0`; ID/EX holds the load. A falsifying implementation without `!mem_wait` gives `id_ex_flush=1` |
| Response plus load-use | `mem_wait=0`, `load_use=1` on a response edge (Trace 2, cycle 2) | Load-use row values, and the BASE response-plus-load-use outcome |
| Response plus redirect | `mem_wait=0`, `redirect_fire=1` (Trace 4) | Redirect row values |
| Load-use bubble and release | Trace 1, cycles 1–3 | Bubble on cycle 1; hold on cycle 2; release and `fetch_accept=1` on cycle 3 |
| Redirect frontend effect | Trace 3 | `fetch_accept=0` on R |
| No stall and flush together | Any input within P1 and P2 | `if_id_stall & if_id_flush = 0`; `id_ex_stall & id_ex_flush = 0` |
| `fetch_accept` consistency (D-3) | Any input within P1 and P2 | `fetch_accept = !if_id_stall && !if_id_flush`; on `fetch_fire = fetch_valid && fetch_accept` the Fetch Buffer frees one entry and IF/ID captures a valid entry; with `fetch_valid = 0` no entry moves |
| Precondition P1 and P2 | Excluded inputs (`redirect_fire=1` with `mem_wait=1` or `load_use=1`) | Outside the contract; not driven in HCU tests |
| Stateless (section 4) | Interface and elaboration | No clock input, no register, no latch |

Boundaries: these checks cover the HCU's combinational outputs for the listed vectors. They do not show
the pipeline registers' valid and payload behavior, the Fetch Buffer's response to `fetch_accept`, or
whole-core execution.

## 9. Rationale and open decisions

### Decisions recorded (Owner, 2026-11-05)

Settled by the Owner, 2026-11-05. Numbers HCU-O1 onward are local to this document.

- **HCU-O1 (boundary).** One purely combinational module with no `clk` and no state. It detects
  load-use and turns MEM wait, redirect and load-use into per-register `stall` and `flush`, `fetch_accept`
  and `advance_allowed`. It does not create `redirect_fire`, does not route redirect to IF (raw EX to IF,
  fetch-stage F-e), does no forwarding, and produces no `valid_i`.
- **HCU-O2 (name).** Module and file `hazard_control_unit`, `rtl/hazard_control_unit.sv`. The RTL is
  written by Việt. The instance name belongs to the later core top design.
- **HCU-O3 (four stalls, no EX/MEM or MEM/WB flush).** Four separate `stall` outputs. The EX/MEM and
  MEM/WB `flush` inputs are never 1 in BASE: the HCU has no output for them, and the core top ties them to 0.
- **HCU-O4 (`rst_n` input).** `rst_n` is an input only so that `advance_allowed = 0` during reset
  (WB-D2).
- **HCU-O5 (`fetch_accept` option A).** `fetch_accept = !if_id_stall && !if_id_flush`. It is 0 on a
  redirect edge. The Fetch Buffer would behave the same with 1, because `kill` frees `READY` entries
  whatever `fetch_accept` is. Option A is chosen so the HCU does not depend on that buffer detail.
- **HCU-O6 (equations).** The equations in section 2, settled by the Owner, 2026-11-05.
- **HCU-O7 (`!mem_wait` in `id_ex_flush`).** PR-D1 gives flush priority over stall. Without this guard, a
  store waiting in MEM, a load in EX and its consumer in ID would erase the load (Trace 2).
- **HCU-O8 (no guard elsewhere).** `redirect_fire` and `mem_wait` are never both 1 (P1, enforced by
  `redirect_unit`). `redirect_fire` and `load_use` are never both 1 (P2, because the one EX entry cannot be
  a load and a control-flow instruction). BASE's "redirect wins" therefore costs no logic, and at IF/ID
  flush beats stall anyway.

### Open items

None inside this document's boundary. Every row of the BASE next-state table is traced to the equations
(section 5.2). The combined cases are in section 5.3: MEM wait with load-use, response plus load-use, and
response plus redirect.

### What can proceed and what stays blocked

- Done: the HCU RTL, `rtl/hazard_control_unit.sv`, against section 2 and section 5. This design closes D-3
  in [fetch-stage.md](fetch-stage.md).
- Blocked for integration, not for the HCU design: the IF/ID, ID/EX, EX/MEM and MEM/WB registers and the
  core top are not written. The sources of `id_valid`, `ex_valid`, `ex_mem_en`, `ex_mem_write` and `ex_rd`
  are therefore not yet checked against RTL.
- Not established by this document: any simulation result, any timing or area number, and any behavior of
  the core as a whole. Section 8 lists obligations only.
- Extensions (for example the IRQ profile) state their own additions to the next-state rows. They are not
  part of this document.
