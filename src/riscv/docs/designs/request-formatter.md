# Request Formatter

| Field | Value |
| --- | --- |
| Description | Combinational address, byte-enable and store-data formatting. |
| Last modified | 2026-11-08 |
| Status | Accepted by Việt on 2026-11-08 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/request_formatter.sv`, module `request_formatter`, instance `mem_req_formatter` in `memory_stage` |
| Parent | [Memory stage](memory-stage.md#4-internal-structure); [BASE data formatting](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary) |

## 1. Overview

- `request_formatter` turns an effective byte address, an access type and a store value into a word-aligned address, byte enables and store write data.
- The source payload belongs to the held EX/MEM instruction, and the data OBI request path of the [memory stage](memory-stage.md) consumes the outputs.
- The block is purely combinational, with no clock, reset, storage or handshake.
- It decodes no instruction, fetches no data, detects no misalignment and suppresses no access.
- Request issue, write authorization, transaction ownership and MEM wait belong to the [data OBI controller](data-obi-controller.md) and the memory stage.
- BASE owns the memory semantics, the memory stage owns the `mem_type_t` encoding, and this block owns the formatting of the request fields.

## 2. Block Design

```text
effective_address, store_data, mem_type            +-------------------+
  <- EX/MEM register                               |                   | -> aligned_address, byte_enable,
                                                   | request_formatter |    write_data (data_obi_controller)
                                                   |                   |
                                                   +-------------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `effective_address` | Input | `ADDR_WIDTH` | EX/MEM register | Effective byte address of the memory instruction. |
| `store_data` | Input | `DATA_WIDTH` | EX/MEM register | Forwarded store value retained by EX/MEM. |
| `mem_type` | Input | `mem_type_t` (3) | EX/MEM register | Access size and load signedness. |
| `aligned_address` | Output | `ADDR_WIDTH` | `data_obi_controller` | Byte address of the containing word. |
| `write_data` | Output | `DATA_WIDTH` | `data_obi_controller` | Store payload on the byte lanes. |
| `byte_enable` | Output | 4 | `data_obi_controller` | Selected byte lanes. |

