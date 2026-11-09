// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module ntt_fifo_piso #(
    parameter int DEPTH = 4
) (
    input  logic        clk,
    input  logic        en,
    input  logic        piso_en,
    input  logic [95:0] line,
    input  logic [23:0] new_value,
    output logic [95:0] fifo_out,
    output logic [23:0] data_out
);
    logic [23:0] fifo [0:DEPTH-1];

    initial fifo = '{default: '0};

    always_comb begin
        fifo_out = {fifo[DEPTH-4], fifo[DEPTH-3], fifo[DEPTH-2], fifo[DEPTH-1]};
    end

    always_ff @(posedge clk) begin
        if (en) begin
            data_out <= fifo[DEPTH-1];
            for (int i = DEPTH - 1; i > 3; i--)
                fifo[i] <= fifo[i-1];

            if (piso_en) begin
                fifo[3] <= line[0 +: 24];
                fifo[2] <= line[24 +: 24];
                fifo[1] <= line[48 +: 24];
                fifo[0] <= line[72 +: 24];
            end else begin
                fifo[3] <= fifo[2];
                fifo[2] <= fifo[1];
                fifo[1] <= fifo[0];
                fifo[0] <= new_value;
            end
        end
    end
endmodule
