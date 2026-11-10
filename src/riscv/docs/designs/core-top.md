# Core Top

| Field | Value |
| --- | --- |
| Description | Wires the five stages, the four pipeline registers and the hazard control unit into the BASE core. |
| Last modified | 2026-11-10 |
| Status | Accepted by Việt on 2026-11-10 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/core_top.sv`, module `core_top`. The file does not exist yet. |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md) (build profiles, pipeline organization, pipeline-control priority, pipeline-register local control, core memory boundary, reset architecture); [reset strategy](../decisions/reset-strategy.md); [Fetch stage](fetch-stage.md); [Decode stage](decode-stage.md); [Execute stage](execute-stage.md); [Memory stage](memory-stage.md); [Writeback stage](writeback-stage.md); [Pipeline register](pipeline-register.md); [Hazard control unit](hazard-control-unit.md); [CI extension](asynchronous-accelerator-control-extension.md#7-native-cpumanager-control-port); [IRQ extension](external-interrupt-extension.md#external-irq-and-drain-boundary) |

## 1. Overview

- `core_top` is the BASE core. It instantiates the five stages, the four pipeline registers and the hazard control unit, and it wires them.
- It is the one common top of the [build profiles](5-stage-baseline-core.md#build-profiles-and-contract-composition), with the same ports in every profile. Only the BASE profile is implemented.
- Its parameter `CORE_PROFILE` defaults to BASE, and any other value must fail elaboration until its extension is implemented ([CORE-D1](#10-decisions-and-open-items)).
- It has no logic of its own beyond constant values, because every behavior belongs to a child.
- BASE owns the pipeline organization, the control priority, the memory boundary, the reset architecture and the profiles. This spec links them and restates none.
- It receives a conditioned `rst_n`, because the `reset_synchronizer` sits outside the core ([RST-D1](../decisions/reset-strategy.md)).
- It has no cache, branch predictor, trace port or debug port, because BASE defines none.

## 2. Block Design

```text
                                     clk, rst_n <- system clock and reset
                                                  |
                                   +-----------------------------+
instr_gnt, instr_rvalid,           |                             | -> instr_req, instr_addr, instr_we, instr_be,
  instr_rdata <- instruction       |                             |      instr_wdata, instr_rready (instruction OBI subordinate)
  OBI subordinate                  |                             |
data_gnt, data_rvalid,             |          core_top           | -> data_req, data_addr, data_we, data_be,
  data_rdata <- data OBI           |                             |      data_wdata, data_rready (data OBI subordinate)
  subordinate                      |                             |
ci_cmd_ready, ci_cmd_result        |                             | -> ci_cmd_valid, ci_cmd_op, ci_cmd_target,
  <- CI manager                    |                             |      ci_cmd_desc (CI manager)
irq_external <- interrupt source   |                             |
                                   +-----------------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | System clock | Clock of all registered state. |
