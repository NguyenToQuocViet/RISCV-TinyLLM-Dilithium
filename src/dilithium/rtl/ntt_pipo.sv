// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module NTT_PIPO #(
    parameter int DEPTH = 5
) (
    input  logic        clk,
    input  logic        en,
    input  logic [95:0] datai,
    output logic [95:0] data0
);
    logic [95:0] pipo [0:DEPTH-1];

    initial pipo = '{default: '0};

    always_comb data0 = pipo[DEPTH-1];

    always_ff @(posedge clk) begin
        if (en) begin
            pipo[0] <= datai;
            for (int i = 0; i < DEPTH - 1; i++)
                pipo[i+1] <= pipo[i];
        end
    end
endmodule
