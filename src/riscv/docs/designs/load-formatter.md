# Load Formatter — Block Design

**Status:** Accepted by Việt on 2026-10-21.
**Revision:** Load Formatter D1 / 2026-10-21.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [MEM composition](memory-stage.md),
[BASE load formatting](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary).
**RTL mapping:** [load_formatter](../../rtl/load_formatter.sv);
functional simulation remains pending.

## 1. Purpose and boundary

Select the requested byte or halfword from a returned memory word and extend
it to the full datapath width, or preserve the returned word for LW. The
producer is the data OBI response path; the consumer is MEM/WB's `load_result`.
The held EX/MEM instruction supplies access type and effective-address offset.

This leaf is combinational: no clock, reset, storage or handshake. It does not
decode instructions, issue requests, track transactions or authorize MEM/WB
capture. Those responsibilities remain with the controller and parent.

## 2. Interface, timing and state

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `read_data` | Input | Unsigned `logic [DATA_WIDTH-1:0]` | Complete returned memory word |
| `effective_address` | Input | Unsigned `logic [ADDR_WIDTH-1:0]` | Complete effective byte address retained by EX/MEM |
| `mem_type` | Input | `riscv_pkg::mem_type_t` | Decoded access size and load signedness |
| `load_result` | Output | `logic [DATA_WIDTH-1:0]` | Selected and extended load value |

Shared constants and `mem_type_t` already exist in
[riscv_pkg](../../rtl/riscv_pkg.sv). Only `DATA_WIDTH = ADDR_WIDTH = 32` is
supported. The wrapper maps `ex_result` into `effective_address` without
changing any bit, placing the datapath-to-address boundary outside this leaf.
Unequal-width conversion is not defined. The leaf selects lanes using
`effective_address[1:0]`; upper address bits do not affect the result. The
input must retain the original byte address, not the aligned bus address.

The output follows current inputs after combinational settling. It is consumed
only for an expected load response under the parent's
[completion rules](5-stage-baseline-core.md#data-transaction-completion).
Other cycles do not require output zeroing or retention of an earlier value.
There is no validity, load/store or response qualifier input.

## 3. Inherited formatting behavior

The parent owns the lane-selection and extension equations. Here, `byte_offset`
denotes `effective_address[1:0]`, and `shifted_data` denotes the logical right
shift of `read_data` by eight times `byte_offset`. These are conceptual values,
not required RTL signals.

| `mem_type` | Code | Required `load_result` |
| --- | --- | --- |
| `MEM_BYTE` | `3'b000` | Sign-extend `shifted_data[7:0]` to `DATA_WIDTH` |
| `MEM_HALF` | `3'b001` | Sign-extend `shifted_data[15:0]` to `DATA_WIDTH` |
| `MEM_WORD` | `3'b010` | Preserve `read_data` |
| `MEM_BYTE_U` | `3'b100` | Zero-extend `shifted_data[7:0]` to `DATA_WIDTH` |
| `MEM_HALF_U` | `3'b101` | Zero-extend `shifted_data[15:0]` to `DATA_WIDTH` |

Sign extension repeats the selected byte's bit 7 or halfword's bit 15. Output
ports remain logic vectors; signed load interpretation does not require a
signed port. The shared encoding is owned by the
[MEM contract](memory-stage.md#3-shared-memory-type-encoding-and-fallback).

## 4. Input domain and fallback

Byte offsets 0–3 are supported for byte loads, offsets 0 and 2 for halfword
loads, and offset 0 for word loads. Misalignment detection, split accesses and
recovery remain outside scope. No supported behavior is promised for a
misaligned access.

Unassigned binary types `011`, `110` and `111` return `32'hDEAD_BEEF`, as
already accepted in the MEM contract. This is a deterministic fallback, not a
unique error signature or CPU trap. MEM integration owns the conditional
checker for invalid memory controls. The guaranteed input domain contains only
0/1; X/Z behavior is outside scope.

## 5. Decision rationale

**LF-D1 — Interface.** Việt selected the full `effective_address` input so
both formatters receive the same address representation and perform their own
address-bit selection. Upper bits are unused by this leaf; this choice changes
the interface, not the inherited load semantics. No local design decision
remains open. Design acceptance does not authorize RTL or test implementation.
