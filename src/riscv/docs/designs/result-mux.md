# Result Mux — Block Design

**Status:** Accepted by Việt on 2026-10-19.
**Revision:** RM D2 / 2026-10-19; width clarification accepted by Việt.
**Owner:** Viet Nguyen To Quoc.
**Parent:** [EX stage](execute-stage.md#46-result-mux).
**Mapping:** Planned module `result_mux` in `src/riscv/rtl/result_mux.sv`;
instance `ex_result_mux` in `execute_stage`.

## 1. Purpose and boundary

Select the EX result from the ALU result and the jump-link value supplied by
[link_adder](link-adder.md). The output feeds the core-owned EX/MEM boundary.

Instruction decode, link calculation, jump-target handling, load-response
formatting, final WB selection and architectural side-effect control belong
outside this block.

## 2. Interface, timing and state

| Port | Direction | Type / width | Meaning |
| --- | --- | --- | --- |
| `alu_result` | Input | Unsigned `logic [DATA_WIDTH-1:0]` | ALU result or effective byte address |
| `pc_plus_4` | Input | Unsigned `logic [ADDR_WIDTH-1:0]` | Jump-link address |
| `result_src` | Input | `riscv_pkg::result_src_t`, `enum logic [0:0]` (planned) | Decoded EX result source |
| `result` | Output | `logic [DATA_WIDTH-1:0]` | Selected EX result |

Link selection crosses from the address domain to the register/datapath domain
under the parent's [width contract](execute-stage.md#width-domains).
All bits are preserved; unequal-width conversion is not supported.

The shared selector type belongs in [riscv_pkg](../../rtl/riscv_pkg.sv).
ID produces `result_src`; ID/EX carries it to this leaf. It is separate from
`wb_src`, which controls final writeback selection outside EX.

The block is combinational: no clock, reset, storage, handshake or stall
ownership. The output follows current inputs after combinational settling.
At EX integration, `result` supplies `ex_result`; parent pipeline control
owns capture, hold and suppression of side effects for invalid entries.

## 3. Selection contract

| `result_src` | Code | `result` |
| --- | --- | --- |
| `RESULT_ALU` | `1'b0` | All 32 bits of `alu_result`, unchanged |
| `RESULT_PC_PLUS_4` | `1'b1` | All 32 bits of `pc_plus_4`, unchanged |

ID supplies decoded selection intent: JAL/JALR select `pc_plus_4` even when
their destination is x0. Other instructions requiring an EX result select
`alu_result`, including loads and stores whose EX result is the effective
byte address. Branches and FENCE require no meaningful EX result; the leaf
still follows its selector and does not force zero for those instructions.

Both binary selector values are defined. Selection performs no arithmetic,
signed conversion, alignment correction or JALR target masking. The jump target
remains separate from the link value.

## 4. Input validity

The specified input domain contains only 0/1. X/Z behavior is outside this
contract's guaranteed domain, consistent with the pipeline's accepted policy.
