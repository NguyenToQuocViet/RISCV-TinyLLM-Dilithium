# Fetch Buffer — Block Design

**Status:** Accepted by Việt on 2026-11-06 (IF-A3). Control content moved to [Fetch Controller Unit](fetch-controller-unit.md).
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner. Decisions FB-O8 and FB-O9 are in section 9 (2026-11-06).
**Parent contract:** [five-stage BASE core](5-stage-baseline-core.md#instruction-fetch-organization) (IF-A3); [Fetch stage](fetch-stage.md) §3, §4.
**RTL mapping:** `rtl/fetch_buffer.sv`, module `fetch_buffer`, instance `if_fetch_buffer` in `prefetch_unit`; RTL for this move is delegated (fetch-stage F-d).

## 1. Purpose and boundary

`fetch_buffer` is the payload array of the instruction frontend: the `pc` and `instruction` of each of the
`FETCH_DEPTH = 3` fetch entries. It holds no entry state, pointers, kill marks or choice of entry; the
[Fetch Controller Unit](fetch-controller-unit.md) owns those. Success criterion: a read of slot `s` returns the last
value written to `s` by a write whose enable was `1` on an earlier edge.

## 2. Interface contract

### Clock, reset and configuration

`clk` is the rising-edge clock of the arrays; there is no reset input. Slots `0..2`; `ADDR_WIDTH` and `INSTR_WIDTH` are
`32` from `riscv_pkg`.

### Ports and payloads

All ports are individual signals: 9 inputs and 3 outputs.

| Signal | Direction | Type / width | Meaning | Source |
| --- | --- | --- | --- | --- |
| `clk` | Input | 1-bit `logic` | Rising-edge clock of the arrays | Reset architecture |
| `pc_write` | Input | 1-bit `logic` | Write `pc` of slot `pc_write_slot` | Controller `pc_write` (FCU-O4) |
| `pc_write_slot` | Input | `logic [1:0]` | Slot written by `pc_write` | Controller `head_ptr` (FCU-O4) |
| `pc_write_data` | Input | `logic [ADDR_WIDTH-1:0]` | Fetch address stored in the slot | Controller `next_fetch_pc` (FCU-O4) |
| `instruction_write` | Input | 1-bit `logic` | Write `instruction` of slot `instruction_write_slot` | Controller `response_fire` (FCU-O4) |
| `instruction_write_slot` | Input | `logic [1:0]` | Slot written by `instruction_write` | Controller `prv` (FCU-O4) |
| `instruction_write_data` | Input | `logic [INSTR_WIDTH-1:0]` | Instruction word stored in the slot | OBI leaf `response_data` (FOI-O6) |
| `present_slot` | Input | `logic [1:0]` | Read address of `present_pc` | Controller `issue_ptr` (FCU-O9) |
| `fetch_slot` | Input | `logic [1:0]` | Read address of `fetch_pc` and `fetch_instruction` | Controller `tail_ptr` (FCU-O7) |
| `present_pc` | Output | `logic [ADDR_WIDTH-1:0]` | `pc[present_slot]` | OBI leaf (FOI-O1) |
| `fetch_pc` | Output | `logic [ADDR_WIDTH-1:0]` | `pc[fetch_slot]` | Fetch stage output |
| `fetch_instruction` | Output | `logic [INSTR_WIDTH-1:0]` | `instruction[fetch_slot]` | Fetch stage output |

## 3. Internal organization

Two indexed arrays, `pc[0..2]` and `instruction[0..2]`, and one read mux per output.

## 4. State and ownership

| State | Width / type | Reset | Meaning | Written by |
| --- | --- | --- | --- | --- |
| `pc[s]`, `s = 0..2` | `ADDR_WIDTH` | not reset | Fetch address of slot `s` | `pc_write` |
| `instruction[s]`, `s = 0..2` | `INSTR_WIDTH` | not reset | Instruction payload of slot `s`; meaningful only while the controller marks the slot `READY` | `instruction_write` |


## 5. Behavioral and next-state rules

- **Write.** At a rising edge, `pc[pc_write_slot] := pc_write_data` when `pc_write = 1`, and
  `instruction[instruction_write_slot] := instruction_write_data` when `instruction_write = 1`. Both may occur on one
  edge. With an enable low the stored value holds. The buffer checks no slot state.
- **Read.** `present_pc = pc[present_slot]`, `fetch_pc = pc[fetch_slot]`, `fetch_instruction = instruction[fetch_slot]`,
  combinational from the arrays and the addresses. The addresses are controller registers, so outputs depend on
  registered state only.
- **Enables.** Enables and addresses come from controller inputs, may change within a cycle, and are sampled only at the
  edge. They never reach the request or valid outputs (fetch-stage §2).

## 6. Reset, cancellation, and exceptional conditions

- **Reset.** No reset action on the arrays; writes still follow their enables. The controller holds every slot `FREE` in
  reset, so `pc_write` may be 1 and a clocked write happens. The value has no meaning, since the controller reads only
  valid entries.
- **Preconditions.** Addresses are `0..2`; `3` is unreachable from reset (FCU-O11). Enables and addresses come from the
  controller only.

## 7. Representative examples or cycle traces

Buffer-level only; the controller supplies the addresses and enables.
| Edge | Inputs | State after | Outputs after the edge |
| --- | --- | --- | --- |
| E1 | `pc_write=1`, `pc_write_slot=2`, `pc_write_data=0x20` | `pc[2] = 0x20` | `present_pc` with `present_slot=2` is `0x20` |
| E2 | `instruction_write=1`, `instruction_write_slot=2`, `instruction_write_data=I1` | `instruction[2] = I1` | `fetch_pc`, `fetch_instruction` with `fetch_slot=2` are `0x20`, `I1` |

## 8. Verification obligations

Planned checks; no fetch-buffer test exists (checked 2026-11-06).

| Requirement / invariant | Stimulus or scenario | Expected observation |
| --- | --- | --- |
| Write, then read; enable low (section 5) | `pc_write` to slot `s`, read `s` through `present_slot` or `fetch_slot`; then change the data with the enable low | Read returns the written value; stored value unchanged |
| Independent writes (section 5) | `pc_write` and `instruction_write` on one edge, to different slots | Both arrays capture their own data |
| Combinational read (section 5) | Change a read address within a cycle | Output follows the array with no edge |
| Reset with enables low (section 6) | Reset asserted with `pc_write` and `instruction_write` held at 0 | Arrays unchanged |

## 9. Rationale and open decisions

**FB-O8. Payload array, not a FIFO (IF-A3).** Decision (Việt, 2026-11-06): an indexed payload array with no reset.
Entries are allocated before their data arrives and a kill reloads the pointers, so a FIFO does not fit.

**FB-O9. Read muxes in the buffer (IF-A3).** Decision (Việt, 2026-11-06): payload does not pass through the controller.

**Decision map and open items.** The only decision map is in [Fetch Controller Unit](fetch-controller-unit.md) §9, which
also holds this design's open items (none here).
