# Five-Stage Baseline Core

**Status:** Accepted
**Owner:** RISC-V subsystem owner

## Purpose and boundary

This design defines a five-stage processor core baseline without a cache or branch predictor. The baseline must execute programs with a standalone memory/test harness and be verified at the core boundary. SoC integration, AXI integration, and execution on FPGA are outside this baseline's completion boundary.

The baseline states its supported instruction set and architectural limitations explicitly. It does not claim full RV32I compliance because trap, exception, and misalignment handling remain outside its implemented scope.

The reset PC is the fixed constant `PC_RESET_VEC = 32'h0000_0000` defined in the RISC-V package, not a core instance parameter. Address `0x0000_0000` is the first word of the core-level harness's code region.

## Reset architecture

The core input is named `rst_n`. It is an active-low synchronous reset: core state observes reset only on the rising edge of `clk`. Generation, synchronization, and distribution of the system reset that drives `rst_n` belong to the later system-level clock/reset contract. The core-level OBI manager and its test-harness subordinates share this reset.

Reset is deliberately limited to the control plane. When a rising edge samples
`rst_n=0`, the Fetch Controller's registered state takes
`next_fetch_pc <= PC_RESET_VEC`; pipeline-valid state, OBI request/transaction
ownership state, and any independent state capable of authorizing a redirect
or architectural side effect return to inactive or idle values. Invalid
pipeline stages must not write the register file, issue a memory request,
perform a store, or redirect the PC, regardless of their payload values.

The reset network does not reset datapath payload merely to give it a known waveform value. Instruction, operand, immediate, ALU-result, memory-address, store-data, and destination-register payload registers retain unspecified values while invalid. General-purpose registers `x1` through `x31` are not reset; software must initialize a register before relying on its value. `x0` always reads as zero and ignores writes. Combinational datapath logic and the memory contents are not reset by the core. Any exception to this selective-reset rule requires a correctness need that cannot be enforced by reset control state and validity gating.

## Supported instruction scope

The baseline supports the following 37 RV32I integer instructions when legally encoded:

- Upper immediates: `LUI`, `AUIPC`.
- Jumps: `JAL`, `JALR`.
- Branches: `BEQ`, `BNE`, `BLT`, `BGE`, `BLTU`, `BGEU`.
- Loads: `LB`, `LH`, `LW`, `LBU`, `LHU`.
- Stores: `SB`, `SH`, `SW`.
- Immediate arithmetic and logic: `ADDI`, `SLTI`, `SLTIU`, `XORI`, `ORI`, `ANDI`, `SLLI`, `SRLI`, `SRAI`.
- Register arithmetic and logic: `ADD`, `SUB`, `SLL`, `SLT`, `SLTU`, `XOR`, `SRL`, `SRA`, `OR`, `AND`.

`FENCE`, `ECALL`, `EBREAK`, privileged instructions, ISA extensions, unsupported or illegal encodings, and misaligned instruction or data accesses are outside this baseline's contract and scope. Their behavior is not specified, and this baseline defines no handling mechanism for them.

## Pipeline organization

The baseline uses five in-order stages: IF, ID, EX, MEM, and WB. Without branch prediction, fetch proceeds sequentially at `PC + 4`. Branches and jumps resolve in EX. The datapath forwards results from EX/MEM and MEM/WB when possible, inserts a bubble for a load-use dependency, and discards younger instructions after a taken control-flow redirect. The detailed priority, hazard, and side-effect rules below define these interactions.

Every architectural pipeline-stage entry follows one pipeline-valid invariant. `valid=1` means the stage contains a live instruction; this remains true even when that instruction has no side effect in the stage, such as a branch or store passing through WB with `reg_write=0`. `valid=0` means the entry is empty, a bubble, or has been flushed, and its datapath and control payload are unspecified and must not affect architectural state. Normal advance transfers the live instruction and its valid state, a hold preserves both valid and payload, and reset, flush, or bubble insertion clears the affected valid state without requiring payload reset. `valid` is necessary but not sufficient to authorize a side effect: the corresponding semantic control and stage ownership must also permit it.

Instruction availability and a data-port wait have different stall scopes. The
absence of a live `READY` instruction prevents new IF/ID delivery;
instruction-side OBI latency does not globally stall older pipeline stages,
which continue to drain. While a load or store occupies MEM with an unresolved
data-port transaction, the global pipeline interlock holds IF/ID, ID/EX,
EX/MEM, and MEM/WB. No pipeline instruction advances or retires until the
expected data response releases the interlock. These memory-wait rules are
separate from the accepted one-cycle load-use bubble and from redirect
flushing.

### IF/ID boundary

The required IF/ID semantic state is `{valid, pc, instruction}`. `valid` states whether the payload represents a live instruction; `pc` is the address of that instruction and remains available for downstream PC-relative computation; `instruction` is the word decoded by ID. Fetch allocation age, killed state, Fetch Buffer lifecycle, protocol-committed state, and OBI ownership remain frontend metadata and do not cross into the pipeline.

When IF/ID accepts the oldest live `READY` entry, it captures that entry's `pc` and `instruction` and asserts `valid`. A hold preserves both valid and payload. Redirect or reset clears valid; payload is then unspecified and is not reset. Load-use holds the current IF/ID entry and inserts its bubble at ID/EX rather than encoding a special IF/ID payload.

Derived or redundant fields such as `pc_plus_4` or predecode bits are not required semantic state. An implementation may carry them as a contract-preserving optimization, but downstream correctness must remain derivable from `{valid, pc, instruction}` and ID remains the owner of instruction decode.

### ID decode contract

ID and its Control Unit are the sole owners of architectural instruction decode. Raw `instruction` terminates at ID and is not propagated into ID/EX, EX/MEM, or MEM/WB. Downstream stages act only on semantic datapath and control produced by ID; they must not independently decode opcode, `funct3`, `funct7`, or other raw instruction fields. Raw instruction is not carried downstream as either functional state or an alternate control source.

ID interprets the encoding fields needed to identify the instruction, register sources and destination, and immediate. It produces one canonical 32-bit immediate; encoding formats are private decode concerns and no `immediate_kind` crosses ID/EX. I-, S-, B-, U-, and J-format immediates are reconstructed according to RV32I, with I/S/B/J values sign-extended and U values placed in bits `[31:12]` with twelve low zeros. B and J immediates have a zero low bit. For an immediate shift, decoded execution control distinguishes the shift operation and EX uses the canonical immediate's low five-bit shift amount; EX does not inspect raw instruction or function bits.

ID produces explicit source identifiers and semantic-use qualifiers. Their required values are:

| Instruction class | `rs1_used` | `rs2_used` |
| --- | ---: | ---: |
| `LUI` | 0 | 0 |
| `AUIPC` | 0 | 0 |
| `JAL` | 0 | 0 |
| `JALR` | 1 | 0 |
| Branch | 1 | 1 |
| Load | 1 | 0 |
| Store | 1 | 1 |
| OP-IMM | 1 | 0 |
| OP | 1 | 1 |

Hazard detection in ID uses these semantic qualifiers with `rs1_id` and `rs2_id`; encoded fields that are not semantically consumed cannot create a dependency. `rs1_used` and `rs2_used` are required ID/hazard metadata but are not mandatory pipeline state beyond ID. An implementation may carry them farther, but baseline correctness does not require it. EX forwarding may compare the carried source identifiers against producer destinations without the qualifiers because an unused source value is not selected or consumed by the already-decoded EX datapath.

The semantic decode result also supplies compact control sufficient to preserve destination and register-write intent, select operands, perform the integer execution operation, resolve branch or jump behavior, carry memory intent, and ultimately select the architecturally required result. This contract requires those semantic distinctions to remain available where consumed; it does not require one pipeline field for every prose concept. Exact RTL encodings and grouping are implementation choices, but all behavior originates from this one ID decode rather than separate downstream interpretations.

Memory intent is represented by `mem_en`, `mem_write`, and `mem_type`, with the following contract:

