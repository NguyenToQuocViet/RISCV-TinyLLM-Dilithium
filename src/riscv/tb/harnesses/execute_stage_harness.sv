//------------------------------------------------------------------------------
// Module      : execute_stage_harness
// Description : Test-only EX registers and supplied pipeline-control stimulus.
// Author      : OpenAI Codex
// Date        : 2026-10-19
//------------------------------------------------------------------------------

module execute_stage_harness
    import riscv_pkg::*;
(
    input  logic                      clk,
    input  logic                      rst_n,
    input  logic                      hold,
    input  logic                      flush_ex,
    input  logic                      load_ex,
    input  logic                      instruction_valid,
    input  logic                      advance_allowed,
    input  logic [ADDR_WIDTH-1:0]     pc,
    input  logic [DATA_WIDTH-1:0]     imm,
    input  logic [4:0]                rs1_id,
    input  logic [4:0]                rs2_id,
    input  logic [DATA_WIDTH-1:0]     rs1_value,
    input  logic [DATA_WIDTH-1:0]     rs2_value,
    input  alu_src_a_t                alu_src_a,
    input  alu_src_b_t                alu_src_b,
    input  alu_op_t                   alu_op,
    input  branch_kind_t              branch_kind,
    input  control_flow_t             control_flow,
    input  result_src_t               result_src,
    input  logic [4:0]                mem_rd,
    input  logic [DATA_WIDTH-1:0]     mem_result,
    input  logic                      mem_valid,
    input  logic                      mem_reg_write,
    input  logic                      mem_wb_from_mem,
    input  logic [4:0]                wb_rd,
    input  logic [DATA_WIDTH-1:0]     wb_data,
    input  logic                      wb_valid,
    input  logic                      wb_reg_write,
    input  logic [31:0]               instruction_tag,
    input  logic [4:0]                instruction_rd,
    input  logic                      instruction_reg_write,
    input  logic                      instruction_mem_en,
    input  logic                      instruction_mem_write,
    output logic [DATA_WIDTH-1:0]     ex_result,
    output logic [DATA_WIDTH-1:0]     store_data,
    output logic                      redirect_fire,
    output logic [ADDR_WIDTH-1:0]     redirect_target,
    output logic                      current_valid,
    output logic [31:0]               current_tag,
    output logic                      captured_valid,
    output logic [31:0]               captured_tag,
    output logic [4:0]                captured_rd,
    output logic                      captured_reg_write,
    output logic                      captured_mem_en,
    output logic                      captured_mem_write,
    output logic [DATA_WIDTH-1:0]     captured_result,
    output logic [DATA_WIDTH-1:0]     captured_store_data
);
    // Synthetic producers are registered stimulus, not an implemented MEM/WB pipeline.
    logic [ADDR_WIDTH-1:0]     pc_q;
    logic [DATA_WIDTH-1:0]     imm_q;
    logic [4:0]                rs1_id_q;
    logic [4:0]                rs2_id_q;
    logic [DATA_WIDTH-1:0]     rs1_value_q;
    logic [DATA_WIDTH-1:0]     rs2_value_q;
    alu_src_a_t                alu_src_a_q;
    alu_src_b_t                alu_src_b_q;
    alu_op_t                   alu_op_q;
    branch_kind_t              branch_kind_q;
    control_flow_t             control_flow_q;
    result_src_t               result_src_q;
    logic [4:0]                mem_rd_q;
    logic [DATA_WIDTH-1:0]     mem_result_q;
    logic                      mem_valid_q;
    logic                      mem_reg_write_q;
    logic                      mem_wb_from_mem_q;
    logic [4:0]                wb_rd_q;
    logic [DATA_WIDTH-1:0]     wb_data_q;
    logic                      wb_valid_q;
    logic                      wb_reg_write_q;
    logic [31:0]               instruction_tag_q;
    logic [4:0]                instruction_rd_q;
    logic                      instruction_reg_write_q;
    logic                      instruction_mem_en_q;
    logic                      instruction_mem_write_q;
    logic instruction_valid_q;
    logic effective_advance;

    assign current_valid = instruction_valid_q;
    assign current_tag = instruction_tag_q;
    assign effective_advance = rst_n && !hold && !flush_ex && advance_allowed;

    execute_stage ex_stage (
        .pc                  (pc_q),
        .imm                 (imm_q),
        .rs1_id              (rs1_id_q),
        .rs2_id              (rs2_id_q),
        .rs1_value           (rs1_value_q),
        .rs2_value           (rs2_value_q),
        .alu_src_a           (alu_src_a_q),
        .alu_src_b           (alu_src_b_q),
        .alu_op              (alu_op_q),
        .branch_kind         (branch_kind_q),
        .control_flow        (control_flow_q),
        .result_src          (result_src_q),
        .mem_rd              (mem_rd_q),
        .mem_result          (mem_result_q),
        .mem_valid           (mem_valid_q),
        .mem_reg_write       (mem_reg_write_q),
        .mem_wb_from_mem     (mem_wb_from_mem_q),
        .wb_rd               (wb_rd_q),
        .wb_data             (wb_data_q),
        .wb_valid            (wb_valid_q),
        .wb_reg_write        (wb_reg_write_q),
        .instruction_valid   (instruction_valid_q),
        .advance_allowed     (effective_advance),
        .ex_result           (ex_result),
        .store_data          (store_data),
        .redirect_fire       (redirect_fire),
        .redirect_target     (redirect_target)
    );

    // Reset only liveness. Payload remains unreset, as in the BASE contract.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            instruction_valid_q <= 1'b0;
            mem_valid_q <= 1'b0;
            wb_valid_q <= 1'b0;
            captured_valid <= 1'b0;
        end
        else if (!hold && advance_allowed) begin
            captured_valid <= instruction_valid_q && !flush_ex;
            if (instruction_valid_q && !flush_ex) begin
                captured_result <= ex_result;
                captured_store_data <= store_data;
                captured_tag <= instruction_tag_q;
                captured_rd <= instruction_rd_q;
                captured_reg_write <= instruction_reg_write_q;
                captured_mem_en <= instruction_mem_en_q;
                captured_mem_write <= instruction_mem_write_q;
            end

            instruction_valid_q <= load_ex && instruction_valid && !flush_ex;
            if (load_ex) begin
                pc_q <= pc;
                imm_q <= imm;
                rs1_id_q <= rs1_id;
                rs2_id_q <= rs2_id;
                rs1_value_q <= rs1_value;
                rs2_value_q <= rs2_value;
                alu_src_a_q <= alu_src_a;
                alu_src_b_q <= alu_src_b;
                alu_op_q <= alu_op;
                branch_kind_q <= branch_kind;
                control_flow_q <= control_flow;
                result_src_q <= result_src;
                instruction_tag_q <= instruction_tag;
                instruction_rd_q <= instruction_rd;
                instruction_reg_write_q <= instruction_reg_write;
                instruction_mem_en_q <= instruction_mem_en;
                instruction_mem_write_q <= instruction_mem_write;
            end

            mem_rd_q <= mem_rd;
            mem_result_q <= mem_result;
            mem_valid_q <= mem_valid;
            mem_reg_write_q <= mem_reg_write;
            mem_wb_from_mem_q <= mem_wb_from_mem;
            wb_rd_q <= wb_rd;
            wb_data_q <= wb_data;
            wb_valid_q <= wb_valid;
            wb_reg_write_q <= wb_reg_write;
        end
    end
endmodule
