# Immediate Generator — Block Design

**Status:** Accepted by Việt on 2026-10-29. The IMM D2 amendment `INSTR_WIDTH` (O7-R) is `was accepted by Việt on 2026-10-29.`.
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Design revision:** IMM D2 / 2026-10-29 (draft; D2 amends the `instruction` type only).
**Parent contract:** [Decode stage](decode-stage.md) (sections 2, 3, 5; D5, D6, D7, O5, O7-R),
[BASE ID decode contract](5-stage-baseline-core.md#id-decode-contract),
[instruction semantic table](5-stage-baseline-core.md#instruction-semantic-table) and
[ID/EX boundary](5-stage-baseline-core.md#idex-boundary).
**RTL mapping:** Planned module `immediate_generator` in `immediate_generator.sv`,
instance `id_immediate_generator` in `decode_stage`; no RTL exists. This document
is neither implementation nor verification evidence.

## 1. Purpose and boundary

`immediate_generator` turns the IF/ID `instruction` into the one canonical
`imm` that ID drives to EX. Observable success criterion: for each supported
instruction class, `imm` equals the RV32I immediate of that class's format,
reconstructed by the equations in section 5.

Non-goals:

- No clock, reset or state; the block is purely combinational.
- No legality check. Whether a word is a supported instruction is the job of
  `control_unit` (decode-stage.md D7).
- No selector from `control_unit` and no `immediate_kind` output. The format is
  chosen inside this block from the instruction word alone.
- No value is defined for words with no immediate (section 5, I1).

Inherited by reference, not restated: one canonical 32-bit immediate; I/S/B/J
sign-extended, U in `[31:12]` with twelve low zeros, B and J low bit zero; for an
immediate shift EX uses only the low five bits of `imm` (BASE ID decode contract).
`instruction` is `logic [INSTR_WIDTH-1:0]` (decode-stage.md O7-R); `imm` is `DATA_WIDTH`
(decode-stage.md section 2). Local refinements are I1–I4 (section 9).

## 2. Interface contract

### Clock, reset and configuration

Clock and reset do not apply. No parameters: `riscv_pkg::DATA_WIDTH` sets the
`imm` width, with the supported configuration `DATA_WIDTH = 32`.

### Ports and payloads

Port names equal the `decode_stage` names, so `decode_stage` only wires them
(decode-stage.md section 3). There is 1 input and 1 output.

| Port | Direction | Type / width | Meaning | Valid when |
| --- | --- | --- | --- | --- |
| `instruction` | Input | `logic [INSTR_WIDTH-1:0]` | IF/ID instruction word; `INSTR_WIDTH` is 32, the width of the base encoding (`IALIGN=32`, decode-stage.md O7-R) | Any value, any cycle |
| `imm` | Output | `logic [DATA_WIDTH-1:0]` | Canonical immediate per section 5 | Instruction belongs to a supported class that uses an immediate (section 4) |

`imm` is an unsigned bit pattern; I/S/B/J values are already sign-extended to
`DATA_WIDTH`, and no further width conversion exists. The one width-domain
crossing, from the 32-bit instruction fields to `imm`, is the reconstruction in
section 5 and follows BASE. The guaranteed input domain contains only 0 and 1;
X/Z behavior is unspecified and untested, as in the accepted
[EX](execute-stage.md#6-verification-and-delivery-boundaries) and
[WB](writeback-stage.md#6-reset-cancellation-and-exceptional-conditions) contracts
and [register-file.md](register-file.md) (O1).

### Transfer and timing rules

`imm` is a combinational function of `instruction` only. There is no latency,
handshake or dependence on any other signal. The block does not know whether
IF/ID is valid; invalid-entry handling stays at ID/EX (decode-stage.md section 9, O2).

## 3. Internal organization

One format selection on `instruction[6:2]`, followed by one bit-slice
concatenation per format (section 5). No arithmetic exists: sign extension is
replication of `instruction[31]`, and every other bit is a copy of an instruction
bit or a constant zero. Equivalent coding styles are free.

## 4. Format selection

Selection examines the full `instruction[6:2]` of each supported class (I2).
`instruction[1:0]`, `funct3` and `funct7` are not examined. Instruction names and
classes follow the BASE semantic tables.

| Class | `instruction[6:2]` | Format |
| --- | --- | --- |
| `LUI` | `01101` | U |
| `AUIPC` | `00101` | U |
| `JAL` | `11011` | J |
| `JALR` | `11001` | I |
| LOAD | `00000` | I |
| OP-IMM (including `SLLI`, `SRLI`, `SRAI`) | `00100` | I |
| STORE | `01000` | S |
| BRANCH | `11000` | B |
| OP (`01100`), MISC-MEM / `FENCE` (`00011`), every other `instruction[6:2]` | — | No format; `imm` is don't care (I1) |

An unsupported word that shares a supported `instruction[6:2]` gets that
format's value, for example `LD` (LOAD, `funct3=011`) gets the I value. That value
is still don't care (I1): legality is not checked here.

## 5. Behavioral rules

Write `i` for `instruction`. The fields below are RV32I bit positions. Each
equation lists every bit 31..0 of `imm` exactly once, from the most significant
side; `{N{x}}` replicates `x` N times.

| Format | Equation | Bits of `imm` |
| --- | --- | --- |
| I | `{ {21{i[31]}}, i[30:25], i[24:21], i[20] }` | `[31:11]` = sign, `[10:5]` = `i[30:25]`, `[4:1]` = `i[24:21]`, `[0]` = `i[20]` |
| S | `{ {21{i[31]}}, i[30:25], i[11:8], i[7] }` | `[31:11]` = sign, `[10:5]` = `i[30:25]`, `[4:1]` = `i[11:8]`, `[0]` = `i[7]` |
| B | `{ {20{i[31]}}, i[7], i[30:25], i[11:8], 1'b0 }` | `[31:12]` = sign, `[11]` = `i[7]`, `[10:5]` = `i[30:25]`, `[4:1]` = `i[11:8]`, `[0]` = 0 |
| U | `{ i[31:12], 12'b0 }` | `[31:12]` = `i[31:12]`, `[11:0]` = 0 |
| J | `{ {12{i[31]}}, i[19:12], i[20], i[30:21], 1'b0 }` | `[31:20]` = sign, `[19:12]` = `i[19:12]`, `[11]` = `i[20]`, `[10:1]` = `i[30:21]`, `[0]` = 0 |

Widths add to 32: I and S 21+6+4+1; B 20+1+6+4+1; U 20+12; J 12+8+1+10+1.

**Immediate shifts.** `SLLI`, `SRLI` and `SRAI` use the I equation unchanged, so
`imm[11:5]` is kept as in the instruction word (`0x00` for `SLLI`/`SRLI`, `0x20`
for `SRAI`) and `imm[4:0]` is the shift amount. This block does not mask or
isolate the shift amount; EX uses only `imm[4:0]` (BASE).

**Don't care (I1).** For OP, MISC-MEM (`FENCE`) and every `instruction[6:2]` not
listed in section 4, `imm` stays don't care. The document fixes no value and no
oracle may use it. The RTL author chooses the value.

## 6. Reset, cancellation and exceptional conditions

- **Reset, flush, stall.** None apply; the block has no state or control input.
- **Unsupported and no-immediate words.** Out of the contract: no error output,
  default vector or legality flag exists (D6). `control_unit` blocks side effects
  for unsupported encodings (decode-stage.md section 5); this block is not part of
  that guard.
- **Out of scope.** X/Z input values (section 2).

## 7. Representative examples

Every row is a test vector. The word is the 32-bit encoding in hex; `imm` is the
expected output. For each format, the sign-0 and sign-1 immediates are bit-for-bit
complements over the immediate bits, so a swapped or mis-sliced field changes the
result. The I and S rows share `0x0000_0555` / `0xFFFF_FAAA`, the B and J rows use
the same alternating pattern at their own widths.

| Format | Assembly | `instruction` | Expected `imm` |
| --- | --- | --- | --- |
| I | `ADDI x1, x2, 1365` | `0x5551_0093` | `0x0000_0555` |
| I | `ADDI x1, x2, -1366` | `0xAAA1_0093` | `0xFFFF_FAAA` |
| S | `SW x6, 1365(x2)` | `0x5461_2AA3` | `0x0000_0555` |
| S | `SW x6, -1366(x2)` | `0xAA61_2523` | `0xFFFF_FAAA` |
| B | `BEQ x1, x2, +2730` | `0x2A20_85E3` | `0x0000_0AAA` |
| B | `BNE x1, x2, -2732` | `0xD420_9A63` | `0xFFFF_F554` |
| U | `LUI x5, 0x55555` | `0x5555_52B7` | `0x5555_5000` |
| U | `LUI x5, 0xAAAAA` | `0xAAAA_A2B7` | `0xAAAA_A000` |
| J | `JAL x1, +699050` | `0x2ABA_A0EF` | `0x000A_AAAA` |
| J | `JAL x1, -699052` | `0xD545_50EF` | `0xFFF5_5554` |
| Shift | `SLLI x1, x2, 31` | `0x01F1_1093` | `0x0000_001F` |
| Shift | `SRAI x1, x2, 3` | `0x4031_5093` | `0x0000_0403` |

The two shift rows show that `imm[11:5]` is kept as is: `SRAI` gives `imm[11:5]=0x20`
(`0x403` = `0x400` + 3).

## 8. Verification obligations

Planned leaf-level checks; none exists yet. Expected values are the literals in
section 7, taken from the RV32I layouts and BASE, never from the DUT. Stimulus
timing follows `tb/README.md`. A leaf pass proves only these vectors; it does not
show decode integration, control selection or whole-core behavior. Composition-level
immediate checks stay in [decode-stage.md section 8](decode-stage.md#8-verification-obligations).

| Requirement | Scenario | Expected observation |
| --- | --- | --- |
| I format | The two I rows of section 7 | `imm` equals the listed value, sign bit 0 and 1 |
| S format | The two S rows | Field split `[31:25]` / `[11:7]` rejoined correctly |
| B format | The two B rows | `i[7]` at `imm[11]`, low bit 0 |
| U format | The two U rows | `imm[31:12]=i[31:12]`, twelve low zeros |
| J format | The two J rows | `i[20]` at `imm[11]`, low bit 0 |
| Shifts | `SLLI x1, x2, 31` and `SRAI x1, x2, 3` | `imm[11:5]` kept as is; `imm[4:0]` is the shift amount |
| Unsupported and no-immediate words | OP, `FENCE` and any `instruction[6:2]` outside section 4 | No oracle: `imm` is not checked (I1) |

Each format is covered at both sign values. Vectors pair with the assembler words
only for supported instructions; a word sharing a supported `instruction[6:2]` but
not a supported instruction is not an oracle.

## 9. Rationale and open decisions

### Decisions recorded for acceptance

Stated by the Owner on 2026-10-29. This document becomes their record on
acceptance.

| Id | Decision | Reason |
| --- | --- | --- |
| I1 | `imm` for OP, MISC-MEM (`FENCE`) and every opcode outside the supported set stays don't care; no value is fixed, no oracle may use it, the RTL author chooses | D5, D6: no added logic, nothing to guarantee |
| I2 | Format selection matches the full `instruction[6:2]` of each supported class (section 4); `instruction[1:0]`, `funct3` and `funct7` are not examined | Maps 1:1 to the BASE opcode table for review; legality belongs to control_unit (D7) |
| I3 | Section 7 gives two hex vectors per format, with sign bit 0 and 1 and complementary immediate bit patterns, and two shift words | A bit-swizzle error becomes visible; `imm[11:5]` kept as is |
| I4 | The RTL is written by Việt | Owner decision |

D6 (safe, no logic beyond what safety requires) is carried from decode-stage.md.

No material open question remains within this document's boundary.

Independent work that can proceed: the `control_unit` block design. Blocked until
acceptance: `immediate_generator` RTL and leaf tests. A pass of the planned checks
would not establish integration with `decode_stage`, the core or timing.