- The types come from `riscv_pkg`, and every vector is unsigned.
- Only `DATA_WIDTH` and `ADDR_WIDTH` both 32 are supported. The parent keeps every bit of the datapath result across the [width crossing](memory-stage.md#width-crossings), and unequal-width conversion is not defined.
- The [memory-type table](memory-stage.md#mem_type_t-table) of the memory stage owns the encoding of `mem_type`.
- The port set has no `mem_write` and no instruction-valid input ([RQF-D1](#10-decisions-and-open-items)).
- There is no error port and no CPU trap.

## 4. Internal Structure

- The block has no sub-module and no internal net.
- Each output is one selection on `mem_type` and the low two bits of `effective_address`.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

### Request formatting

| `mem_type` | `byte_enable` | `write_data` |
| --- | --- | --- |
| `MEM_BYTE`, `MEM_BYTE_U` | One lane, chosen by `effective_address[1:0]`: `4'b0001`, `4'b0010`, `4'b0100` or `4'b1000` for offset 0 to 3 | `store_data[7:0]` repeated four times |
| `MEM_HALF`, `MEM_HALF_U` | Two adjacent lanes: `4'b0011` at offset 0 and `4'b1100` at offset 2 | `store_data[15:0]` repeated twice |
| `MEM_WORD` | `4'b1111` | `store_data` unchanged |
| Unassigned code | `4'b0000` | Zero |

- `aligned_address` is `effective_address` with bits 1:0 cleared, and every other bit is kept. It does not depend on `mem_type`.
- Signed and unsigned types select identical lanes and identical data. Signedness affects the load-result extension in the [load formatter](load-formatter.md) only.
- The write data is formatted for loads and stores alike, and it is not forced to zero for a load ([RQF-D1](#10-decisions-and-open-items)). A load request carries no write enable, so its write data causes no memory write.
- The outputs do not authorize a bus operation.
- The unassigned-code row is the fallback of [MEM-D7](memory-stage.md#10-decisions-and-open-items). It neither prevents a request nor guarantees harmless MMIO behavior.
- The checks for an unassigned type, or for a store with an unsigned-load type, belong to the memory stage ([MEM-D8](memory-stage.md#10-decisions-and-open-items)).

## 7. Timing and Control

- The outputs follow the current inputs after combinational settling.
- The block has no latency, no handshake and no registered output.

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input and no state, and its outputs may be nonzero during reset because the payload is not reset. |
| Stall | None: the block has no stall input, and the memory stage holds the source payload stable ([MEM-D4](memory-stage.md#10-decisions-and-open-items)). |
| Flush | None: the block has no flush input. |

- Trace: None, because the block has no sequence in time, and its outputs depend on the current inputs alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| A halfword access is at offset 0 or 2, a word access at offset 0, and a byte access at any offset | The core ([BASE](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary)) | A misaligned access has no specified recovery, and the byte enables follow the offset without a check. |
| The source payload stays stable while the request waits for grant | The memory stage ([MEM-D4](memory-stage.md#10-decisions-and-open-items)) | The request fields change under a waiting request. |
| Request suppression during reset does not rely on zero outputs of this block | The core, through the reset-valid boundary ([MEM-D5](memory-stage.md#10-decisions-and-open-items)) | A nonzero output during reset reaches the request path. |

| Case | Inputs | Result |
| --- | --- | --- |
| A halfword at the top word | `MEM_HALF`, `effective_address` `0xFFFFFFFE` | `aligned_address` is `0xFFFFFFFC` and `byte_enable` is `4'b1100`. |
| A reserved code at any offset | An unassigned `mem_type`, any `effective_address` | `byte_enable` and `write_data` are zero, and `aligned_address` is still aligned. |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_request_formatter.py` and cocotb module `tb/testcases/request_formatter_cocotb.py`.
- The module has 6 tests, and each planned check below has one test.
- Expected values are literals in the tests and never come from the DUT.
- Integration verification of the request path is owned by the [memory stage](memory-stage.md#9-verification).

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Byte formatting | `MEM_BYTE` at all four offsets, with data `0`, `0xFFFFFFFF` and `0xDEADBEEF`, addresses `0`, `0xFFFFFFFC` and `0xFFFFFFFF`, and upper data bits varied | One lane at the offset, the low byte repeated four times, and the aligned address | `test_byte_formatting` |
| Halfword formatting | `MEM_HALF` at offsets 0 and 2, with the same data, address and upper-bit variations | `4'b0011` or `4'b1100`, the low halfword repeated twice, and the aligned address | `test_halfword_formatting` |
| Word formatting | `MEM_WORD` with eight vectors, including data `0`, `0x7FFFFFFF` and `0x80000000` | `4'b1111`, `store_data` unchanged, and the aligned address | `test_word_formatting` |
| Unsigned byte | The vectors of `test_byte_formatting` with `MEM_BYTE_U` | The same outputs as `MEM_BYTE` | `test_unsigned_byte_formatting` |
| Unsigned halfword | The vectors of `test_halfword_formatting` with `MEM_HALF_U` | The same outputs as `MEM_HALF` | `test_unsigned_halfword_formatting` |
| Unassigned codes | Codes `3'b011`, `3'b110` and `3'b111`, each at four addresses of different offsets | `byte_enable` and `write_data` zero, and the aligned address | `test_reserved_mem_type` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| RQF-D1 | The formatter takes the access size only, with no `mem_write` and no validity input, and it formats the write data for loads as for stores. | Formatting stays separate from request and write authorization, and the block needs no extra input and no load-specific zero selection. It keeps the load-cycle write-data policy of the old LSU without its combined module boundary. No switching-power or PPA benefit is claimed. |

- History: 2026-10-21 the Owner accepted the spec and the size-only formatting, under the revision label Request Formatter D1.
- 2026-11-08 rewritten in the block spec format, with the formatting as section 6 and the checks of the six tests as section 9. The decision gets the ID RQF-D1, because the old file stated it in a rationale section without an ID.
- Length: 4 pages, above the 2-3 limit, because section 9 has six planned checks with their stimulus.
- Open items: none.
