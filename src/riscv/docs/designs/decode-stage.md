# Decode Stage — Block Design

**Status:** Accepted by Việt on 2026-10-29 — composition-level draft; owner decisions D1–D7 stated on
2026-10-29 and resolutions O1–O7 are recorded here for acceptance (section 9).
The ID D2 amendment `INSTR_WIDTH` (O7-R, section 9) is `accepted by Việt on 2026-10-29.`.
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Design revision:** ID D2 / 2026-10-29 (draft; D2 amends O7 only).
**Parent contract:** [Five-stage BASE core](5-stage-baseline-core.md), in
particular [ID decode contract](5-stage-baseline-core.md#id-decode-contract),
[instruction semantic table](5-stage-baseline-core.md#instruction-semantic-table),
[ID/EX boundary](5-stage-baseline-core.md#idex-boundary),
[register-file timing and WB-to-ID bypass](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass)
and [reset architecture](5-stage-baseline-core.md#reset-architecture).
**RTL mapping:** Planned; no `decode_stage`, `register_file`,
`immediate_generator` or `control_unit` RTL exists. This document is neither
implementation nor verification evidence.

## 1. Purpose and boundary

`decode_stage` is the BASE ID stage as one wrapper. From the IF/ID
`instruction` it produces the canonical immediate, the two register-source
values (after the WB-to-ID bypass), the register identifiers, the semantic
control for EX/MEM/WB, and the source-use qualifiers. It is the sole owner of
instruction decode; no other stage re-decodes (BASE ID decode contract).

Observable success criterion: for each of the 38 supported BASE operations the
outputs equal the BASE semantic tables; for any other encoding the three
side-effect enables are inactive (section 5).

Non-goals:

- No hazard detection. Load-use affects IF and ID, so it belongs to a later
  core-level Hazard Control Unit (D2). `decode_stage` only exports the inputs
  that unit needs.
- No pipeline storage. IF/ID and ID/EX registers, their valid, stall, flush and
  reset belong to the core ([pipeline-register control](5-stage-baseline-core.md#pipeline-register-local-control)).
- No trap, illegal-instruction flag, error port or recovery for unsupported
  encodings (D4).
- No CSR, CI, IRQ or other extension decode; BASE profile only.

Producers and consumers: IF/ID supplies `instruction`; WB and the core supply
the register-file write; the core routes the outputs into ID/EX and to the
future Hazard Control Unit. EX, MEM and WB consume the carried fields through
their own contracts.

## 2. Interface contract

### Clock, reset and configuration

`clk` is the only clock; rising edge. It is used by `register_file` alone.
There is **no reset port**: `register_file` is not reset (BASE reset
architecture: `x1`–`x31` not reset, `x0` reads zero) and the other two leaves
are combinational (D3). No parameters. The supported configuration is
`DATA_WIDTH = ADDR_WIDTH = 32` from `riscv_pkg`.

### Ports and payloads

All ports are individual signals; no packed payload struct. Types refer to
`riscv_pkg`. There are 5 inputs and 19 outputs.

| Signal | Direction | Type / width | Meaning | Valid when |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1-bit `logic` | Clock for the register-file write | Always |
| `instruction` | Input | `logic [INSTR_WIDTH-1:0]` | IF/ID instruction word (`IALIGN=32`) | Meaningful only for a live IF/ID entry; core owns validity |
| `rf_write_fire` | Input | 1-bit `logic` | WB permission to write `wb_rd` with `wb_data` at the rising edge | From the WB stage; already excludes `rd=x0` |
| `wb_rd` | Input | `logic [4:0]` | MEM/WB destination register | When `rf_write_fire=1` |
| `wb_data` | Input | `logic [DATA_WIDTH-1:0]` | Selected architectural WB value | When `rf_write_fire=1` |
| `rs1_id`, `rs2_id` | Output | `logic [4:0]` each | Raw `instruction[19:15]`, `instruction[24:20]` | Always; raw field extraction, any encoding |
| `rd` | Output | `logic [4:0]` | Raw `instruction[11:7]` | Always; destination only if `reg_write=1` |
| `rs1_value`, `rs2_value` | Output | `logic [DATA_WIDTH-1:0]` each | Register values after the WB-to-ID bypass | Combinational from `rs*_id` and the write inputs |
| `rs1_used`, `rs2_used` | Output | 1-bit `logic` each | Semantic source-use qualifiers toward the core hazard logic; not ID/EX state | Supported encodings; don't care otherwise |
| `imm` | Output | `logic [DATA_WIDTH-1:0]` | Canonical 32-bit immediate | Supported classes that use an immediate |
| `reg_write` | Output | 1-bit `logic` | Semantic register-write intent | Always defined; `0` for unsupported (D5) |
| `mem_en` | Output | 1-bit `logic` | Data-memory access intent | Always defined; `0` for unsupported (D5) |
| `control_flow` | Output | `control_flow_t` | NONE / BRANCH / JAL / JALR | Always defined; `CF_NONE` for unsupported (D5) |
| `mem_write` | Output | 1-bit `logic` | `0` load, `1` store | Supported memory instructions |
| `mem_type` | Output | `mem_type_t` | Access width and load signedness | Supported memory instructions |
| `wb_src` | Output | 1-bit `logic` | `0` = EX result, `1` = load result; BASE assigns `1` to loads and `0` to every other register-writing instruction and to stores | Every supported instruction except branches and FENCE (BASE leaves those unspecified); don't care for unsupported encodings |
| `alu_op` | Output | `alu_op_t` | ALU operation | Supported classes that use the ALU |
| `alu_src_a` | Output | `alu_src_a_t` | First ALU operand source | Supported classes that use the ALU |
| `alu_src_b` | Output | `alu_src_b_t` | Second ALU operand source | Supported classes that use the ALU |
| `branch_kind` | Output | `branch_kind_t` | Branch comparison | Conditional branches |
| `result_src` | Output | `result_src_t` | ALU result or link selection | Instructions with an EX result |

Names `rs1_id`, `rs2_id`, `rs1_value`, `rs2_value`, `imm`, `alu_*`,
`branch_kind`, `result_src`, `control_flow`, `rd`, `reg_write`, `mem_*` and
`wb_src` match the EX flat wrapper ([Flat wrapper interface](execute-stage.md#flat-wrapper-interface)),
[memory-stage.md](memory-stage.md) and [writeback-stage.md](writeback-stage.md).
`wb_rd`, `wb_data` and `rf_write_fire` match the EX producer ports and the WB
outputs. `wb_src` stays a one-bit `logic`; no shared enum exists. `pc` and IF/ID `valid`
are not ports; the reason is recorded in section 9 (O2).

Width domains: `instruction` is the 32-bit instruction word, typed with
`riscv_pkg::INSTR_WIDTH` (O7-R), the width of the 32-bit base encoding
(`IALIGN=32`); it is not ILEN and not a configuration point. `imm`, `rs*_value` and `wb_data` belong to `DATA_WIDTH`. The
instruction-to-`imm` reconstruction follows BASE: I/S/B/J sign-extended, U in
bits `[31:12]` with zero low bits, B/J low bit zero. No other width crossing
exists.

### Transfer and timing rules

All outputs except the register-file write are combinational functions of
`instruction` and, for `rs*_value`, of `rf_write_fire`, `wb_rd`, `wb_data`.
The only clocked behavior is the register-file write at the rising edge. There
is no handshake, valid output or stall input; the core decides whether the
outputs are captured. `wb_data` comes from the registered MEM/WB entry through
the combinational WB leaf, so it creates no loop with the outputs.

## 3. Internal organization

### Hierarchy and naming (D1)

`decode_stage` contains exactly three leaves. Extracting `rs1`, `rs2` and `rd`
from `instruction` is wrapper wiring, not a leaf. Module and file names follow
the EX convention (function names, no `riscv_` prefix); instance names with the
`id_` prefix follow the EX `ex_` convention.

| Module | File basename | Instance name | Instantiated by |
| --- | --- | --- | --- |
| `decode_stage` | `decode_stage.sv` | `id_stage` | Core |
| `register_file` | `register_file.sv` | `id_register_file` | `decode_stage` |
| `immediate_generator` | `immediate_generator.sv` | `id_immediate_generator` | `decode_stage` |
| `control_unit` | `control_unit.sv` | `id_control_unit` | `decode_stage` |

```text
id_stage : decode_stage
  id_register_file       : register_file
  id_immediate_generator : immediate_generator
  id_control_unit        : control_unit
```

### Wiring

```text
instruction ──┬─ [19:15] ─► rs1_id ──► register_file ──► rs1_value
              ├─ [24:20] ─► rs2_id ──►   (+ write port) ─► rs2_value
              ├─ [11:7]  ─► rd
              ├────────────► immediate_generator ──────► imm
              └────────────► control_unit ─────────────► reg_write, mem_*, wb_src,
                                                          alu_*, branch_kind, result_src,
                                                          control_flow, rs1_used, rs2_used
rf_write_fire, wb_rd, wb_data ─────────► register_file write port
```

### Leaf responsibilities

Each leaf gets its own later block design; those documents are planned and do
not exist yet. This document does not restate their detail.

- **`register_file`** ([planned: register-file.md](register-file.md)). 32 × 32
  storage, two combinational read ports, one rising-edge write port gated by
  `rf_write_fire`; `x0` reads zero and ignores writes; per-port WB-to-ID
  bypass with the BASE priority; `x1`–`x31` not reset. It owns read-address
  matching and bypass selection (BASE register-file timing).
- **`immediate_generator`** ([planned: immediate-generator.md](immediate-generator.md)).
  Produces the single canonical `imm` from `instruction`. The format-selection
  rule for each supported class and the value for classes without an immediate
  belong to that document; no `immediate_kind` leaves ID.
- **`control_unit`** ([planned: control-unit.md](control-unit.md)). Recognizes
  the 38 supported operations from their complete RV32I encodings (D7) and
  produces all semantic control and the `rs*_used` qualifiers per the BASE
  tables. The exact field-check table and the per-class control values live in
  that document. It applies the side-effect guard of section 5.

## 4. State and ownership

The only storage is the register file, owned by `register_file`.

| State | Meaning and owner | Update event | Hold rule | Reset |
| --- | --- | --- | --- | --- |
| `x1`–`x31` | Architectural registers; `register_file` | Rising edge with `rf_write_fire=1`, written index `wb_rd` | Retained otherwise | None; software initializes before use |
| `x0` | Constant zero | Never written | — | Reads zero |

`decode_stage` holds no pipeline entry, valid bit or control state. The core
owns IF/ID and ID/EX and decides whether the combinational outputs are
captured. Invalid IF/ID payload must not authorize a side effect through the
core's valid gating; the guard in section 5 is independent of that.

## 5. Behavioral rules

**Field extraction.** `rs1_id = instruction[19:15]`, `rs2_id = instruction[24:20]`,
`rd = instruction[11:7]`, for every encoding, supported or not.

**Supported operations.** Outputs follow the BASE tables for each of the 38
operations: [`rs1_used`/`rs2_used`](5-stage-baseline-core.md#id-decode-contract),
[memory intent](5-stage-baseline-core.md#id-decode-contract),
[semantic decode, `reg_write` and `wb_src`](5-stage-baseline-core.md#instruction-semantic-table),
and the operand/ALU mapping of [execute-stage.md §4.2](execute-stage.md#42-operand-mux).
FENCE decodes as a live non-writing instruction with `reg_write=0`, `mem_en=0`,
`control_flow=CF_NONE`. `reg_write=1` stays the semantic value even when
`rd=x0`; the physical write is suppressed by `rf_write_fire` (BASE).

**Recognition (D7).** An operation is recognized only by its complete RV32I
encoding. Every other encoding is unsupported. The field-check table belongs to
the control-unit design.

**Unsupported encodings — side-effect blocking, not error handling (D4, D5).**
Unsupported encodings stay unsupported: there is no trap, no error flag and no
new port. For safety, when the encoding is not one of the 38 supported
operations, exactly these three outputs are forced inactive:

| Output | Forced value |
| --- | --- |
| `reg_write` | `0` |
| `mem_en` | `0` |
| `control_flow` | `CF_NONE` |

These three enables are the only ID outputs that can start a register write, a
memory access or a redirect. This is side-effect blocking only; the
instruction is not reported, replaced or retired differently.

**Don't-care outputs (D5, O5).** Every value the BASE instruction tables
assign to a supported instruction binds, for example `wb_src=0` for stores and
the `rs1_used`/`rs2_used` values of every supported class. The don't-care rule
applies only to (a) the non-enable outputs of an unsupported encoding and
(b) fields BASE leaves unspecified or unused for that class, such as
`mem_write`/`mem_type` for a non-memory instruction, `wb_src` for branches and
FENCE, and `imm` for a class without an immediate. For these the contract
assigns no value, and verification must not use them as an oracle. The affected
outputs are `imm`, `rs1_used`, `rs2_used`, `wb_src`, `mem_write`, `mem_type`,
`alu_op`, `alu_src_a`, `alu_src_b`, `branch_kind` and `result_src`.
`rs1_id`, `rs2_id` and `rd` are not in this list: they are raw extraction.

**Design principle (D6).** ID is safe with no added logic, or the minimum needed
for safety. The guard above is that minimum; no default vector, legality flag
or output cleanup is added.

## 6. Reset, cancellation and exceptional conditions

- **Reset.** None in `decode_stage`. Register contents are unspecified until
  written; `x0` reads zero. BASE reset keeps invalid stages from writing the
  register file (valid gating in the core, `rf_write_fire` from WB).
- **Flush, stall, load-use.** Outside this wrapper. The core flushes, holds or
  bubbles IF/ID and ID/EX; a held IF/ID presents the same `instruction`, so the
  combinational outputs are stable.
- **Unsupported encodings.** Outside BASE; no handling beyond section 5. The
  core may reach EX/MEM/WB with such an instruction carrying inactive enables.
- **Consequence for the Hazard Control Unit.** Because `rs*_used` is don't care
  for unsupported encodings, the future unit may insert a load-use bubble for
  one. This only delays the pipeline; it does not create an architectural side
  effect. The unit must not rely on `rs*_used` for unsupported encodings.
- **Consequence for EX/MEM/WB.** Don't-care outputs may carry any enum value.
  Reserved `alu_op` or operand-select codes may therefore appear for unsupported
  encodings; no logic is added to avoid them (O6). Fallback behavior for those
  codes stays in the EX leaf contracts, and EX checkers apply to supported
  instructions only.

## 7. Representative examples

Combinational; values follow the BASE tables, not any RTL.

| Instruction word | Class | Key outputs |
| --- | --- | --- |
| `LW x5, 8(x2)` | Load | `rs1_id=2`, `rd=5`, `rs1_used=1`, `rs2_used=0`, `imm=8`, `reg_write=1`, `mem_en=1`, `mem_write=0`, `mem_type=MEM_WORD`, `wb_src=1`, `alu_op=ALU_ADD`, `alu_src_a=ALU_A_RS1`, `alu_src_b=ALU_B_IMM`, `control_flow=CF_NONE` |
| `SW x6, 12(x2)` | Store | `rs1_used=1`, `rs2_used=1`, `imm=12`, `reg_write=0`, `mem_en=1`, `mem_write=1`, `mem_type=MEM_WORD`, `wb_src=0`, `control_flow=CF_NONE` |
| `JAL x1, +16` | Jump | `rs1_used=0`, `rs2_used=0`, `imm=16`, `reg_write=1`, `mem_en=0`, `control_flow=CF_JAL`, `result_src=RESULT_PC_PLUS_4`, `wb_src=0` |
| `ECALL` (`0x00000073`) | Unsupported | `reg_write=0`, `mem_en=0`, `control_flow=CF_NONE`; all other control outputs don't care; `rs1_id=0`, `rs2_id=0`, `rd=0` |
| `MUL x3, x4, x5` (funct7 `0000001`) | Unsupported | the same three forced values; `rs1_id=4`, `rs2_id=5`, `rd=3` (raw) |

Register-file case through the wrapper: write `x7` at edge E with
`rf_write_fire=1`, `wb_rd=7`, `wb_data=D`; before E, `rs1_id=7` already reads
`D` (bypass); after E it reads `D` from storage. With `rf_write_fire=0` and
`wb_rd=7` the bypass is inactive.

## 8. Verification obligations

Planned composition-level checks; none exists yet. Expected values come from
the BASE tables and the D1–D7 decisions, never from the DUT. Leaf-level
evidence belongs to the later leaf documents. The exact field-check table is
the oracle for recognition and exists only once the control-unit design is
accepted.

| Requirement | Scenario | Expected observation |
| --- | --- | --- |
| D1 hierarchy | Verilator elaboration of `decode_stage` | Exactly three leaves; no other instance |
| Raw extraction | Any encoding, supported or not | `rs1_id`, `rs2_id`, `rd` equal the instruction bit fields |
| BASE decode | Each of the 38 operations, all register-field combinations that matter (`rd=x0`) | Outputs equal the BASE tables for defined fields; don't-care fields not compared |
| D4/D5 guard | Unsupported words: all-zero, `0xFFFFFFFF`, `ECALL`, a CSR word, `FENCE.I`, `MUL`, `LD` (LOAD funct3 `011`), BRANCH funct3 `010`, SLLI with `imm[11:5]≠0` | `reg_write=0`, `mem_en=0`, `control_flow=CF_NONE`; no assertion on any other control output |
| D5 scope | Same words | No test uses `imm`, `rs*_used`, `wb_src`, `mem_*`, `alu_*`, `branch_kind` or `result_src` as an oracle |
| Immediate | One word per format | Canonical `imm` per BASE |
| RF through wrapper | Write then read; same-cycle bypass on each port independently; `rf_write_fire=0` with matching `wb_rd`; `x0` | BASE priority; `x0` reads zero; no bypass without `rf_write_fire` |
| No reset | Read before any write | Not an oracle; value unspecified |
| Port contract | Elaborate with EX wrapper, MEM and WB ports | Names and types connect without conversion |

Evidence boundary: a pass at this level shows only the stated vectors. It does
not show load-use, ID/EX storage, redirect, flush, timing or whole-core
behavior.

## 9. Rationale and open decisions

### Decisions recorded for acceptance

All stated by the Owner on 2026-10-29. This document becomes their record on
acceptance.

| Id | Decision | Reason |
| --- | --- | --- |
| D1 | Three leaves; field extraction is wiring | Visible hierarchy, as in EX |
| D2 | No load-use detector in ID; export `rs1_id`, `rs2_id`, `rs1_used`, `rs2_used` | Load-use affects IF and ID; core-level unit later |
| D3 | `register_file` inside `decode_stage`; ports `clk` and RF write inputs; no `rst_n` | Logical hierarchy; RF has no reset |
| D4 | Unsupported stays unsupported; no trap, flag or port | BASE has no illegal-instruction handling |
| D5 | Force `reg_write`, `mem_en`, `control_flow` inactive for unsupported encodings; other outputs don't care where BASE assigns nothing (O5) | Block side effects with minimum logic |
| D6 | Safe, with no added logic or the minimum for safety | ID design principle |
| D7 | Recognition only by complete RV32I encoding | Exact table in control-unit design |

### Resolutions of O1–O7

Stated by the Owner on 2026-10-29, after the open items of the first draft.

| Id | Resolution | Reason |
| --- | --- | --- |
| O1 | Instance names `id_stage`, `id_register_file`, `id_immediate_generator`, `id_control_unit` | Follows the EX `ex_` convention |
| O2 | Neither `pc` nor IF/ID `valid` is a `decode_stage` port | See below |
| O3 | RF write destination input is `wb_rd` | Matches the EX producer port; same net |
| O4 | `rd`, `reg_write`, `mem_en`, `mem_write`, `mem_type`, `wb_src` are `decode_stage` outputs | They originate in ID |
| O5 | BASE wins: every value the BASE tables assign to a supported instruction binds, including `wb_src=0` for stores; D5 don't-care applies only to fields BASE leaves unspecified or unused for the class and to non-enable outputs of unsupported encodings. No BASE edit | BASE stays the single source for instruction semantics |
| O6 | Reserved `alu_op` / operand-select codes may appear for unsupported encodings; no extra logic; EX checkers apply to supported instructions only | D6; unsupported encodings are outside BASE |
| O7 | `instruction` is `logic [31:0]` per `IALIGN=32`; no new `riscv_pkg` constant | BASE fixes 32-bit instructions. Revised by O7-R |
| O7-R | `riscv_pkg` gains `localparam int INSTR_WIDTH = 32`, in the style of `DATA_WIDTH` and `ADDR_WIDTH`; `instruction` is `logic [INSTR_WIDTH-1:0]`. `INSTR_WIDTH` names the width of the 32-bit base encoding (`IALIGN=32`), not ILEN, and is not a configuration point: the bit positions in [immediate-generator.md](immediate-generator.md) section 5 fix the value at 32. **was accepted by Việt on 2026-10-29.** (ID D2) | Naming consistency with `DATA_WIDTH`/`ADDR_WIDTH`; the instruction and data widths stay separate domains |

**O2 reason.** No block inside ID consumes `pc` or IF/ID `valid`. ID creates no
side effect of its own: the register-file write is authorized by WB's
`rf_write_fire`. Invalid decode output is discarded through ID/EX `valid`, which
the core takes from IF/ID valid. The core-level Hazard Control Unit qualifies
`rs1_used` and `rs2_used` with IF/ID valid. Gating outputs with valid would add
logic without a safety gain (D6).

No material question remains within this document's boundary. Independent work
that can proceed: the register-file block design (D3 and BASE fix its port set).
Blocked until acceptance: leaf RTL and any readiness claim for composition. The
control-unit field-check table (D7) and the immediate rules remain dependencies
of the leaf documents.
