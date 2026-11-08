# Operand Mux

| Field | Value |
| --- | --- |
| Description | Combinational selection of the two ALU operands. |
| Last modified | 2026-11-08 |
| Status | Accepted by Việt on 2026-11-08 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/operand_mux.sv`, module `operand_mux`, instance `ex_operand_mux` in `execute_stage` |
| Parent | [Execute stage](execute-stage.md#4-internal-structure) ([class-to-operand table](execute-stage.md#class-to-operand-table)) |

## 1. Overview

- `operand_mux` selects the two ALU operands. The first comes from a forwarded register value, the instruction address or a constant zero. The second comes from a forwarded register value or the immediate.
- The [forwarding unit](forwarding-unit.md) supplies the register values, ID owns decode and immediate reconstruction, and the [ALU](alu.md) consumes the operands.
- The branch comparison and the store data read the forwarded register values directly and not the outputs of this block.
- The block is purely combinational, with no clock, reset, storage, handshake or stall input.
- It receives no instruction encoding and no register identifier, and it performs no arithmetic, sign extension, shifting, alignment correction or immediate-format selection.
- The execute stage owns the composition and the selection per instruction class, and this block owns the two selections.

## 2. Block Design

```text
rs1_value, rs2_value <- forwarding_unit                 +--------------+
pc, imm <- ID/EX register                               |              | -> operand_a, operand_b (alu)
alu_src_a, alu_src_b <- ID/EX register                  | operand_mux  |
                                                        |              |
                                                        +--------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `rs1_value` | Input | `DATA_WIDTH` | `forwarding_unit` | Forwarded value of the first register source. |
| `rs2_value` | Input | `DATA_WIDTH` | `forwarding_unit` | Forwarded value of the second register source. |
| `pc` | Input | `ADDR_WIDTH` | ID/EX register | Address of the instruction in EX. |
| `imm` | Input | `DATA_WIDTH` | ID/EX register | Canonical immediate built in ID. |
| `alu_src_a` | Input | `alu_src_a_t` (2) | ID/EX register | Source selector of the first operand. |
| `alu_src_b` | Input | `alu_src_b_t` (1) | ID/EX register | Source selector of the second operand. |
| `operand_a` | Output | `DATA_WIDTH` | `alu` | First ALU operand. |
| `operand_b` | Output | `DATA_WIDTH` | `alu` | Second ALU operand. |

- The selector types come from `riscv_pkg`, and every vector is unsigned.
- `pc` belongs to the address domain and the other vectors to the datapath domain ([width domains](execute-stage.md#width-domains)). Selecting `pc` is a crossing that keeps every bit ([width crossings](execute-stage.md#width-crossings)).
- There is no error port and no CPU trap.

### Selector encoding

| Selector | Member | Code |
| --- | --- | --- |
| `alu_src_a` | `ALU_A_RS1` | `2'b00` |
| `alu_src_a` | `ALU_A_PC` | `2'b01` |
| `alu_src_a` | `ALU_A_ZERO` | `2'b10` |
| `alu_src_b` | `ALU_B_RS2` | `1'b0` |
| `alu_src_b` | `ALU_B_IMM` | `1'b1` |

- The code `2'b11` of `alu_src_a` is unassigned, and both codes of `alu_src_b` are assigned.

## 4. Internal Structure

- The block has no sub-module and no internal net, and one case on each selector selects its operand.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

### Selection

| Selector value | Output | Value |
| --- | --- | --- |
| `ALU_A_RS1` | `operand_a` | `rs1_value`, all 32 bits |
| `ALU_A_PC` | `operand_a` | `pc`, all 32 bits |
| `ALU_A_ZERO` | `operand_a` | 32-bit zero, a constant and not a value read from a register input |
| Unassigned code | `operand_a` | `32'hDEAD_BEEF` at any data input |
| `ALU_B_RS2` | `operand_b` | `rs2_value`, all 32 bits |
| `ALU_B_IMM` | `operand_b` | `imm`, all 32 bits |

- The two operands are selected independently and concurrently, so `operand_b` follows its own selector whatever the code of `alu_src_a`.
- The unassigned-code row is the diagnostic fallback of [OM-D1](#10-decisions-and-open-items), and it is not an additional source.
- FENCE needs no meaningful ALU operands, and the parent control governs their use ([EX-D10](execute-stage.md#10-decisions-and-open-items)).

## 7. Timing and Control

- The outputs follow the current inputs after combinational settling.
- The block has no latency, no handshake and no registered output, and the parent pipeline control owns the capture of the inputs.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input and no state. |
| Stall | None: the block has no stall input. |
| Flush | None: the block has no flush input. |

- Trace: None, because the block has no sequence in time, and its outputs depend on the current inputs alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| A valid supported instruction that consumes operand A selects an assigned `alu_src_a` code | The [control unit](control-unit.md) in ID | `operand_a` is the fallback value of [OM-D1](#10-decisions-and-open-items), and the EX checker of [EX-D10](execute-stage.md#10-decisions-and-open-items) fails. |
| The operands of an unsupported word or an invalid entry authorize no side effect | The core, which uses a result only for a valid instruction that needs it ([execute stage](execute-stage.md#8-assumptions-and-corner-cases)) | An arbitrary payload could cause a side effect. |

- Corner cases: None, because the block has no state and each output depends on its own selector (section 6).

## 9. Verification

- No test of `operand_mux` exists in `tb/`: it has no runner and no cocotb module.
- The `execute_stage_cocotb` module drives the selectors through the stage, including a reserved `alu_src_a` code in an invalid entry. The [execute stage](execute-stage.md#9-verification) owns those tests and the operand A checker.
- Expected values would come from the selection table of section 6, never from the DUT.

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Operand A from the register | `ALU_A_RS1` with `rs1_value`, `pc` and `imm` all different | `operand_a` equals `rs1_value` | none |
| Operand A from the address | `ALU_A_PC` with `pc` values `0x80000000`, `0xFFFFFFFF` and `0x00000004`, and `rs1_value` different | `operand_a` equals `pc` in all 32 bits | none |
| Operand A zero | `ALU_A_ZERO` with `rs1_value`, `pc` and `imm` all `0xFFFFFFFF` | `operand_a` is zero | none |
| Operand A fallback | `2'b11` with `rs1_value` zero, then with `rs1_value`, `pc` and `imm` all ones | `operand_a` is `32'hDEAD_BEEF` in both | none |
| Operand B from the register | `ALU_B_RS2` with `rs2_value` and `imm` different | `operand_b` equals `rs2_value` | none |
| Operand B from the immediate | `ALU_B_IMM` with `imm` values `0x80000000` and `0xFFFFFFFF`, and `rs2_value` different | `operand_b` equals `imm` in all 32 bits | none |
| Independent selection | Every combination of the four `alu_src_a` codes and the two `alu_src_b` codes, with distinct data on the four data inputs | Each output follows its own selector alone | none |
| Full-width data | A single set bit walked through the 32 positions of each data input, with its selector chosen | The output shows the same bit position | none |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| OM-D1 | The unassigned code `2'b11` of `alu_src_a` returns `operand_a` as `32'hDEAD_BEEF` at any data input, as a diagnostic fallback. The block adds no error port and no CPU trap. | None recorded. |

- History: 2026-10-19 the Owner accepted the spec, under the revision label OM D2. The old file also records, with no date, a width clarification that the Owner accepted.
- 2026-11-08 rewritten in the block spec format, with an ID for the decision that the old file stated in prose.
- Open items: none.
