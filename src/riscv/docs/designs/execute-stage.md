# Execute Stage

| Field | Value |
| --- | --- |
| Description | Combinational execution, forwarding and control-flow resolution. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/execute_stage.sv`, module `execute_stage`, instance name `ex_stage` |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md) (EX computation contract, forwarding rules, redirect contract, pipeline priority, ID/EX and EX/MEM boundaries, reset architecture); [Hazard control unit](hazard-control-unit.md); [Decode stage](decode-stage.md) (O6); [Writeback stage](writeback-stage.md); the seven leaves ([forwarding unit](forwarding-unit.md), [operand mux](operand-mux.md), [ALU](alu.md), [branch comparator](branch-comparator.md), [link adder](link-adder.md), [result mux](result-mux.md), [redirect unit](redirect-unit.md)) |

## 1. Overview

- `execute_stage` is the BASE EX stage. It computes `ex_result`, `store_data`, `redirect_fire` and `redirect_target` for the instruction in ID/EX.
- It composes the seven leaves of section 4 and has one function of its own, the wiring of `store_data`. The leaf specs own the leaf behavior.
- BASE owns instruction semantics, forwarding eligibility, memory ordering and side-effect rules, and this spec refines them without overriding them.
- It is combinational, with no clock, reset or state.
- It decodes nothing: raw instruction, opcode, funct fields and immediate format never enter it, and `imm` arrives as the canonical 32-bit value built in ID.
- It has no error, stall or output-valid port.
- It does not write the register file or issue OBI, because EX computes the store address and data and MEM owns the request.
- It does not carry the current-instruction metadata, which the core connects from ID/EX to EX/MEM ([EX-D8](#10-decisions-and-open-items)).
- CI, CSR/MRET, IRQ, cache and prediction are outside it, and a later extension must keep the BASE behavior and define its own override.

## 2. Block Design

```text
                                                  +------------------------+
pc, imm, rs1_id, rs2_id <- ID/EX register         |                        |
rs1_value, rs2_value, alu_op <- ID/EX register    |                        | -> ex_result, store_data (EX/MEM register)
alu_src_a, alu_src_b <- ID/EX register            |                        |
branch_kind, control_flow <- ID/EX register       |                        | -> redirect_fire (fetch_stage)
result_src, instruction_valid <- ID/EX register   |     execute_stage      | -> redirect_fire (hazard_control_unit)
mem_rd, mem_result, mem_valid <- EX/MEM register  |                        |
mem_reg_write, mem_wb_src <- EX/MEM register      |                        | -> redirect_target (fetch_stage)
wb_rd, wb_valid, wb_reg_write <- MEM/WB register  |                        |
wb_data <- writeback_stage                        |                        |
                                                  +------------------------+
                                                              ^
                                                      advance_allowed <- hazard_control_unit
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `pc` | Input | `ADDR_WIDTH` | ID/EX register | Address of the instruction in EX. |
| `imm` | Input | `DATA_WIDTH` | ID/EX register | Canonical immediate built in ID. |
| `rs1_id` | Input | 5 | ID/EX register | Source register identifier. |
| `rs2_id` | Input | 5 | ID/EX register | Source register identifier. |
| `rs1_value` | Input | `DATA_WIDTH` | ID/EX register | Register value after the WB bypass in ID. |
| `rs2_value` | Input | `DATA_WIDTH` | ID/EX register | Register value after the WB bypass in ID. |
| `alu_src_a` | Input | `alu_src_a_t` (2) | ID/EX register | Source of the first ALU operand. |
| `alu_src_b` | Input | `alu_src_b_t` (1) | ID/EX register | Source of the second ALU operand. |
| `alu_op` | Input | `alu_op_t` (4) | ID/EX register | ALU operation. |
| `branch_kind` | Input | `branch_kind_t` (3) | ID/EX register | Conditional-branch comparison. |
| `control_flow` | Input | `control_flow_t` (2) | ID/EX register | `CF_NONE`, `CF_BRANCH`, `CF_JAL` or `CF_JALR`. |
| `result_src` | Input | `result_src_t` (1) | ID/EX register | ALU result or link selection. |
| `instruction_valid` | Input | 1 | ID/EX register | The instruction in EX is live. |
| `advance_allowed` | Input | 1 | `hazard_control_unit` | The hazard control unit permits the instruction to leave EX this cycle. |
| `mem_rd` | Input | 5 | EX/MEM register | Destination register of the EX/MEM producer. |
| `mem_result` | Input | `DATA_WIDTH` | EX/MEM register | Selected EX result of that producer. |
| `mem_valid` | Input | 1 | EX/MEM register | The EX/MEM producer is live. |
| `mem_reg_write` | Input | 1 | EX/MEM register | Register-write intent of the EX/MEM producer. |
| `mem_wb_src` | Input | 1 | EX/MEM register | `0` for the EX result, `1` for the load result. |
| `wb_rd` | Input | 5 | MEM/WB register | Destination register of the MEM/WB producer. |
| `wb_data` | Input | `DATA_WIDTH` | `writeback_stage` | Selected writeback value of that producer. |
| `wb_valid` | Input | 1 | MEM/WB register | The MEM/WB producer is live. |
| `wb_reg_write` | Input | 1 | MEM/WB register | Register-write intent of the MEM/WB producer. |
| `ex_result` | Output | `DATA_WIDTH` | EX/MEM register | Selected EX result. |
| `store_data` | Output | `DATA_WIDTH` | EX/MEM register | Store data. |
| `redirect_fire` | Output | 1 | `fetch_stage`, `hazard_control_unit` | A valid instruction permitted to advance redirects this cycle. |
| `redirect_target` | Output | `ADDR_WIDTH` | `fetch_stage` | Redirect address, meaningful when `redirect_fire` is 1. |

