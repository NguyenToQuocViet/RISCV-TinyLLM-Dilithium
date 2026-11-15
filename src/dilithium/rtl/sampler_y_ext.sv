// Author: Luke Beckwith
// License: Apache-2.0
`timescale 1ns/1ps

module sampler_y_ext #(
    parameter int W        = 64,
    parameter int SAMPLE_W = 23,
    parameter int BUS_W    = 4
) (
    input  logic                        start,
    input  logic                        rst,
    input  logic                        clk,
    input  logic [2:0]                  sec_lvl,
    input  logic [15:0]                 nonce,
    input  logic                        valid_i,
    output logic                        ready_i,
    input  logic [W-1:0]                seed_i,
    output logic [SAMPLE_W*BUS_W-1:0]   samples,
    output logic                        valid_o,
    input  logic                        ready_o,
    output logic                        done,
    output logic                        rst_k,
    output logic [63:0]                 din,
    input  logic [63:0]                 dout,
    output logic                        src_ready,
    input  logic                        src_read,
    input  logic                        dst_write,
    output logic                        dst_ready
);
    typedef enum logic [2:0] {
        INIT, LOAD_MODE, WAITING_FOR_SEED, LOADING_SEED, LOADING_NONCE, SAMPLING
    } state_t;

    state_t state, state_next;
    logic [511:0] seed_sipo;
    logic [7:0] sipo_status;
    logic [7:0] sample_ctr;
    logic rst_y;
    logic [63:0] din_rejy;
    logic valid_o_y, ready_o_y;

    assign din_rejy = {dout[7:0], dout[15:8], dout[23:16], dout[31:24],
                       dout[39:32], dout[47:40], dout[55:48], dout[63:56]};

    rejection_y #(.W(W), .SAMPLE_W(SAMPLE_W), .BUS_W(BUS_W)) rej (
        .rst(rst_y), .clk, .sec_lvl, .valid_i(dst_write), .ready_i(dst_ready),
        .rdi(din_rejy), .samples, .valid_o(valid_o_y), .ready_o(ready_o_y)
    );

    always_comb begin
        state_next = state;
        ready_i = 1'b0;
        done = 1'b0;
        din = '0;
        ready_o_y = 1'b0;
        valid_o = 1'b0;
        rst_k = 1'b0;
        rst_y = 1'b0;

        case (state)
            INIT: begin
                rst_k = 1'b1;
                rst_y = 1'b1;
                if (start)
                    state_next = LOAD_MODE;
            end
            LOAD_MODE: begin
                din = 64'hE00f000000000210;
                if (src_read)
                    state_next = WAITING_FOR_SEED;
            end
            WAITING_FOR_SEED: begin
                ready_i = valid_i;
                if (sipo_status[6] && valid_i)
                    state_next = LOADING_SEED;
            end
            LOADING_SEED: begin
                din = seed_sipo[511:448];
                if (sipo_status == 8'b00000001 && src_read)
                    state_next = LOADING_NONCE;
            end
            LOADING_NONCE: begin
                din = {nonce[7:0], nonce[15:8], 48'd0};
                if (src_read)
                    state_next = SAMPLING;
            end
            SAMPLING: begin
                ready_o_y = ready_o;
                valid_o = valid_o_y;
                if (sample_ctr == 8'd252 && valid_o_y && ready_o) begin
                    state_next = INIT;
                    done = 1'b1;
                end
            end
            default: state_next = INIT;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst)
            state <= INIT;
        else
            state <= state_next;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            seed_sipo <= '0;
            sipo_status <= '0;
            sample_ctr <= '0;
            src_ready <= 1'b1;
        end else begin
            src_ready <= 1'b1;
            case (state)
                INIT: begin
                    sipo_status <= '0;
                    sample_ctr <= '0;
                end
                LOAD_MODE: src_ready <= 1'b0;
                WAITING_FOR_SEED: begin
                    if (valid_i && ready_i) begin
                        sipo_status <= {sipo_status[6:0], 1'b1};
                        seed_sipo <= {seed_sipo[447:0], seed_i};
                    end
                end
                LOADING_SEED: begin
                    src_ready <= 1'b0;
                    if (src_read) begin
                        src_ready <= 1'b1;
                        sipo_status <= {1'b0, sipo_status[7:1]};
                        seed_sipo <= {seed_sipo[447:0], 64'd0};
                    end
                end
                LOADING_NONCE: src_ready <= 1'b0;
                SAMPLING: begin
                    if (valid_o && ready_o)
                        sample_ctr <= sample_ctr + 8'd4;
                end
                default: begin end
            endcase
        end
    end
endmodule
