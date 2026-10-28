//------------------------------------------------------------------------------
// Module      : execute_stage
// Description : Combinational execution, forwarding and control-flow resolution.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-19
//------------------------------------------------------------------------------

module execute_stage
    import riscv_pkg::*;
(
    input logic [ADDR_WIDTH-1:0] pc,
    input logic [DATA_WIDTH-1:0] imm,

    input logic [4:0] rs1_id,
    input logic [4:0] rs2_id,

    input logic [DATA_WIDTH-1:0] rs1_value,
    input logic [DATA_WIDTH-1:0] rs2_value,

    input alu_src_a_t alu_src_a,
    input alu_src_b_t alu_src_b,
    input alu_op_t alu_op,
    input branch_kind_t branch_kind,
    input control_flow_t control_flow,
    input result_src_t result_src,

    input logic instruction_valid,
    input logic advance_allowed,

    input logic [4:0] mem_rd,
    input logic [DATA_WIDTH-1:0] mem_result,
    input logic mem_valid,
    input logic mem_reg_write,
    input logic mem_wb_src,

    input logic [4:0] wb_rd,
    input logic [DATA_WIDTH-1:0] wb_data,
    input logic wb_valid,
    input logic wb_reg_write,

    output logic [DATA_WIDTH-1:0] ex_result,
    output logic [DATA_WIDTH-1:0] store_data,

    output logic redirect_fire,
    output logic [ADDR_WIDTH-1:0] redirect_target
);
    logic [DATA_WIDTH-1:0] fwd_rs1;
    logic [DATA_WIDTH-1:0] fwd_rs2;

    forwarding_unit ex_forwarding (
        .rs1_id         (rs1_id),
        .rs2_id         (rs2_id),

        .rs1_value      (rs1_value),
        .rs2_value      (rs2_value),

        .mem_rd         (mem_rd),
        .mem_result     (mem_result),
        .mem_valid      (mem_valid),
        .mem_reg_write  (mem_reg_write),
        .mem_wb_src     (mem_wb_src),

        .wb_rd          (wb_rd),
        .wb_data        (wb_data),
        .wb_valid       (wb_valid),
        .wb_reg_write   (wb_reg_write),

        .fwd_rs1        (fwd_rs1),
        .fwd_rs2        (fwd_rs2)
    );

    logic [DATA_WIDTH-1:0] operand_a;
    logic [DATA_WIDTH-1:0] operand_b;

    operand_mux ex_operand_mux (
        .rs1_value  (fwd_rs1),
        .rs2_value  (fwd_rs2),

        .pc         (pc),
        .imm        (imm),

        .alu_src_a  (alu_src_a),
        .alu_src_b  (alu_src_b),

        .operand_a  (operand_a),
        .operand_b  (operand_b)
    );

    logic [DATA_WIDTH-1:0] alu_result;

    alu ex_alu (
        .operand_a  (operand_a),
        .operand_b  (operand_b),
        .alu_op     (alu_op),

        .alu_result (alu_result)
    );

    logic [ADDR_WIDTH-1:0] pc_plus_4;

    link_adder ex_link_adder (
        .pc         (pc),
        .pc_plus_4  (pc_plus_4)
    );

    result_mux ex_result_mux (
        .alu_result (alu_result),
        .pc_plus_4  (pc_plus_4),
        .result_src (result_src),

        .result     (ex_result)     //ex_result
    );

    assign store_data = fwd_rs2;    //store_data

    logic branch_condition;

    branch_comparator ex_branch_comparator (
        .operand_a          (fwd_rs1),      //sau fwd, truoc op-mux, lay reg value
        .operand_b          (fwd_rs2),      //sau fwd, truoc op-mux, lay reg value
        .branch_kind        (branch_kind),

        .branch_condition   (branch_condition)
    );

    redirect_unit ex_redirect (
        .alu_result         (alu_result),
        .branch_condition   (branch_condition),
        .control_flow       (control_flow),

        .advance_allowed    (advance_allowed),
        .instruction_valid  (instruction_valid),

        .redirect_fire      (redirect_fire),    //redirect_fire
        .redirect_target    (redirect_target)   //redirect_target
    );
endmodule
