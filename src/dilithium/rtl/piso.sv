// Author: Nguyen Hung
// License: Nguyen Hung
module piso #(
    parameter int N = 128,
    parameter int M = 32
) (
    input  logic         clk,
    input  logic         en,
    input  logic         sel,
    input  logic [N-1:0] data_i,
    output logic [M-1:0] data_o
);
    localparam int PARTS = N / M;
    logic [M-1:0] stages [0:PARTS-1];

    always_ff @(posedge clk) begin
        if (en) begin
            for (int i = 0; i < PARTS - 1; i++)
                stages[i] <= sel ? data_i[N - 1 - M*i -: M] : stages[i + 1];
            stages[PARTS - 1] <= data_i[M-1:0];
        end
    end

    always_comb data_o = stages[0];
endmodule
