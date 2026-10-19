# Redirect Unit — Block Design

**Status:** Accepted by Việt on 2026-10-19.
**Revision:** RU D2 / 2026-10-19; width clarification accepted by Việt.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [EX stage](execute-stage.md#47-redirect-unit),
[BASE redirect contract](5-stage-baseline-core.md#redirect-event-and-pipeline-recovery).
**Mapping:** Planned module `redirect_unit` in `src/riscv/rtl/redirect_unit.sv`;
instance `ex_redirect` in `execute_stage`.

## 1. Purpose and boundary

Qualify a branch/jump redirect and format its target from an already computed
ALU result. Instruction decode belongs to ID; target arithmetic belongs to the
[ALU](alu.md), and comparison belongs to the
[branch comparator](branch-comparator.md).

The leaf does not calculate a link value, flush pipeline registers, update the
fetch PC or arbitrate extension redirects. It contains no clock, reset, storage
or private `redirect_sent` state. Parent control owns pipeline advance and
suppression of side effects during reset and hold.

## 2. Interface, timing and state

Port names and the shared control representation below are accepted.
Design acceptance does not establish RTL correctness or verification results.

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `alu_result` | Input | Unsigned `logic [DATA_WIDTH-1:0]` | ALU datapath result containing the computed target |
| `branch_condition` | Input | 1-bit logic | Selected comparison result; consumed only for a conditional branch |
| `control_flow` | Input | `riscv_pkg::control_flow_t`, 2-bit enum (planned) | Decoded NONE / BRANCH / JAL / JALR intent |
| `instruction_valid` | Input | 1-bit logic | Current instruction is live |
| `advance_allowed` | Input | 1-bit logic | Parent permits the current instruction to leave EX |
| `redirect_fire` | Output | 1-bit logic | Qualified redirect event for the consuming edge |
| `redirect_target` | Output | Unsigned `logic [ADDR_WIDTH-1:0]` | Target address; meaningful when `redirect_fire=1` |

Target formatting crosses from the register/datapath domain to the address
domain under the parent's
[stage-boundary contract](execute-stage.md#3-stage-boundary-and-storage-ownership).
All bits except the JALR bit-zero adjustment are preserved; unequal-width
conversion is not supported.

The accepted shared type is `enum logic [1:0]` in `riscv_pkg`:

| Member | Code | Meaning |
| --- | --- | --- |
| `CF_NONE` | `2'b00` | No control-flow operation |
| `CF_BRANCH` | `2'b01` | Conditional branch |
| `CF_JAL` | `2'b10` | Direct jump |
| `CF_JALR` | `2'b11` | Register-indirect jump |

All four binary codes are assigned and mutually exclusive. This explicit
semantic selector keeps redirect behavior independent of operand-source
encoding; it replaces the proposed separate branch/jump intent flags rather
than adding another copy of that intent. `branch_kind` and `result_src` retain
their separate comparison and result-selection responsibilities.

ID produces control-flow intent; ID/EX carries it to this leaf. At integration,
`instruction_valid` is ID/EX valid. `advance_allowed` incorporates parent
reset/hold control and must not depend circularly on `redirect_fire`.
Outputs follow current inputs after combinational settling; the parent consumes
the event at its clock edge. The leaf does not generate a registered pulse.

## 3. Redirect behavior

| Decoded intent | Redirect requested | `redirect_target` |
| --- | --- | --- |
| No control-flow operation | Never | `alu_result`, unchanged |
| Conditional branch | When `branch_condition=1` | `alu_result`, unchanged |
| JAL | Always | `alu_result`, unchanged |
| JALR | Always | Complete `alu_result` with only bit 0 forced to zero |

Target formatting is independent of `instruction_valid`, `advance_allowed`,
`branch_condition` and `redirect_fire`. The target follows the current datapath
even when no redirect fires; it is not forced to zero and does not retain a
previous target. The parent must consume it only when `redirect_fire=1`.

`redirect_fire` requires all three: a redirect request, `instruction_valid=1`
and `advance_allowed=1`. Jump behavior is independent of the comparison result
and destination register, including rd=x0. A non-control-flow instruction never
redirects, even when the comparison result is true.

A held branch/jump cannot redirect during an unresolved MEM wait. When parent
control permits advance on the memory-response edge, the held instruction may
redirect and leave EX together. Parent pipeline recovery prevents replay; this
leaf neither tracks previous events nor cancels outstanding bus transactions.

## 4. Input validity and target formatting

The guaranteed input domain contains only 0/1; X/Z behavior remains outside
scope under the accepted pipeline policy. There is no error port or CPU trap.
JALR clears only bit 0; bit 1 is preserved. This formatting does not guarantee
four-byte alignment. Misaligned targets remain outside BASE.

## 5. Local decisions

All decisions below belong to Việt. Inherited behavior above is unchanged.

| ID | Decision | Accepted choice and consequence |
| --- | --- | --- |
| RU-D1 | ID-to-EX control representation | Accepted by Việt on 2026-10-19: shared 2-bit enum as defined in section 2, with explicit semantic intent independent of operand selection. |
| RU-D2 | Final port names | Accepted by Việt on 2026-10-19: use section 2 names, without an EX prefix or direction suffix. Their producer mapping remains an integration concern. |
| RU-D3 | Target output while no redirect fires | Accepted by Việt on 2026-10-19: target follows the datapath independently of fire, as defined in section 3. Parent consumption is qualified by fire; no extra zero-output selection is required. |

No open design decisions remain within this leaf's scope.
Verification obligations for redirect, hold/release and invalid pipeline state
remain in the [parent EX contract](execute-stage.md#6-verification-and-delivery-boundaries).
