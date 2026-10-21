# Request Formatter — Block Design

**Status:** Accepted by Việt on 2026-10-21.
**Revision:** Request Formatter D1 / 2026-10-21.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [MEM composition](memory-stage.md),
[BASE data formatting](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary).
**RTL mapping:** [request_formatter](../../rtl/request_formatter.sv);
functional simulation remains pending.

## 1. Purpose and boundary

Format an effective byte address, access type and store value into a
word-aligned address, byte enables and store write data. The source payload
belongs to the held EX/MEM instruction; the consumer is the data OBI request
path in `memory_stage`.

This leaf is combinational: no clock, reset, storage or handshake. Request
issue, write authorization, transaction ownership and MEM wait belong to
`data_obi_controller` and the parent composition. The formatter does not
decode instructions, fetch data, detect misalignment or suppress an access.

## 2. Interface, timing and state

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `effective_address` | Input | Unsigned `logic [ADDR_WIDTH-1:0]` | Effective byte address |
| `store_data` | Input | Unsigned `logic [DATA_WIDTH-1:0]` | Forwarded store value retained by EX/MEM |
| `mem_type` | Input | `riscv_pkg::mem_type_t`, `enum logic [2:0]` | Access size and load signedness |
| `aligned_address` | Output | `logic [ADDR_WIDTH-1:0]` | Containing word's byte address |
| `byte_enable` | Output | `logic [3:0]` | Selected byte lanes |
| `write_data` | Output | `logic [DATA_WIDTH-1:0]` | Replicated store payload |

`DATA_WIDTH` and `ADDR_WIDTH` already exist in
[riscv_pkg](../../rtl/riscv_pkg.sv). The accepted
[memory-type encoding](memory-stage.md#3-shared-memory-type-encoding-and-fallback)
is listed below for this interface; the MEM contract owns the shared encoding.
The package defines `mem_type_t` with all five accepted enum members.

### Shared control type: `mem_type_t`

`mem_type_t` is an `enum logic [2:0]` defined in `riscv_pkg`, shared by ID and
the MEM leaves. Its accepted members are:

| Member | Encoding | Instruction use | Formatter size |
| --- | --- | --- | --- |
| `MEM_BYTE` | `3'b000` | LB, SB | Byte |
| `MEM_HALF` | `3'b001` | LH, SH | Halfword |
| `MEM_WORD` | `3'b010` | LW, SW | Word |
| `MEM_BYTE_U` | `3'b100` | LBU | Byte, identical request formatting to `MEM_BYTE` |
| `MEM_HALF_U` | `3'b101` | LHU | Halfword, identical request formatting to `MEM_HALF` |

Codes `3'b011`, `3'b110` and `3'b111` are unassigned. ID supplies the decoded
semantic selector; the formatter does not extract instruction `funct3`.
Signedness affects load-result extension in `load_formatter`, not request
formatting here.

### Width boundary

Only `DATA_WIDTH = ADDR_WIDTH = 32` is supported. The wrapper maps
`ex_result` into `effective_address` without changing any bit, placing the
datapath-to-address boundary outside this leaf. Unequal-width conversion is
not defined. There is no `mem_write` or instruction-valid input.

## 3. Inherited formatting behavior

The parent owns the lane-selection and replication equations. For the current
32-bit configuration, the local outputs correspond to its `data_addr`, `be`
and `wdata`:

- Address: clear the effective address's low two bits; preserve all others.
- Byte enables: select one byte, two adjacent bytes or the complete word
  according to `mem_type` and the effective address's low two bits. Signed
  and unsigned load types select identical lanes.
- Write data: `MEM_BYTE` and `MEM_BYTE_U` repeat `store_data[7:0]` four
  times; `MEM_HALF` and `MEM_HALF_U` repeat `store_data[15:0]` twice;
  `MEM_WORD` preserves the complete value. This formatting applies to loads
  and stores alike; write data is not forced to zero for loads.

Outputs follow current inputs after combinational settling. They do not
authorize a bus operation; the parent determines when request fields are
presented and holds the source payload stable while awaiting grant. Load
requests use `we=0`; their write-data value does not cause a memory write.

## 4. Input domain and fallback

Legal accesses obey the parent's alignment restrictions: bytes at any offset,
halfwords at offset zero or two, and words at offset zero. Misaligned accesses
remain outside scope, without a specified recovery mechanism.

For unassigned binary `mem_type` codes `011`, `110` and `111`, byte enables
and write data are zero; address alignment remains unchanged. This fallback
does not guarantee harmless MMIO behavior or prevent a request. Integration
checks for illegal types and unsigned-load types used by stores remain owned
by the [MEM contract](memory-stage.md#3-shared-memory-type-encoding-and-fallback).
The guaranteed input domain contains only 0/1; X/Z behavior is outside scope.

## 5. Decision rationale

Việt selected size-only formatting without `mem_write` or validity inputs.
This keeps formatting separate from request/write authorization and avoids
an extra input and load-specific zero selection. It preserves the old LSU's
load-cycle write-data policy without inheriting its combined module boundary.
No switching-power or PPA benefit is claimed. No local design decision remains
open within this boundary.
