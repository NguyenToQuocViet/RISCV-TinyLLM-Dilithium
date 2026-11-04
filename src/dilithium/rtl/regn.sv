// Author: Nguyen Hung
// License: Nguyen Hung
module regn #(
    parameter int N = 32,
    parameter logic [N-1:0] INIT = '0
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         en,
    input  logic [N-1:0] data_i,
    output logic [N-1:0] data_o
);
    always_ff @(posedge clk) begin
        if (rst)
            data_o <= INIT;
        else if (en)
            data_o <= data_i;
    end
endmodule
