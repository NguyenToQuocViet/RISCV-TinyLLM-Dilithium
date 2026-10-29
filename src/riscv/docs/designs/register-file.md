# Register File — Block Design

**Status:** Accepted by Việt on 2026-10-29; Owner decisions R1–R4 stated on 2026-10-29 are
recorded here for acceptance, with the resolution of O1 (section 9).
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Design revision:** RF D1 / 2026-10-29 (draft).
**Parent contract:** [Decode stage](decode-stage.md) (sections 2, 3, 4, 8; D3),
[BASE register-file timing and WB-to-ID bypass](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass),
[BASE reset architecture](5-stage-baseline-core.md#reset-architecture) and
[writeback-stage.md](writeback-stage.md) (sections 1, 2).
**RTL mapping:** Planned module `register_file`, instance `id_register_file` in
`decode_stage`; no RTL exists. This document is neither implementation nor
verification evidence.

## 1. Purpose and boundary

`register_file` holds the architectural registers `x1`–`x31` and provides the
two ID read values with the WB-to-ID bypass applied. Observable success
criterion: each read port returns the value defined by the read priority in
section 5, and a write changes exactly the register named by `wb_rd` at the
rising edge when `rf_write_fire=1`.

Non-goals:

- No reset (BASE: `x1`–`x31` not reset).
- No hazard detection, forwarding to EX, valid input or stall input.
- No debug or observation port (R3).
- No decode or instruction knowledge; it sees only register indices and data.

Inherited by reference, not restated: 32 architectural registers of
`DATA_WIDTH` bits, two combinational read ports, one rising-edge write port,
`x0` reads zero, no falling-edge write, no dependence on read-during-write
behavior of the storage (BASE register-file timing). WB owns `wb_data` and
`rf_write_fire`; this leaf owns storage, read ports and read-port forwarding
(writeback-stage.md sections 1, 2). Local refinements are R1–R4 below.

## 2. Interface contract

### Clock, reset and configuration

`clk`, rising edge, clocks the write only. No reset port (decode-stage.md D3).
No parameters: 32 registers, 5-bit indices, `riscv_pkg::DATA_WIDTH` data, with
the supported configuration `DATA_WIDTH = 32`.

### Ports and payloads

Port names equal the `decode_stage` names, so `decode_stage` only wires them
(R1). There are 6 inputs and 2 outputs.

| Port | Direction | Type / width | Meaning | Valid when |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1-bit `logic` | Write clock | Always |
| `rs1_id`, `rs2_id` | Input | `logic [4:0]` each | Read indices, one per port | Any value, any cycle; an unused source is still read |
| `rf_write_fire` | Input | 1-bit `logic` | WB permission to write `wb_rd` with `wb_data` at the rising edge | Driven by WB; exactly once per retirement edge |
| `wb_rd` | Input | `logic [4:0]` | Write index | Consumed only when `rf_write_fire=1` |
| `wb_data` | Input | `logic [DATA_WIDTH-1:0]` | Write and bypass data | Consumed only when `rf_write_fire=1` |
| `rs1_value`, `rs2_value` | Output | `logic [DATA_WIDTH-1:0]` each | Read result per section 5 | Defined except for a read of a register never written (section 6) |

All vectors are unsigned bit patterns. No width conversion exists in this leaf.
The guaranteed input domain contains only 0 and 1 (O1); X/Z behavior is
unspecified and untested, as in the accepted [EX](execute-stage.md#6-verification-and-delivery-boundaries)
and [WB](writeback-stage.md#6-reset-cancellation-and-exceptional-conditions)
contracts.

### Transfer and timing rules

- **Reads.** Combinational. `rs1_value` depends on `rs1_id`, `rf_write_fire`,
  `wb_rd`, `wb_data` and storage; `rs2_value` likewise on `rs2_id`. There is no
  clock dependence, latency or handshake. Each port applies the priority
  independently.
- **Write.** At the rising edge of `clk`, inputs sampled before the edge decide
  the update (section 5). Setup and hold belong to the core.
- **Read-during-write.** A read in the cycle of a write sees `wb_data` through
  the bypass, never the storage. The result does not depend on any simulator or
  storage read-during-write behavior. After the edge, storage holds the new
  value and the read returns it from storage.
- **Environment precondition.** WB and the core assert `rf_write_fire` for one
  retirement edge only; a held WB entry gives `rf_write_fire=0` (BASE, WB
  section 5). The RF cannot detect a repeated `rf_write_fire` and does not try.

## 3. Internal organization

Storage of 31 entries of `DATA_WIDTH` bits for `x1`–`x31` (R2), a write-index
decode enabled by `rf_write_fire` with `wb_rd != 0`, and per read port an index
mux over storage followed by the bypass and `x0` selection. No storage exists
for `x0`. How the 31 entries map to array indices, the internal storage name
(R3) and the coding style are implementation freedom.

## 4. State and ownership

| State | Meaning and owner | Update event | Hold rule | Reset |
| --- | --- | --- | --- | --- |
| `x1`–`x31` | Architectural registers; this leaf | Rising edge with `rf_write_fire=1` and `wb_rd = k`, `k != 0`: `xk <= wb_data` | Retained otherwise | None; unspecified until written, software initializes before use |
| `x0` | Not stored | Never written | — | Read returns zero through the read priority |

No valid, pending or control state exists. `rf_write_fire` is the only write
authorization (WB qualifies validity and retirement), so an invalid pipeline
entry cannot write.

## 5. Behavioral rules

Read priority, applied independently to each port (`rs_id` is `rs1_id` or
`rs2_id`; BASE):

```text
if rs_id == 0:
    rs_value = 0
else if rf_write_fire && rs_id == wb_rd:
    rs_value = wb_data
else:
    rs_value = x[rs_id]
```

Write, at each rising edge (R2):

```text
if rf_write_fire && wb_rd != 0:
    x[wb_rd] <= wb_data
```

`wb_rd = 0` with `rf_write_fire = 1` has no target and changes no storage.
WB's `rd != 0` term in `rf_write_fire` stays, but the RF does not rely on it:
`x0` behavior is guaranteed by this leaf alone (R2).

### Concurrent cases

Every case has one outcome. "Stored" means the storage value before the edge.

| Condition (same cycle) | Port outputs | Storage after the edge |
| --- | --- | --- |
| `rf_write_fire=1`, `wb_rd=k≠0`, `rs1_id=k`, `rs2_id=j≠k`, `j≠0` | `rs1_value=wb_data`; `rs2_value=x[j]` stored | `xk=wb_data`; others unchanged |
| `rf_write_fire=1`, `wb_rd=k≠0`, `rs1_id=rs2_id=k` | Both `wb_data` | `xk=wb_data` |
| `rf_write_fire=1`, `wb_rd=k≠0`, `rs1_id=j`, `rs2_id=k`, `j∉{0,k}` | `rs1_value=x[j]`; `rs2_value=wb_data` | `xk=wb_data` |
| `rf_write_fire=0`, `wb_rd` equals a read index | Stored value on that port; no bypass | Unchanged |
| `rf_write_fire=1`, `wb_rd=0`, `rs_id≠0` | Stored value (no match: `rs_id≠wb_rd`) | Unchanged |
| `rf_write_fire=1`, `wb_rd=0`, `rs_id=0` | `0` | Unchanged |
| Any `rf_write_fire`, `rs_id=0` | `0` | Per write rule |
| `rf_write_fire=1`, `wb_rd=k≠0`, port reads `j≠k` | Stored `x[j]`, unaffected by the write | `xj` unchanged |
| Read of a register never written, `rf_write_fire=0` or index not matching | Unspecified | — |

Only one write port exists, so there is no write-write conflict in a cycle.
Consecutive writes to the same register on consecutive edges leave the later
value.

## 6. Reset, cancellation and exceptional conditions

- **Reset.** None. After reset assertion the register contents are retained or
  unspecified; no value is guaranteed for `x1`–`x31` until written. Valid
  gating in the core and `rf_write_fire` from WB keep reset from writing
  (BASE reset architecture).
- **Read before write.** A read of a register that has never been written
  returns an unspecified value; the bypass case (the register is being written
  this cycle) is defined. No oracle may use an unspecified read.
- **Stall, flush, redirect.** The leaf has no stall or flush input. An
  unresolved MEM wait gives `rf_write_fire=0` (BASE), so no write occurs; on
  the release edge the one retiring write happens once. A younger redirect does
  not cancel an older WB write.
- **Out of scope.** Misuse such as a repeated `rf_write_fire` for one
  retirement is an environment violation; no error mechanism exists. X/Z
  input values are outside the guaranteed domain (O1).

## 7. Representative traces

Initial storage: `x7 = 0x1111_1111`, `x8 = 0x2222_2222`. Values are sampled
just before each rising edge. The rows can be used directly as test vectors.

| Edge | Inputs before the edge | Read outputs before the edge | Action | Storage after |
| --- | --- | --- | --- | --- |
| E1 | `rf_write_fire=1`, `wb_rd=7`, `wb_data=0xDDDD_DDDD`, `rs1_id=7`, `rs2_id=8` | `rs1_value=0xDDDD_DDDD` (bypass), `rs2_value=0x2222_2222` | `x7 <= 0xDDDD_DDDD` | `x7=0xDDDD_DDDD`, `x8=0x2222_2222` |
| E2 | `rf_write_fire=0`, `wb_rd=7`, `wb_data=0xEEEE_EEEE`, `rs1_id=7`, `rs2_id=7` | Both `0xDDDD_DDDD` (storage; `wb_data` ignored) | none | `x7=0xDDDD_DDDD` |
| E3 | `rf_write_fire=1`, `wb_rd=0`, `wb_data=0xEEEE_EEEE`, `rs1_id=0`, `rs2_id=8` | `rs1_value=0x0000_0000`, `rs2_value=0x2222_2222` | no write | `x7=0xDDDD_DDDD`, `x8=0x2222_2222` |

Trace E1 followed by E2 is the write-then-read case: the value arrives at the
read port one cycle before it is in storage and remains afterwards.

## 8. Verification obligations

Planned leaf-level checks; none exists yet. Expected values are literals taken
from the BASE read priority and R1–R4, never from the DUT. Stimulus timing
follows the conventions in `tb/README.md`. A leaf pass proves only these
vectors; it does not show decode integration, hazards or whole-core behavior.
Composition-level RF checks stay in [decode-stage.md section 8](decode-stage.md#8-verification-obligations).

| Requirement | Scenario | Expected observation |
| --- | --- | --- |
| Write and storage | Write a distinct pattern to each of `x1`–`x31`, then read all back | Each returns its own pattern; no aliasing or index shift |
| Data width | Patterns `0xFFFFFFFF`, `0xA5A5A5A5`, `0x5A5A5A5A` | All 32 bits stored and returned |
| Write isolation | Write `xk`, read all other registers | Only `xk` changes |
| Bypass, each port | `rf_write_fire=1`, read index equals `wb_rd`, on port 1 and on port 2 separately | That port returns `wb_data`; the other returns its stored value |
| Bypass, both ports | Both ports read the written index | Both return `wb_data` |
| Read-during-write independence | Sample the read before the edge, after the edge | Before: `wb_data`; after: the same value from storage |
| No bypass without fire | `rf_write_fire=0`, `wb_rd` equals a read index, `wb_data` differs from stored | Stored value |
| `x0` read | Read index 0 with and without `rf_write_fire`, with `wb_rd` 0 and nonzero | `0` always |
| `x0` write ignored | `rf_write_fire=1`, `wb_rd=0`, `wb_data` nonzero, then read `x1`–`x31` and `x0` | No register changed; `x0` reads `0` |
| Consecutive writes | Same register on consecutive edges | Later value; earlier value never observed after its edge |
| Read before write | Read of an unwritten register | Not an oracle |

## 9. Rationale and open decisions

### Decisions recorded for acceptance

Stated by the Owner on 2026-10-29. This document becomes their record on
acceptance.

| Id | Decision | Reason |
| --- | --- | --- |
| R1 | Port names equal the stage names; `decode_stage` is pure wiring | No renaming layer; matches decode-stage.md |
| R2 | Storage holds only `x1`–`x31`; the RF guarantees `x0` itself: read of index 0 returns zero through the read priority, write with `wb_rd=0` has no target; WB's `rd != 0` term stays but is not relied on | Safe independent of WB; no storage for `x0` |
| R3 | No debug or observation port; core verification observes architectural results black-box (self-checking programs writing a memory signature); hierarchical storage access is for debugging only, not an oracle; internal storage name not fixed | Keeps the interface minimal |
| R4 | Safe, no added logic beyond what safety requires (decode-stage.md D6) | ID design principle |

### Resolution of O1

Stated by the Owner on 2026-10-29.

| Id | Resolution | Reason |
| --- | --- | --- |
| O1 | The guaranteed input domain is 0/1 only; X/Z behavior is unspecified and untested | Same as the accepted EX and WB contracts; no extra logic (R4) |

No open item remains within this document's boundary.

Independent work that can proceed: the immediate-generator block design.
Blocked until acceptance: `register_file` RTL and leaf tests. A pass of the
planned checks would not establish integration with `decode_stage`, the core or
timing.
