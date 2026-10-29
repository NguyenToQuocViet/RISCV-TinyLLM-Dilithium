//------------------------------------------------------------------------------
// Module      : immediate_generator
// Description : Reconstruct the canonical immediate from the instruction word.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-29
//------------------------------------------------------------------------------

module immediate_generator
    import riscv_pkg::*;
(
    input logic [INSTR_WIDTH-1:0] instruction,
    output logic [DATA_WIDTH-1:0] imm
);
    logic [4:0] opc;
    assign opc = instruction[6:2];

    always_comb begin : imm_gen
        //default
        imm = '0;

        case (opc)
            //I-Type
            OPC_OP_IMM, OPC_LOAD, OPC_JALR: begin
                imm = {{20{instruction[31]}}, instruction[31:20]};
            end

            //S-Type
            OPC_STORE: begin
                imm = {{20{instruction[31]}}, instruction[31:25], instruction[11:7]};
            end

            //B-Type
            OPC_BRANCH: begin
                imm = {{19{instruction[31]}}, instruction[31], instruction[7], instruction[30:25], instruction[11:8], 1'b0};
            end

            //U-Type
            OPC_LUI, OPC_AUIPC: begin
                imm = {instruction[31:12], 12'd0};
            end

            //J-Type
            OPC_JAL: begin
                imm = {{11{instruction[31]}}, instruction[31], instruction[19:12], instruction[20], instruction[30:21], 1'b0};
            end

            default: begin
                imm = '0;
            end
        endcase
    end

endmodule
