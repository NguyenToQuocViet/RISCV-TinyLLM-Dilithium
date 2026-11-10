//------------------------------------------------------------------------------
// Module      : core_top
// Description : Wires the five stages, the four pipeline registers and the
//               hazard control unit into the BASE core.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-10
//------------------------------------------------------------------------------

module core_top
    import riscv_pkg::*;
#(
    parameter int CORE_PROFILE = 0  //0=BASE, 1=BASE_CI, 2=BASE_CI_IRQ
)
(
    //system
    input  logic clk,
    input  logic rst_n,

    //instruction OBI
    input  logic                    instr_gnt,
    input  logic                    instr_rvalid,
    input  logic [INSTR_WIDTH-1:0]  instr_rdata,
    output logic                    instr_req,
    output logic [ADDR_WIDTH-1:0]   instr_addr,
    output logic                    instr_we,
    output logic [3:0]              instr_be,
    output logic [DATA_WIDTH-1:0]   instr_wdata,
    output logic                    instr_rready,

    //data OBI
    input  logic                  data_gnt,
    input  logic                  data_rvalid,
    input  logic [DATA_WIDTH-1:0] data_rdata,
    output logic                  data_req,
    output logic [ADDR_WIDTH-1:0] data_addr,
    output logic                  data_we,
    output logic [3:0]            data_be,
    output logic [DATA_WIDTH-1:0] data_wdata,
    output logic                  data_rready,

    //CI manager
    output logic        ci_cmd_valid,
    output logic [1:0]  ci_cmd_op,
    output logic [31:0] ci_cmd_target,
    output logic [31:0] ci_cmd_desc,
    input  logic        ci_cmd_ready,
    input  logic [31:0] ci_cmd_result,

    //interrupt source
    input  logic irq_external
);
    localparam int PROFILE_BASE = 0;

    //only BASE is implemented, any other profile fails elaboration
    if (CORE_PROFILE != PROFILE_BASE) begin : g_profile_check
        $fatal(1, "core_top: CORE_PROFILE %0d is not implemented, only BASE (0)", CORE_PROFILE);
    end

    //IF stage to IF/ID register
    logic                   fetch_valid;
    logic [ADDR_WIDTH-1:0]  fetch_pc;
    logic [INSTR_WIDTH-1:0] fetch_instruction;

    //IF/ID register to ID stage and ID/EX register
    logic                   if_id_reg_valid;
    logic [ADDR_WIDTH-1:0]  if_id_reg_pc;
    logic [INSTR_WIDTH-1:0] if_id_reg_instruction;

    //ID stage to HCU and ID/EX register
    logic [4:0]             rs1_id;
    logic [4:0]             rs2_id;
    logic                   rs1_used;
    logic                   rs2_used;
    logic [4:0]             rd;
    logic [DATA_WIDTH-1:0]  rs1_value;
    logic [DATA_WIDTH-1:0]  rs2_value;
    logic [DATA_WIDTH-1:0]  imm;
    logic                   reg_write;
    alu_op_t                alu_op;
    alu_src_a_t             alu_src_a;
    alu_src_b_t             alu_src_b;
    result_src_t            result_src;
    branch_kind_t           branch_kind;
    control_flow_t          control_flow;
    logic                   mem_en;
    logic                   mem_write;
    mem_type_t              mem_type;
    logic                   wb_src;

    //ID/EX register to EX stage, HCU and EX/MEM register
    logic                   id_ex_reg_valid;
    logic [ADDR_WIDTH-1:0]  id_ex_reg_pc;
    logic [4:0]             id_ex_reg_rs1_id;
    logic [4:0]             id_ex_reg_rs2_id;
    logic [DATA_WIDTH-1:0]  id_ex_reg_rs1_value;
    logic [DATA_WIDTH-1:0]  id_ex_reg_rs2_value;
    logic [DATA_WIDTH-1:0]  id_ex_reg_imm;
    alu_op_t                id_ex_reg_alu_op;
    alu_src_a_t             id_ex_reg_alu_src_a;
    alu_src_b_t             id_ex_reg_alu_src_b;
    result_src_t            id_ex_reg_result_src;
    branch_kind_t           id_ex_reg_branch_kind;
    control_flow_t          id_ex_reg_control_flow;
    logic [4:0]             id_ex_reg_rd;
    logic                   id_ex_reg_reg_write;
    logic                   id_ex_reg_mem_en;
    logic                   id_ex_reg_mem_write;
    mem_type_t              id_ex_reg_mem_type;
    logic                   id_ex_reg_wb_src;

    //EX stage to EX/MEM register and IF stage
    logic [DATA_WIDTH-1:0]  ex_result;
    logic [DATA_WIDTH-1:0]  store_data;
    logic                   redirect_fire;
    logic [ADDR_WIDTH-1:0]  redirect_target;

    //EX/MEM register to MEM stage, EX stage and MEM/WB register
    logic                   ex_mem_reg_valid;
    logic [DATA_WIDTH-1:0]  ex_mem_reg_ex_result;
    logic [DATA_WIDTH-1:0]  ex_mem_reg_store_data;
    logic [4:0]             ex_mem_reg_rd;
    logic                   ex_mem_reg_reg_write;
    logic                   ex_mem_reg_mem_en;
    logic                   ex_mem_reg_mem_write;
    mem_type_t              ex_mem_reg_mem_type;
    logic                   ex_mem_reg_wb_src;

    //MEM stage to MEM/WB register and HCU
    logic [DATA_WIDTH-1:0]  load_result;
    logic                   mem_wait;

    //MEM/WB register to WB stage, ID stage and EX stage
    logic                   mem_wb_reg_valid;
    logic [DATA_WIDTH-1:0]  mem_wb_reg_ex_result;
    logic [DATA_WIDTH-1:0]  mem_wb_reg_load_result;
    logic                   mem_wb_reg_wb_src;
    logic [4:0]             mem_wb_reg_rd;
    logic                   mem_wb_reg_reg_write;

    //WB stage to ID stage and EX stage
    logic [DATA_WIDTH-1:0]  wb_data;
    logic                   rf_write_fire;

    //HCU controls
    logic                   advance_allowed;
    logic                   fetch_accept;
    logic                   if_id_stall;
    logic                   if_id_flush;
    logic                   id_ex_stall;
    logic                   id_ex_flush;
    logic                   ex_mem_stall;
    logic                   mem_wb_stall;

    //constants: EX/MEM and MEM/WB never flush, BASE has no CI command
    logic                   ex_mem_flush;
    logic                   mem_wb_flush;
    assign ex_mem_flush  = 1'b0;
    assign mem_wb_flush  = 1'b0;
    assign ci_cmd_valid  = 1'b0;
    assign ci_cmd_op     = 2'b00;
    assign ci_cmd_target = 32'h0000_0000;
    assign ci_cmd_desc   = 32'h0000_0000;

    //BASE gives these inputs no effect
    logic unused_inputs;
    assign unused_inputs = ^{ci_cmd_ready, ci_cmd_result, irq_external};

    //IF
    fetch_stage if_stage (
        .clk                (clk),
        .rst_n              (rst_n),

        .fetch_accept       (fetch_accept),
        .redirect_fire      (redirect_fire),
        .redirect_target    (redirect_target),

        .gnt                (instr_gnt),
        .rvalid             (instr_rvalid),
        .rdata              (instr_rdata),
        .req                (instr_req),
        .addr               (instr_addr),
        .rready             (instr_rready),
        .we                 (instr_we),
        .be                 (instr_be),
        .wdata              (instr_wdata),

        .fetch_valid        (fetch_valid),
        .fetch_pc           (fetch_pc),
        .fetch_instruction  (fetch_instruction)
    );

    if_id_pipeline if_id_reg (
        .clk                (clk),
        .rst_n              (rst_n),

        .stall              (if_id_stall),
        .flush              (if_id_flush),

        .valid_i            (fetch_valid),
        .pc_i               (fetch_pc),
        .instruction_i      (fetch_instruction),

        .valid_o            (if_id_reg_valid),
        .pc_o               (if_id_reg_pc),
        .instruction_o      (if_id_reg_instruction)
    );

    //ID
    decode_stage id_stage (
        .clk                (clk),

        .instruction        (if_id_reg_instruction),

        .rf_write_fire      (rf_write_fire),
        .wb_rd              (mem_wb_reg_rd),
        .wb_data            (wb_data),

        .rs1_id             (rs1_id),
        .rs2_id             (rs2_id),
        .rd                 (rd),
        .rs1_value          (rs1_value),
        .rs2_value          (rs2_value),
        .rs1_used           (rs1_used),
        .rs2_used           (rs2_used),

        .imm                (imm),

        .reg_write          (reg_write),
        .mem_en             (mem_en),
        .control_flow       (control_flow),
        .mem_write          (mem_write),
        .mem_type           (mem_type),
        .wb_src             (wb_src),
        .alu_op             (alu_op),
        .alu_src_a          (alu_src_a),
        .alu_src_b          (alu_src_b),
        .branch_kind        (branch_kind),
        .result_src         (result_src)
    );

    id_ex_pipeline id_ex_reg (
        .clk                (clk),
        .rst_n              (rst_n),

        .stall              (id_ex_stall),
        .flush              (id_ex_flush),

        .valid_i            (if_id_reg_valid),
        .pc_i               (if_id_reg_pc),
        .rs1_id_i           (rs1_id),
        .rs2_id_i           (rs2_id),
        .rs1_value_i        (rs1_value),
        .rs2_value_i        (rs2_value),
        .imm_i              (imm),
        .rd_i               (rd),
        .reg_write_i        (reg_write),
        .alu_op_i           (alu_op),
        .alu_src_a_i        (alu_src_a),
        .alu_src_b_i        (alu_src_b),
        .result_src_i       (result_src),
        .branch_kind_i      (branch_kind),
        .control_flow_i     (control_flow),
        .mem_en_i           (mem_en),
        .mem_write_i        (mem_write),
        .mem_type_i         (mem_type),
        .wb_src_i           (wb_src),

        .valid_o            (id_ex_reg_valid),
        .pc_o               (id_ex_reg_pc),
        .rs1_id_o           (id_ex_reg_rs1_id),
        .rs2_id_o           (id_ex_reg_rs2_id),
        .rs1_value_o        (id_ex_reg_rs1_value),
        .rs2_value_o        (id_ex_reg_rs2_value),
        .imm_o              (id_ex_reg_imm),
        .rd_o               (id_ex_reg_rd),
        .reg_write_o        (id_ex_reg_reg_write),
        .alu_op_o           (id_ex_reg_alu_op),
        .alu_src_a_o        (id_ex_reg_alu_src_a),
        .alu_src_b_o        (id_ex_reg_alu_src_b),
        .result_src_o       (id_ex_reg_result_src),
        .branch_kind_o      (id_ex_reg_branch_kind),
        .control_flow_o     (id_ex_reg_control_flow),
        .mem_en_o           (id_ex_reg_mem_en),
        .mem_write_o        (id_ex_reg_mem_write),
        .mem_type_o         (id_ex_reg_mem_type),
        .wb_src_o           (id_ex_reg_wb_src)
    );

    //EX
    execute_stage ex_stage (
        .pc                 (id_ex_reg_pc),
        .imm                (id_ex_reg_imm),
        .rs1_id             (id_ex_reg_rs1_id),
        .rs2_id             (id_ex_reg_rs2_id),
        .rs1_value          (id_ex_reg_rs1_value),
        .rs2_value          (id_ex_reg_rs2_value),
        .alu_src_a          (id_ex_reg_alu_src_a),
        .alu_src_b          (id_ex_reg_alu_src_b),
        .alu_op             (id_ex_reg_alu_op),
        .branch_kind        (id_ex_reg_branch_kind),
        .control_flow       (id_ex_reg_control_flow),
        .result_src         (id_ex_reg_result_src),
        .instruction_valid  (id_ex_reg_valid),
        .advance_allowed    (advance_allowed),

        .mem_rd             (ex_mem_reg_rd),
        .mem_result         (ex_mem_reg_ex_result),
        .mem_valid          (ex_mem_reg_valid),
        .mem_reg_write      (ex_mem_reg_reg_write),
        .mem_wb_src         (ex_mem_reg_wb_src),

        .wb_rd              (mem_wb_reg_rd),
        .wb_data            (wb_data),
        .wb_valid           (mem_wb_reg_valid),
        .wb_reg_write       (mem_wb_reg_reg_write),

        .ex_result          (ex_result),
        .store_data         (store_data),
        .redirect_fire      (redirect_fire),
        .redirect_target    (redirect_target)
    );

    ex_mem_pipeline ex_mem_reg (
        .clk                (clk),
        .rst_n              (rst_n),

        .stall              (ex_mem_stall),
        .flush              (ex_mem_flush),

        .valid_i            (id_ex_reg_valid),
        .ex_result_i        (ex_result),
        .store_data_i       (store_data),
        .rd_i               (id_ex_reg_rd),
        .reg_write_i        (id_ex_reg_reg_write),
        .mem_en_i           (id_ex_reg_mem_en),
        .mem_write_i        (id_ex_reg_mem_write),
        .mem_type_i         (id_ex_reg_mem_type),
        .wb_src_i           (id_ex_reg_wb_src),

        .valid_o            (ex_mem_reg_valid),
        .ex_result_o        (ex_mem_reg_ex_result),
        .store_data_o       (ex_mem_reg_store_data),
        .rd_o               (ex_mem_reg_rd),
        .reg_write_o        (ex_mem_reg_reg_write),
        .mem_en_o           (ex_mem_reg_mem_en),
        .mem_write_o        (ex_mem_reg_mem_write),
        .mem_type_o         (ex_mem_reg_mem_type),
        .wb_src_o           (ex_mem_reg_wb_src)
    );

    //MEM
    memory_stage mem_stage (
        .clk                (clk),
        .rst_n              (rst_n),

        .instruction_valid  (ex_mem_reg_valid),
        .ex_result          (ex_mem_reg_ex_result),
        .store_data         (ex_mem_reg_store_data),
        .mem_en             (ex_mem_reg_mem_en),
        .mem_write          (ex_mem_reg_mem_write),
        .mem_type           (ex_mem_reg_mem_type),

        .load_result        (load_result),
        .mem_wait           (mem_wait),

        .gnt                (data_gnt),
        .rvalid             (data_rvalid),
        .rdata              (data_rdata),
        .req                (data_req),
        .addr               (data_addr),
        .wdata              (data_wdata),
        .we                 (data_we),
        .be                 (data_be),
        .rready             (data_rready)
    );

    mem_wb_pipeline mem_wb_reg (
        .clk                (clk),
        .rst_n              (rst_n),

        .stall              (mem_wb_stall),
        .flush              (mem_wb_flush),

        .valid_i            (ex_mem_reg_valid),
        .ex_result_i        (ex_mem_reg_ex_result),
        .load_result_i      (load_result),
        .wb_src_i           (ex_mem_reg_wb_src),
        .rd_i               (ex_mem_reg_rd),
        .reg_write_i        (ex_mem_reg_reg_write),

        .valid_o            (mem_wb_reg_valid),
        .ex_result_o        (mem_wb_reg_ex_result),
        .load_result_o      (mem_wb_reg_load_result),
        .wb_src_o           (mem_wb_reg_wb_src),
        .rd_o               (mem_wb_reg_rd),
        .reg_write_o        (mem_wb_reg_reg_write)
    );

    //WB
    writeback_stage wb_stage (
        .ex_result          (mem_wb_reg_ex_result),
        .load_result        (mem_wb_reg_load_result),
        .rd                 (mem_wb_reg_rd),
        .wb_src             (mem_wb_reg_wb_src),
        .reg_write          (mem_wb_reg_reg_write),
        .instruction_valid  (mem_wb_reg_valid),
        .advance_allowed    (advance_allowed),

        .wb_data            (wb_data),
        .rf_write_fire      (rf_write_fire)
    );

    //hazard control
    hazard_control_unit hcu (
        .rst_n              (rst_n),

        .mem_wait           (mem_wait),
        .redirect_fire      (redirect_fire),

        .id_valid           (if_id_reg_valid),
        .id_rs1_id          (rs1_id),
        .id_rs2_id          (rs2_id),
        .id_rs1_used        (rs1_used),
        .id_rs2_used        (rs2_used),

        .ex_valid           (id_ex_reg_valid),
        .ex_mem_en          (id_ex_reg_mem_en),
        .ex_mem_write       (id_ex_reg_mem_write),
        .ex_rd              (id_ex_reg_rd),

        .advance_allowed    (advance_allowed),
        .fetch_accept       (fetch_accept),
        .if_id_stall        (if_id_stall),
        .if_id_flush        (if_id_flush),
        .id_ex_stall        (id_ex_stall),
        .id_ex_flush        (id_ex_flush),
        .ex_mem_stall       (ex_mem_stall),
        .mem_wb_stall       (mem_wb_stall)
    );
endmodule
