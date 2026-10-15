# ALU — Block Design

**Status:** Accepted by Việt on 2026-10-15.
**Revision:** ALU D3 / 2026-10-15.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [EX stage](execute-stage.md#43-alu),
[BASE execution semantics](5-stage-baseline-core.md#ex-computation-contract).
**Mapping:** [alu](../../rtl/alu.sv), instance `ex_alu` in `execute_stage`;
shared type in [riscv_pkg](../../rtl/riscv_pkg.sv).

## 1. Purpose and boundary

Compute a 32-bit arithmetic, logic, shift or comparison result. ID supplies
semantic control; `operand_mux` supplies operands after forwarding. The result
feeds `result_mux` and, for target calculation, `redirect_unit`.

Instruction decode, forwarding, operand selection, branch predicates, jump-link
calculation, JALR target masking and architectural side-effect control belong
outside this block, as defined by the parent EX contract.

## 2. Interface, timing and state

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `operand_a` | Input | Unsigned 32-bit logic vector | Operand A |
| `operand_b` | Input | Unsigned 32-bit logic vector | Operand B |
| `alu_op` | Input | `riscv_pkg::alu_op_t`, `enum logic [3:0]` | Operation selector |
| `alu_result` | Output | 32-bit logic vector | Selected result |

`riscv_pkg::DATA_WIDTH` is fixed at 32 for this design. The ALU is combinational:
no clock, reset, storage, handshake, stall ownership or registered latency.
The output follows current inputs after combinational settling, without retaining
an earlier result. Parent pipeline control determines when it is used.

## 3. Operation contract

| Selector | Code | Required result |
| --- | --- | --- |
| `ALU_ADD` | `4'h0` | ADD(A, B), low 32 bits |
| `ALU_SUB` | `4'h1` | SUB(A, B), subtract B from A, low 32 bits |
| `ALU_AND` | `4'h2` | Bitwise AND(A, B) |
| `ALU_OR` | `4'h3` | Bitwise OR(A, B) |
| `ALU_XOR` | `4'h4` | Bitwise XOR(A, B) |
| `ALU_SLL` | `4'h5` | Shift A left by B[4:0], zero fill, low 32 bits |
| `ALU_SRL` | `4'h6` | Shift A right by B[4:0], zero fill |
| `ALU_SRA` | `4'h7` | Shift A right by B[4:0], fill with A[31] |
| `ALU_SLT` | `4'h8` | 32-bit one if signed A is less than signed B, otherwise zero |
| `ALU_SLTU` | `4'h9` | 32-bit one if unsigned A is less than unsigned B, otherwise zero |

ADD/SUB wrap modulo 2^32 with no carry/overflow output or trap. Signed operations
interpret operands as two's-complement values. B[31:5] cannot affect shifts.
There are exactly ten operations; no dedicated FENCE, PASS or link operation.

Shared add/subtract, comparison or shift hardware is not required. Resource
mapping is left to synthesis. Revisit organization if timing evidence shows the
ALU path limits EX; such changes preserve this behavioral interface.

## 4. Input validity and exceptional conditions

The specified input domain contains only 0/1. X/Z behavior is outside this
contract's guaranteed domain.

All six unassigned binary selector codes, `4'hA` through `4'hF`, return
`32'hDEAD_BEEF` independently of the operands. This is a diagnostic fallback,
not an additional operation or a unique error signature. No error port or CPU
trap is introduced.

Live EX instruction control must select a defined operation. An invalid pipeline
entry may carry arbitrary payload; its result cannot authorize side effects.
