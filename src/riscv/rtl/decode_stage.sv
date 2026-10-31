//------------------------------------------------------------------------------
// Module      : decode_stage
// Description : Structural ID stage: register file, immediate generator and
//               control unit driven from one instruction word.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-31
//------------------------------------------------------------------------------

module decode_stage
    import riscv_pkg::*;
(
    //system
    input logic clk,

    //IF/ID interface
    input logic [INSTR_WIDTH-1:0] instruction,

    //WB interface
    input logic rf_write_fire,
    input logic [4:0] wb_rd,
    input logic [DATA_WIDTH-1:0] wb_data,

    //register fields and values
    output logic [4:0] rs1_id,
    output logic [4:0] rs2_id,
    output logic [4:0] rd,
    output logic [DATA_WIDTH-1:0] rs1_value,
    output logic [DATA_WIDTH-1:0] rs2_value,
    output logic rs1_used,
    output logic rs2_used,

    //immediate
    output logic [DATA_WIDTH-1:0] imm,

    //control to EX/MEM/WB
    output logic reg_write,
    output logic mem_en,
    output control_flow_t control_flow,
    output logic mem_write,
    output mem_type_t mem_type,
    output logic wb_src,
    output alu_op_t alu_op,
    output alu_src_a_t alu_src_a,
    output alu_src_b_t alu_src_b,
    output branch_kind_t branch_kind,
    output result_src_t result_src
);
    //raw field extraction
    assign rs1_id = instruction[19:15];
    assign rs2_id = instruction[24:20];
    assign rd     = instruction[11:7];

    register_file id_register_file (
        .clk            (clk),

        .rs1_id         (rs1_id),
        .rs2_id         (rs2_id),

        .rf_write_fire  (rf_write_fire),
        .wb_rd          (wb_rd),
        .wb_data        (wb_data),

        .rs1_value      (rs1_value),
        .rs2_value      (rs2_value)
    );

    immediate_generator id_immediate_generator (
        .instruction    (instruction),
        .imm            (imm)
    );

    control_unit id_control_unit (
        .instruction    (instruction),

        .rs1_used       (rs1_used),
        .rs2_used       (rs2_used),

        .alu_src_a      (alu_src_a),
        .alu_src_b      (alu_src_b),
        .alu_op         (alu_op),
        .branch_kind    (branch_kind),
        .result_src     (result_src),
        .control_flow   (control_flow),

        .mem_type       (mem_type),
        .mem_write      (mem_write),
        .mem_en         (mem_en),

        .reg_write      (reg_write),
        .wb_src         (wb_src)
    );
endmodule
