//------------------------------------------------------------------------------
// Module      : id_ex_pipeline
// Description : ID/EX pipeline register for decoded operands and control.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-06
//------------------------------------------------------------------------------

module id_ex_pipeline
    import riscv_pkg::*;
(
    //system interface
    input logic clk,
    input logic rst_n,

    //hcu interface
    input logic stall,
    input logic flush,

    //id interface
    input logic valid_i,
    input logic [ADDR_WIDTH-1:0] pc_i,

    input logic [4:0] rs1_id_i,
    input logic [4:0] rs2_id_i,
    input logic [DATA_WIDTH-1:0] rs1_value_i,
    input logic [DATA_WIDTH-1:0] rs2_value_i,

    input logic [DATA_WIDTH-1:0] imm_i,

    input logic [4:0] rd_i,
    input logic reg_write_i,

    input alu_op_t alu_op_i,
    input alu_src_a_t alu_src_a_i,
    input alu_src_b_t alu_src_b_i,
    input result_src_t result_src_i,

    input branch_kind_t branch_kind_i,
    input control_flow_t control_flow_i,

    input logic mem_en_i,
    input logic mem_write_i,
    input mem_type_t mem_type_i,

    input logic wb_src_i,

    //ex interface
    output logic valid_o,
    output logic [ADDR_WIDTH-1:0] pc_o,

    output logic [4:0] rs1_id_o,
    output logic [4:0] rs2_id_o,
    output logic [DATA_WIDTH-1:0] rs1_value_o,
    output logic [DATA_WIDTH-1:0] rs2_value_o,

    output logic [DATA_WIDTH-1:0] imm_o,

    output logic [4:0] rd_o,
    output logic reg_write_o,

    output alu_op_t alu_op_o,
    output alu_src_a_t alu_src_a_o,
    output alu_src_b_t alu_src_b_o,
    output result_src_t result_src_o,

    output branch_kind_t branch_kind_o,
    output control_flow_t control_flow_o,

    output logic mem_en_o,
    output logic mem_write_o,
    output mem_type_t mem_type_o,

    output logic wb_src_o
);
    logic capture;

    assign capture = valid_i && !stall && !flush;

    always_ff @(posedge clk or negedge rst_n) begin : valid_reg
        if (!rst_n) begin
            valid_o <= 1'b0;
        end else if (flush) begin
            valid_o <= 1'b0;
        end else if (stall) begin
            valid_o <= valid_o; //hold
        end else begin
            valid_o <= valid_i;
        end
    end

    //payload has no reset, PR-D1
    always_ff @(posedge clk) begin : payload_reg
        if (capture) begin
            pc_o           <= pc_i;
            rs1_id_o       <= rs1_id_i;
            rs2_id_o       <= rs2_id_i;
            rs1_value_o    <= rs1_value_i;
            rs2_value_o    <= rs2_value_i;
            imm_o          <= imm_i;
            rd_o           <= rd_i;
            reg_write_o    <= reg_write_i;
            alu_op_o       <= alu_op_i;
            alu_src_a_o    <= alu_src_a_i;
            alu_src_b_o    <= alu_src_b_i;
            result_src_o   <= result_src_i;
            branch_kind_o  <= branch_kind_i;
            control_flow_o <= control_flow_i;
            mem_en_o       <= mem_en_i;
            mem_write_o    <= mem_write_i;
            mem_type_o     <= mem_type_i;
            wb_src_o       <= wb_src_i;
        end
    end
endmodule
