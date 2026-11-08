# Load Formatter

| Field | Value |
| --- | --- |
| Description | Combinational load-lane selection and sign/zero extension. |
| Last modified | 2026-11-08 |
| Status | Accepted by Việt on 2026-11-08 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | `rtl/load_formatter.sv`, module `load_formatter`, instance `mem_load_formatter` in `memory_stage` |
| Parent | [Memory stage](memory-stage.md#4-internal-structure); [BASE load formatting](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary) |

## 1. Overview

- `load_formatter` selects the requested byte or halfword from a returned memory word and extends it to the datapath width.
- For a word load it keeps the whole word.
- The data OBI response path supplies the word, and the MEM/WB register captures the result as `load_result`.
- The held EX/MEM instruction supplies the access type and the effective address.
- The block is purely combinational, with no clock, reset, storage or handshake.
- It decodes no instruction, issues no request, tracks no transaction and does not authorize the MEM/WB capture.
- Those duties belong to the [data OBI controller](data-obi-controller.md) and the [memory stage](memory-stage.md).
- BASE owns the memory semantics, the memory stage owns the `mem_type_t` encoding and the fallback, and this block owns the lane selection and the extension.

## 2. Block Design

```text
read_data                                          +----------------+
  <- data_obi_controller                           |                |
effective_address, mem_type                        | load_formatter | -> load_result (MEM/WB register)
  <- EX/MEM register                               |                |
                                                   +----------------+
```

## 3. Interface

| Signal | Dir | Width | Peer | Description |
| --- | --- | --- | --- | --- |
| `read_data` | Input | `DATA_WIDTH` | `data_obi_controller` | Complete word returned by the data bus. |
| `effective_address` | Input | `ADDR_WIDTH` | EX/MEM register | Original effective byte address of the load, not the aligned bus address. |
| `mem_type` | Input | `mem_type_t` (3) | EX/MEM register | Access size and load signedness. |
| `load_result` | Output | `DATA_WIDTH` | MEM/WB register | Selected and extended load value. |

- The types come from `riscv_pkg`, and every vector is unsigned.
- Only `DATA_WIDTH` and `ADDR_WIDTH` both 32 are supported. The parent keeps every bit of the datapath result across the [width crossing](memory-stage.md#width-crossings), and unequal-width conversion is not defined.
- The [memory-type table](memory-stage.md#mem_type_t-table) of the memory stage owns the encoding of `mem_type`.
- The port set has no validity, load or store, or response qualifier input, because the core qualifies the consumption of the result ([MEM-D9](memory-stage.md#10-decisions-and-open-items)).
- There is no error port and no CPU trap.

## 4. Internal Structure

- The block has no sub-module.
- One internal net, `byte_offset`, holds `effective_address[1:0]`.
- A case on `mem_type` selects the lane of `read_data` by `byte_offset` and applies the extension.

## 5. State

- None, because the block is purely combinational (section 1).

## 6. Behavior

### Load formatting

| `mem_type` | Selected bits of `read_data` | Upper bits of `load_result` |
| --- | --- | --- |
| `MEM_BYTE` | Offset 0: `[7:0]`, offset 1: `[15:8]`, offset 2: `[23:16]`, offset 3: `[31:24]` | Copies of the top selected bit |
| `MEM_HALF` | Offset 0: `[15:0]`, offset 2: `[31:16]` | Copies of the top selected bit |
| `MEM_WORD` | All 32 bits, at offset 0 | None: the word fills the result |
| `MEM_BYTE_U` | The lanes of `MEM_BYTE` | Zero |
| `MEM_HALF_U` | The lanes of `MEM_HALF` | Zero |
| Unassigned code | None: `load_result` is `32'hDEAD_BEEF` at any offset | None: the constant fills the result |

- The offset is `effective_address[1:0]`, and the upper address bits do not affect the result.
- The unassigned-code row is the fallback of [MEM-D7](memory-stage.md#10-decisions-and-open-items), and it is no CPU trap.
- The check for an unassigned type belongs to the memory stage ([MEM-D8](memory-stage.md#10-decisions-and-open-items)).

## 7. Timing and Control

- The output follows the current inputs after combinational settling.
- The block has no latency, no handshake and no registered output.
- Outside the expected load response the output has no meaning, and it needs no zeroing and no retention of an earlier value ([MEM-D9](memory-stage.md#10-decisions-and-open-items)).

### Reset, stall, flush

| Event | Effect on this block |
| --- | --- |
| Reset | None: the block has no reset input and no state, and its output need not be reset. |
| Stall | None: the block has no stall input. |
| Flush | None: the block has no flush input. |

- Trace: None, because the block has no sequence in time, and its output depends on the current inputs alone.

## 8. Assumptions and Corner Cases

| Assumption | Guaranteed by | If violated |
| --- | --- | --- |
| Every input bit is 0 or 1 | The environment ([RF-D5](register-file.md#10-decisions-and-open-items)) | X and Z behavior is unspecified and untested. |
| A halfword access is at offset 0 or 2, a word access at offset 0, and a byte access at any offset | The core ([BASE](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary)) | A misaligned access has no specified recovery and no promised result. |
| `effective_address` carries the original byte address | The memory stage ([width crossings](memory-stage.md#width-crossings)) | With the aligned bus address instead, the block always selects the lane of offset 0. |
| The core consumes `load_result` only at the expected load completion | The core ([MEM-D9](memory-stage.md#10-decisions-and-open-items)) | Arbitrary load data is taken as a load result. |

| Case | Inputs | Result |
| --- | --- | --- |
| A word load of `0xDEADBEEF` | `MEM_WORD`, `read_data` `0xDEADBEEF` | `load_result` equals the fallback value, so the fallback is not a unique error signature. |

## 9. Verification

- A directed leaf test exists: runner `tb/runners/test_load_formatter.py` and cocotb module `tb/testcases/load_formatter_cocotb.py`.
- The module has 6 tests, and each planned check below has one test.
- Expected values are literals in the tests and never come from the DUT.
- Integration verification of the response path is owned by the [memory stage](memory-stage.md#9-verification).

### Planned checks

| Requirement | Stimulus | Expected observation | Test |
| --- | --- | --- | --- |
| Signed byte | 11 `MEM_BYTE` vectors: offsets 0 to 3 of `0xDEADBEEF`, the next word, the byte values `0x00`, `0x7F`, `0x80` and `0xFF` in different lanes, and addresses `0` and `0xFFFFFFFF` | The selected byte, sign-extended | `test_byte_formatting` |
| Signed halfword | 9 `MEM_HALF` vectors: both halfwords of `0xDEADBEEF`, the values `0x0000`, `0x7FFF`, `0x8000` and `0xFFFF` in both lanes, and addresses `0`, `0xFFFFFFFC` and `0xFFFFFFFE` | The selected halfword, sign-extended | `test_halfword_formatting` |
| Word | 8 `MEM_WORD` vectors, including data `0`, `0xFFFFFFFF`, `0x7FFFFFFF` and `0x80000000`, and addresses `0` and `0xFFFFFFFC` | `read_data` unchanged | `test_word_formatting` |
| Unsigned byte | The 11 vectors of `test_byte_formatting` with `MEM_BYTE_U` | The selected byte, zero-extended | `test_unsigned_byte_formatting` |
| Unsigned halfword | The 9 vectors of `test_halfword_formatting` with `MEM_HALF_U` | The selected halfword, zero-extended | `test_unsigned_halfword_formatting` |
| Unassigned codes | 12 vectors: codes `3'b011`, `3'b110` and `3'b111`, each at four offsets with different data | `32'hDEAD_BEEF` | `test_reserved_mem_type` |

## 10. Decisions and Open Items

| ID | Decision | Reason |
| --- | --- | --- |
| LF-D1 | The block takes the full `effective_address` and selects the lane from its low bits itself. | Both formatters receive the same address representation and perform their own address-bit selection. |

- History: 2026-10-21 the Owner accepted the spec and the full-address interface, under the revision label Load Formatter D1.
- 2026-11-08 rewritten in the block spec format, with the formatting as section 6 and the checks of the six tests as section 9. LF-D1 keeps its ID.
- Open items: none.
