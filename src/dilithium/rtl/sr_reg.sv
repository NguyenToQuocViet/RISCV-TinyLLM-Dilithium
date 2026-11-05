// Author: Nguyen Hung
// License: Nguyen Hung
module sr_reg #(
    parameter bit INIT = 1'b0
) (
    input  logic clk,
    input  logic rst,
    input  logic set,
    input  logic clr,
    output logic q
);
    always_ff @(posedge clk) begin
        if (rst)
            q <= INIT;
        else
            q <= set | (~clr & q);
    end
endmodule
