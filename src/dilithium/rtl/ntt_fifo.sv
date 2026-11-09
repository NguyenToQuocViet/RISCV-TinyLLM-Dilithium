// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module ntt_fifo (
    input  logic        clk,
    input  logic        rst,
    input  logic        en,
    input  logic [2:0]  mode,
    input  logic [95:0] data_in,
    input  logic [95:0] new_value,
    output logic [95:0] data_out
);
    localparam logic [2:0] FORWARD_NTT_MODE = 3'd0;
    localparam logic [2:0] INVERSE_NTT_MODE = 3'd1;

    logic [1:0] count;
    logic piso_ena, piso_enb, piso_enc, piso_end;
    logic [23:0] fifo_a, fifo_b, fifo_c, fifo_d;
    logic [95:0] fifo_outa, fifo_outb, fifo_outc, fifo_outd;

    ntt_fifo_piso #(.DEPTH(4)) piso_a (
        .clk, .en, .piso_en(piso_ena), .line(data_in), .new_value(new_value[0 +: 24]),
        .fifo_out(fifo_outa), .data_out(fifo_a)
    );
    ntt_fifo_piso #(.DEPTH(6)) piso_b (
        .clk, .en, .piso_en(piso_enb), .line(data_in), .new_value(new_value[24 +: 24]),
        .fifo_out(fifo_outb), .data_out(fifo_b)
    );
    ntt_fifo_piso #(.DEPTH(5)) piso_c (
        .clk, .en, .piso_en(piso_enc), .line(data_in), .new_value(new_value[48 +: 24]),
        .fifo_out(fifo_outc), .data_out(fifo_c)
    );
    ntt_fifo_piso #(.DEPTH(7)) piso_d (
        .clk, .en, .piso_en(piso_end), .line(data_in), .new_value(new_value[72 +: 24]),
        .fifo_out(fifo_outd), .data_out(fifo_d)
    );

    always_comb begin
        piso_ena = 1'b0;
        piso_enb = 1'b0;
        piso_enc = 1'b0;
        piso_end = 1'b0;
        data_out = '0;

        if (en) begin
            case (mode)
                FORWARD_NTT_MODE: begin
                    case (count)
                        2'd0: piso_end = 1'b1;
                        2'd1: piso_enb = 1'b1;
                        2'd2: piso_enc = 1'b1;
                        2'd3: piso_ena = 1'b1;
                    endcase
                    data_out = {fifo_a, fifo_b, fifo_c, fifo_d};
                end
                INVERSE_NTT_MODE: begin
                    case (count)
                        2'd0: data_out = fifo_outa;
                        2'd1: data_out = fifo_outc;
                        2'd2: data_out = fifo_outb;
                        2'd3: data_out = fifo_outd;
                    endcase
                end
                default: begin end
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst)
            count <= '0;
        else if (en)
            count <= count + 2'd1;
    end
endmodule
