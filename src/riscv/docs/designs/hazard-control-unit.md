# Hazard Control Unit

| Field | Value |
| --- | --- |
| Description | Detects load-use and drives pipeline stall, flush, advance and fetch acceptance from the MEM wait and EX redirect events. |
| Last modified | 2026-11-06 |
| Status | Accepted by Việt on 2026-11-06 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/hazard_control_unit.sv`, module `hazard_control_unit` |
| Parent | [Five-stage BASE core](5-stage-baseline-core.md) (pipeline-control priority, pipeline-register local control, load-use definition, reset architecture); [Fetch stage](fetch-stage.md) §2 and D-3 |

## 1. Overview

- The HCU is the only block that turns core events into per-register control, because under [PR-D1](5-stage-baseline-core.md#pipeline-register-local-control), a pipeline register obeys its inputs and arbitrates nothing.
- It handles the MEM wait, the EX redirect and load-use.
  - It detects load-use itself, because it sees the ID and EX instructions together.
- It is purely combinational, because every decision depends only on the current cycle.
- It does not create `redirect_fire`, route the redirect to IF, forward operands, or produce any `valid_i`.

## 2. Block Design

```text
                                              rst_n (core reset)
                                                |
                                 +------------------------------+
mem_wait <- memory_stage         |                              | -> advance_allowed (execute_stage, writeback_stage)
redirect_fire <- execute_stage   |                              | -> fetch_accept (fetch_stage)
id_valid <- IF/ID                |                              | -> if_id_stall (IF/ID)
id_rs1_id <- decode_stage        |                              | -> if_id_flush (IF/ID)
id_rs2_id <- decode_stage        |                              | -> id_ex_stall (ID/EX)
id_rs1_used <- decode_stage      |     hazard_control_unit      | -> id_ex_flush (ID/EX)
id_rs2_used <- decode_stage      |                              | -> ex_mem_stall (EX/MEM)
ex_valid <- ID/EX                |                              | -> mem_wb_stall (MEM/WB)
ex_mem_en <- ID/EX               |                              |
ex_mem_write <- ID/EX            |                              |
ex_rd <- ID/EX                   |                              |
                                 +------------------------------+