| Instruction | `mem_en` | `mem_write` | `mem_type` |
| --- | ---: | ---: | --- |
| `LB` | 1 | 0 | `BYTE` |
| `LBU` | 1 | 0 | `BYTE_U` |
| `LH` | 1 | 0 | `HALF` |
| `LHU` | 1 | 0 | `HALF_U` |
| `LW` | 1 | 0 | `WORD` |
| `SB` | 1 | 1 | `BYTE` |
| `SH` | 1 | 1 | `HALF` |
| `SW` | 1 | 1 | `WORD` |
| Non-memory | 0 | unspecified | unspecified |

`mem_type` is semantic memory information, not a propagated `funct3`. Unsigned variants have meaning only for loads; store types describe width. ID does not generate OBI byte enables or lane-shifted store data. EX computes the effective address from the forwarded base plus canonical immediate and preserves forwarded architectural store data. MEM owns aligned OBI address formation, byte enables, store-lane placement, load-lane selection, and load sign or zero extension.

The memory semantics required to interpret a response remain associated with the accepted transaction for its full lifetime. The held MEM instruction or equivalent transaction state preserves at least the effective-address offset, `mem_write`, and `mem_type`; response formatting cannot use newly decoded instruction information.

### Instruction semantic table

The instruction tables define semantic decode outcomes rather than physical control fields or enum encodings. An implementation may use any compact representation that produces these results without downstream raw-instruction re-decode.

Upper-immediate and control-flow instructions decode as follows:

| Instruction | Sources used | Immediate | EX architectural result | `reg_write` | Redirect semantics |
| --- | --- | --- | --- | ---: | --- |
| `LUI` | None | U | `imm` | 1 | None |
| `AUIPC` | None | U | `pc + imm` | 1 | None |
| `JAL` | None | J | `pc + 4` | 1 | Always to `pc + imm` |
| `JALR` | `rs1` | I | `pc + 4` | 1 | Always to `(fwd_rs1 + imm) & 32'hffff_fffe` |
| `BEQ` | `rs1`, `rs2` | B | Unused | 0 | `pc + imm` when `fwd_rs1 == fwd_rs2` |
| `BNE` | `rs1`, `rs2` | B | Unused | 0 | `pc + imm` when `fwd_rs1 != fwd_rs2` |
| `BLT` | `rs1`, `rs2` | B | Unused | 0 | `pc + imm` when signed `fwd_rs1 < fwd_rs2` |
| `BGE` | `rs1`, `rs2` | B | Unused | 0 | `pc + imm` when signed `fwd_rs1 >= fwd_rs2` |
| `BLTU` | `rs1`, `rs2` | B | Unused | 0 | `pc + imm` when unsigned `fwd_rs1 < fwd_rs2` |
| `BGEU` | `rs1`, `rs2` | B | Unused | 0 | `pc + imm` when unsigned `fwd_rs1 >= fwd_rs2` |

`LUI` selects `{ZERO, imm}` and `AUIPC` selects `{pc, imm}` as their execution operands. Branch conditions compare `fwd_rs1` and `fwd_rs2` directly. `JAL` and `JALR` produce independent values for `ex_result=pc+4` and the redirect target. “Always” in the table describes jump semantics, not an ungated control pulse: `redirect_fire` still requires a valid jump in EX that is allowed to advance, so an unresolved MEM wait suppresses it. `reg_write=1` remains the semantic decode for a destination-writing instruction even when `rd=x0`; physical register-file write remains gated by `rd != 0`.

Memory instructions decode as follows:

| Instruction | Sources used | Immediate | EX output | Memory intent | `reg_write` | `wb_from_mem` |
| --- | --- | --- | --- | --- | ---: | ---: |
| `LB` | `rs1` | I | Effective byte address | Read `BYTE` | 1 | 1 |
| `LH` | `rs1` | I | Effective byte address | Read `HALF` | 1 | 1 |
| `LW` | `rs1` | I | Effective byte address | Read `WORD` | 1 | 1 |
| `LBU` | `rs1` | I | Effective byte address | Read `BYTE_U` | 1 | 1 |
| `LHU` | `rs1` | I | Effective byte address | Read `HALF_U` | 1 | 1 |
| `SB` | `rs1`, `rs2` | S | Effective byte address and separate store data | Write `BYTE` | 0 | 0 |
| `SH` | `rs1`, `rs2` | S | Effective byte address and separate store data | Write `HALF` | 0 | 0 |
| `SW` | `rs1`, `rs2` | S | Effective byte address and separate store data | Write `WORD` | 0 | 0 |

Every memory instruction selects `{fwd_rs1, imm}` and produces `ex_result=fwd_rs1+imm`. This `ex_result` remains the complete effective byte address; MEM alone forms the word-aligned `data_addr` and byte enable. A store additionally produces `store_data=fwd_rs2` as a distinct EX/MEM field rather than combining it with `ex_result`. Loads decode `mem_en=1`, `mem_write=0`; stores decode `mem_en=1`, `mem_write=1`. `mem_type` preserves load signedness and width through response formatting. Misaligned accesses remain outside the aligned-only baseline contract.

Loads produce their selected and extended result only in MEM and semantically retain `reg_write=1` even when `rd=x0`; the physical write is still suppressed. Stores pass through MEM/WB with `valid=1`, `reg_write=0`, and a response-completed transaction, but never select a register-file result. No memory instruction redirects control flow.

Integer immediate operations decode with `operand1=fwd_rs1` and `operand2=imm`:

| Instruction | EX result |
| --- | --- |
| `ADDI` | `fwd_rs1 + imm` modulo 32 bits |
| `SLTI` | 32-bit one when `signed(fwd_rs1) < signed(imm)`, otherwise zero |
| `SLTIU` | 32-bit one when `unsigned(fwd_rs1) < unsigned(imm)`, otherwise zero |
| `XORI` | `fwd_rs1 ^ imm` |
| `ORI` | `fwd_rs1 \| imm` |
| `ANDI` | `fwd_rs1 & imm` |
| `SLLI` | `fwd_rs1 << imm[4:0]` |
| `SRLI` | Logical `fwd_rs1 >> imm[4:0]` |
| `SRAI` | Arithmetic `signed(fwd_rs1) >>> imm[4:0]` |

`SLTIU` first uses the canonical sign-extended I-immediate, then interprets both 32-bit comparison operands as unsigned. ID distinguishes legal immediate-shift operations; EX consumes only the selected operation and `imm[4:0]` and does not re-decode instruction fields.

Integer register operations decode with `operand1=fwd_rs1` and `operand2=fwd_rs2`:

| Instruction | EX result |
| --- | --- |
| `ADD` | `fwd_rs1 + fwd_rs2` modulo 32 bits |
| `SUB` | `fwd_rs1 - fwd_rs2` modulo 32 bits |
| `SLL` | `fwd_rs1 << fwd_rs2[4:0]` |
| `SLT` | 32-bit one when `signed(fwd_rs1) < signed(fwd_rs2)`, otherwise zero |
| `SLTU` | 32-bit one when `unsigned(fwd_rs1) < unsigned(fwd_rs2)`, otherwise zero |
| `XOR` | `fwd_rs1 ^ fwd_rs2` |
| `SRL` | Logical `fwd_rs1 >> fwd_rs2[4:0]` |
| `SRA` | Arithmetic `signed(fwd_rs1) >>> fwd_rs2[4:0]` |
| `OR` | `fwd_rs1 \| fwd_rs2` |
| `AND` | `fwd_rs1 & fwd_rs2` |

All nineteen integer ALU instructions decode `reg_write=1`, `wb_from_mem=0`, `mem_en=0`, and no redirect. `SRA` and `SRAI` are signed arithmetic right shifts. Addition and subtraction use 32-bit modulo arithmetic and do not trap on overflow. ID owns encoding legality and semantic operation selection; EX executes the selected `alu_op` without raw-instruction re-decode. The physical `alu_op` encoding remains an implementation choice.

### ID/EX boundary

ID/EX carries only the semantic state required for the conventional five-stage EX datapath and for later-stage intent to survive without raw-instruction re-decode. Its required conceptual state is:

```text
Liveness and identity: valid, pc
Register sources:      rs1_id, rs2_id, rs1_value, rs2_value
Immediate:             imm
Destination:           rd, reg_write
Execution control:     alu_op, operand1_sel, operand2_sel
Control flow:          compact branch/jump control sufficient for EX resolution
Memory control:        mem_en, mem_write, mem_type
```

