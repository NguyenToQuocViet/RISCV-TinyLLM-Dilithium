//------------------------------------------------------------------------------
// Module      : hazard_control_unit
// Description : Detects load-use and drives pipeline stall, flush, advance and
//               fetch acceptance from the MEM wait and EX redirect events.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-05
//------------------------------------------------------------------------------

module hazard_control_unit
    import riscv_pkg::*;
(
    input logic rst_n,

    input logic mem_wait,
    input logic redirect_fire,

    input logic id_valid,
    input logic [4:0] id_rs1_id,
    input logic [4:0] id_rs2_id,
    input logic id_rs1_used,
    input logic id_rs2_used,
    input logic ex_valid,
    input logic ex_mem_en,
    input logic ex_mem_write,
    input logic [4:0] ex_rd,

    output logic advance_allowed,
    output logic fetch_accept,

    output logic if_id_stall,
    output logic if_id_flush,
    output logic id_ex_stall,
    output logic id_ex_flush,
    output logic ex_mem_stall,
    output logic mem_wb_stall
);
    logic ex_load;      //valid load in EX with a nonzero destination
    logic rs1_match;    //ID reads the load destination through rs1
    logic rs2_match;    //ID reads the load destination through rs2
    logic load_use;

    assign ex_load   = ex_valid && ex_mem_en && !ex_mem_write && (ex_rd != 5'd0);
    assign rs1_match = id_rs1_used && (id_rs1_id == ex_rd);
    assign rs2_match = id_rs2_used && (id_rs2_id == ex_rd);
    assign load_use  = id_valid && ex_load && (rs1_match || rs2_match);

    assign mem_wb_stall    = mem_wait;
    assign ex_mem_stall    = mem_wait;
    assign id_ex_stall     = mem_wait;
    assign if_id_stall     = mem_wait || load_use;
    assign if_id_flush     = redirect_fire;
    assign id_ex_flush     = redirect_fire || (load_use && !mem_wait);

    assign advance_allowed = rst_n && !mem_wait;
    assign fetch_accept    = !if_id_stall && !if_id_flush;
endmodule
