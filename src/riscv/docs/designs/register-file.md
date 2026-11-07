# Register File

| Field | Value |
| --- | --- |
| Description | Store x1-x31 with two bypassed read ports and one write port. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-07 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/register_file.sv`, module `register_file`, instance `id_register_file` in `decode_stage` |
| Parent | [Decode stage](decode-stage.md) (composition and leaf connections, ID-D3); [Five-stage BASE core](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass) (register-file timing, WB-to-ID bypass priority) and [reset architecture](5-stage-baseline-core.md#reset-architecture); [Writeback stage](writeback-stage.md) (`rf_write_fire`, `wb_data`) |

## 1. Overview

- `register_file` holds `x1` to `x31` and returns the two ID read values with the WB-to-ID bypass applied.
- WB owns `wb_data` and `rf_write_fire`, and this block owns the storage, the read ports and the WB-to-ID bypass ([Writeback stage](writeback-stage.md)).
- It has no reset port, because BASE does not reset `x1` to `x31` ([BASE reset architecture](5-stage-baseline-core.md#reset-architecture)).
- It has no hazard detection, no forwarding to EX, no valid input, no stall input and no debug port ([RF-D3](#10-decisions-and-open-items)). It sees only register indices and data, with no instruction knowledge.

## 2. Block Design

```text
                      clk <- core clock
                             |
                +--------------------------+
rs1_id, rs2_id  |                          | -> rs1_value, rs2_value
rf_write_fire,  |      register_file       |      (decode_stage)
wb_rd, wb_data  |                          |
 <- decode_stage|                          |
                +--------------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1 | Core clock | Clock of the write. |
| `rs1_id` | Input | 5 | `decode_stage` | Read index of port 1. |
| `rs2_id` | Input | 5 | `decode_stage` | Read index of port 2. |
| `rf_write_fire` | Input | 1 | `decode_stage` | Permission to write `wb_rd` with `wb_data` at the rising edge. |
| `wb_rd` | Input | 5 | `decode_stage` | Write index. |
| `wb_data` | Input | `DATA_WIDTH` | `decode_stage` | Write and bypass data. |
| `rs1_value` | Output | `DATA_WIDTH` | `decode_stage` | Read result of port 1. |
| `rs2_value` | Output | `DATA_WIDTH` | `decode_stage` | Read result of port 2. |

- A read index is accepted in any cycle, and an unused source is still read.
- The vectors are unsigned bit patterns with no width conversion. The block has no module parameter, and the supported configuration is `DATA_WIDTH` 32.

### Width domains

| Domain | Package constant | Signals |
| --- | --- | --- |
| Register and arithmetic datapath | `DATA_WIDTH` | `wb_data`, `rs1_value`, `rs2_value` |

## 4. Internal Structure

