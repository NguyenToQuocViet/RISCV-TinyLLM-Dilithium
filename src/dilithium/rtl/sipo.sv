// Author: Nguyen Hung
// License: Nguyen Hung
module sipo #(
    parameter int N = 512,
    parameter int M = 32
) (
    input  logic         clk,
    input  logic         en,
    input  logic [M-1:0] data_i,
    output logic [N-1:0] data_o
);
    localparam int PARTS = N / M;
    logic [M-1:0] stages [0:PARTS-1];

    always_ff @(posedge clk) begin
        if (en) begin
            for (int i = 0; i < PARTS - 1; i++)
                stages[i] <= stages[i + 1];
            stages[PARTS - 1] <= data_i;
        end
    end

    always_comb begin
        data_o = '0;
        for (int i = 0; i < PARTS; i++)
            data_o[M*i +: M] = stages[PARTS - 1 - i];
    end
endmodule
