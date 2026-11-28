// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module gen_c #(
    parameter int SAMPLER_W = 4,
    parameter int SAMPLE_W  = 23,
    parameter int W         = 64
) (
    input  logic                             start,
    input  logic                             rst,
    input  logic                             clk,
    input  logic [2:0]                       sec_lvl,
    input  logic                             mode,
    input  logic                             valid_i,
    output logic                             ready_i,
    input  logic [W-1:0]                     seed_i,
    output logic [SAMPLER_W*SAMPLE_W-1:0]    samples,
    output logic                             valid_o,
    input  logic                             ready_o,
    input  logic                             ch_read,
    output logic [W-1:0]                     ch,
    output logic                             done_sampler,
    output logic                             rst_k,
    output logic [63:0]                      din,
    input  logic [63:0]                      dout,
    output logic                             src_ready,
    input  logic                             src_read,
    input  logic                             dst_write,
    output logic                             dst_ready
);
    typedef enum logic [3:0] { HOLD, STORE_MU, INIT, ABSORB_MU, ABSORB_W1,
                               HASH_CHAT, INIT2, ABSORB_CHAT, STORE_SIGN,
                               SAMPLEC, UNLOAD_C, STORE_CHAT, STALL } state_t;
    localparam logic [22:0] NEG_ONE = 23'd8380416;

    state_t state, state_next;
    logic [31:0] ctrl_len, ctr, ctr_next;
    logic [8:0] sample_no;
    logic [7:0] sample_addr, tau;
    logic [5:0] sample_byte_offset;
    logic [10:0] w1_len;
    logic [63:0] dout_buffer, sign;
    logic [511:0] mu_sipo;
    logic [255:0] c_sipo;
    logic [1:0] c_poly [0:255];

    always_comb begin
        ch = c_sipo[255 -: 64];
        case (sec_lvl)
            3'd2: begin w1_len = 11'd96;  tau = 8'd39; end
            3'd3: begin w1_len = 11'd96;  tau = 8'd49; end
            3'd5: begin w1_len = 11'd128; tau = 8'd60; end
            default: begin w1_len = '0; tau = '0; end
        endcase

        state_next = state;
        ready_i = 1'b0;
        valid_o = 1'b0;
        rst_k = 1'b0;
        din = '0;
        src_ready = 1'b1;
        dst_ready = 1'b1;
        ctrl_len = w1_len * 64 + 512;
        ctr_next = ctr;
        done_sampler = 1'b0;
        samples = '0;
        sample_addr = '0;
        sample_byte_offset = '0;

        case (state)
            HOLD: begin
                state_next = start ? (mode ? STORE_CHAT : STORE_MU) : HOLD;
                rst_k = 1'b1;
            end
            STORE_MU: begin
                ready_i = valid_i;
                ctr_next = ctr + 1'b1;
                if (ctr == 7 && valid_i)
                    state_next = INIT;
            end
            STORE_CHAT: begin
                ready_i = valid_i;
                ctr_next = (valid_i && ready_i) ? ctr + 1'b1 : ctr;
                if (ctr == 3 && valid_i)
                    state_next = INIT2;
            end
            INIT: begin
                src_ready = 1'b0;
                din = {32'he0000100, ctrl_len};
                if (src_read)
                    state_next = ABSORB_MU;
            end
            ABSORB_MU: begin
                din = mu_sipo[511 -: 64];
                src_ready = 1'b0;
                ctr_next = src_read ? ctr + 1'b1 : ctr;
                if (ctr == 7 && src_read)
                    state_next = ABSORB_W1;
            end
            ABSORB_W1: begin
                din = seed_i;
                src_ready = !valid_i;
                ready_i = src_read;
                ctr_next = src_read ? ctr + 1'b1 : ctr;
                if (ctr == ({21'd0, w1_len} - 32'd1) && src_read)
                    state_next = HASH_CHAT;
            end
            HASH_CHAT: begin
                ctr_next = dst_write ? ctr + 1'b1 : ctr;
                dst_ready = 1'b0;
                if (ctr == 3 && dst_write)
                    state_next = INIT2;
                rst_k = ctr == 3 && dst_write;
            end
            INIT2: begin
                src_ready = 1'b0;
                din = {32'he0008000, 32'd256};
                if (src_read)
                    state_next = ABSORB_CHAT;
            end
            ABSORB_CHAT: begin
                din = c_sipo[255 -: 64];
                src_ready = 1'b0;
                ctr_next = src_read ? ctr + 1'b1 : ctr;
                if (ctr == 3 && src_read)
                    state_next = STORE_SIGN;
            end
            STORE_SIGN: begin
                ctr_next = dst_write ? ctr + 1'b1 : ctr;
                dst_ready = 1'b0;
                if (ctr == 0 && dst_write)
                    state_next = STALL;
            end
            STALL: state_next = SAMPLEC;
            SAMPLEC: begin
                sample_byte_offset = {3'd7 - ctr[2:0], 3'd0};
                sample_addr = dout_buffer[sample_byte_offset +: 8];
                ctr_next = ctr + 1'b1;
                if (sample_no == 256)
                    state_next = UNLOAD_C;
                rst_k = sample_no == 256;
                dst_ready = ctr[2:0] != 3'd6;
            end
            UNLOAD_C: begin
                valid_o = ctr < 64;
                done_sampler = ctr == 64;
                ctr_next = ready_o && valid_o ? ctr + 1'b1 : ctr;
                case (c_poly[{ctr[5:0], 2'd0}])
                    2'd1: samples[0*SAMPLE_W +: SAMPLE_W] = 1;
                    2'd2: samples[0*SAMPLE_W +: SAMPLE_W] = NEG_ONE;
                    default: samples[0*SAMPLE_W +: SAMPLE_W] = '0;
                endcase
                case (c_poly[{ctr[5:0], 2'd1}])
                    2'd1: samples[1*SAMPLE_W +: SAMPLE_W] = 1;
                    2'd2: samples[1*SAMPLE_W +: SAMPLE_W] = NEG_ONE;
                    default: samples[1*SAMPLE_W +: SAMPLE_W] = '0;
                endcase
                case (c_poly[{ctr[5:0], 2'd2}])
                    2'd1: samples[2*SAMPLE_W +: SAMPLE_W] = 1;
                    2'd2: samples[2*SAMPLE_W +: SAMPLE_W] = NEG_ONE;
                    default: samples[2*SAMPLE_W +: SAMPLE_W] = '0;
                endcase
                case (c_poly[{ctr[5:0], 2'd3}])
                    2'd1: samples[3*SAMPLE_W +: SAMPLE_W] = 1;
                    2'd2: samples[3*SAMPLE_W +: SAMPLE_W] = NEG_ONE;
                    default: samples[3*SAMPLE_W +: SAMPLE_W] = '0;
                endcase
                if (ctr == 64)
                    state_next = INIT;
            end
            default: state_next = HOLD;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= HOLD;
            ctr <= '0;
            sample_no <= '0;
            dout_buffer <= '0;
            mu_sipo <= '0;
            c_sipo <= '0;
            sign <= '0;
            c_poly <= '{default: '0};
        end else begin
            state <= state_next;
            dout_buffer <= dout;
            if (ch_read)
                c_sipo <= {c_sipo[191:0], c_sipo[255 -: 64]};

            case (state)
                HOLD: ctr <= '0;
                STORE_MU: if (valid_i && ready_i) begin
                    ctr <= ctr_next;
                    mu_sipo <= {mu_sipo[447:0], seed_i};
                end
                STORE_CHAT: begin
                    ctr <= (ctr == 3 && valid_i && ready_i) ? '0 : ctr_next;
                    if (valid_i && ready_i)
                        c_sipo <= {c_sipo[191:0], seed_i};
                end
                INIT: ctr <= '0;
                ABSORB_MU: begin
                    ctr <= (ctr == 7 && src_read) ? '0 : ctr_next;
                    if (src_read)
                        mu_sipo <= {mu_sipo[447:0], mu_sipo[511 -: 64]};
                end
                ABSORB_W1: ctr <= (ctr == ({21'd0, w1_len} - 32'd1) && src_read) ? '0 : ctr_next;
                HASH_CHAT: begin
                    ctr <= (ctr == 3 && dst_write) ? '0 : ctr_next;
                    if (dst_write)
                        c_sipo <= {c_sipo[191:0], dout};
                end
                ABSORB_CHAT: begin
                    ctr <= (ctr == 3 && src_read) ? '0 : ctr_next;
                    if (src_read)
                        c_sipo <= {c_sipo[191:0], c_sipo[255 -: 64]};
                end
                STORE_SIGN: begin
                    sample_no <= 256 - tau;
                    c_poly <= '{default: '0};
                    ctr <= dst_write ? '0 : ctr_next;
                    if (dst_write)
                        sign <= {dout[0 +: 8], dout[8 +: 8], dout[16 +: 8], dout[24 +: 8],
                                 dout[32 +: 8], dout[40 +: 8], dout[48 +: 8], dout[56 +: 8]};
                end
                SAMPLEC: begin
                    if (sample_no <= 255) begin
                        ctr <= ctr_next;
                        if (sample_addr <= sample_no[7:0]) begin
                            sample_no <= sample_no + 1'b1;
                            c_poly[sample_no[7:0]] <= c_poly[sample_addr];
                            c_poly[sample_addr] <= sign[0] ? 2 : 1;
                            sign <= sign >> 1;
                        end
                    end else begin
                        ctr <= '0;
                    end
                end
                UNLOAD_C: ctr <= ctr_next;
                default: begin end
            endcase
        end
    end
endmodule