- `DATA_WIDTH` is the GPR and ALU width (XLEN here) and not a memory-bus width.
- `ADDR_WIDTH` is the PC and redirect address domain and defines no virtual or physical mapping.
- Both are 32, as BASE requires. The two names separate roles and promise no independent width and no RV64.
- The enum types come from `riscv_pkg`, and the leaf specs own their encodings, so the stage adds no selector type ([EX-D9](#10-decisions-and-open-items)).
- The `mem_*` and `wb_*` inputs are the producer facts that forwarding consumes.

### Width domains

| Domain | Package constant | EX values |
| --- | --- | --- |
| Register and arithmetic datapath | `DATA_WIDTH` | Register values, `imm`, ALU operands and result, forwarded values, `ex_result`, `store_data` |
| PC and redirect address | `ADDR_WIDTH` | `pc`, the link value (`pc` plus 4), `redirect_target` |

### Width crossings

| Boundary | Source | Destination |
| --- | --- | --- |
| Operand selection of `pc` | `pc`: `ADDR_WIDTH` | The first ALU operand: `DATA_WIDTH` |
| Link selection | The link value: `ADDR_WIDTH` | `ex_result`: `DATA_WIDTH` |
| Redirect target formatting | The ALU result: `DATA_WIDTH` | `redirect_target`: `ADDR_WIDTH` |

- A crossing keeps every bit in this configuration, and no widening, narrowing or translation policy exists at it.
- Unequal widths need an Owner-approved contract update before implementation, because implicit assignment conversion is not an accepted policy.

## 4. Internal Structure

| Module | Instance | File | Spec |
| --- | --- | --- | --- |
| `execute_stage` | `ex_stage` | `rtl/execute_stage.sv` | This spec |
| `forwarding_unit` | `ex_forwarding` | `rtl/forwarding_unit.sv` | [forwarding-unit.md](forwarding-unit.md) |
| `operand_mux` | `ex_operand_mux` | `rtl/operand_mux.sv` | [operand-mux.md](operand-mux.md) |
| `alu` | `ex_alu` | `rtl/alu.sv` | [alu.md](alu.md) |
| `branch_comparator` | `ex_branch_comparator` | `rtl/branch_comparator.sv` | [branch-comparator.md](branch-comparator.md) |
| `link_adder` | `ex_link_adder` | `rtl/link_adder.sv` | [link-adder.md](link-adder.md) |
| `result_mux` | `ex_result_mux` | `rtl/result_mux.sv` | [result-mux.md](result-mux.md) |
| `redirect_unit` | `ex_redirect` | `rtl/redirect_unit.sv` | [redirect-unit.md](redirect-unit.md) |

| Net | Width | Driver | Consumers |
| --- | --- | --- | --- |
| `fwd_rs1` | `DATA_WIDTH` | `ex_forwarding`, port `fwd_rs1` | `ex_operand_mux` port `rs1_value`; `ex_branch_comparator` port `operand_a` |
| `fwd_rs2` | `DATA_WIDTH` | `ex_forwarding`, port `fwd_rs2` | `ex_operand_mux` port `rs2_value`; `ex_branch_comparator` port `operand_b`; stage output `store_data` |
| `operand_a` | `DATA_WIDTH` | `ex_operand_mux`, port `operand_a` | `ex_alu` port `operand_a` |
| `operand_b` | `DATA_WIDTH` | `ex_operand_mux`, port `operand_b` | `ex_alu` port `operand_b` |
| `alu_result` | `DATA_WIDTH` | `ex_alu`, port `alu_result` | `ex_result_mux` port `alu_result`; `ex_redirect` port `alu_result` |
| `pc_plus_4` | `ADDR_WIDTH` | `ex_link_adder`, port `pc_plus_4` | `ex_result_mux` port `pc_plus_4` |
| `branch_condition` | 1 | `ex_branch_comparator`, port `branch_condition` | `ex_redirect` port `branch_condition` |

- The stage instantiates the seven leaves, one each, and has no other logic than `store_data`, which is the `fwd_rs2` net.
- Every leaf input that is not an internal net connects to the stage input of the same name.
- `ex_result` is the `result` port of `ex_result_mux`, and `redirect_fire` and `redirect_target` are the same-named ports of `ex_redirect`.

## 5. State

- None, because the stage and its seven leaves are combinational (section 1).
- The core owns the clocked ID/EX and EX/MEM registers outside this hierarchy ([ID/EX boundary](5-stage-baseline-core.md#idex-boundary), [EX/MEM boundary](5-stage-baseline-core.md#exmem-boundary-and-data-request-ownership)).
- The core applies the valid, reset, hold, bubble and flush rules to them.

## 6. Behavior

| Output | Equals | Rule owner |
| --- | --- | --- |
| `ex_result` | The link value (`pc` plus 4) for JAL and JALR, and the ALU result for every other class with a result. That result is the effective address for a load or store. A branch and FENCE have no meaningful result. | [result-mux.md](result-mux.md#3-selection-contract), [link-adder.md](link-adder.md#3-arithmetic-contract), [alu.md](alu.md#3-operation-contract) |
| `store_data` | The forwarded `rs2` value, whatever the second ALU operand is | [forwarding-unit.md](forwarding-unit.md#3-selection-contract) |
| `redirect_fire` | 1 for a valid instruction that `advance_allowed` lets leave EX and that requests a redirect: a conditional branch with a true condition, JAL or JALR | [redirect-unit.md](redirect-unit.md#3-redirect-behavior), [branch-comparator.md](branch-comparator.md#3-comparison-contract) |
| `redirect_target` | The ALU result, with bit 0 cleared for JALR. It follows the datapath when `redirect_fire` is 0 | [redirect-unit.md](redirect-unit.md#3-redirect-behavior) |

### Class-to-operand table

| Instruction class | ALU operand A | ALU operand B | ALU operation |
| --- | --- | --- | --- |
| Register arithmetic and logic | Forwarded `rs1` | Forwarded `rs2` | Decoded operation |
| Immediate arithmetic and logic | Forwarded `rs1` | `imm` | Decoded operation |
| LUI | Zero | `imm` | ADD |
| AUIPC | `pc` | `imm` | ADD |
| Load and store | Forwarded `rs1` | `imm` | ADD |
| Conditional branch | `pc` | `imm` | ADD |
| JAL | `pc` | `imm` | ADD |
| JALR | Forwarded `rs1` | `imm` | ADD |

- [alu.md](alu.md#3-operation-contract) owns the table of ALU operations.
- The forwarded values feed operand selection, branch comparison, the JALR base and store data.
- The comparator reads the forwarded register values, not the ALU operands, so a branch compares registers while the ALU computes the target.
- `advance_allowed` and `instruction_valid` gate no computation and force no data output to zero. Only `redirect_fire` depends on them.
- The core consumes `redirect_fire` under the BASE [redirect contract](5-stage-baseline-core.md#redirect-event-and-pipeline-recovery) and [pipeline priority](5-stage-baseline-core.md#pipeline-control-priority).

## 7. Timing and Control

- Every output is a combinational function of the current inputs, so the stage adds no latency and has no handshake.
- A combinational value implies no stage acceptance, no retirement and no fixed propagation delay, because the core decides when EX advances.

### When valid

| Signal group | When valid |
| --- | --- |
| `redirect_fire` | Every cycle, from the current inputs |
| `redirect_target` | When `redirect_fire` is 1 |
| `ex_result`, `store_data` | For a valid instruction that uses them |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the stage has no reset input and no state. The core's reset reaches EX through `instruction_valid` and `advance_allowed`. |
| Stall | None: the stage has no stall input. A held instruction has `advance_allowed` 0, so no redirect fires. |
| Flush | None: the stage has no flush input. An EX kill clears `instruction_valid`, so no redirect fires. |

- Trace: None, because the stage is combinational and has no sequence in time.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment, as in each leaf spec | X and Z behavior is unspecified and untested. |
| `advance_allowed` does not depend on `redirect_fire` in the same cycle | The hazard control unit ([section 7](hazard-control-unit.md#7-timing-and-control)), [redirect-unit.md](redirect-unit.md#2-interface-timing-and-state) | The core would contain a combinational loop. |
| The core keeps metadata, validity and computed data of one instruction together under capture, hold, bubble, flush and reset | The core, through the EX/MEM register control ([EX-D8](#10-decisions-and-open-items)) | A result enters EX/MEM with the metadata of another instruction. |
| The core uses `ex_result` and `store_data` only for a valid instruction that needs them, and `redirect_target` only when `redirect_fire` is 1 | The core ([pipeline priority](5-stage-baseline-core.md#pipeline-control-priority)) | A value with no architectural meaning could authorize a side effect. |

| Case | Inputs | Result |
| --- | --- | --- |
| MEM wait with a branch or jump in EX | `advance_allowed` 0 | The values may stay available, and `redirect_fire` is 0, so no redirect fires merely because the target or condition is ready. |
| A response releases the wait | `advance_allowed` 1 in the cycle the data response arrives, and a WB producer is held | The held WB producer still forwards in that cycle. A held branch with a true condition, or a held jump, fires `redirect_fire` in that cycle ([HCU behavior table](hazard-control-unit.md#6-behavior)). |
| Invalid entry | `instruction_valid` 0, any control values | `redirect_fire` is 0, and the data outputs follow the leaf contracts with no architectural effect. |

## 9. Verification

- A directed test exists: runner `tb/runners/test_execute_stage.py` runs two tops with Verilator and cocotb.
  - `execute_stage` runs the module `execute_stage_cocotb`, which has 11 tests.
  - The test-only `execute_stage_harness` runs the module `execute_stage_pipeline_cocotb`, which has 6 tests.
- The harness resets synchronously, so no test establishes the BASE [R2](5-stage-baseline-core.md#reset-architecture) asynchronous assertion or its synchronized release.
- A pass shows only the checked vectors, not decode, full-core pipeline control, OBI, FPGA, timing or PPA correctness.
- Expected values come from the BASE instruction semantics and independently calculated constants, not from a duplicate RTL decoder. The BASE [verification strategy](5-stage-baseline-core.md#verification-strategy-and-ownership) owns tools and oracle independence.
- Full EX acceptance needs these checks under pipeline-register and control stimulus, and it needs no real frontend, OBI subordinate or accelerator.

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| ALU operations | All ten operations with independently calculated values; ADD and SUB wraparound; opposite-sign comparisons; SLT against SLTU; SRA against SRL; shifts by 0 and 31; operands that share bits 4:0 and differ above | Every result equals the expected value, and the ALU vectors table holds |
| ALU reserved codes | Each of the six unassigned `alu_op` codes | The fallback of [alu.md](alu.md#4-input-validity-and-exceptional-conditions) |
| ALU checker ([EX-D10](#10-decisions-and-open-items)) | A valid supported instruction that uses an unassigned `alu_op` code | Checker FAIL |
| ALU checker scope (EX-D10) | Arbitrary `alu_op` payload in an invalid entry or in an unsupported word | No checker FAIL |
| Operand A checker (EX-D10) | A valid supported instruction that consumes operand A and uses the reserved A selector of [operand-mux.md](operand-mux.md#4-input-validity-and-exceptional-conditions) | Checker FAIL |
| Operand A checker scope (EX-D10) | A bubble, or FENCE with the reserved A selector | No checker FAIL |
| Forwarding priority | EX/MEM and MEM/WB producers both eligible for one source | The EX/MEM value ([forwarding-unit.md](forwarding-unit.md#3-selection-contract)) |
| Source and producer x0 | A source x0, and a producer with destination x0 | No producer overrides the source |
| Unavailable EX/MEM load | An EX/MEM load (`mem_wb_src` 1) matching a source | The EX/MEM result is not used, and the MEM/WB value follows once the load is there |
| Both branch operands forwarded | A branch whose two sources both match producers | The comparator sees both forwarded values |
| Compare and target together | A taken branch | The condition is true and the target is available in the same cycle, and `redirect_fire` is 1 |
| Jump target and link together | JAL and JALR | `ex_result` is the link and `redirect_target` is the target |
| JALR bit 0 | JALR whose computed address has bit 0 set | `redirect_target` has bit 0 clear and keeps every other bit |
| Store data independence | A store with `imm` as operand B and a forwarded `rs2` | `store_data` equals the forwarded `rs2` value |
| Invalid EX state | `instruction_valid` 0 with branch or jump control | As the section 8 row "Invalid entry" |
| MEM-wait hold | A branch or jump in EX with `advance_allowed` 0 | As the section 8 row "MEM wait with a branch or jump in EX" |
| MEM-wait release | `advance_allowed` 1 in the cycle the data response arrives, and a WB producer is held | As the section 8 row "A response releases the wait" |

### ALU vectors

| Inputs and operation | Expected result |
| --- | --- |
| ADD(0xFFFFFFFF, 0x00000001) | 0x00000000 |
| SLT(0xFFFFFFFF, 0x00000000) | 0x00000001 |
| SLTU(0xFFFFFFFF, 0x00000000) | 0x00000000 |
| SRA(0x80000000, 0x00000001) | 0xC0000000 |
| SRL(0x80000000, 0x00000001) | 0x40000000 |
| SLL(0x00000001, 0x00000020) | 0x00000001 |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| EX-D1 | Names are functional and `lower_snake_case`, with no `riscv_` or `u_` prefix, and instance names carry the `ex_` prefix. | A name says what a block is, and an instance name says where it is used. |
| EX-D2 | Seven semantic functions are leaves, including the link adder and the muxes. | The Owner prefers a visible hierarchy and independently reviewable boundaries, including small mux and adder functions. |
| EX-D3 | A dedicated branch comparator compares registers, and the ALU computes the target. | Both run at once, so EX gains no cycle. |
| EX-D4 | A dedicated link adder in EX computes `pc` plus 4, and no earlier pipeline register carries it. | The target and the link are available together, and the pipeline needs no extra payload. |
| EX-D5 | The ALU has ten operations. | They cover the arithmetic and logic instructions and the address and target calculations, and branch conditions and JALR masking have other owners. |
| EX-D6 | The ALU and the comparator have separate interfaces, and SLT and SLTU stay in the ALU. | Each contract stays local, and possible duplicated comparison logic is accepted with no claim of measured area or timing. |
| EX-D7 | The redirect leaf is named `redirect_unit`. | It qualifies a redirect from an existing condition and target, and it covers branch and jump without owning all branch calculation. |
| EX-D8 | `rd`, `reg_write`, `mem_en`, `mem_write`, `mem_type`, the valid bit and the writeback selection bypass the stage. The core connects them from ID/EX to EX/MEM. | The core keeps the metadata with the computed data at EX/MEM, so the stage exposes only computation inputs and outputs. |
| EX-D9 | The stage ports are individual signals grouped by role. They reuse the leaf interfaces and add no packed payload type, clock, reset, stall output or output-valid port. | The leaf contracts already own the types and encodings. |
| EX-D10 | The ALU and operand-mux checkers fire only for a valid supported instruction. FENCE is exempt from the operand A check. Each is a verification check and not a hardware error port or CPU trap. | A reserved code may appear for an unsupported word and no logic avoids it ([decode-stage O6](decode-stage.md#9-rationale-and-open-decisions)). |

- Revisit: sharing for PPA, or moving the link computation upstream, needs evidence and an Owner decision.
- History: 2026-10-15 the Owner accepted the decomposition, naming and semantic boundaries, with the ALU as the first increment. The module name `alu` superseded the earlier proposal `ex_alu`.
- 2026-10-19 the Owner accepted the flat wrapper interface and the core-owned metadata bypass (revision EX D3).
- 2026-10-30 the amendment EX D4 set the checker scope, and the Owner accepted it on 2026-10-31.
- 2026-11-07 rewritten in the block spec format, with IDs renumbered. The stale `mem_wb_from_mem` note went, because the RTL uses `mem_wb_src`.

| Old ID | New ID | Status |
| --- | --- | --- |
| Functional module and file names; EX-prefixed instances | EX-D1 | Kept |
| Semantic functions exposed as seven leaves | EX-D2 | Kept |
| Dedicated branch comparator; ALU computes target | EX-D3 | Kept |
| Dedicated EX link adder | EX-D4 | Kept |
| Ten ALU operations | EX-D5 | Kept |
| Separate ALU and comparator interfaces | EX-D6 | Kept; takes the SLT and SLTU rule of old 4.3 |
| `redirect_unit` name | EX-D7 | Kept |
| EX first complete feature; ALU first increment | none | Retired: it records a delivery order that is complete |
| Current-instruction metadata bypasses the wrapper | EX-D8 | Kept |
| Flat wrapper ports | EX-D9 | Kept |
| EX D4 (checker scope amendment, 2026-10-30) | EX-D10 | Kept as a decision; the date goes to History |
| EX D3 (revision label, 2026-10-19) | none | Retired as a label: History carries the date, and its decisions are EX-D8 and EX-D9. `tb/README.md` cites "EX D3" |

- Length: 7 pages, above the 2-4 limit, because the spec has 27 ports, a seven-net table, 17 check rows and 6 ALU vectors.
- Open items:
  - The harness resets synchronously, so no test shows the stage under the R2 asynchronous reset.
    - Consequence: EX under R2 is unverified. Responsible: Việt.
    - Options: (a) move the harness to asynchronous reset; (b) cover it in a core-level reset test.
    - Recommendation: (b), because the stage has no reset input and R2 acts on the registers around it.
