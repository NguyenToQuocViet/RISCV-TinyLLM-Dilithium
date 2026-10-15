# Execute Stage — Decomposition and Submodule Boundaries

**Status:** Accepted decomposition, naming and semantic boundaries, confirmed by
Nguyễn Tô Quốc Việt on 2026-10-15. RTL interface details listed in
[section 8](#8-remaining-interface-decisions) are not yet accepted.
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner.
**Design revision:** EX D1 / 2026-10-15; refines BASE R1 without revising it.
**Parent contract:** [Five-stage BASE core](5-stage-baseline-core.md).
**RTL mapping:** Planned; this document is not implementation or verification evidence.

## 1. Purpose, authority and delivery scope

This document records the owner's selected EX decomposition and the semantic
boundary of each child. Naming, responsibility allocation and rationale live
here so they do not need to be reconstructed from chat. The parent continues
to own instruction semantics, pipeline control, forwarding eligibility,
memory ordering and architectural side-effect rules. This design refines
those requirements; it does not override them.

The first complete RTL feature to deliver is the BASE execute stage. The
2026-10-15 implementation target is only its ALU leaf, including independent
block verification. This is an internal subsystem increment, not a project
release or evidence that BASE executes programs. The full stage is a later
integration boundary; finishing ALU does not finish EX.

This task authorizes recording the design, not writing RTL, test infrastructure,
or build scripts. Core RTL remains human-authored unless Việt explicitly
delegates implementation. Project milestone ownership and integration workflow
remain under [PROJECT_MANAGEMENT](../../../../docs/PROJECT_MANAGEMENT.md) and
[AGENT_POLICY](../AGENT_POLICY.md).

CI, CSR/MRET, IRQ, cache and prediction are outside this BASE stage increment.
Later extensions must preserve ordinary BASE behavior and define their own
overrides rather than being anticipated in today's ALU.

## 2. Selected hierarchy and naming

There are **seven direct submodules, eight RTL modules including the parent**.
The design deliberately exposes semantic functions as leaves, including the
link adder and muxes. Module and file names describe function; instance names
identify use in EX. Use `lower_snake_case`, with no `riscv_` module prefix or
mandatory `u_` instance prefix.

| Module | File basename | Instance name | Instantiated by |
| --- | --- | --- | --- |
| `execute_stage` | `execute_stage.sv` | `ex_stage` | Core |
| `forwarding_unit` | `forwarding_unit.sv` | `ex_forwarding` | `execute_stage` |
| `operand_mux` | `operand_mux.sv` | `ex_operand_mux` | `execute_stage` |
| `alu` | `alu.sv` | `ex_alu` | `execute_stage` |
| `branch_comparator` | `branch_comparator.sv` | `ex_branch_comparator` | `execute_stage` |
| `link_adder` | `link_adder.sv` | `ex_link_adder` | `execute_stage` |
| `result_mux` | `result_mux.sv` | `ex_result_mux` | `execute_stage` |
| `redirect_unit` | `redirect_unit.sv` | `ex_redirect` | `execute_stage` |

```text
ex_stage : execute_stage
  ex_forwarding        : forwarding_unit
  ex_operand_mux       : operand_mux
  ex_alu               : alu
  ex_branch_comparator : branch_comparator
  ex_link_adder        : link_adder
  ex_result_mux        : result_mux
  ex_redirect          : redirect_unit
```

These are module/file basenames, not a decision to create a new RTL directory
tree. No files or modules in this table are claimed to exist yet.

## 3. Stage boundary and storage ownership

`execute_stage` and all seven children are combinational. They have no private
pipeline registers, transaction state, clock or reset input. The core owns the
clocked ID/EX and EX/MEM registers outside this hierarchy and applies the
parent's valid, reset, hold, bubble and flush rules.

Inputs comprise the registered
[ID/EX semantic payload](5-stage-baseline-core.md#idex-boundary), producer
information from EX/MEM and MEM/WB, and the permission for the current EX
instruction to advance. Addresses, PC, register values, immediate and execution
results are 32 bits; register identifiers are 5 bits; predicates are 1 bit.
Control encodings remain subject to section 8.

ID exclusively decodes instructions. Raw instruction, opcode, funct fields and
immediate-format selection do not enter this hierarchy. The incoming immediate
is already reconstructed as a canonical 32-bit value by ID. In particular,
U-type reconstruction has already placed the 20-bit field in bits 31:12 and
filled bits 11:0 with zero.

There are two distinct output paths:

| Output path | Consumer and meaning |
| --- | --- |
| `ex_result`, `store_data`, destination and memory intent | Core-owned EX/MEM register; capture only according to parent pipeline control |
| `redirect_fire`, `redirect_target` | Core/frontend control; target is meaningful when redirect fires |

The exact carried fields are owned by the parent's
[EX/MEM boundary](5-stage-baseline-core.md#exmem-boundary-and-data-request-ownership).
The wrapper passes metadata and wiring; functional decisions belong to the
named leaves. No EX output directly writes the register file or issues OBI.
In particular, EX computes a store address and data but MEM owns the request.

Unused datapath outputs need not have architectural meaning. Invalid payload
must never authorize a redirect or another side effect. Combinational results
do not imply stage acceptance, retirement or a fixed physical propagation delay.

## 4. Child semantic contracts

Names below identify logical fields and responsibilities. They do not silently
freeze an unreviewed packed struct, port suffix convention or numeric encoding.

### 4.1 Forwarding unit

Inputs are the two source identifiers and values from ID/EX, EX/MEM producer
destination/valid/write intent/result availability and result, and MEM/WB
producer destination/valid/write intent and selected `wb_data`.
Outputs are `fwd_rs1` and `fwd_rs2`.

For each source independently, select the youngest eligible producer using the
parent's [forwarding rules](5-stage-baseline-core.md#forwarding-and-load-use-hazards).
EX/MEM has priority over MEM/WB, then the ID/EX source value is the fallback.
An invalid producer, a non-writer or destination x0 is ineligible. EX/MEM loads
are not forwarding sources; MEM/WB supplies the selected architectural WB value.
This leaf does not detect or schedule the ID load-use bubble.

The forwarded outputs feed operand selection, branch comparison, the JALR base
and store data. `store_data` is wired from `fwd_rs2`, independently of the ALU's
second operand. A held MEM/WB producer remains available during a MEM wait and
on its release edge, as required by the parent.

### 4.2 Operand mux

Inputs are `fwd_rs1`, `fwd_rs2`, instruction PC, canonical immediate and the
decoded operand selectors. Outputs are two 32-bit ALU operands.

| Instruction class | Operand A | Operand B | ALU operation |
| --- | --- | --- | --- |
| Register arithmetic/logic | `fwd_rs1` | `fwd_rs2` | Decoded operation |
| Immediate arithmetic/logic | `fwd_rs1` | `imm` | Decoded operation |
| LUI | ZERO | `imm` | ADD |
| AUIPC | `pc` | `imm` | ADD |
| Load/store | `fwd_rs1` | `imm` | ADD |
| Conditional branch | `pc` | `imm` | ADD |
| JAL | `pc` | `imm` | ADD |
| JALR | `fwd_rs1` | `imm` | ADD |

Branch comparison bypasses these mux outputs: it requires the two forwarded
register values while the ALU computes the target from PC and immediate.
FENCE requires no meaningful ALU operands or result.

### 4.3 ALU

Inputs are 32-bit `operand_a`, 32-bit `operand_b` and semantic `alu_op`.
The output is 32-bit `alu_result`. The selected operation set is exactly:

| Operation | Required result |
| --- | --- |
| ADD | ADD of both operands, retaining the low 32 bits |
| SUB | SUB of operand B from operand A, retaining the low 32 bits |
| AND | Bitwise AND |
| OR | Bitwise OR |
| XOR | Bitwise XOR |
| SLL | Logical left shift of A by B[4:0], filling with zero |
| SRL | Logical right shift of A by B[4:0], filling with zero |
| SRA | Arithmetic right shift of signed A by B[4:0], replicating the sign bit |
| SLT | Signed less-than comparison; 32-bit one when true, otherwise zero |
| SLTU | Unsigned less-than comparison; 32-bit one when true, otherwise zero |

Operation names describe semantic choices, not accepted enum identifiers or bit
patterns. Addition/subtraction do not produce overflow traps or architectural
flags. The ALU does not decode an instruction, choose operands, perform
forwarding, select a link result or authorize redirect.

LUI uses ADD with ZERO; it needs no extra shift or PASS operation. SLT/SLTU stay
in the ALU even though a separate branch comparator exists. FENCE requires no
dedicated ALU operation. JALR's bit-zero clearing belongs to the redirect unit.

### 4.4 Branch comparator

Inputs are `fwd_rs1`, `fwd_rs2` and decoded branch kind. The output is a Boolean
`branch_condition`, consumed only for a conditional branch.

Supported conditions are EQ, NE, LT_SIGNED, GE_SIGNED, LT_UNSIGNED and
GE_UNSIGNED, with meanings inherited from the parent's
[instruction semantic table](5-stage-baseline-core.md#instruction-semantic-table).
No instruction encoding is interpreted here. The comparator does not compute a
target, create a link value, apply stage-valid/advance gating or emit redirect.

The condition is a predicate, not a 32-bit architectural SLT result. Sharing
comparison logic across ALU and comparator is not part of this decomposition;
there is no cross-leaf comparison-result interface.

### 4.5 Link adder

Input is the 32-bit PC belonging to the instruction in ID/EX. Output is the
32-bit link value `ADD(pc, 4)`, retaining the low 32 bits. This dedicated leaf
operates in parallel with target calculation in the ALU.

Use the instruction PC, not the frontend's current or next fetch PC. Do not
carry `pc_plus_4` through earlier pipeline registers for this design. BASE has
fixed 32-bit instructions; this leaf has no compressed-instruction increment.
It computes a value only; it does not write rd.

### 4.6 Result mux

Inputs are the ALU result, link value and decoded selection intent. Output is
`ex_result`: select link for JAL/JALR and the ALU result for the other classes
that require a meaningful EX result, including load/store effective addresses.
Branches and FENCE have no architectural register result.

This is EX result selection, not final WB selection. Load-response formatting
and the final choice between formatted load data and `ex_result` remain in
MEM/WB as specified by the parent. Target and link must remain distinct for a
jump even when its destination is x0.

### 4.7 Redirect unit

Inputs are ALU target, branch condition, decoded branch/jump intent, EX valid
and the core's permission for EX to advance. Outputs are `redirect_fire` and
32-bit `redirect_target`.

- A conditional branch requests redirect only when its condition is true.
- JAL and JALR request redirect unconditionally with respect to branch condition.
- The request becomes `redirect_fire` only for a valid instruction permitted to
  advance. Core permission incorporates reset/hold control; it must not depend
  circularly on the redirect output it qualifies.
- Branch/JAL target is the ALU result. JALR target keeps bits 31:1 of that result
  and forces bit 0 to zero by wiring; there is no second ALU operation.

The leaf does not itself flush registers or update fetch PC. Core/frontend
control consumes its outputs under the parent's
[redirect contract](5-stage-baseline-core.md#redirect-event-and-pipeline-recovery)
and [pipeline priority](5-stage-baseline-core.md#pipeline-control-priority).
No private `redirect_sent` state or early redirect during MEM wait is added.
Clearing bit 0 does not guarantee four-byte alignment; misaligned targets
remain outside BASE rather than being silently rounded down further.

## 5. Composition and simultaneous work

```text
ID/EX sources + producer metadata
             |
        forwarding_unit
          |         |
          |         +----> branch_comparator ----> branch_condition
          |
          +----> operand_mux ----> alu ----+-----> result_mux ---> ex_result
          |                              |
          +----> store_data              +-----> redirect_unit ---> redirect

ID/EX.pc ----> link_adder ----------------------> result_mux
```

Decoded intent and valid/advance control feed the leaves described above; the
diagram shows datapath connections, not a complete physical port declaration.

| Case | Work performed in parallel | Required observation |
| --- | --- | --- |
| Taken branch | Compare forwarded registers; ALU ADD of PC and immediate | Target and true condition available in the same EX stage |
| JAL/JALR | ALU computes target; link adder computes link | Result mux emits link while redirect unit emits target |
| Store | ALU computes address; forwarded rs2 supplies store data | Immediate selection cannot replace store data |
| MEM wait with branch/jump in EX | Values may remain combinationally available; core forbids advance | No redirect fires merely because target/condition is ready |
| Expected data response releases wait | Parent permits advance; retained WB source still forwards | Held control-flow instruction redirects on the release edge if required |

Reset, hold and flush affect the surrounding pipeline control/state, not private
EX storage. No output becomes an architectural side effect solely because its
combinational value changes.

## 6. Verification and delivery boundaries

These are planned checks, not recorded passes. The parent's
[verification strategy](5-stage-baseline-core.md#verification-strategy-and-ownership)
owns tools, oracle independence and core-level acceptance.

**ALU increment:** cover all ten operations with independently calculated
expected values. Include wraparound for ADD/SUB; opposite-sign comparisons;
SLT versus SLTU; SRA versus SRL; shifts by 0 and 31; and operands with identical
low five shift bits but different upper bits. For example:

| Inputs and operation | Expected result |
| --- | --- |
| ADD(0xFFFFFFFF, 0x00000001) | 0x00000000 |
| SLT(0xFFFFFFFF, 0x00000000) | 0x00000001 |
| SLTU(0xFFFFFFFF, 0x00000000) | 0x00000000 |
| SRA(0x80000000, 0x00000001) | 0xC0000000 |
| SRL(0x80000000, 0x00000001) | 0x40000000 |
| SLL(0x00000001, 0x00000020) | 0x00000001 |

ALU-related verification uses only 0/1 inputs, both in isolation and at EX
integration; X/Z tests and dedicated unknown-input checkers are outside scope.
Test all six unassigned binary selectors against the fallback in the
[ALU contract](alu.md#4-input-validity-and-exceptional-conditions). At EX
integration, a valid instruction using one of those codes must cause checker
FAIL; arbitrary selector payload in an invalid entry must not trigger that check.

**Complete EX feature:** verify leaf contracts and their composition. Important
cases include conflicting forwarding producers, x0, unavailable EX/MEM loads,
both branch operands forwarded, simultaneous compare/target generation,
simultaneous jump target/link generation, JALR bit-zero clearing, store-data
independence, invalid EX state, and MEM-wait hold/release with redirect.
Compare against the parent's instruction semantics, not a duplicate RTL decoder.

Full EX acceptance requires these checks under surrounding pipeline-register and
control stimulus; it does not require the actual frontend, OBI subordinate or
accelerator IP. Conversely, standalone EX evidence does not establish complete
pipeline, memory-interface, FPGA, timing or PPA correctness. Simulator selection,
runner setup and exact reproducible commands are separate implementation work;
none is introduced by this document.

## 7. Recorded rationale and revisit conditions

| Selected decision | Reason and consequence |
| --- | --- |
| Functional module/file names; EX-prefixed instances | Separate what a block is from where it is used; supersedes the earlier proposal to name the ALU module `ex_alu` |
| Semantic functions exposed as seven leaves | Owner prefers visible hierarchy and independently reviewable boundaries, including small mux/adder functions |
| Dedicated branch comparator; ALU computes target | Compare register operands and calculate target simultaneously without adding EX cycles |
| Dedicated EX link adder | Target and link are available together; no extra PC-plus-four pipeline payload |
| Ten ALU operations | Arithmetic/logic instructions and address/target calculations are covered; branch conditions and JALR masking have separate owners |
| Separate ALU/comparator interfaces | Clear local contracts; possible comparison-logic duplication is accepted without claiming measured area or timing |
| `redirect_unit` name | Leaf qualifies a redirect using an existing condition/target; it covers branch and jump without owning all branch calculation |
| EX first complete feature; ALU first increment | Establish a bounded integration target while limiting today's implementation scope |

Naming/decomposition were accepted in the owner's request to record these
decisions. Numeric control encoding and other open details were not implicitly
accepted by that request. Any later material change needs owner approval and
an update here before implementation; change the parent only if its behavioral
contract changes. PPA-driven sharing or moving link computation upstream requires
evidence and explicit reconsideration, not an automatic cleanup.

This document records local design rationale in the same requested artifact;
it does not create a second decision ledger or copy the baseline contract.

## 8. Remaining interface decisions

The decomposition and semantic responsibilities above are selected. They do not
yet constitute a complete pin/encoding specification for every leaf.

| Remaining choice | Scope and effect | Owner / next recommendation |
| --- | --- | --- |
| `alu_op` representation | Resolved for ALU; ID and ALU consume the same shared definition | See the accepted [ALU interface](alu.md#2-interface-timing-and-state) and operation mapping; this row does not independently define the encoding |
| Unsupported ALU selector values | Resolved: leaf contract owns fallback behavior; section 6 owns checker requirements | See [ALU input validity](alu.md#4-input-validity-and-exceptional-conditions) |
| Remaining EX control/interface encoding | Operand selectors, decoded branch/jump/result intent, producer metadata grouping and advance-permission wiring must agree at integration | Việt; preserve the semantic boundaries above and the parent's single ID decode; finalize before implementing the affected leaves or wrapper |

The first two rows are resolved by the accepted ALU contract. The last row
does not block the isolated ALU increment; it must be resolved before
implementing the affected leaves or wrapper.
No deadline pressure, selected module name or passing test substitutes for
these choices. Ordinary equivalent coding style is not a new architecture
decision. There is no RTL implementation delegation, new project milestone
acceptance or hardware-verification claim in this document.