Exact signal names, enum encodings, and physical grouping are not part of the contract. Separate fields such as `branch_kind`, `jump_kind`, `redirect_capable`, `is_load`, `is_store`, or `wb_source` are not mandatory merely because those semantics can be described independently; a compact Control Unit encoding is valid if it preserves every required behavior through the stage where that behavior is consumed.

`rs1_value` and `rs2_value` are the register-file values observed in ID after the required same-cycle WB-to-ID visibility. EX forwarding may replace either base value with a newer eligible producer using the carried source identifier. `rs1_used` and `rs2_used` remain available to ID hazard logic but need not cross ID/EX. `rs2_value` becomes final store data only after EX forwarding. The immediate is the canonical 32-bit value from ID. Raw instruction, opcode, function fields, and immediate-format information do not cross the boundary.

On normal advance, ID/EX captures the decoded semantic state and takes IF/ID valid. A hold preserves valid and payload. Load-use bubble, redirect flush, or reset clears valid; payload and control are then unspecified and are not reset. Derived fields may be carried as contract-preserving optimizations, but the baseline does not enlarge EX solely to anticipate a future seven-stage split.

### EX computation contract

EX owns forwarding resolution, operand selection, integer execution or effective-address calculation, and branch or jump resolution. It executes semantic control received from ID and never interprets raw instruction encoding. Register-file source values first pass through the accepted newest-nearest forwarding selection to produce `fwd_rs1` and `fwd_rs2`; decoded operand selection then forms the ALU operands.

Ordinary register operations select `{fwd_rs1, fwd_rs2}`; immediate operations select `{fwd_rs1, imm}`; `LUI` selects `{zero, imm}`; `AUIPC` selects `{pc, imm}`; and loads or stores select `{fwd_rs1, imm}`. `ADD` and `SUB` use 32-bit modulo arithmetic without overflow traps. Logical operations are bitwise. `SLL`, `SRL`, and signed arithmetic `SRA` use `operand2[4:0]` as the shift amount. `SLT` compares signed operands and `SLTU` compares unsigned operands.

The resulting architectural values include `LUI = imm`, `AUIPC = pc + imm`, and load/store effective address `fwd_rs1 + imm`. Final architectural store data is `fwd_rs2`, independently of the address-calculation operand mux.

Branch conditions use the forwarded architectural sources directly: `BEQ` and `BNE` test equality or inequality; `BLT` and `BGE` perform signed comparison; `BLTU` and `BGEU` perform unsigned comparison. A taken branch targets `pc + imm`. `JAL` always redirects to `pc + imm`; `JALR` always redirects to `(fwd_rs1 + imm) & 32'hffff_fffe`. A non-taken branch emits no redirect. Both jumps produce the link value `pc + 4`, generated in EX.

Execution result and redirect target are distinct values. In particular, `JAL` and `JALR` produce architectural result `pc + 4` while redirecting to their separately computed target. EX conceptually produces an execution or architectural result, effective address and final store data when applicable, and `redirect_fire` with `redirect_target`. This semantic contract does not require physically separate ALU, comparator, target-adder, or link-adder hardware; logic may be shared while preserving the five-stage EX boundary and the defined results.

### EX/MEM boundary and data-request ownership

A load or store must first become registered EX/MEM state before the data port may present its request. There is no combinational path from current EX forwarding, operand selection, or ALU output to data OBI. EX computes the result, effective address, and final store data; the clocked EX/MEM boundary then makes that instruction the MEM owner, and MEM derives the OBI request only from this held registered state.

The minimum EX/MEM semantic state is:

```text
valid
ex_result
store_data
rd, reg_write
mem_en, mem_write, mem_type
```

`ex_result` is the architectural ALU, `LUI`, or `AUIPC` result for the corresponding instruction, the `pc + 4` link value for `JAL` or `JALR`, and the effective byte address for a load or store. `store_data` is the final forwarded `rs2` value. `pc`, `imm`, source identifiers and values, operand selectors, `alu_op`, branch or jump control, and redirect target have completed their required role in EX and need not cross EX/MEM.

MEM may combinationally derive `addr`, `be`, `wdata`, `we`, and `req` from the held EX/MEM state and separate data-port protocol state. Conceptually, a request is presented only for a valid memory instruction whose address phase has not yet been accepted. It is not simply `valid && mem_en`: after `data_request_fire`, the accepted instruction must not issue a duplicate request. Request-accepted and outstanding ownership are control-plane state separate from the semantic `mem_en`, `mem_write`, and `mem_type` fields.

While a request waits for `gnt`, EX/MEM state and every contract-defined OBI request field remain stable. After `data_request_fire`, `req` for that transaction is no longer issued, but the same instruction continues to own MEM until `data_response_fire`. EX/MEM may advance only on that expected completion; non-memory instructions are not subject to this transaction wait.

The baseline keeps conventional late writeback-result selection. Non-load register-writing instructions carry `ex_result` toward WB. MEM forms a formatted `load_result` for a completed load, and MEM/WB carries compact selection state equivalent to `wb_from_mem`, which is one only for a load. WB selects:

```text
wb_data = wb_from_mem ? load_result : ex_result
```

Thus the load response path in MEM ends with lane selection and sign or zero extension before the MEM/WB register; it does not add a load-versus-non-load result mux in MEM. The accepted trade-off is that the WB result mux remains on the MEM/WB-to-EX forwarding path. Moving result normalization earlier is a later localized optimization only if timing evidence justifies it.

### Redirect event and pipeline recovery

A taken branch, `JAL`, or `JALR` produces `redirect_fire` only when the valid control-flow instruction in EX is allowed to advance from EX. A target computed while an older load or store holds MEM does not redirect the frontend early: the control-flow instruction remains held in EX with the rest of the younger pipeline. On the edge that `data_response_fire` completes the older memory transaction, the older instruction may advance from MEM to WB, the control-flow instruction may advance from EX to MEM, and `redirect_fire` occurs exactly once. The baseline deliberately does not add early-redirect or `redirect_sent` state to hide this specific memory-stall latency.

On a redirect edge, the control-flow instruction advances normally and every older instruction is preserved. IF/ID is invalidated, and ID/EX becomes invalid after the redirecting instruction leaves it for EX/MEM; no younger instruction advances into EX. Any wrong-path instruction transfer that would otherwise enter IF/ID on that edge is suppressed. Thus no instruction younger than the redirecting instruction can retain valid pipeline state or create an architectural side effect after the redirect edge.

### Forwarding and load-use hazards

Every architectural source operand consumed by an instruction observes the youngest older producer whose result is available. The forwarding priority is `EX/MEM ready result > MEM/WB writeback result > register-file value`. A producer is ineligible when its pipeline state is invalid, it does not write a register, or its destination is `x0`. A load is not an EX/MEM forwarding source because its data does not exist until its memory response completes; it becomes eligible from MEM/WB after that response.

Forwarded source values cover ALU `rs1`, ALU `rs2` when the instruction does not select an immediate, both branch-comparison operands, the `JALR` base, the load/store effective-address base, and store write data. If ID reads a register that WB retires on the same cycle, ID observes the selected `wb_data` through the explicit WB-to-ID bypass defined below.

During an unresolved MEM wait, MEM/WB remains valid with stable payload and therefore remains an eligible forwarding source for the instruction held in EX. On the release cycle, that same MEM/WB value is forwarded combinationally before its instruction retires at the edge, while the held EX instruction advances with the correct operands. ID/EX source-value payload is not selectively refreshed during the hold.

### Register-file timing and WB-to-ID bypass

The register file has 32 architectural 32-bit registers, two combinational read ports used by ID, and one rising-edge write port. `x0` always reads as zero and ignores writes. A register-file write occurs only on:

```text
rf_write_fire = wb_retire_fire
                && MEM/WB.reg_write
                && MEM/WB.rd != 0
```

Each ID read port applies this priority independently:

```text
if rs_id == 0:
    rs_value = 0
else if rf_write_fire && rs_id == MEM/WB.rd:
    rs_value = wb_data
else:
    rs_value = rf[rs_id]
```

