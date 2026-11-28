// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module expandmask_ext #(
    parameter int SAMPLER_W = 4,
    parameter int SAMPLE_W  = 23,
    parameter int W         = 64
) (
    input  logic                         start,
    input  logic                         rst,
    input  logic                         clk,
    input  logic [2:0]                   sec_lvl,
    input  logic [31:0]                  msg_len,
    input  logic                         valid_seed,
    output logic                         ready_for_seed,
    input  logic [W-1:0]                 seed_i,
    output logic [W-1:0]                 mu_out,
    output logic                         mu_valid,
    output logic [SAMPLER_W*SAMPLE_W-1:0] samples,
    output logic                         valid_o,
    input  logic                         ready_o,
    output logic                         done_sampler,
    output logic                         rst_k,
    output logic [63:0]                  din,
    input  logic [63:0]                  dout,
    output logic                         src_ready,
    input  logic                         src_read,
    input  logic                         dst_write,
    output logic                         dst_ready
);
    typedef enum logic [3:0] { HOLD, INIT, ABSORB_TR, ABSORB_M, HASH_MU, INIT_K,
                               ABSORB_K, ABSORB_MU, HASH_RHO_P, LOAD_SAMPLERS,
                               RUN_SAMPLERS, WAIT_STATE } state_t;
    state_t state, state_next;
    logic [31:0] ctr, ctr_next, msg_bytes, ctrl_len;
    logic rst_y, valid_seed_sampler, start_y;
    logic [511:0] seed_sipo;
    logic [7:0] sipo_status;
    logic [15:0] nonce, offset, l_count;
    logic ready_i, sampler_done;
    logic [W-1:0] seed_i_sampler;
    logic rst_k_y, src_ready_y, dst_ready_y;
    logic [63:0] din_y;

    sampler_y_ext #(.W(W), .SAMPLE_W(SAMPLE_W), .BUS_W(SAMPLER_W)) sampler_y (
        .start(start_y), .rst(rst_y), .clk, .sec_lvl, .nonce(nonce+offset),
        .valid_i(valid_seed_sampler), .ready_i, .seed_i(seed_i_sampler), .samples, .valid_o, .ready_o,
        .done(sampler_done), .rst_k(rst_k_y), .din(din_y), .dout, .src_ready(src_ready_y),
        .src_read, .dst_write, .dst_ready(dst_ready_y)
    );

    always_comb begin
        case (sec_lvl)
            3'd2: l_count = 4;
            3'd3: l_count = 5;
            default: l_count = 7;
        endcase
        state_next = state;
        ready_for_seed = 1'b0;
        din = '0;
        rst_k = 1'b0;
        src_ready = 1'b1;
        dst_ready = 1'b0;
        valid_seed_sampler = 1'b0;
        seed_i_sampler = '0;
        ctr_next = ctr;
        ctrl_len = '0;
        case (state)
            HOLD: begin rst_k = 1'b1; if (start) state_next = INIT; end
            INIT: begin
                src_ready = 1'b0;
                ctrl_len = {msg_bytes, 3'd0} + 32'h100;
                din = {32'he0000200, ctrl_len};
                if (src_read) state_next = ABSORB_TR;
            end
            ABSORB_TR: begin
                din = seed_i; src_ready = !valid_seed; ready_for_seed = src_read;
                ctr_next = src_read ? ctr+1 : ctr;
                if (ctr_next == 4) state_next = ABSORB_M;
            end
            ABSORB_M: begin
                din = seed_i; src_ready = !valid_seed; ready_for_seed = src_read;
                ctr_next = src_read ? ctr+1 : ctr;
                if ({ctr_next, 3'd0} >= msg_bytes) state_next = HASH_MU;
            end
            HASH_MU: begin dst_ready = 1'b1; if (dst_write && sipo_status[6]) state_next = INIT_K; end
            INIT_K: begin
                src_ready = 1'b0; din = {32'he0000200, 32'h300};
                if (src_read) state_next = ABSORB_K;
            end
            ABSORB_K: begin
                din = seed_i; src_ready = !valid_seed; ready_for_seed = src_read;
                ctr_next = src_read ? ctr+1 : ctr;
                if (ctr_next == 4) state_next = ABSORB_MU;
            end
            ABSORB_MU: begin
                din = seed_sipo[511:448]; src_ready = 1'b0;
                if (sipo_status == 1 && src_read) state_next = HASH_RHO_P;
            end
            HASH_RHO_P: begin
                dst_ready = 1'b1; rst_k = dst_write && sipo_status[6];
                if (dst_write && sipo_status[6]) state_next = LOAD_SAMPLERS;
            end
            LOAD_SAMPLERS: begin
                valid_seed_sampler = 1'b1; seed_i_sampler = seed_sipo[511:448];
                ctr_next = ctr+1;
                if (ctr == 7 && &ready_i) state_next = RUN_SAMPLERS;
                rst_k = rst_k_y; din = din_y; src_ready = src_ready_y; dst_ready = dst_ready_y;
            end
            RUN_SAMPLERS: begin
                if (sampler_done && nonce == l_count-1) state_next = WAIT_STATE;
                else if (sampler_done) state_next = LOAD_SAMPLERS;
                rst_k = rst_k_y; din = din_y; src_ready = src_ready_y; dst_ready = dst_ready_y;
            end
            WAIT_STATE: if (start) state_next = LOAD_SAMPLERS;
            default: state_next = HOLD;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= HOLD;
            rst_y <= 1'b1;
            ctr <= '0;
            seed_sipo <= '0;
            sipo_status <= '0;
            nonce <= '0;
            offset <= '0;
            msg_bytes <= '0;
            mu_out <= '0;
            mu_valid <= 1'b0;
            done_sampler <= 1'b0;
            start_y <= 1'b0;
        end else begin
            state <= state_next;
            rst_y <= 1'b0;
            msg_bytes <= msg_len;
            mu_valid <= 1'b0;
            done_sampler <= 1'b0;
            start_y <= 1'b0;
            case (state)
                HOLD: begin nonce <= '0; offset <= '0; sipo_status <= '0; ctr <= '0; end
                ABSORB_TR: ctr <= (ctr_next == 4) ? '0 : ctr_next;
                ABSORB_M: ctr <= ({ctr_next,3'd0} >= msg_bytes) ? '0 : ctr_next;
                HASH_MU: if (dst_write) begin
                    mu_valid <= 1'b1; mu_out <= dout;
                    sipo_status <= {sipo_status[6:0],1'b1}; seed_sipo <= {seed_sipo[447:0],dout};
                end
                ABSORB_K: ctr <= (ctr_next == 4) ? '0 : ctr_next;
                ABSORB_MU: if (src_read) begin
                    sipo_status <= {1'b0,sipo_status[7:1]}; seed_sipo <= {seed_sipo[447:0],64'd0};
                end
                HASH_RHO_P: if (dst_write) begin
                    sipo_status <= {sipo_status[6:0],1'b1}; seed_sipo <= {seed_sipo[447:0],dout};
                    start_y <= sipo_status[6];
                end
                LOAD_SAMPLERS: if (&ready_i) begin
                    seed_sipo <= {seed_sipo[447:0],seed_sipo[511:448]};
                    ctr <= (ctr == 7) ? '0 : ctr_next;
                end
                RUN_SAMPLERS: begin
                    start_y <= sampler_done && nonce < l_count-1;
                    if (sampler_done && nonce == l_count-1) begin
                        done_sampler <= 1'b1; offset <= offset+l_count; nonce <= '0;
                    end else if (sampler_done) nonce <= nonce+1;
                end
                WAIT_STATE: start_y <= start;
                default: begin end
            endcase
        end
    end
endmodule