| `rst_n` | Input | 1 | System reset | Active-low core reset. It asserts asynchronously and releases synchronously to `clk`. |
| `instr_gnt` | Input | 1 | Instruction OBI subordinate | Grant of the request that `instr_req` raises. |
| `instr_rvalid` | Input | 1 | Instruction OBI subordinate | An instruction response is valid. |
| `instr_rdata` | Input | `INSTR_WIDTH` | Instruction OBI subordinate | Instruction word of the response. |
| `instr_req` | Output | 1 | Instruction OBI subordinate | Instruction request for the presented entry. |
| `instr_addr` | Output | `ADDR_WIDTH` | Instruction OBI subordinate | Request address, the `pc` of the presented entry. |
| `instr_we` | Output | 1 | Instruction OBI subordinate | Write enable of the read-only port. |
| `instr_be` | Output | 4 | Instruction OBI subordinate | Byte enable of the read-only port. |
| `instr_wdata` | Output | `DATA_WIDTH` | Instruction OBI subordinate | Write data of the read-only port. |
| `instr_rready` | Output | 1 | Instruction OBI subordinate | Readiness to accept an instruction response. |
| `data_gnt` | Input | 1 | Data OBI subordinate | Request acceptance, when `data_req` is 1. |
| `data_rvalid` | Input | 1 | Data OBI subordinate | A data response is valid. |
| `data_rdata` | Input | `DATA_WIDTH` | Data OBI subordinate | Response word. |
| `data_req` | Output | 1 | Data OBI subordinate | Data request presentation. |
| `data_addr` | Output | `ADDR_WIDTH` | Data OBI subordinate | Word-aligned request address, meaningful with `data_req`. |
| `data_we` | Output | 1 | Data OBI subordinate | Store write enable, meaningful with `data_req`. |
| `data_be` | Output | 4 | Data OBI subordinate | Selected byte lanes, meaningful with `data_req`. |
| `data_wdata` | Output | `DATA_WIDTH` | Data OBI subordinate | Store payload, meaningful for a store request. |
| `data_rready` | Output | 1 | Data OBI subordinate | Readiness to accept a data response. |
| `ci_cmd_valid` | Output | 1 | CI manager | A CI instruction presents a command. In BASE it is constant 0 ([build profiles](5-stage-baseline-core.md#build-profiles-and-contract-composition)). |
| `ci_cmd_op` | Output | 2 | CI manager | CI operation code. In BASE it is constant 0. |
| `ci_cmd_target` | Output | 32 | CI manager | Accelerator identifier of the command. In BASE it is constant 0. |
| `ci_cmd_desc` | Output | 32 | CI manager | Descriptor pointer of the command. In BASE it is constant 0. |
| `ci_cmd_ready` | Input | 1 | CI manager | The manager can return a result. BASE gives it no effect. |
| `ci_cmd_result` | Input | 32 | CI manager | Result of the command. BASE gives it no effect. |
| `irq_external` | Input | 1 | Interrupt source | External interrupt level. BASE gives it no effect. |

- Every vector is unsigned. `INSTR_WIDTH`, `ADDR_WIDTH` and `DATA_WIDTH` are 32, from `riscv_pkg`.
- The CI names, directions and widths come from the [CI extension port](asynchronous-accelerator-control-extension.md#7-native-cpumanager-control-port), and `irq_external` comes from the [IRQ extension](external-interrupt-extension.md#external-irq-and-drain-boundary).
- The instruction port is read-only, so its write fields and `instr_rready` carry the constants of the [OBI baseline configuration](5-stage-baseline-core.md#obi-baseline-configuration).
- `data_rready` is constant by the single-transaction contract of the same section.
- Each OBI port permits one outstanding transaction. That is a link contract and not a port ([core memory boundary](5-stage-baseline-core.md#core-memory-boundary)).
- `CORE_PROFILE` is the only parameter. Its values and default come from the profile table of the build profiles.
- The core has no other port.

## 4. Internal Structure

| Module | Instance | File | Spec |
| --- | --- | --- | --- |
| `core_top` | Top | `rtl/core_top.sv` | This spec |
| `fetch_stage` | `if_stage` | `rtl/fetch_stage.sv` | [fetch-stage.md](fetch-stage.md) |
| `decode_stage` | `id_stage` | `rtl/decode_stage.sv` | [decode-stage.md](decode-stage.md) |
| `execute_stage` | `ex_stage` | `rtl/execute_stage.sv` | [execute-stage.md](execute-stage.md) |
| `memory_stage` | `mem_stage` | `rtl/memory_stage.sv` | [memory-stage.md](memory-stage.md) |
| `writeback_stage` | `wb_stage` | `rtl/writeback_stage.sv` | [writeback-stage.md](writeback-stage.md) |
| `if_id_pipeline` | `if_id_reg` | `rtl/if_id_pipeline.sv` | [pipeline-register.md](pipeline-register.md) |
| `id_ex_pipeline` | `id_ex_reg` | `rtl/id_ex_pipeline.sv` | [pipeline-register.md](pipeline-register.md) |
| `ex_mem_pipeline` | `ex_mem_reg` | `rtl/ex_mem_pipeline.sv` | [pipeline-register.md](pipeline-register.md) |
| `mem_wb_pipeline` | `mem_wb_reg` | `rtl/mem_wb_pipeline.sv` | [pipeline-register.md](pipeline-register.md) |
| `hazard_control_unit` | `hcu` | `rtl/hazard_control_unit.sv` | [hazard-control-unit.md](hazard-control-unit.md) |

- The stage instance names come from the RTL rows of the stage specs. The other names follow [CORE-D4](#10-decisions-and-open-items).

### Nets

| Net | Width | Driver | Receivers |
| --- | --- | --- | --- |
| `clk` | 1 | `core_top.clk` | `if_stage.clk`, `id_stage.clk`, `mem_stage.clk`, `if_id_reg.clk`, `id_ex_reg.clk`, `ex_mem_reg.clk`, `mem_wb_reg.clk` |
| `rst_n` | 1 | `core_top.rst_n` | `if_stage.rst_n`, `mem_stage.rst_n`, `if_id_reg.rst_n`, `id_ex_reg.rst_n`, `ex_mem_reg.rst_n`, `mem_wb_reg.rst_n`, `hcu.rst_n` |
| `fetch_valid` | 1 | `if_stage.fetch_valid` | `if_id_reg.valid_i` |
| `fetch_pc` | ADDR_WIDTH | `if_stage.fetch_pc` | `if_id_reg.pc_i` |
| `fetch_instruction` | INSTR_WIDTH | `if_stage.fetch_instruction` | `if_id_reg.instruction_i` |
| `if_id_reg_valid` | 1 | `if_id_reg.valid_o` | `hcu.id_valid`, `id_ex_reg.valid_i` |
| `if_id_reg_pc` | ADDR_WIDTH | `if_id_reg.pc_o` | `id_ex_reg.pc_i` |
| `if_id_reg_instruction` | INSTR_WIDTH | `if_id_reg.instruction_o` | `id_stage.instruction` |
| `rs1_id` | 5 | `id_stage.rs1_id` | `hcu.id_rs1_id`, `id_ex_reg.rs1_id_i` |
| `rs2_id` | 5 | `id_stage.rs2_id` | `hcu.id_rs2_id`, `id_ex_reg.rs2_id_i` |
| `rs1_used` | 1 | `id_stage.rs1_used` | `hcu.id_rs1_used` |
| `rs2_used` | 1 | `id_stage.rs2_used` | `hcu.id_rs2_used` |
| `rd` | 5 | `id_stage.rd` | `id_ex_reg.rd_i` |
| `rs1_value` | DATA_WIDTH | `id_stage.rs1_value` | `id_ex_reg.rs1_value_i` |
| `rs2_value` | DATA_WIDTH | `id_stage.rs2_value` | `id_ex_reg.rs2_value_i` |
| `imm` | DATA_WIDTH | `id_stage.imm` | `id_ex_reg.imm_i` |
| `reg_write` | 1 | `id_stage.reg_write` | `id_ex_reg.reg_write_i` |
| `alu_op` | alu_op_t (4) | `id_stage.alu_op` | `id_ex_reg.alu_op_i` |
| `alu_src_a` | alu_src_a_t (2) | `id_stage.alu_src_a` | `id_ex_reg.alu_src_a_i` |
| `alu_src_b` | alu_src_b_t (1) | `id_stage.alu_src_b` | `id_ex_reg.alu_src_b_i` |
| `result_src` | result_src_t (1) | `id_stage.result_src` | `id_ex_reg.result_src_i` |
| `branch_kind` | branch_kind_t (3) | `id_stage.branch_kind` | `id_ex_reg.branch_kind_i` |
| `control_flow` | control_flow_t (2) | `id_stage.control_flow` | `id_ex_reg.control_flow_i` |
| `mem_en` | 1 | `id_stage.mem_en` | `id_ex_reg.mem_en_i` |
| `mem_write` | 1 | `id_stage.mem_write` | `id_ex_reg.mem_write_i` |
| `mem_type` | mem_type_t (3) | `id_stage.mem_type` | `id_ex_reg.mem_type_i` |
| `wb_src` | 1 | `id_stage.wb_src` | `id_ex_reg.wb_src_i` |
| `id_ex_reg_valid` | 1 | `id_ex_reg.valid_o` | `ex_stage.instruction_valid`, `ex_mem_reg.valid_i`, `hcu.ex_valid` |
| `id_ex_reg_pc` | ADDR_WIDTH | `id_ex_reg.pc_o` | `ex_stage.pc` |
| `id_ex_reg_rs1_id` | 5 | `id_ex_reg.rs1_id_o` | `ex_stage.rs1_id` |
| `id_ex_reg_rs2_id` | 5 | `id_ex_reg.rs2_id_o` | `ex_stage.rs2_id` |
| `id_ex_reg_rs1_value` | DATA_WIDTH | `id_ex_reg.rs1_value_o` | `ex_stage.rs1_value` |
| `id_ex_reg_rs2_value` | DATA_WIDTH | `id_ex_reg.rs2_value_o` | `ex_stage.rs2_value` |
| `id_ex_reg_imm` | DATA_WIDTH | `id_ex_reg.imm_o` | `ex_stage.imm` |
| `id_ex_reg_alu_op` | alu_op_t (4) | `id_ex_reg.alu_op_o` | `ex_stage.alu_op` |
| `id_ex_reg_alu_src_a` | alu_src_a_t (2) | `id_ex_reg.alu_src_a_o` | `ex_stage.alu_src_a` |
| `id_ex_reg_alu_src_b` | alu_src_b_t (1) | `id_ex_reg.alu_src_b_o` | `ex_stage.alu_src_b` |
| `id_ex_reg_result_src` | result_src_t (1) | `id_ex_reg.result_src_o` | `ex_stage.result_src` |
| `id_ex_reg_branch_kind` | branch_kind_t (3) | `id_ex_reg.branch_kind_o` | `ex_stage.branch_kind` |
| `id_ex_reg_control_flow` | control_flow_t (2) | `id_ex_reg.control_flow_o` | `ex_stage.control_flow` |
| `id_ex_reg_rd` | 5 | `id_ex_reg.rd_o` | `hcu.ex_rd`, `ex_mem_reg.rd_i` |
| `id_ex_reg_reg_write` | 1 | `id_ex_reg.reg_write_o` | `ex_mem_reg.reg_write_i` |
| `id_ex_reg_mem_en` | 1 | `id_ex_reg.mem_en_o` | `hcu.ex_mem_en`, `ex_mem_reg.mem_en_i` |
| `id_ex_reg_mem_write` | 1 | `id_ex_reg.mem_write_o` | `hcu.ex_mem_write`, `ex_mem_reg.mem_write_i` |
| `id_ex_reg_mem_type` | mem_type_t (3) | `id_ex_reg.mem_type_o` | `ex_mem_reg.mem_type_i` |
| `id_ex_reg_wb_src` | 1 | `id_ex_reg.wb_src_o` | `ex_mem_reg.wb_src_i` |
| `ex_result` | DATA_WIDTH | `ex_stage.ex_result` | `ex_mem_reg.ex_result_i` |
| `store_data` | DATA_WIDTH | `ex_stage.store_data` | `ex_mem_reg.store_data_i` |
| `redirect_fire` | 1 | `ex_stage.redirect_fire` | `if_stage.redirect_fire`, `hcu.redirect_fire` |
| `redirect_target` | ADDR_WIDTH | `ex_stage.redirect_target` | `if_stage.redirect_target` |
| `ex_mem_reg_valid` | 1 | `ex_mem_reg.valid_o` | `ex_stage.mem_valid`, `mem_stage.instruction_valid`, `mem_wb_reg.valid_i` |
| `ex_mem_reg_ex_result` | DATA_WIDTH | `ex_mem_reg.ex_result_o` | `ex_stage.mem_result`, `mem_stage.ex_result`, `mem_wb_reg.ex_result_i` |
| `ex_mem_reg_store_data` | DATA_WIDTH | `ex_mem_reg.store_data_o` | `mem_stage.store_data` |
| `ex_mem_reg_rd` | 5 | `ex_mem_reg.rd_o` | `ex_stage.mem_rd`, `mem_wb_reg.rd_i` |
| `ex_mem_reg_reg_write` | 1 | `ex_mem_reg.reg_write_o` | `ex_stage.mem_reg_write`, `mem_wb_reg.reg_write_i` |
| `ex_mem_reg_mem_en` | 1 | `ex_mem_reg.mem_en_o` | `mem_stage.mem_en` |
| `ex_mem_reg_mem_write` | 1 | `ex_mem_reg.mem_write_o` | `mem_stage.mem_write` |
| `ex_mem_reg_mem_type` | mem_type_t (3) | `ex_mem_reg.mem_type_o` | `mem_stage.mem_type` |
| `ex_mem_reg_wb_src` | 1 | `ex_mem_reg.wb_src_o` | `ex_stage.mem_wb_src`, `mem_wb_reg.wb_src_i` |
| `load_result` | DATA_WIDTH | `mem_stage.load_result` | `mem_wb_reg.load_result_i` |
| `mem_wait` | 1 | `mem_stage.mem_wait` | `hcu.mem_wait` |
| `mem_wb_reg_valid` | 1 | `mem_wb_reg.valid_o` | `wb_stage.instruction_valid`, `ex_stage.wb_valid` |
| `mem_wb_reg_ex_result` | DATA_WIDTH | `mem_wb_reg.ex_result_o` | `wb_stage.ex_result` |
| `mem_wb_reg_load_result` | DATA_WIDTH | `mem_wb_reg.load_result_o` | `wb_stage.load_result` |
| `mem_wb_reg_wb_src` | 1 | `mem_wb_reg.wb_src_o` | `wb_stage.wb_src` |
| `mem_wb_reg_rd` | 5 | `mem_wb_reg.rd_o` | `wb_stage.rd`, `id_stage.wb_rd`, `ex_stage.wb_rd` |
| `mem_wb_reg_reg_write` | 1 | `mem_wb_reg.reg_write_o` | `wb_stage.reg_write`, `ex_stage.wb_reg_write` |
| `wb_data` | DATA_WIDTH | `wb_stage.wb_data` | `id_stage.wb_data`, `ex_stage.wb_data` |
| `rf_write_fire` | 1 | `wb_stage.rf_write_fire` | `id_stage.rf_write_fire` |
| `advance_allowed` | 1 | `hcu.advance_allowed` | `ex_stage.advance_allowed`, `wb_stage.advance_allowed` |
| `fetch_accept` | 1 | `hcu.fetch_accept` | `if_stage.fetch_accept` |
| `if_id_stall` | 1 | `hcu.if_id_stall` | `if_id_reg.stall` |
| `if_id_flush` | 1 | `hcu.if_id_flush` | `if_id_reg.flush` |
| `id_ex_stall` | 1 | `hcu.id_ex_stall` | `id_ex_reg.stall` |
| `id_ex_flush` | 1 | `hcu.id_ex_flush` | `id_ex_reg.flush` |
| `ex_mem_stall` | 1 | `hcu.ex_mem_stall` | `ex_mem_reg.stall` |
| `mem_wb_stall` | 1 | `hcu.mem_wb_stall` | `mem_wb_reg.stall` |
| `ex_mem_flush` | 1 | Constant 0 | `ex_mem_reg.flush` |
| `mem_wb_flush` | 1 | Constant 0 | `mem_wb_reg.flush` |
| `ci_cmd_valid` | 1 | Constant 0 | `core_top.ci_cmd_valid` |
| `ci_cmd_op` | 2 | Constant 0 | `core_top.ci_cmd_op` |
| `ci_cmd_target` | 32 | Constant 0 | `core_top.ci_cmd_target` |
| `ci_cmd_desc` | 32 | Constant 0 | `core_top.ci_cmd_desc` |

- Net names follow [CORE-D5](#10-decisions-and-open-items). A constant net is named for the register and the port it drives.
- Each `instr_` port connects to the `if_stage` port of the same name without the prefix. Each `data_` port connects to the `mem_stage` port the same way, so the table lists no OBI net.
- `ci_cmd_ready`, `ci_cmd_result` and `irq_external` connect to no instance, because BASE gives them no effect.
- Every instance port sits on exactly one net, and no port is unconnected.
- The IF/ID register takes `fetch_valid` as its valid, and each later register takes the valid of the register before it ([pipeline-control priority](5-stage-baseline-core.md#pipeline-control-priority)).
- `pc` and the IF/ID valid bypass `id_stage` on the way from IF/ID to ID/EX ([ID-D8](decode-stage.md#10-decisions-and-open-items)).
- `rd`, `reg_write`, `mem_en`, `mem_write`, `mem_type` and `wb_src` bypass `ex_stage` on the way to EX/MEM ([EX-D8](execute-stage.md#10-decisions-and-open-items)).
- `rd`, `reg_write` and `wb_src` bypass `mem_stage` on the way to MEM/WB ([MEM-D2](memory-stage.md#10-decisions-and-open-items)).
- `rs1_used` and `rs2_used` reach the hazard control unit only, because ID/EX does not carry them ([decode stage](decode-stage.md#3-interface)).
- `redirect_fire` and `redirect_target` go from `ex_stage` straight to `if_stage`, and `redirect_fire` also goes to the hazard control unit ([IF-D4](fetch-stage.md#10-decisions-and-open-items)).
- The flush inputs of EX/MEM and MEM/WB are constant 0 ([PIPE-D3](pipeline-register.md#10-decisions-and-open-items), [HCU-D2](hazard-control-unit.md#10-decisions-and-open-items)).

## 5. State

- None, because the top holds no register. Each child holds its own state.
- The pipeline registers hold the stored valid and the payload, and the fetch controller holds the fetch state.
- The data OBI controller holds the transaction state, and the register file holds the architectural registers.

## 6. Behavior

- The top adds no behavior to the children. Each output follows from the children and the wiring of section 4.
- The hazard control unit drives every `stall` and `flush` input, except the two constant flushes of section 4.
- The priority among reset, MEM wait, redirect, load-use and normal advance is the table of the [hazard control unit](hazard-control-unit.md#6-behavior) ([pipeline-control priority](5-stage-baseline-core.md#pipeline-control-priority)).
- The behavior of a register under reset, flush, stall and load is the [condition table](pipeline-register.md#condition-table).
- The WB result reaches ID as the bypass and EX as forwarding. The register file and the forwarding unit own the selection ([writeback stage](writeback-stage.md#1-overview)).
- `rst_n` reaches `if_stage`, `mem_stage`, the four registers and the hazard control unit. `id_stage`, `ex_stage` and `wb_stage` have no reset port, because they hold no reset state.

## 7. Timing and Control

- The OBI outputs follow the stage specs: the [fetch stage](fetch-stage.md#3-interface) for the instruction port and the [memory stage](memory-stage.md#3-interface) for the data port.
- No combinational path runs from `data_rvalid` to `instr_req` ([IF-A1](5-stage-baseline-core.md#pipeline-control-priority)).
- The path from `data_rvalid` through `mem_wait` to the register controls holds no state, and it has no combinational loop ([HCU timing](hazard-control-unit.md#7-timing-and-control)).
- The top sets no timing target, because BASE claims no timing closure.

### When valid

| Signal group | When valid |
| --- | --- |
| `instr_*` outputs | As the fetch stage states |
| `data_*` outputs | As the memory stage states |
| `ci_cmd_*` outputs | Every cycle, constant 0 in BASE |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | Clears the pipeline valid and the control state of the children at once, with no clock edge. The top adds no gate. |
| Stall | A MEM wait stalls all four registers; a load-use stalls IF/ID only. |
| Flush | A redirect flushes IF/ID and ID/EX; a load-use flushes ID/EX. EX/MEM and MEM/WB never flush. |

- The trace shows the hardest case: a redirect on the edge where the data response ends a MEM wait.
- Before edge 1, a load `L` owns MEM and waits for its response, and `B` is in WB.
- A taken branch `J` is in EX, and `Y` is in ID.
- `data_rvalid` is low in cycle 1 and high in cycle 2.

| Cycle / edge | Inputs | State before (ID, EX, MEM, WB) | Controls | State after |
| --- | --- | --- | --- | --- |
| 1 | `data_rvalid` low | `Y`, `J`, `L`, `B` | All four stalls high; `redirect_fire` low; `advance_allowed` low | Unchanged |
| 2 | `data_rvalid` high for `L` | `Y`, `J`, `L`, `B` | `mem_wait` low; `advance_allowed` high; `redirect_fire` high; IF/ID and ID/EX flushed | `B` retires, `L` in WB, `J` in MEM, ID and EX invalid |

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| `rst_n` asserts asynchronously and releases synchronously to `clk` | The `reset_synchronizer` outside the core ([RST-D1](../decisions/reset-strategy.md)) | Recovery and removal fail at the registers. |
| Both OBI subordinates share the core reset and return no response for a transaction from before the reset | The environment ([OBI response validity and reset](5-stage-baseline-core.md#obi-response-validity-and-reset)) | A stale response is taken as the answer to a new transaction. |
| Each OBI subordinate follows the baseline configuration and accepts one outstanding transaction | The environment ([OBI baseline configuration](5-stage-baseline-core.md#obi-baseline-configuration)) | The expected-response rule fails. |
| `clk` is the only clock of every child | The integration | Behavior is unspecified. |
| The preconditions P1 to P3 of the hazard control unit hold | The redirect unit, the control unit and the pipeline registers ([hazard control unit](hazard-control-unit.md#8-assumptions-and-corner-cases)) | The hazard control unit gives the results stated there. |
| Every consumer qualifies a payload with its valid | The stages ([pipeline register](pipeline-register.md#8-assumptions-and-corner-cases)) | A stale payload acts. |
| Fetch addresses lie in the code region | The harness and the test program ([fetch stage](fetch-stage.md#1-overview)) | Behavior is unspecified. |

| Case | Inputs | Result |
| --- | --- | --- |
| Reset during a MEM wait or a pending transfer | `rst_n` low while a memory instruction owns MEM | The valid clears, and `data_req` is 0 through the reset EX/MEM valid ([reset architecture](5-stage-baseline-core.md#reset-architecture)). |
| Response with redirect | `data_rvalid` ends a MEM wait while `J` redirects | The trace of section 7. |
| Response with load-use | `data_rvalid` ends a MEM wait while a load-use holds | The load-use row of the [hazard control unit](hazard-control-unit.md#8-assumptions-and-corner-cases). |
| Reset release with the clock stopped | `rst_n` source releases while `clk` is stopped | `rst_n` stays asserted until the synchronizer finishes after the clock restarts ([reset architecture](5-stage-baseline-core.md#reset-architecture)). |

## 9. Verification

- No test of `core_top` exists in `tb/`, and `core_top.sv` does not exist. The planned checks below have Test `none`.
- No core-level lint or synthesis run exists.
- Expected values come from the records in the Requirement column, never from the DUT.

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Lint ([CORE-D2](#10-decisions-and-open-items)) | Verilator `-Wall`, lint only, top `core_top`, `riscv_pkg.sv` first, then every file of `rtl/` | Zero warnings. A waiver sits on the line it waives, with a comment giving the reason | none |
| Synthesis ([CORE-D3](#10-decisions-and-open-items)) | Vivado `synth_design`, out-of-context, for the interim part and then the target part | Zero errors, zero critical warnings and zero inferred latches. Utilization is reported | none |
| Profile check ([CORE-D1](#10-decisions-and-open-items)) | `CORE_PROFILE` 1 in Verilator and in Vivado; then BASE | Elaboration fails for 1 in both tools. BASE elaborates in both | none |
| Connectivity | A script reads the instantiations of `core_top.sv` and the ports of the ten modules | Each instance port connects exactly once, with no width or type mismatch, and the nets equal the table of section 4 | none |
| Constant inputs | Read the flush connections and the CI outputs | The two flushes and the four CI outputs are constant 0 | none |
| Per-boundary arbitration | A core run that drives each hazard event | The stall and flush of each boundary match the [hazard control unit table](hazard-control-unit.md#6-behavior) | none |
| Reset under R2 | Assert reset between edges, with the clock stopped, during a stall and during a pending transfer; then release | The valid clears at once, and no stale work appears after release | none |
| Response with redirect | The trace of section 7 | The cycle 2 row | none |
| No data-to-fetch path | A structural trace from `data_rvalid` | No combinational path reaches `instr_req` | none |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| CORE-D1 | The core is the one common top with the parameter `CORE_PROFILE`, default BASE. Only BASE is implemented, and any other value must fail elaboration until its extension is implemented. | BASE requires one common top with fixed port names, widths and directions, so a later extension adds logic and no port. |
| CORE-D2 | The lint target is Verilator `-Wall` with zero warnings. A waiver is allowed only on the line, with a comment giving the reason. |  |
| CORE-D3 | The synthesis target is Vivado `synth_design`, out-of-context, for `xcvu9p-flga2104-2L-e`. Until that part runs, the interim part is `xczu7ev-ffvc1156-2-e`. It must finish with zero errors, zero critical warnings and zero inferred latches, and the utilization is reported. No timing target is set. | The VCU118 is the project board, the target part has no device data on the development machine, and BASE claims no timing closure. |
| CORE-D4 | The stages use the instance names of their specs. The registers are `if_id_reg`, `id_ex_reg`, `ex_mem_reg` and `mem_wb_reg`, and the hazard control unit is `hcu`. | The stage specs call each peer an "IF/ID register" and so on, and the specs call the unit the HCU. |
| CORE-D5 | A stage output net keeps its port name. A register output net is the register instance name, an underscore and the field name. | One name per net lets a script check the table against the RTL. |

- History: 2026-11-10 first draft. The Owner chose the common top with `CORE_PROFILE` on 2026-11-10 after comparing four open cores. The interim part was installed and checked by a trial synthesis on 2026-11-10.
- Old ID map: none, because the file is new.
- Length: 8 pages, above the 2-4 limit, because section 4 lists 83 nets and section 3 lists 27 ports.
- Open items:
  - The CI port names and widths come from the CI extension, which is `Proposed`.
    - Consequence: the top ports change if the extension changes them.
    - Options: (a) the top follows each change; (b) the port list freezes when the extension is accepted.
    - Recommendation: (a), because the common top must match the extension.
    - Responsible: Việt.
  - The synthesis has not run on `xcvu9p-flga2104-2L-e`, because the device data is not installed.
    - Consequence: the synthesis result holds for the interim part only.
    - Options: (a) install the device data; (b) run the check on a machine that has it.
    - Recommendation: (a).
    - Responsible: Việt.
  - Three leaves report unused-signal warnings under `-Wall`: `control_unit`, `immediate_generator` and `load_formatter`.
    - Consequence: the lint target fails until the waivers exist.
    - Options: (a) design-worker adds an on-line waiver with its reason in each leaf; (b) change the leaf ports.
    - Recommendation: (a), because the Owner allows that form.
    - Responsible: Việt.