This is an explicit combinational WB-to-ID bypass. Correctness does not depend on read-during-write or write-first behavior of the register-file implementation, and the baseline does not use a falling-edge write. When an unresolved MEM wait holds the pipeline, `wb_retire_fire=0`, so the register file does not write and ID/EX does not advance. On the release cycle, the same selected `wb_data` may feed EX forwarding and either ID read bypass while the WB instruction retires exactly once at the rising edge.

A load-use hazard exists when EX contains a valid load with a nonzero destination and the valid younger instruction in ID actually consumes that destination as a source. The load advances to MEM, the dependent instruction and IF/ID are held, Fetch Buffer delivery is not consumed, and invalid state is inserted into ID/EX for one cycle. Source-use qualification prevents dependencies on encoded register fields that the consumer does not semantically read.

The load-use bubble and variable memory wait are separate mechanisms. After the initial bubble, a load that lacks an expected response holds MEM and the dependent instruction remains held by the MEM-wait rule. On the `data_response_fire` edge, the load advances into MEM/WB, the dependent instruction may advance into EX, and its operand is supplied by MEM/WB forwarding.

### Pipeline-control priority

Next-state arbitration follows this priority:

1. Synchronous reset.
2. Unresolved MEM wait.
3. `redirect_fire`.
4. Load-use hazard.
5. Normal advance and IF availability.

Reset invalidates pipeline, Fetch Buffer ownership/control, and OBI ownership state and suppresses every architectural side effect. An unresolved MEM wait exists when a valid load or store owns MEM and its data transaction has not completed with `data_response_fire`. It holds IF/ID, ID/EX, EX/MEM, and MEM/WB; suppresses new fetch consumption and every pipeline retirement; and prevents any pipeline instruction from advancing. If `data_response_fire` occurs in the current cycle, the MEM wait is resolved for that edge's next-state arbitration. The held WB instruction may then retire, the completed memory instruction may replace it in MEM/WB, and a redirect or load-use event behind MEM may be processed without an extra release bubble.

This baseline deliberately propagates the unresolved MEM wait through WB. Allowing an older WB instruction to retire early would neither release the younger stages nor improve single-issue throughput or memory bandwidth, but would require preserving a forwarding value after its producer left MEM/WB. The accepted cost is delayed retirement of an older instruction for the duration of a younger memory wait. This policy must be revisited if precise trap or interrupt semantics, a decoupled retirement mechanism, or another feature makes early architectural retirement observable or necessary.

If no higher-priority event blocks it, redirect preserves older work and the redirecting instruction while invalidating all younger work. Redirect takes priority over a simultaneous load-use indication because the ID instruction is wrong-path. If neither applies, load-use performs the bubble behavior defined above. Otherwise valid instructions advance normally; lack of a `READY` fetch instruction prevents a new IF/ID valid entry but does not stop older stages from draining.

The per-stage next state follows the first applicable row below. “Capture the
output from current X” means capture the combinational stage output produced by
processing the current pre-edge X entry. It never means capturing an entry
newly written into X on the same edge. Specifically, MEM/WB captures MEM output
derived from current EX/MEM, including a load result formatted from the current
expected response; EX/MEM captures EX output derived from current ID/EX; and
ID/EX captures ID output derived from current IF/ID.

| Event | MEM/WB next | EX/MEM next | ID/EX next | IF/ID next | `wb_retire_fire` |
| --- | --- | --- | --- | --- | ---: |
| Synchronous reset | Invalid | Invalid | Invalid | Invalid | `0` |
| Unresolved MEM wait | Hold | Hold | Hold | Hold | `0` |
| `redirect_fire` | Capture MEM output from current EX/MEM | Capture EX output from redirecting current ID/EX | Invalid | Invalid | Current MEM/WB valid |
| Load-use hazard | Capture MEM output from current EX/MEM | Capture EX output from load in current ID/EX | Invalid bubble | Hold dependent instruction | Current MEM/WB valid |
| Normal / IF availability | Capture MEM output from current EX/MEM | Capture EX output from current ID/EX | Capture ID output from current IF/ID | Capture oldest `READY`, otherwise invalid | Current MEM/WB valid |

`data_response_fire` makes the MEM wait resolved for the current edge, so arbitration continues to redirect, load-use, or normal behavior. On a response-plus-redirect edge, the old WB instruction retires, the completed memory instruction enters MEM/WB, the redirecting EX instruction enters EX/MEM, and both younger pipeline entries become invalid. On a response-plus-load-use edge, the old WB instruction retires, the completed memory instruction enters MEM/WB, the load in EX enters EX/MEM, ID/EX receives a bubble, and the dependent IF/ID instruction remains held.

During a load-use hazard, IF/ID does not consume a new instruction, but the
Prefetch Unit continues normal response capture, `READY` creation, PC
allocation, and request issue subject to Fetch Buffer capacity,
`OBI_OUTSTANDING_MAX=1`, and the registered-MEM-occupancy rule below. During an
unresolved MEM wait, proactive frontend progress is frozen: the Prefetch Unit
does not allocate a new PC, consume a `READY` entry into IF/ID, or first-present
an uncommitted queued request.

First presentation of an instruction request is qualified by current
registered MEM occupancy, not by combinational MEM-wait release. While
`EX/MEM.valid && EX/MEM.mem_en` is true, the frontend must not first-present an
uncommitted queued request, including during the cycle in which
`data_response_fire` releases the pipeline. After that edge, first presentation
is permitted only if the updated EX/MEM entry does not contain another memory
instruction and the other fetch-issue conditions permit it. This rule uses
existing registered state and prevents a combinational path from
`data_rvalid` to `instr_req`. It does not delay pipeline advance, fetch
allocation, IF/ID delivery, or redirect processing otherwise permitted on the
response edge, and it adds no pipeline release bubble.

Mandatory OBI progress continues during both load-use and MEM stalls. A request
already asserted retains stable `req` and payload and may be granted, including
on the MEM response edge; `instr_request_fire` is recorded; an expected
outstanding response is accepted on `instr_response_fire`; and the Fetch Buffer
performs every state transition required by those events. MEM stall freezes
architectural and proactive fetch progress, not protocol obligations.

### Architectural side effects

Every architectural or externally visible side effect requires a valid instruction that owns the responsible pipeline stage. `wb_retire_fire` means that the current live instruction leaves the terminal WB stage on this edge; it is distinct from any particular architectural side effect. Conceptually:

```text
wb_retire_fire = current MEM/WB.valid
                 && WB stage is allowed to advance
```

`wb_retire_fire` is not a universal commit point for every externally visible
side effect. In particular, a younger store may transfer its data-interface
request while an older RF-only instruction is held in WB by the unresolved MEM
wait caused by that same store. The older instruction need not retire before
the younger store's address phase is accepted.

Synchronous reset and an unresolved MEM wait prevent WB advance and force `wb_retire_fire=0`. Redirect, load-use, normal flow, and a `data_response_fire` edge that releases a MEM wait allow WB to advance. A held WB instruction therefore cannot be counted as retiring repeatedly. The register file write is the separate side effect `rf_write_fire = wb_retire_fire && MEM/WB.reg_write && MEM/WB.rd != 0`; branch and jump link values use this ordinary WB path. Invalid, flushed, or killed pipeline state cannot write the register file, create a data request, perform a store, or redirect control flow. A valid MEM owner remains responsible for continuing its current request and response protocol while the architectural pipeline is frozen; the interlock does not suppress mandatory OBI progress.