```

## 3. Interface

- The HCU has 12 inputs and 8 outputs.
- Each port is 1 bit wide, except the three 5-bit register identifiers.

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `rst_n` | Input | 1 | Core reset | Active-low core reset. Only `advance_allowed` depends on it. |
| `mem_wait` | Input | 1 | `memory_stage` | MEM holds an unresolved wait: a memory owner has not completed. |
| `redirect_fire` | Input | 1 | `execute_stage` | EX takes a control-flow redirect this cycle. The redirect unit already gates it with `advance_allowed`. |
| `id_valid` | Input | 1 | IF/ID | The instruction in ID is valid. |
| `id_rs1_id` | Input | 5 | `decode_stage` | `rs1` field of the ID instruction. |
| `id_rs2_id` | Input | 5 | `decode_stage` | `rs2` field of the ID instruction. |
| `id_rs1_used` | Input | 1 | `decode_stage` | The ID instruction reads `rs1`. |
| `id_rs2_used` | Input | 1 | `decode_stage` | The ID instruction reads `rs2`. |
| `ex_valid` | Input | 1 | ID/EX | The instruction in EX is valid. |
| `ex_mem_en` | Input | 1 | ID/EX | The EX instruction accesses memory. |
| `ex_mem_write` | Input | 1 | ID/EX | The EX memory access is a store. |
| `ex_rd` | Input | 5 | ID/EX | Destination register of the EX instruction. |
| `advance_allowed` | Output | 1 | `execute_stage`, `writeback_stage` | EX and WB may advance this cycle. |
| `fetch_accept` | Output | 1 | `fetch_stage` | `1` lets IF/ID take a fetch entry this cycle, if one is valid; `0` blocks it. |
| `if_id_stall` | Output | 1 | IF/ID | Holds the IF/ID register. |
| `if_id_flush` | Output | 1 | IF/ID | Invalidates the IF/ID register. |
| `id_ex_stall` | Output | 1 | ID/EX | Holds the ID/EX register. |
| `id_ex_flush` | Output | 1 | ID/EX | Invalidates the ID/EX register. |
| `ex_mem_stall` | Output | 1 | EX/MEM | Holds the EX/MEM register. |
| `mem_wb_stall` | Output | 1 | MEM/WB | Holds the MEM/WB register. |

## 4. Internal Structure

- None, because the HCU has no sub-blocks.

## 5. State

- None, because every decision depends only on the current cycle (section 1).

## 6. Behavior

- The HCU applies the next-state priority of the BASE core: reset, MEM wait, redirect, load-use, then normal advance ([pipeline-control priority](5-stage-baseline-core.md#pipeline-control-priority)).
- A load-use exists when EX holds a valid load with a nonzero destination and ID reads that destination through `rs1` or `rs2`, because the loaded value is not ready until MEM ([load-use definition](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass)).
  - The `x0` destination never counts, because a write to `x0` creates no dependency.
- The table gives each output for each condition, in priority order.

| Condition | advance_allowed | fetch_accept | if_id_stall | if_id_flush | id_ex_stall | id_ex_flush | ex_mem_stall | mem_wb_stall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Reset (`rst_n` low) | 0 | any | any | any | any | any | any | any |
| MEM wait (`mem_wait` high) | 0 | 0 | 1 | 0 | 1 | 0 | 1 | 1 |
| Redirect (`redirect_fire` high, no MEM wait) | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 |
| Load-use (load-use present, no MEM wait, no redirect) | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 0 |
| Normal (none of the above) | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

- Reset makes `advance_allowed` 0 and leaves the other outputs any, because register reset beats stall and flush under PR-D1, and fetch ignores `fetch_accept` during reset.
- A MEM wait stalls all four registers, because nothing may move until MEM completes.
- A load-use holds IF/ID and flushes ID/EX, because the dependent instruction must wait, a bubble must enter EX, and the load must still advance to EX/MEM.
- A load-use does not flush ID/EX during a MEM wait, because PR-D1 gives flush priority over stall, so without this exception the load in ID/EX would be cleared while it must hold.
- Outside reset, `fetch_accept` is 1 exactly when IF/ID is neither stalled nor flushed, because a fetch entry is released only when IF/ID takes it.
- No other exception exists, because a redirect never coincides with a MEM wait or a load-use ([section 8](#8-assumptions-and-corner-cases) gives the enforcement).

## 7. Timing and Control

- Every output is combinational in the same cycle, because the block holds no state that could delay a value.
- No combinational loop passes through the block, because the redirect path leaves through `if_id_flush`, `id_ex_flush` and `fetch_accept` and never reaches `advance_allowed` or the load-use decision.
- `data_obi_controller` drives `mem_wait` high while its owner waits for a response.
  - `mem_wait` stays high until `rvalid` arrives, because the response is what completes the wait.
  - The path from `rvalid` through `mem_wait` reaches frontend next-state logic and the register control inputs that this block drives.
  - No path from `rvalid` reaches `req`, because `req` depends only on registered fetch-entry state.

### When valid

| Signal group | When valid |
| --- | --- |
| All eight outputs | Every cycle, combinational from the inputs of that cycle |

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset (`rst_n` low) | Forces `advance_allowed` to 0. The other outputs are any: register reset beats stall and flush under PR-D1, and fetch ignores `fetch_accept` during reset. |
| Stall | Drives the four `*_stall` outputs from `mem_wait` and the load-use decision. Holds no stall state. |
| Flush | Drives the `*_flush` outputs. Clears no register itself; each register applies its own flush. |

- The trace shows the hardest case: a load-use behind a MEM wait, then the response.
- Before edge 1, `C` (reads `x5`) is in IF/ID, `Lx` (`LW x5, 0(x2)`) is in ID/EX, `S` waits in EX/MEM, and `B` is in MEM/WB.

| Cycle / edge | Inputs | State before (IF/ID, ID/EX, EX/MEM, MEM/WB) | Outputs | State after |
| --- | --- | --- | --- | --- |
| 1 | `mem_wait` high (S waits, `rvalid` low); load-use present | `C`, `Lx`, `S`, `B` | `id_ex_flush` low; all stalls high; `fetch_accept` low; `advance_allowed` low | Unchanged |
| 2 | `mem_wait` low (`rvalid` high for S); load-use present | `C`, `Lx`, `S`, `B` | `id_ex_flush` high; `if_id_stall` high; `fetch_accept` low; `advance_allowed` high; `B` retires | `C` held in IF/ID; bubble in ID/EX; `Lx` in EX/MEM; `S` completes in MEM/WB |

- Without the exception, edge 1 raises both stall and flush on ID/EX, and flush wins under PR-D1, so the load is cleared although BASE holds it.
- After edge 2, `Lx` owns MEM and waits for its own response.

## 8. Assumptions and Corner Cases

- The behavior relies on three preconditions that the HCU does not check, because the HCU sees only its inputs and each precondition is guaranteed upstream.

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| P1: `redirect_fire` is high only when `mem_wait` is low and `rst_n` is high | `redirect_unit`, which gates `redirect_fire` with `advance_allowed` | ID/EX receives stall and flush together, and flush wins, so the instruction held by MEM wait is cleared. Outside the contract. |
| P2: `redirect_fire` never occurs together with a load-use | `control_unit`: `mem_en` is set only for loads and stores, and cleared for unsupported encodings | IF/ID receives stall and flush together, and flush wins. The EX instruction would be a load and a redirect at once, which the decoder does not produce. |
| P3: the `id_*` inputs are the ID instruction's fields, and the `ex_*` inputs are the EX instruction's | The IF/ID and ID/EX pipeline registers and the decode stage | A wrong `ex_rd` or source field gives a false or missed load-use stall. |

- Three corner cases combine two events on one edge.

| Case | Inputs | Result | Reason |
| --- | --- | --- | --- |
| MEM wait with load-use | MEM wait high and load-use present | All four registers hold; `id_ex_flush` low | The MEM-wait exception in section 6 keeps the load in ID/EX. |
| Response with load-use | MEM wait low and load-use present on the response edge | Load-use outputs; the completed memory instruction enters MEM/WB, the load enters EX/MEM, a bubble enters ID/EX | `mem_wait` is low on the response edge ([memory stage](memory-stage.md)). |
| Response with redirect | MEM wait low and `redirect_fire` high on the response edge | Redirect outputs; the completed memory instruction enters MEM/WB, the redirecting instruction enters EX/MEM | `advance_allowed` is high on that edge, so the redirect is allowed. |

- No register is stalled and flushed in the same cycle, because P1 and P2 exclude each input pair that would set both.

## 9. Verification

- No HCU test exists.
- The checks below are planned. Expected values follow from the priority table in section 6.

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Reset row | `rst_n` low; other inputs any | `advance_allowed` 0 |
| MEM wait row | `mem_wait` high; no load-use; no redirect | All four stalls high; both flushes low; `fetch_accept` low; `advance_allowed` low |
| Redirect row | `redirect_fire` high; `mem_wait` low; no load-use | Both flushes high; the four stalls low; `fetch_accept` low; `advance_allowed` high |
| Load-use row | ID reads the destination of a valid load in EX; `mem_wait` low; no redirect | `if_id_stall` high; `id_ex_flush` high; `id_ex_stall`, `ex_mem_stall` and `mem_wb_stall` low; `fetch_accept` low |
| Normal row | All inputs 0 | All stalls and flushes low; `fetch_accept` high; `advance_allowed` high |
| MEM wait with load-use (exception) | `mem_wait` high; load-use present | `id_ex_flush` low; `id_ex_stall` high. A design that raises `id_ex_flush` here fails this row. |
| Response with load-use | `mem_wait` low on the response edge; load-use present | Load-use row values, with the completed memory instruction entering MEM/WB |
| Response with redirect | `mem_wait` low and `redirect_fire` high on the response edge | Redirect row values, with the completed memory instruction entering MEM/WB |
| Stateless | Any input sequence | Outputs depend only on the current inputs; no clock input exists |

## 10. Decisions and Open Items

- The Owner settled these decisions on 2026-11-05.

| ID | Decision | Reason |
| --- | --- | --- |
| HCU-D1 | One purely combinational module with no clock and no state. It does not create `redirect_fire`, route the redirect to IF, forward operands, or produce `valid_i`. | Each event is decided in the cycle it occurs, and each responsibility stays with its owner block. |
| HCU-D2 | Four separate `stall` outputs. No EX/MEM or MEM/WB flush output exists. | BASE never sets those two flushes, and the core top ties them to 0. |
| HCU-D3 | `rst_n` is an input, used only for `advance_allowed`. | Reset must suppress EX and WB advance (WB-D2). |
| HCU-D4 | `fetch_accept` is 0 whenever IF/ID is stalled or flushed, so it is 0 on a redirect edge. | The HCU does not depend on how the Fetch Controller Unit treats `READY` entries on a redirect; the kill frees them either way. |
| HCU-D5 | A load-use does not flush ID/EX during a MEM wait. | PR-D1 gives flush priority over stall, so without this exception the load in ID/EX would be cleared under a MEM wait. |
| HCU-D6 | No other exception exists. | Preconditions P1 and P2 in section 8 exclude the other coinciding pairs, so another exception would add logic and no case. |

- History: 2026-11-05 decisions settled; 2026-11-06 rewritten in the block spec format, IDs renumbered.

| Old ID | New ID | Status |
| --- | --- | --- |
| HCU-O1 | HCU-D1 | Kept |
| HCU-O2 | none | Retired: the module name is in the header |
| HCU-O3 | HCU-D2 | Kept |
| HCU-O4 | HCU-D3 | Kept |
| HCU-O5 | HCU-D4 | Kept |
| HCU-O6 | none | Retired: behavior is defined by the table in section 6 |
| HCU-O7 | HCU-D5 | Kept |
| HCU-O8 | HCU-D6 | Kept |

- Open items: none.