- None, because the block is one storage array with its read and write logic and has no sub-blocks.
- The mapping of the 31 entries to array indices and the coding style are implementation freedom, and the internal storage name is not fixed ([RF-D3](#10-decisions-and-open-items)).

## 5. State

| Register | Reset value | Updater |
| --- | --- | --- |
| `x1` to `x31`, 31 entries of `DATA_WIDTH` bits | None, so unspecified until written | The rising edge of `clk`, as the Write table shows |

- `x0` has no storage ([RF-D2](#10-decisions-and-open-items)).
- The block holds no valid, pending or control state, so `rf_write_fire` is the only write authorization. An invalid pipeline entry cannot write, because WB qualifies validity and retirement ([Writeback stage](writeback-stage.md)).

## 6. Behavior

### Read table

| Condition, per read port | `rs1_value` or `rs2_value` equals |
| --- | --- |
| The read index is 0 | 0 |
| The read index is nonzero, `rf_write_fire` is 1 and `wb_rd` equals the read index | `wb_data` |
| The read index is nonzero and either `rf_write_fire` is 0 or `wb_rd` differs from it | The stored value of the register named by the read index |

### Write table

| Condition at the rising edge | Effect |
| --- | --- |
| `rf_write_fire` is 1 and `wb_rd` is nonzero | The register named by `wb_rd` takes `wb_data`, and every other register holds |
| `rf_write_fire` is 1 and `wb_rd` is 0 | No register changes |
| `rf_write_fire` is 0 | No register changes |

- BASE owns the read priority ([BASE register-file timing](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass)), and the Read table states what the block does at its ports.
- Each read port applies the Read table independently of the other.
- A read in the cycle of a write returns `wb_data` through the bypass, never the storage. Its result does not depend on read-during-write behavior of the storage implementation.
- The block has one write port, so no write-write conflict exists. Consecutive writes to the same register on consecutive edges leave the later value.

## 7. Timing and Control

- `rs1_value` depends on `rs1_id`, `rf_write_fire`, `wb_rd`, `wb_data` and the storage, and `rs2_value` likewise on `rs2_id`. There is no clock dependence, latency or handshake.
- The write happens at the rising edge of `clk`, and the inputs sampled before the edge decide it. `clk` clocks the write only, and there is no falling-edge write. Setup and hold belong to the core.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset port. Valid gating in the core and `rf_write_fire` from WB keep reset from writing ([BASE reset architecture](5-stage-baseline-core.md#reset-architecture)). |
| Stall | None: the block has no stall input. An unresolved MEM wait gives `rf_write_fire` 0 (BASE), so the block writes nothing, and the one retiring write happens once on the release edge. |
| Flush | None: the block has no flush input. A younger redirect does not cancel an older WB write. |

### Trace

- Initial storage: `x7` is `0x1111_1111` and `x8` is `0x2222_2222`. Values are sampled just before each rising edge.

| Edge | Inputs before the edge | Read outputs before the edge | Storage after the edge |
| --- | --- | --- | --- |
| E1 | `rf_write_fire` 1, `wb_rd` 7, `wb_data` 0xDDDD_DDDD, `rs1_id` 7, `rs2_id` 8 | `rs1_value` 0xDDDD_DDDD (bypass), `rs2_value` 0x2222_2222 | `x7` 0xDDDD_DDDD, `x8` 0x2222_2222 |
| E2 | `rf_write_fire` 0, `wb_rd` 7, `wb_data` 0xEEEE_EEEE, `rs1_id` 7, `rs2_id` 7 | `rs1_value` 0xDDDD_DDDD, `rs2_value` 0xDDDD_DDDD (storage, `wb_data` ignored) | `x7` 0xDDDD_DDDD |
| E3 | `rf_write_fire` 1, `wb_rd` 0, `wb_data` 0xEEEE_EEEE, `rs1_id` 0, `rs2_id` 8 | `rs1_value` 0x0000_0000, `rs2_value` 0x2222_2222 | `x7` 0xDDDD_DDDD, `x8` 0x2222_2222 |

- E1 followed by E2 is the write-then-read case: the value reaches the read port one cycle before it is in storage and stays there afterwards.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](#10-decisions-and-open-items)) | X and Z behavior is unspecified. |
| `rf_write_fire` is 1 for one retirement edge only, and a held WB entry gives `rf_write_fire` 0 | WB and the core ([Writeback stage](writeback-stage.md), [BASE](5-stage-baseline-core.md#register-file-timing-and-wb-to-id-bypass)) | The block cannot detect a repeated `rf_write_fire` and has no error mechanism. |

| Case | Inputs | Result |
| --- | --- | --- |
| Read before write | A read of a register never written, with no bypass match | The value is unspecified, and no oracle may use it. |

## 9. Verification

1. A directed leaf test exists: runner `tb/runners/test_register_file.py` runs the top `register_file` with Verilator and cocotb. The module `register_file_cocotb` has 10 tests: `test_write_read_all`, `test_data_width`, `test_write_isolation`, `test_bypass_each_port`, `test_bypass_both_ports`, `test_read_during_write`, `test_no_bypass_without_fire`, `test_x0_read`, `test_x0_write_ignored` and `test_consecutive_writes`.
2. Each planned check below has one test in the module.
3. Expected values are literals taken from the Read and Write tables, never from the DUT. Stimulus timing follows `tb/README.md`.
4. A leaf pass shows only the checked vectors. The register-file checks through the stage are in [decode-stage.md](decode-stage.md#planned-checks).

### Planned checks

| Requirement | Stimulus | Expected observation |
| --- | --- | --- |
| Write and storage | Write a distinct pattern to each of `x1` to `x31`, then read all back | Each returns its own pattern, with no aliasing or index shift |
| Data width | Patterns `0xFFFFFFFF`, `0xA5A5A5A5`, `0x5A5A5A5A` | All 32 bits are stored and returned |
| Write isolation | Write `xk`, then read all other registers | Only `xk` changes |
| Bypass, each port | `rf_write_fire` 1 and the read index equal to `wb_rd`, on port 1 and on port 2 separately | That port returns `wb_data`, and the other returns its stored value |
| Bypass, both ports | Both ports read the written index | Both return `wb_data` |
| Read-during-write independence | Sample the read before the edge and after it | Before the edge `wb_data`, after the edge the same value from storage |
| No bypass without fire | `rf_write_fire` 0, `wb_rd` equal to a read index, `wb_data` different from the stored value | The stored value |
| `x0` read | Read index 0 with and without `rf_write_fire`, with `wb_rd` 0 and nonzero | 0 always |
| `x0` write ignored | `rf_write_fire` 1, `wb_rd` 0, `wb_data` nonzero, then read `x1` to `x31` and `x0` | No register changes, and `x0` reads 0 |
| Consecutive writes | The same register on consecutive edges | The later value, and the earlier value is never observed after its edge |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| RF-D1 | The port names equal the `decode_stage` names, so the stage only wires them. | There is no renaming layer, and it matches [decode-stage.md](decode-stage.md). |
| RF-D2 | The storage holds only `x1` to `x31`. The block guarantees `x0` itself: a read of index 0 returns 0 through the Read table, and a write with `wb_rd` 0 has no target. WB's `rd` nonzero term in `rf_write_fire` stays, and the block does not rely on it. | It is safe independently of WB, and no storage exists for `x0`. |
| RF-D3 | The block has no debug or observation port. Core verification observes architectural results black-box, with self-checking programs that write a memory signature. Hierarchical access to the storage is for debugging only, not an oracle. The internal storage name is not fixed. | It keeps the interface minimal. |
| RF-D4 | The block is safe, with no logic added beyond what safety requires ([ID-D6](decode-stage.md#10-decisions-and-open-items)). | None recorded. |
| RF-D5 | The guaranteed input domain is 0 and 1 only, and X and Z behavior is unspecified and untested. | The same as the accepted [EX](execute-stage.md#8-assumptions-and-corner-cases) and [WB](writeback-stage.md) contracts, with no extra logic (RF-D4). |

- History: 2026-10-29 the Owner accepted the spec, stated R1 to R4 and resolved O1 (revision RF D1).
- 2026-11-07 rewritten in the block spec format, with IDs renumbered. The RTL mapping paragraph and the closing remarks went.

| Old ID | New ID | Status |
| --- | --- | --- |
| R1 | RF-D1 | Kept |
| R2 | RF-D2 | Kept; the read priority and the write rule of the old section 5 are the Read and Write tables |
| R3 | RF-D3 | Kept |
| R4 | RF-D4 | Kept |
| O1 | RF-D5 | Kept; `immediate-generator.md` and `control-unit.md` cite it |
| RF D1 (revision label, 2026-10-29; `tb/README.md` cites it) | none | Retired as a label: History carries the date |

- Open items: none.
