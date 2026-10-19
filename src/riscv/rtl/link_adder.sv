//------------------------------------------------------------------------------
// Module      : link_adder
// Description : Combinational 32-bit PC increment for the jump return address.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-19
//------------------------------------------------------------------------------

module link_adder
    import riscv_pkg::*;
(
    input logic [ADDR_WIDTH-1:0] pc,
    output logic [ADDR_WIDTH-1:0] pc_plus_4
);
    assign pc_plus_4 = pc + 32'h4;
endmodule
