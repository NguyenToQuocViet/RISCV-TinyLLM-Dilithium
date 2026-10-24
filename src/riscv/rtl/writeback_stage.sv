//------------------------------------------------------------------------------
// Module      : writeback_stage
// Description : Select writeback data and qualify register-file writes.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-24
//------------------------------------------------------------------------------

module writeback_stage
    import riscv_pkg::*;
(
    input logic [DATA_WIDTH-1:0] ex_result,
    input logic [DATA_WIDTH-1:0] load_result,
    input logic [4:0] rd,
    input logic wb_src,
    input logic reg_write,

    input logic instruction_valid,
    input logic advance_allowed,

    output logic [DATA_WIDTH-1:0] wb_data,
    output logic rf_write_fire
);
    logic wb_retire_fire;

    assign wb_data = wb_src ? load_result : ex_result;

    assign wb_retire_fire = instruction_valid && advance_allowed;
    assign rf_write_fire = wb_retire_fire && reg_write && (rd != 5'd0);

endmodule