A store address transfer on `data_request_fire`, as defined in
[OBI response validity and reset](#obi-response-validity-and-reset), is
irrevocable from the core's perspective: transaction ownership has passed to
the data interface and the core no longer has the right to roll it back. This transfer does not imply that
physical memory must be updated in the handshake cycle; the subordinate owns
that internal timing. `data_response_fire` confirms transaction completion. A younger
redirect does not cancel an older store already accepted in MEM, whereas a
wrong-path store younger than the redirect is invalidated before it can own MEM
or issue a request.

Data transactions remain ordered in program order. The single-issue pipeline
does not allow a younger memory instruction to bypass the current MEM owner,
and `DATA_OUTSTANDING_MAX=1` permits only one accepted, incomplete data
transaction. This ordering guarantee is separate from WB retirement timing.

### Instruction-fetch organization

IF is an architectural pipeline boundary, not another name for the Prefetch Unit. In the baseline, the hierarchy is `core -> IF -> Prefetch Unit -> {Fetch Controller Unit, Fetch Buffer, OBI Interface}`. The Prefetch Unit converts the selected instruction-address stream into a valid instruction stream for the pipeline. A later IF design may also contain a branch predictor, including structures such as a BHT, PHT, BTB, or RAS, but the five-stage baseline contains no predictor. A future predictor would inform next-PC selection in the Fetch Controller Unit; it would not replace the Prefetch Unit.

The Fetch Controller Unit is the instruction-fetch control plane. It owns current- and next-PC selection, sequential `PC + 4` progression, redirect selection, issue policy, and commands to drop or kill wrong-path work. It does not store the per-transaction metadata and does not directly implement OBI request stability or handshake state.

The Fetch Buffer stores which fetch transactions exist, their lifecycle state, and completed instruction responses awaiting pipeline consumption. Its baseline capacity is `FETCH_DEPTH=3`. Each entry conceptually contains `{valid, pc, state, killed, protocol_committed, instruction}`; `instruction` is datapath payload and is meaningful only for a live `READY` entry. An implementation may encode equivalent state differently without changing the contract. The OBI Interface presents the selected entry as protocol signals and enforces the OBI hold, stability, and handshake rules.

## Core memory boundary

The core exposes two independent OBI 1.6.0 memory ports: a read-only instruction port for IF and a load/store data port for MEM. The data port permits at most one outstanding transaction. The instruction frontend has three Fetch Buffer entries, while the baseline core-level instruction-memory model accepts at most one granted-but-not-responded transaction; therefore the current instruction-port configuration has `FETCH_DEPTH=3` and `OBI_OUTSTANDING_MAX=1`. Memory responses may be delayed; the core must use the protocol handshake rather than assume a fixed response latency.

The OBI configuration below classifies every signal or property as one of the following:

- **Present:** exposed with the behavior defined by the baseline contract.
- **Constant by port contract:** present or given equivalent tie-off semantics with a fixed value required by the port's role.
- **Not present at the five-stage baseline boundary:** the optional feature has no baseline pin or logic.

No OBI item remains open for the five-stage baseline. Any future unclassified
item requires an explicit contract update and must not be chosen implicitly by
an implementation.

These selections apply only to the five-stage baseline links. They are not project-wide constants and do not prohibit a later core or memory-subsystem configuration from selecting additional OBI features. The contract does not use “not implemented yet” for an absent feature because that phrase neither defines the current interface nor establishes a future commitment.

### OBI baseline configuration

Both ports expose `req`, `gnt`, `addr[31:0]`, `we`, `be[3:0]`, `wdata[31:0]`, `rvalid`, `rready`, and `rdata[31:0]`. The instruction port classifies `we=1'b0`, `be=4'b1111`, `wdata=32'b0`, and `rready=1'b1` as constant by its read-only full-word port contract. The data port drives the request payload according to the accepted aligned load or store and classifies `rready=1'b1` as constant by its single-transaction MEM/WB contract.

The baseline selects these OBI properties:

| Property | Value |
| --- | ---: |
| `COMB_GNT` | `False` |
| `AUSER_WIDTH` | `0` |
| `WUSER_WIDTH` | `0` |
| `RUSER_WIDTH` | `0` |
| `ADDR_WIDTH` | `32` |
| `DATA_WIDTH` | `32` |
| `ID_WIDTH` | `0` |
| `MID_WIDTH` | `0` |
| `ACHK_WIDTH` | `0` |
| `RCHK_WIDTH` | `0` |
| `INTEGRITY` | `0` |
| `BE_FULL` | `0` |

`BE_FULL=0` still permits nonzero contiguous byte-enable patterns. The core's aligned-access restriction is a separate architectural contract. `OBI_OUTSTANDING_MAX=1` on the instruction link and `DATA_OUTSTANDING_MAX=1` on the data link are manager/subordinate link contracts, not OBI properties.

The following optional signals are not present at the five-stage baseline boundary: `auser`, `wuser`, `ruser`, `aid`, `rid`, `mid`, `prot`, `memtype`, `dbg`, `atop`, `err`, `exokay`, `reqpar`, `gntpar`, `rvalidpar`, `rreadypar`, `achk`, and `rchk`. Consequently, the baseline has no bus-error response, transaction or manager identifiers, privilege or memory-type attributes, debug marker, atomic or exclusive signaling, user metadata, or interface-integrity signaling. Legal in-range accesses to the core-level harness are therefore required to complete without a bus error.

### OBI response validity and reset

The per-port outstanding state records whether the core expects a response for
an accepted address transfer. At each rising edge of `clk`, request and
response events use the sampled `rst_n` and per-port signals as follows:

```text
request_fire          = rst_n && req && gnt
raw_response_transfer = rst_n && rvalid && rready
response_fire         = outstanding && raw_response_transfer
```

Reset has priority in the core, both harness subordinates, and their checkers.
On an edge sampling `rst_n=0`, no request is accepted, no response creates a
result or completion, and no new instruction side effect occurs, even if the
pre-edge `req && gnt` or `rvalid && rready` signals are high. All three events
above are zero, and unexpected-response checking is inactive on that edge.
These are sampled-edge event definitions, not a requirement to gate OBI
outputs asynchronously with `rst_n`.

Here `outstanding` is the current pre-edge state. On an edge sampling
`rst_n=1`, each port's accepted request and expected-response events update
ownership as
`next_outstanding = current_outstanding + request_fire - response_fire`, subject
to that port's one-outstanding limit. On a reset edge, next outstanding state
is zero instead.

The instruction port therefore has `instr_request_fire` and
`instr_response_fire`; the data port has `data_request_fire` and
`data_response_fire`. Each event uses its own port signals, and each response
event uses that port's current outstanding state and raw response transfer.
`rready` reports only whether the core can accept or
deliberately discard a raw response transfer on the current rising edge; it
does not report whether a transaction is outstanding. Only `response_fire` is
an expected response and may advance a transaction lifecycle, consume its
outstanding state, or create an architectural or pipeline result. `rdata` has
no effect without an expected response and is ignored for a store response.

An unexpected response is
`raw_response_transfer && !outstanding`. Because `rready=1`, it is drained, but
it does not decrement legitimate outstanding state, resolve a MEM wait, create
a `READY` instruction, or create a `load_result`. It only reports a protocol
violation through verification.

Instruction-side `rready` is tied to `1'b1`. Every instruction transaction reserves its Fetch Buffer entry before becoming `OUTSTANDING`, so an expected response always has storage in its own entry and a killed expected response can always be discarded. IF/ID stall and redirect therefore do not backpressure instruction responses. An unexpected instruction response is still drained, discarded, and reported as a protocol violation by verification; constant readiness must not conceal the violation.

Data-side `rready` is also tied to `1'b1`. With `DATA_OUTSTANDING_MAX=1`, the load or store that created the transaction retains ownership of MEM until `data_response_fire`. WB has no independent downstream backpressure, although the global unresolved-MEM interlock deliberately holds MEM/WB and suppresses retirement. The expected-response cycle releases that interlock: any held WB instruction retires on the same edge that the completed memory instruction enters MEM/WB. MEM/WB therefore remains the reserved destination for an expected load response; a store response requires no response payload storage. An unexpected data response is drained, discarded, and reported as a protocol violation by verification, without releasing the interlock.

Reset clears pipeline-valid, Fetch Buffer entry-valid and lifecycle state, and
per-port outstanding state. It does not reset the `pc` or `instruction` payload
of an invalid Fetch Buffer entry. The baseline contains no separate
data-response buffer. After a rising edge samples `rst_n=0`, the reset control
state drives core `req=0`; the harness subordinate drives `rvalid=0` and clears
all pending transaction and response state. This is synchronous behavior and
does not require asynchronous combinational gating merely because `rst_n`
becomes low between rising edges. The harness must never return a response for
a pre-reset transaction after reset. Responses for newly accepted post-reset transactions
follow the normal expected-response rules.

A response received outside reset while no transaction is outstanding is
drained, discarded, and reported as a protocol violation without creating a
valid pipeline entry or architectural side effect. This is not a guarantee
that the core can identify every stale response: with no transaction ID or
reset epoch, a forbidden pre-reset response cannot necessarily be distinguished
from a response to a newly outstanding transaction. Correct operation therefore
depends on both subordinates honoring the shared-reset flush contract. The
core reset does not clear backing memory and does not guarantee rollback of a
store whose address transfer was accepted before reset.

### Instruction fetch capacity and transaction states

`FETCH_DEPTH=3` is frontend capacity, not a claim that the current memory accepts three outstanding transactions. A Fetch Buffer entry has the following conceptual lifecycle:

```text
FREE
  -> QUEUED
  -> OUTSTANDING
  -> READY
  -> FREE
```

The states have these meanings:

- `QUEUED` means the fetch transaction exists in the Fetch Buffer but its address handshake has not completed.
- `OUTSTANDING` means `instr_request_fire` accepted the address transfer and the corresponding response is mandatory.
- `READY` means the memory transaction has completed and the entry holds `{pc, instruction}`, but IF/ID has not yet accepted that instruction.

`FREE` denotes an invalid entry rather than useful payload state. Under the baseline memory model, the intended full-throughput occupancy is one `READY` entry, one `OUTSTANDING` entry, and one next `QUEUED` entry. Other legal occupancies include multiple `READY` entries while pipeline consumption is delayed, but no occupancy may contain more than one `OUTSTANDING` entry.

A queued entry may either be internal and not yet presented to OBI, or be driving an asserted `req` while waiting for `gnt`. The conceptual `protocol_committed` state distinguishes these cases. Before presentation, `protocol_committed=0`, so a redirect may remove the entry immediately. Once `req` has been asserted, the entry is protocol-committed: its request payload remains stable and the request is not retracted merely because of a redirect. If the entry is then found to be on the wrong path, it is marked killed and its transaction is completed and drained without producing a valid instruction.

The OBI Interface selects the oldest eligible `QUEUED` entry by allocation age for instruction-memory issue. A numerically lower PC does not imply an older entry. An older `READY` entry does not block issue because its memory transaction is already complete. Once a queued entry has been presented with `req=1` and is waiting for `gnt`, neither a younger queued entry nor a redirect target may bypass or replace it.

The next queued entry may be presented while one older instruction transaction remains `OUTSTANDING`. The subordinate holds `gnt=0` until it has capacity to accept that request. It may assert `gnt` on the same edge that the older expected response fires, but it must not create a state in which more than one instruction transaction is granted but not responded. Verification enforces `next_outstanding <= OBI_OUTSTANDING_MAX`, where `OBI_OUTSTANDING_MAX=1`. On an edge sampling `rst_n=1`, `next_outstanding = current_outstanding + instr_request_fire - instr_response_fire`; a reset edge instead clears the count to zero. A raw unexpected response does not decrement this count. The presented request exists in registered Fetch Buffer state and must not arise combinationally from the older response.

No deasserted-`req` bubble is required between accepted instruction transactions. After `instr_request_fire` for one request on cycle N, the OBI Interface may select the next queued entry, change to its request payload after the accepting edge, and keep `req=1` during cycle N+1. Each individual entry's payload nevertheless remains stable from its first asserted `req` until its own `gnt`.

The Fetch Controller owns the registered `next_fetch_pc`; the Fetch Buffer does not calculate `PC + 4` or otherwise choose the next address. When the Fetch Controller allocates a free entry as `QUEUED`, it assigns the current `next_fetch_pc` to that entry. Ownership of that fetch PC then transfers to the entry, and the Fetch Controller advances its registered next-fetch state immediately without waiting for `gnt` or a response. A later predictor may change how the Fetch Controller selects `next_fetch_pc`, but it does not change this ownership boundary.

The additional entries therefore allow the sequential next fetch to be prepared from registered frontend state while an older transaction awaits its response and an older completed instruction awaits pipeline consumption. A new instruction request must not be created through a combinational dependency on the current `rvalid`, `rdata`, or `gnt` of either OBI port. In particular, first presentation follows the registered-MEM-occupancy rule in [Pipeline-control priority](#pipeline-control-priority). If a later instruction memory, cache, or interconnect accepts more than one granted-but-not-responded transaction, multiple entries may become `OUTSTANDING` only after an explicit configuration-contract update; the Fetch Buffer architecture itself need not be replaced.

When `instr_response_fire` occurs for a live `OUTSTANDING` entry, the Fetch Buffer captures `rdata` as that entry's instruction payload and changes the entry to `READY`, independently of whether IF/ID can accept an instruction on that cycle. The subordinate then has no further responsibility for that transaction. `RESPONSE_BYPASS=0`: a response cannot pass combinationally from OBI into IF/ID, and even an immediately consumable expected response must first become registered `READY` state. If the `OUTSTANDING` entry is killed, its expected response is accepted and discarded and the entry becomes `FREE` without ever becoming a valid `READY` instruction.

Live `READY` entries are offered to IF/ID in oldest-first allocation order, not numerical-PC order. A younger entry cannot bypass an older live entry. When IF/ID accepts the oldest live `READY` entry, that entry becomes `FREE`. A killed `READY` entry is discarded without producing instruction-valid; after it is removed, the next live entry becomes oldest. A killed `OUTSTANDING` entry retains its ordering position until its mandatory response has been drained.

The instruction memory may produce `instr_response_fire` for A and `instr_request_fire` for an already-presented B in the same cycle. A was already `OUTSTANDING`, and B already existed in registered `QUEUED` protocol-committed state with stable `req` and request payload. On that edge A becomes `READY` and B becomes `OUTSTANDING`; the outstanding count remains one. No combinational dependency from A's `rvalid` to B's `req` is permitted.

With one-cycle response latency, `instr_request_fire` available for the next queued request in the same cycle as the current `instr_response_fire`, and IF/ID accepting one instruction every cycle, the three entries can sustain a steady-state occupancy of `READY + OUTSTANDING + QUEUED`. In one edge, the oldest `READY` entry may be consumed, the `OUTSTANDING` entry may complete with `instr_response_fire`, the `QUEUED` entry may be accepted with `instr_request_fire`, and the newly freed entry may be allocated the next registered fetch PC. After initial fill, this permits one instruction delivery per cycle without an OBI-to-IF/ID combinational path. Arbitrary response latency, unavailable grants, redirect recovery, or pipeline backpressure may reduce throughput and are not hidden by this conditional claim.

### Data transaction completion

For a load or store, MEM presents the request only from registered EX/MEM state whose address phase has not yet been accepted. `data_request_fire` accepts that held address-phase payload but does not complete the transaction; request-accepted state suppresses duplicate issue while the instruction remains valid in EX/MEM. `DATA_OUTSTANDING_MAX=1`: the instruction remains in MEM and the data-port transaction remains outstanding until `data_response_fire`. A load then formats the selected response lane into `load_result`, captures it into MEM/WB, and advances to WB. A store ignores `rdata`; its expected response marks successful completion and allows the store to advance to WB with `reg_write=0`. No younger instruction passes a data transaction waiting in MEM, and no later data transaction is issued before the current one completes.

WB has no independent downstream backpressure in the baseline, but it is held by the unresolved-MEM interlock. If an older instruction occupies WB while the data transaction waits, its MEM/WB valid and payload remain stable and it does not retire repeatedly. When `data_response_fire` occurs, that older instruction retires on the same edge that the completed memory instruction advances from MEM into WB. Consequently, MEM/WB is the storage reserved for the response-completed instruction and no separate data-response FIFO or buffer exists. A later design with multiple data transactions, independently returning cache responses, or WB backpressure must revisit data-side readiness and response buffering. The subordinate may apply an accepted store at any point after the request transfer permitted by its interface contract, including before returning its response. The core assumes neither an exact physical-memory update cycle nor rollback after the transfer.

The separation between store acceptance and older WB retirement is specific to
this baseline, which has no precise exception, trap, interrupt, or debug
retirement semantics. Revisit this policy, the full-pipeline MEM-wait freeze,
and reset/recovery behavior before adding any of those semantics or any stronger
rollback requirement.

### MEM data formatting and MEM/WB boundary

MEM interprets `EX/MEM.ex_result` as the effective byte address for a load or store:

```text
byte_offset = EX/MEM.ex_result[1:0]
data_addr   = {EX/MEM.ex_result[31:2], 2'b00}
```

The aligned data-port address is `data_addr`. The low effective-address bits remain internal and select the accessed byte lanes. `BYTE` and `BYTE_U` use `be = 4'b0001 << byte_offset`; `HALF` and `HALF_U` use `be = 4'b0011 << byte_offset`; and `WORD` uses `be = 4'b1111`. Legal byte offsets are any value for a byte, zero or two for a halfword, and zero for a word. No accepted access crosses a 32-bit word boundary; an odd-addressed halfword or non-word-aligned word remains outside the baseline contract.

Store write data uses replication rather than lane shifting:

```text
SB: wdata = {4{store_data[7:0]}}
SH: wdata = {2{store_data[15:0]}}
SW: wdata = store_data
```

`be` alone selects the byte lanes written by the subordinate. Masked lanes remain semantically unspecified and must be ignored even though the replicated implementation value makes every physical lane convenient to drive. Correctness therefore depends on the accepted address-phase payload and `be`, not on masked-lane values.

For an expected load response on `data_response_fire`, MEM first aligns the selected lane conceptually as `shifted_rdata = rdata >> (8 * byte_offset)`, then produces:

```text
LB:  sign-extend shifted_rdata[7:0]
LBU: zero-extend shifted_rdata[7:0]
LH:  sign-extend shifted_rdata[15:0]
LHU: zero-extend shifted_rdata[15:0]
LW:  rdata
```

The minimum MEM/WB semantic state is:

```text
valid
ex_result
load_result
wb_from_mem
rd, reg_write
```

`wb_from_mem=1` only for a load and selects `load_result`; every other instruction uses `wb_from_mem=0`, so a register-writing non-load selects `ex_result`. Every live instruction leaving MEM, including a branch or completed store, passes through MEM/WB with `valid=1`; instructions that do not write the register file carry `reg_write=0`. Payload not selected or consumed by that instruction is unspecified. Memory controls, store data, and data-port protocol ownership end in MEM and do not cross MEM/WB.

### Stale instruction responses after redirect

When `redirect_fire` occurs, every younger Fetch Buffer entry allocated before
the redirect is stale and wrong-path, regardless of whether its stored PC
happens to equal `redirect_target`. No such entry is reused based on a matching
PC. The Fetch Controller Unit selects `redirect_target` as the new next fetch
address and always allocates it as a fresh `QUEUED` entry with new allocation
ownership. Redirect controls architectural validity but does not undo an OBI
handshake that occurs on the same edge:

- A wrong-path `READY` entry is freed and cannot create IF/ID valid, even if IF/ID would otherwise accept it on that edge.
- A wrong-path `OUTSTANDING` entry for which `instr_response_fire` occurs on that edge accepts and discards the expected response, then becomes `FREE` rather than `READY`.
- A wrong-path protocol-committed `QUEUED` entry whose request is granted on that edge accepts the address handshake, becomes `OUTSTANDING` with `killed=1`, and must drain its eventual response.
- A wrong-path unpresented `QUEUED` entry is freed immediately.

A protocol-committed queued request that is not granted on the redirect edge remains stable and marked killed until its address transfer is accepted. It cannot be retracted or bypassed by the redirect target. An already-outstanding wrong-path entry without `instr_response_fire` on the redirect edge is likewise marked killed and retained until its expected response is drained.

With `OBI_OUTSTANDING_MAX=1`, the fresh redirected fetch may occupy a slot reclaimed from a dropped, uncommitted queued entry but cannot become a second outstanding transaction. It remains queued until the stale outstanding transaction has been drained and the instruction-memory model can accept the redirected request. This is a consequence of the current memory configuration, not a permanent restriction of the three-entry Fetch Buffer architecture.

The baseline has no `redirect_pending` state. With three Fetch Buffer entries, at most one entry can be `OUTSTANDING` and at most one other entry can be the single protocol-committed queued request currently presented on OBI. The remaining entry is already free or can be reclaimed from stale `READY` or unpresented `QUEUED` state on redirect. The Fetch Controller therefore allocates the redirect target through the normal selected-PC path as a fresh `QUEUED` entry on the redirect edge, then advances its registered next-fetch state to the following sequential PC. The target request can first be presented in the following cycle; there is no combinational EX-to-OBI request path.

Request/outstanding ownership and killed state are control-plane state and are reset. Fetch-entry PC payload is not reset and has meaning only while its entry is valid. Constant instruction-side `rready=1'b1` drains a killed expected response on `instr_response_fire`; stale work cannot block forward progress merely because it will be discarded. A future configuration that cannot guarantee a reclaimable entry on redirect must revisit whether pending-target state is required.

For core-level verification, the testbench provides one independently responding OBI memory model per port, with separate backing storage and non-overlapping code and data address regions. The code model covers `0x0000_0000` through `0x0000_FFFF`; IF fetches instructions only from this region. The data model covers `0x0001_0000` through `0x0001_FFFF`; MEM loads and stores only in this region. Read-only constants loaded by the program, initialized and uninitialized data, stack, and test result locations belong in the data region. Programs that write executable code or access the other port's region are outside this baseline's scope. There is no IF/MEM arbiter at this core-to-testbench boundary.

The code-region restriction applies to every presented instruction request,
including speculative and wrong-path fetches, not only to instructions that
eventually execute. The harness and test program jointly own this precondition.
Test images must provide suitable padding with legal NOP instructions and safe
terminal control flow so that sequential prefetch remains in range, including
while a terminating status-store awaits its response. Keeping only executed
PCs in range is insufficient near the end of the code region. On each edge
sampling `rst_n=1` and instruction `req=1`, the harness checks the request
address independently of `gnt`; an out-of-range request immediately fails the
test instead of being left waiting for grant. This is a harness/program
requirement and does not add a range checker or exception mechanism to the core.

These testbench responders verify core behavior, not DDR timing or performance. The later system may place code and data in distinct regions of the same physical DDR; its memory map, OBI-to-AXI path, and shared arbitration belong to the project-level integration contract.

## Verification strategy and ownership

Baseline verification uses a layered, self-checking oracle rather than requiring
a full instruction-set simulator or retire-stream comparison.

The primary directed layer uses Python, cocotb, and pytest. Directed instruction
tests calculate expected results independently from this semantic contract; they
must not reuse the RTL decoder or implementation logic as their oracle.

Pipeline and OBI monitors combine testbench observation with SystemVerilog
assertions for temporal and protocol invariants. Their scope includes pipeline
valid, hold, bubble, and flush behavior; request stability through grant;
outstanding limits and transaction ordering; and the prohibition on any
architectural or externally visible side effect from invalid state.

Short integration programs check final register and data-memory signatures and
use the [harness completion and timeout contract](#harness-completion-and-timeout-contract)
below.

A RISC-V architectural or ISA test suite provides an additional independent
architectural-correctness layer. The selected tests and harness adaptation must
respect the explicitly supported 37-instruction subset and the baseline's
unsupported exception, trap, privileged, and misalignment behavior. Passing
that suite does not establish full RV32I compliance and does not replace
microarchitectural stress tests for pipeline, redirect, stall, forwarding,
reset, or OBI concurrency behavior.

Mandatory directed verification is organized around six scenario groups:

1. **Instruction semantics.** Cover all 37 supported instructions, immediate
   sign extension, signed and unsigned comparison, shift amounts 0, 1, and 31,
   `x0` behavior, `JALR` bit-zero clearing, forward and backward control-flow
   targets, every legal byte and halfword lane, and load sign and zero
   extension. Each conditional branch requires at least one directed taken case
   and at least one directed not-taken case.
2. **Dependencies.** Cover EX/MEM and MEM/WB forwarding into `rs1`, `rs2`,
   branch comparison, the `JALR` base, effective-address generation, and store
   data; explicit WB-to-ID bypass; and both true and source-use-qualified false
   load-use hazards. When multiple producers match one source, a directed case
   must confirm that the newest eligible producer wins.
3. **Pipeline control.** Cover normal draining while IF lacks a new
   instruction, load-use hold plus bubble insertion, the full-pipeline
   unresolved-MEM freeze, `data_response_fire` release, redirect flushing,
   redirect delayed behind a MEM wait, and `data_response_fire` simultaneous
   with redirect or load-use processing.
4. **Instruction OBI.** Cover request stability while awaiting grant,
   back-to-back requests, simultaneous `instr_response_fire` for A and
   `instr_request_fire` for B, and the
   `READY + OUTSTANDING + QUEUED` steady state, frontend progress during a
   load-use hazard, proactive frontend freeze with mandatory protocol progress
   during a MEM wait, and first-presentation suppression through the MEM
   response cycle, including when another memory instruction replaces the
   completed one. Cover every specified redirect disposition for `READY`,
   `OUTSTANDING`, presented `QUEUED`, and unpresented `QUEUED` entries.
5. **Data OBI.** Cover delayed grant and expected response, duplicate-request
   suppression, the one-outstanding limit, load and store formatting, store
   acceptance while an older WB instruction remains held as permitted by the
   side-effect contract, and unexpected-response handling.
6. **Reset and recovery.** Cover reset while idle, with occupied pipeline
   stages, while a request awaits grant, with an instruction or data transaction
   outstanding, and with a killed instruction response pending. Cover reset
   edges with pre-edge `req && gnt` or `rvalid && rready` high; no new transaction
   is accepted and no response result or completion is created. Confirm that
   both subordinates flush pre-reset protocol state, that invalid state creates
   no side effect, and that the core does not treat a store accepted before
   reset as rolled back.

Every semantic distinction and simultaneous-event case named above requires at
least one directed self-checking test. The contract does not require the full
cross-product of instruction, stall, redirect, and latency combinations; broad
combinations belong to randomized and exploratory verification. This is a
scenario and semantic coverage contract, not a requirement for 100 percent RTL
statement, branch, condition, or toggle coverage.

An unexpected response is always drained so protocol progress cannot deadlock,
but its monitor or assertion reports a protocol violation and the test fails.

Verification artifacts are organized under `src/riscv/tb/` by role in the
verification lifecycle, consistently with the project-level subsystem layout:

```text
tb/
├── common/
├── regression/
├── exploratory/
├── integration/
└── riscv_arch/
```

`common/` contains the harness, helpers, monitors, assertions, and reusable
infrastructure. `regression/` contains the reviewed mandatory self-checking
tests that the project commits to passing. `exploratory/` is the sandbox for
directed corner-case hunting and adversarial or randomized testing, including
tests created by Codex or by a developer. `integration/` contains the short
program and signature tests. `riscv_arch/` contains the architectural or ISA
test-suite integration.

Codex may inspect this design contract and the RTL and use the verification
environment for exploratory or adversarial bug hunting. An exploratory test is
evidence, not specification, and does not automatically become a mandatory
acceptance criterion. After an exploratory test exposes a real bug and the
failure and root cause have been reviewed and understood, the relevant test is
promoted into `regression/`.

Python, cocotb, and pytest form the current verification backbone. If the
environment grows enough to need reusable agents, sequences, scoreboards, or
coverage-driven stimulus, pyUVM may be introduced incrementally. A later
focused SystemVerilog-UVM environment may be added for learning and practicing
UVM methodology; it does not require rewriting the existing verification stack
or displacing the Python backbone.

### Harness completion and timeout contract

The aligned word at `TEST_STATUS = 32'h0001_FFFC` is reserved for test
completion. The test program's linker layout must exclude all four bytes from
ordinary data and stack allocation. Completion uses only `SW` to this address:
`32'd1` means PASS and `32'd2` means FAIL. Any other value or access width used
for a status-store is a test-convention violation and fails the test; partial
stores to any byte of the reserved word are not completion events.

The harness identifies the status-store from its accepted address-phase
payload and retains that identity until the matching `data_response_fire`.
Neither address acceptance alone nor an unexpected response completes a test.
On the expected response edge, final register and data-memory signatures are
sampled only after that edge's sequential updates have settled, including any
older WB register write retiring on that same edge. The test then ends with
the reported status and signature/checker results; a PASS status does not
override a failed signature or checker. This completion ABI avoids a sampling
race with the baseline's held-WB release behavior.

Every test declares finite grant-delay, response-latency, and total-cycle
limits in its version-controlled configuration. The memory responders honor
the configured delay bounds, and harness watchdogs fail the test when a bound
is exceeded. The acceptance evidence records the configuration used. These
are test-environment limits, not fixed-latency assumptions or timeout hardware
in the core; the core continues to use OBI handshakes for progress. Finite,
recorded bounds make a timeout distinguishable from an intentionally delayed
transaction and reproducible with the rest of the test configuration.

### Objective acceptance gate

The verification environment selected for an acceptance run is defined by
version-controlled acceptance manifests. A run may not choose a convenient
subset ad hoc. At minimum, the acceptance evidence identifies:

```text
regression manifest
integration manifest
reviewed and pinned riscv_arch manifest
required assertions and checkers
Git revision
simulator and tool versions
exact commands
randomized seeds
test delay bounds and watchdog limits
```

An acceptance run must satisfy all of the following conditions:

1. The core top and every source selected by the acceptance manifests compile
   and elaborate successfully. The manifests and recorded commands, rather
   than an operator's runtime selection, define the environment under test.
2. Every test selected by the regression and integration manifests passes, and
   every mandatory semantic distinction and scenario from the directed
   coverage contract traces to at least one passing self-checking test.
3. Every applicable test in the reviewed and pinned architectural-test
   manifest passes. A skip, disable, or expected failure is allowed only when
   its specific reason is reviewed and mapped to behavior outside the
   implemented ISA scope. Blanket skipping is not permitted.
4. No unexpected assertion or monitor violation, timeout, or deadlock occurs.
   Checkers have negative self-tests that inject the corresponding violation
   and demonstrate that it is detected. For example, an injected unexpected
   response must make the inner simulation fail; failure to detect it makes the
   checker self-test fail.
5. The evidence is reproducible from the recorded revision, manifests, tool
   versions, commands, and seeds. A fixed-seed randomized test promoted into
   `regression/` becomes mandatory under the same rule as a directed test.
6. `exploratory/` is not an unbounded pass-all gate, but any reproducible
   exploratory failure that has been reviewed and confirmed as a contract
   violation blocks acceptance even before its minimized regression test is
   promoted.

Coverage answers which behavior and structure have been exercised; the
independent oracle and assertions answer whether the exercised behavior is
correct. The baseline therefore sets no numeric RTL line, branch, condition,
toggle, or FSM coverage threshold as an acceptance gate. Structural and
functional coverage are diagnostic inputs used to locate meaningful holes, not
correctness oracles.

The intended closure flow is:

1. Directed regression covers every mandatory semantic distinction and
   scenario defined above.
2. Constrained-random exploratory tests generate combinations of instructions,
   dependencies, and OBI latency.
3. An independent reference or golden model checks randomized architectural
   behavior within the implemented ISA scope, while monitors and assertions
   continue to check pipeline and OBI temporal behavior. This does not require
   a full ISA simulator or retire-stream comparison.
4. Structural and functional coverage identify unexercised behavior.
5. Targeted-random or directed tests close meaningful holes.
6. An understood random failure is minimized into a small reproducible case and
   promoted into `regression/`.

The required functional and contract coverage therefore traces every accepted
requirement to verification evidence. RTL coverage percentages remain
diagnostic metrics and may become CI gates only after the environment matures
and a later explicit contract establishes appropriate thresholds.

This gate establishes the five-stage baseline within its implemented ISA scope
at the core-level harness. It does not establish any capability outside the
current contract, including full RV32I compliance, SoC or DDR integration, FPGA
operation, timing closure, area, or power.

## Contract closure

None within the five-stage baseline scope.
