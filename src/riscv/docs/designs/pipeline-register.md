# Pipeline Register

| Field | Value |
| --- | --- |
| Description | Hold one pipeline stage's entry as a valid bit and a payload, under reset, flush and stall. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/if_id_pipeline.sv`, `rtl/id_ex_pipeline.sv`, `rtl/ex_mem_pipeline.sv` and `rtl/mem_wb_pipeline.sv`, one module each (section 4) |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md) (pipeline-register local control PR-D1, reset architecture, the four boundary sections); [Hazard control unit](hazard-control-unit.md); [Memory stage](memory-stage.md) |

## 1. Overview

- Four modules, `if_id_pipeline`, `id_ex_pipeline`, `ex_mem_pipeline` and `mem_wb_pipeline`, share one port template and one behavior (section 4).
- Each module holds one entry: a stored valid and a payload of fields.
- The BASE boundary sections define the fields, so this spec names none.
- The behavior is PR-D1 of BASE, restated at the ports in section 6.
- The [hazard control unit](hazard-control-unit.md) drives `stall` and `flush`, because under PR-D1 a register obeys its inputs and arbitrates nothing.
- All outputs are registered, and the stored valid and the payload are the only state.
- It does not choose which entry to hold or clear, define a field, tie unused controls (the core top does), or amend BASE.

## 2. Block Design

