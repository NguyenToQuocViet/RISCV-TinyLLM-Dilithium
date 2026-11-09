// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module twiddle_resolver (
    input  logic       clk,
    input  logic       rst,
    input  logic [2:0] mode,
    input  logic       en,
    input  logic [5:0] k,
    input  logic [3:0] s,
    output logic [7:0] twiddle_addr1,
    output logic [7:0] twiddle_addr2,
    output logic [7:0] twiddle_addr3,
    output logic [7:0] twiddle_addr4
);
    localparam int DILITHIUM_N = 256;
    localparam logic [2:0] FORWARD_NTT_MODE = 3'd0;
    localparam logic [2:0] INVERSE_NTT_MODE = 3'd1;

    logic [7:0] tw_base_i [0:3];
    logic       t_last;
    logic [7:0] l1, l2, l3, l4;
    logic [7:0] l1_base, l2_base, l3_base, l4_base;
    logic [7:0] l1_addmask, l2_addmask, l3_addmask, l4_addmask;

    always_comb begin
        l1_addmask = 8'((l1 + 8'd1) & ((9'd2 << s) - 9'd1));
        l2_addmask = 8'((l2 + 8'd1) & ((9'd2 << s) - 9'd1));
        l3_addmask = 8'((l3 + 8'd2) & ((9'd2 << (s + 4'd1)) - 9'd1));
        l4_addmask = 8'((l4 + 8'd2) & ((9'd2 << (s + 4'd1)) - 9'd1));
    end

    always_comb begin
        twiddle_addr1 = '0;
        twiddle_addr2 = '0;
        twiddle_addr3 = '0;
        twiddle_addr4 = '0;
        l1_base = '0;
        l2_base = '0;
        l3_base = '0;
        l4_base = '0;

        case (mode)
            INVERSE_NTT_MODE: begin
                if (k == '0) begin
                    l1_base = 8'((DILITHIUM_N >> s) - 1);
                    l2_base = 8'((DILITHIUM_N >> s) - 2);
                    l3_base = 8'((DILITHIUM_N >> (s + 1)) - 1);
                    l4_base = l3_base;
                end else begin
                    l1_base = l1 - 2;
                    l2_base = l2 - 2;
                    l3_base = l3 - 1;
                    l4_base = l4 - 1;
                end
                twiddle_addr1 = l1_base;
                twiddle_addr2 = l2_base;
                twiddle_addr3 = l3_base;
                twiddle_addr4 = l4_base;
            end
            FORWARD_NTT_MODE: begin
                if ((s < 4'd6 && k == '0) || (s >= 4'd6 && !t_last)) begin
                    l1_base = 8'(1 << s);
                    l2_base = 8'(1 << s);
                    l3_base = 8'(1 << (s + 1));
                    l4_base = 8'((1 << (s + 1)) + 1);
                end else if (s < 4'd6) begin
                    l1_base = (tw_base_i[0] > l1_addmask) ? tw_base_i[0] : l1_addmask;
                    l2_base = (tw_base_i[1] > l2_addmask) ? tw_base_i[1] : l2_addmask;
                    l3_base = (tw_base_i[2] > l3_addmask) ? tw_base_i[2] : l3_addmask;
                    l4_base = (tw_base_i[3] > l4_addmask) ? tw_base_i[3] : l4_addmask;
                end else begin
                    l1_base = l1 + 1;
                    l2_base = l2 + 1;
                    l3_base = l3 + 2;
                    l4_base = l4 + 2;
                end
                twiddle_addr1 = l1_base;
                twiddle_addr2 = l2_base;
                twiddle_addr3 = l3_base;
                twiddle_addr4 = l4_base;
            end
            default: begin end
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            l1        <= l1_base;
            l2        <= l2_base;
            l3        <= l3_base;
            l4        <= l4_base;
            t_last    <= 1'b0;
            tw_base_i <= '{default: '0};
        end else if (en) begin
            case (mode)
                INVERSE_NTT_MODE: begin
                    l1 <= l1_base;
                    l2 <= l2_base;
                    l3 <= l3_base;
                    l4 <= l4_base;
                    if (k == '0) begin
                        tw_base_i[0] <= l1_base;
                        tw_base_i[1] <= l2_base;
                        tw_base_i[2] <= l3_base;
                        tw_base_i[3] <= l4_base;
                    end
                end
                FORWARD_NTT_MODE: begin
                    l1 <= l1_base;
                    l2 <= l2_base;
                    l3 <= l3_base;
                    l4 <= l4_base;
                    if ((s < 4'd6 && k == '0) || (s >= 4'd6 && !t_last)) begin
                        tw_base_i[0] <= l1_base;
                        tw_base_i[1] <= l2_base;
                        tw_base_i[2] <= l3_base;
                        tw_base_i[3] <= l4_base;
                        t_last <= (s >= 4'd6);
                    end
                end
                default: begin end
            endcase
        end
    end
endmodule
