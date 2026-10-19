# Forwarding Unit — Block Design

**Status:** Accepted by Việt on 2026-10-19.
**Revision:** FU D1 / 2026-10-19.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [EX stage](execute-stage.md#41-forwarding-unit),
[BASE forwarding rules](5-stage-baseline-core.md#forwarding-and-load-use-hazards).
**Mapping:** Planned module `forwarding_unit` in `src/riscv/rtl/forwarding_unit.sv`;
instance `ex_forwarding` in `execute_stage`.

## 1. Purpose and boundary

Select the current values of both register sources independently, using older
pipeline producers before falling back to the values carried in ID/EX.
Outputs feed operand selection, branch comparison and store data; the forwarded
RS1 also supplies the JALR base through operand selection.

The leaf includes selection and data muxing. It does not decode instructions,
read the register file, choose ALU operands, format load data, reconstruct a
jump link or generate a stall. ID load-use detection and parent MEM interlock
remain outside this block.

## 2. Interface, timing and state

All data vectors belong to `DATA_WIDTH`; register identifiers are unsigned
5-bit vectors and qualifiers are 1-bit logic. The parent's
[stage-boundary contract](execute-stage.md#3-stage-boundary-and-storage-ownership) applies.

| Port(s) | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `rs1_id`, `rs2_id` | Input | `logic [4:0]` each | Consumer register identifiers from ID/EX |
| `rs1_value`, `rs2_value` | Input | `logic [DATA_WIDTH-1:0]` each | Register values carried in ID/EX after ID's WB bypass |
| `mem_valid` | Input | 1-bit logic | EX/MEM producer is live |
| `mem_reg_write` | Input | 1-bit logic | Producer has semantic register-write intent |
| `mem_wb_from_mem` | Input | 1-bit logic | Producer's architectural result comes from memory; excludes its EX/MEM result from forwarding |
| `mem_rd` | Input | `logic [4:0]` | EX/MEM destination register |
| `mem_result` | Input | `logic [DATA_WIDTH-1:0]` | Selected EX result, including jump link; a load address is not load data |
| `wb_valid` | Input | 1-bit logic | MEM/WB producer is live |
| `wb_reg_write` | Input | 1-bit logic | Producer has semantic register-write intent |
| `wb_rd` | Input | `logic [4:0]` | MEM/WB destination register |
| `wb_data` | Input | `logic [DATA_WIDTH-1:0]` | Selected architectural writeback value, including formatted load data |
| `fwd_rs1`, `fwd_rs2` | Output | `logic [DATA_WIDTH-1:0]` each | Selected register-source values |

The leaf is combinational: no clock, reset, storage, handshake or private hold
state. Both outputs follow current inputs after settling, including while EX
is held. Producer stages own payload stability and validity. No retirement or
RF-write pulse qualifies forwarding: a held MEM/WB producer remains usable.

## 3. Selection contract

The following refines the inherited priority using the accepted interface.
Apply it independently to each source identifier and its carried value:

| Priority | Matching producer eligibility | Selected value |
| --- | --- | --- |
| 1 | `mem_valid && mem_reg_write && !mem_wb_from_mem && mem_rd != 0`, with destination matching the source | `mem_result` |
| 2 | `wb_valid && wb_reg_write && wb_rd != 0`, with destination matching the source | `wb_data` |
| 3 | No eligible matching producer | Corresponding `rs1_value` or `rs2_value` |

Both sources can select the same producer or different producers. Selection
preserves all data bits without signed conversion or arithmetic. Neither an
invalid producer, a non-writer nor a destination x0 can override a source.
For a source identifier x0, no producer can match while remaining eligible.
The output therefore follows the corresponding carried source value through
the ordinary fallback. The leaf does not add a separate source-x0 zero override.

EX/MEM loads remain ineligible even on their response edge; their completed
data becomes a forwarding source from MEM/WB. Parent hazard/interlock control
must prevent consumption while the nearest older writer to that source is still
unavailable; selecting an older WB value during a hold does not resolve that
dependency. This leaf neither signals readiness to EX nor repairs a missing
load-use stall.

## 4. Input validity

The guaranteed domain contains only 0/1; X/Z behavior remains outside scope.
ID/EX must supply zero for a consumed source x0. Standalone legal-input tests
must likewise supply zero when a source identifier is x0; a nonzero carried
value is outside this precondition, not an input the leaf repairs.
Invalid producer payload is ignored through its valid qualifier. The leaf
has no consumer-valid or source-use inputs:
parent control ignores outputs for invalid entries or unused sources.
There is no error port or CPU trap.

## 5. Local decisions

All local decisions below were accepted by Việt on 2026-10-19.

| ID | Decision | Accepted choice and consequence |
| --- | --- | --- |
| FU-D1 | How to express EX/MEM availability | Accepted by Việt on 2026-10-19: receive `mem_wb_from_mem` with valid/write intent/destination and exclude loads inside the leaf. Parent supplies decoded semantic facts rather than a precomputed availability qualifier. |
| FU-D2 | Final interface | Accepted by Việt on 2026-10-19: use the flat ports in section 2, with mem/wb names identifying producer stages and priority. Return forwarded data directly, without public mux selectors or consumer-valid/use ports. |
| FU-D3 | Consumer source x0 | Rely on ID/EX supplying x0=0 and use the ordinary fallback. Exclude every producer with rd=x0; do not add a separate zero-selection path. Legal standalone tests must supply the same x0 input invariant. |

No open design decisions remain within this leaf's scope. Acceptance defines
intended behavior and does not constitute RTL implementation or verification.

Integration verification remains owned by the
[parent EX contract](execute-stage.md#6-verification-and-delivery-boundaries).