```text
                                  clk, rst_n <- core
                                          |
                              +------------------------+
valid_i <- source stage       |                        | -> valid_o (destination stage)
<field>_i <- source stage     |   <stage>_pipeline     | -> <field>_o (destination stage)
                              +------------------------+
                                          |
                        stall, flush <- hazard_control_unit
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | Core | The rising edge clocks the stored valid and the payload. |
| `rst_n` | Input | 1 | Core reset | Active-low core reset. It clears the stored valid asynchronously. |
| `stall` | Input | 1 | Hazard control unit | Retain the stored valid and the payload. |
| `flush` | Input | 1 | Hazard control unit | Clear the stored valid and retain the payload. |
| `valid_i` | Input | 1 | Source stage | The source stage presents a live entry. |
| `<field>_i` | Input | Type of the field | Source stage | Source-stage value of one field. Meaningful when `valid_i` is 1. |
| `valid_o` | Output | 1 | Destination stage | The stored entry is live. |
| `<field>_o` | Output | Same as `<field>_i` | Destination stage | Stored value of the same field. Meaningful when `valid_o` is 1. |

- The ports appear in four groups: system (`clk`, `rst_n`), hazard control (`stall`, `flush`), source stage (`valid_i`, then the `<field>_i` ports) and destination stage (`valid_o`, then the `<field>_o` ports) ([PIPE-D2](#10-decisions-and-open-items)).
- Each module has one `<field>_i` and `<field>_o` pair per field.
- Each `<field>_o` has the type and width of its `<field>_i`, enums included.
- The field list and each field's type come from the BASE boundary section in the section 4 table ([PIPE-D4](#10-decisions-and-open-items)).
- The block has no parameter, because each width comes from the field type.

## 4. Internal Structure

| Module | RTL file | Description | Source stage | Destination stage | Fields defined in |
| --- | --- | --- | --- | --- | --- |
| `if_id_pipeline` | `rtl/if_id_pipeline.sv` | IF/ID pipeline register for the fetched instruction and its PC. | IF | ID | [IF/ID boundary](5-stage-baseline-core.md#ifid-boundary) |
| `id_ex_pipeline` | `rtl/id_ex_pipeline.sv` | ID/EX pipeline register for decoded operands and control. | ID | EX | [ID/EX boundary](5-stage-baseline-core.md#idex-boundary) |
| `ex_mem_pipeline` | `rtl/ex_mem_pipeline.sv` | EX/MEM pipeline register for the EX result and memory control. | EX | MEM | [EX/MEM boundary](5-stage-baseline-core.md#exmem-boundary-and-data-request-ownership) |
| `mem_wb_pipeline` | `rtl/mem_wb_pipeline.sv` | MEM/WB pipeline register for the results and writeback control. | MEM | WB | [MEM/WB boundary](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary) |

- The four modules have no sub-block, and the table lists one module per file ([PIPE-D1](#10-decisions-and-open-items)).
- The [memory stage](memory-stage.md) owns the rule that EX/MEM and MEM/WB carry `rd`, `reg_write` and `wb_src` unchanged.

## 5. State

| Register | Reset value | Updater |
| --- | --- | --- |
| `valid_o` | 0, asynchronously on `rst_n` low | The rising edge of `clk`, by the Condition table of section 6 |
| `<field>_o` | None, because BASE does not reset datapath payload ([reset architecture](5-stage-baseline-core.md#reset-architecture)) | The rising edge of `clk`, when the payload bullet of section 6 holds |

- Each register owns its stored valid and its payload.
- The source stage owns `valid_i` and the `<field>_i` ports only for the cycle it presents them.
- A dead entry has a stored valid of 0, and its payload has no defined value.
  - At power-up, before the first load, the payload is unknown.
  - After a flush, the payload keeps the last loaded value, which is defined but not meaningful.
  - After reset, the payload keeps its value until a load. A load can happen during reset (section 6), and no consumer may use it, because the stored valid is 0.

## 6. Behavior

- The priority is reset, flush, stall, then load, and the first applicable condition decides ([PR-D1](5-stage-baseline-core.md#pipeline-register-local-control)).

### Condition table

| First applicable condition | Stored valid | Stored payload |
| --- | --- | --- |
| Reset active (`rst_n` 0) | Clears to 0, asynchronously | Not reset; the payload bullet below states when it loads |
| `flush` 1 | Clears to 0 | Retains |
| `stall` 1, `flush` 0 | Retains | Retains |
| `valid_i` 0, `stall` 0, `flush` 0 | Clears to 0 | Retains |
| Otherwise | Becomes 1 | Loads `<field>_i` |

- The payload loads at a rising edge of `clk` exactly when `valid_i` is 1, `stall` is 0 and `flush` is 0.
  - This holds whether or not `rst_n` is 0, because the payload has no reset.

## 7. Timing and Control

- `valid_o` and the `<field>_o` ports change only at the rising edge of `clk`, except that `rst_n` clears `valid_o` asynchronously.
- Apart from that clear, no output depends on an input in the same cycle, because the outputs are registered.
- `stall`, `flush`, `valid_i` and the `<field>_i` ports are sampled at the same edge.
- The hazard control unit logic that drives `flush` is therefore a path into every payload load enable.
  - The [hazard control unit](hazard-control-unit.md#6-behavior) states which events drive it, and no timing target is set for this path.

### When valid

| Signal group | When valid |
| --- | --- |
| `valid_o` | Every cycle |
| `<field>_o` | When `valid_o` is 1 |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | Takes effect at once, with no clock edge. |
| Stall | Takes effect at the rising edge of `clk`. |
| Flush | Takes effect at the rising edge of `clk`. |

- The trace shows every row of the Condition table once, then the reset edge.
- Before E1, `rst_n` was released after power-up, `valid_o` is 0 and the payload is unknown.
- `rst_n` is 1 from E1 to E6.
- `A`, `B`, `C` and `D` are values on `<field>_i`.

| Edge | Inputs | State before (`valid_o`, payload) | Action | State after |
| --- | --- | --- | --- | --- |
| E1 | `valid_i` 1, `stall` 0, `flush` 0, `<field>_i` = `A` | (0, unknown) | Load | (1, `A`) |
| E2 | `valid_i` 1, `stall` 1, `flush` 0, `<field>_i` = `B` | (1, `A`) | Retain both | (1, `A`) |
| E3 | `valid_i` 0, `stall` 0, `flush` 0 | (1, `A`) | Clear valid; retain payload | (0, `A`) |
| E4 | `valid_i` 1, `stall` 0, `flush` 0, `<field>_i` = `B` | (0, `A`) | Load | (1, `B`) |
| E5 | `valid_i` 1, `stall` 1, `flush` 1, `<field>_i` = `C` | (1, `B`) | Flush beats stall: clear valid; retain payload | (0, `B`) |
| E6 | `valid_i` 1, `stall` 0, `flush` 0, `<field>_i` = `C` | (0, `B`) | Load | (1, `C`) |
| E7 | `rst_n` falls while `clk` is low | (1, `C`) | Clear valid asynchronously; payload unchanged | (0, `C`) |
| E8 | `rst_n` 0, `valid_i` 1, `stall` 0, `flush` 0, `<field>_i` = `D` | (0, `C`) | Valid stays 0; payload loads | (0, `D`) |

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| `stall` and `flush` of each register follow the table of the hazard control unit, and its preconditions P1 to P3 hold | The hazard control unit ([table](hazard-control-unit.md#6-behavior), [preconditions](hazard-control-unit.md#8-assumptions-and-corner-cases)) | The register obeys the wrong controls, because it arbitrates nothing. |
| Every consumer qualifies each effect with `valid_o` | The destination stages | A consumer that omits the qualifier acts on a stale or unknown payload. |

| Case | Inputs | Result |
| --- | --- | --- |
| Flush and stall together | `flush` 1, `stall` 1 | `valid_o` becomes 0 and the payload is retained, because a flush invalidates an entry and a stall only preserves one that is still live. |
| Reset with flush or stall | `rst_n` 0, any `flush` and `stall` | `valid_o` is 0 whatever `flush` and `stall` are; the payload follows section 6. |
| Invalid entry with stall | `stall` 1, `flush` 0, `valid_i` 0 | A stored live entry is held, and `valid_o` stays 1. |

## 9. Verification

- No test of these modules exists in `tb/`.
- Expected values come from the Condition table of section 6 and PR-D1, not from the RTL.

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Flush beats stall | `flush` 1 and `stall` 1 on an edge with stored valid 1 | `valid_o` 0; payload unchanged |
| Reset overrides both | `rst_n` 0, with `flush` and `stall` each at 0 and 1 | `valid_o` 0; payload changes only when `valid_i` is 1, `stall` is 0 and `flush` is 0 |
| Invalid entry | `valid_i` 0, `stall` 0, `flush` 0 on an edge with stored valid 1 | `valid_o` 0; payload unchanged |
| Stall retains | `stall` 1, `flush` 0, `valid_i` 1, `<field>_i` differs from the stored value | `valid_o` and payload unchanged |
| Flush retains payload | `flush` 1, `stall` 0, `valid_i` 1, `<field>_i` differs from the stored value | `valid_o` 0; payload unchanged |
| Load | `valid_i` 1, `stall` 0, `flush` 0 | `valid_o` 1; payload equals `<field>_i` |
| Payload qualification (not adopted) | Random initial payload at power-up, with `valid_o` 0 for the first cycles; a core run with bubbles | No architectural effect from a dead entry; a consumer that ignores `valid_o` mismatches the reference model |
| Per-boundary arbitration | A core-level run with the hazard control unit driving `stall` and `flush` per register | Each boundary's stall and flush match the [hazard control unit table](hazard-control-unit.md#6-behavior) |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| PIPE-D1 | Four modules, one per file, and no parameterized module. All four share the ports of section 3 and the behavior of section 6. | Owner decision. |
| PIPE-D2 | The ports use the generic groups and order of section 3. Each `<field>_o` has the type of its `<field>_i`, enums included. | The shared template keeps the four registers identical, so one review covers all four. |
| PIPE-D3 | Every module has `stall` and `flush`. The core top must tie `flush` of EX/MEM and MEM/WB to 0. | BASE never sets those two flushes and the HCU has no output for them ([HCU-D2](hazard-control-unit.md#10-decisions-and-open-items)). The shared template costs a `flush` input on two registers that never use it. |
| PIPE-D4 | The spec names no field. The BASE boundary sections are the authority for each field list and type. | One owner for each field list. |
| PIPE-D5 | A valid bit, not payload zeroing, encodes a bubble. | The payload then needs no reset and no zeroing. A payload that is not cleared means every side effect must be qualified by `valid_o` (section 8). |

- Exception to the Description rule: the header Description is one sentence for four modules, because no RTL Description line fits all four. Section 4 lists the four lines verbatim.
- Exception to rule 3: section 6 repeats the PR-D1 condition table of BASE, because the table is the whole behavior of this block. Its Reset row refines BASE: reset does not gate the payload.
- History: 2026-11-06 the Owner settled PR-O1 to PR-O8 and accepted the spec. The format descends from an older project's pipeline register, changed to meet PR-D1.
- 2026-11-07 rewritten in the block spec format. IDs renumbered, the code block and three coding-shape decisions dropped, and the trace made one sequence.

| Old ID | New ID | Status |
| --- | --- | --- |
| PR-O1 | PIPE-D1 | Kept |
| PR-O2 | PIPE-D2 | Kept |
| PR-O3 | none | Retired: it fixes the RTL coding shape (rule 12); section 7 states that the outputs are registered |
| PR-O4 | none | Retired: it fixes the RTL coding shape (rule 12); section 6 states the priority |
| PR-O5 | none | Retired: it fixes the RTL coding shape (rule 12); section 6 states the payload load in words |
| PR-O6 | PIPE-D3 | Kept |
| PR-O7 | PIPE-D4 | Kept |
| PR-O8 | PIPE-D5 | Kept; the two design reasons stay, and the older-project wording moved to History |

- Open items:
  - The random-payload check (section 9, "Payload qualification") is not adopted, and no BASE record states it.
    - Without it, the section 8 qualification row has no evidence.
    - Options: (a) adopt it in BASE's verification plan; (b) keep it as a planned check only.
    - Recommendation: (a), because the cost of qualifying every effect comes from the payload not being reset.
    - Responsible: Việt.
