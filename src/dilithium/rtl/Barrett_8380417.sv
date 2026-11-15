// Author: Nguyen Hung
// License: Nguyen Hung
module DecoupledStage (
    input  logic        clock,
    input  logic        reset,
    output logic        io_in_ready,
    input  logic        io_in_valid,
    input  logic [23:0] io_in_bits_ul,
    input  logic [23:0] io_in_bits_quo,
    input  logic        io_out_ready,
    output logic        io_out_valid,
    output logic [23:0] io_out_bits_ul,
    output logic [23:0] io_out_bits_quo
);
    logic valid;
    logic [23:0] reg_ul;
    logic [23:0] reg_quo;
    logic capture;

    assign capture = io_in_ready && io_in_valid;
    assign io_in_ready = !valid || io_out_ready;
    assign io_out_valid = valid;
    assign io_out_bits_ul = reg_ul;
    assign io_out_bits_quo = reg_quo;

    always_ff @(posedge clock) begin
        if (reset)
            valid <= 1'b0;
        else
            valid <= capture || (!io_out_ready && valid);

        if (capture) begin
            reg_ul <= io_in_bits_ul;
            reg_quo <= io_in_bits_quo;
        end
    end
endmodule

module DecoupledStage_1 (
    input  logic        clock,
    input  logic        reset,
    output logic        io_in_ready,
    input  logic        io_in_valid,
    input  logic [23:0] io_in_bits_ul,
    input  logic [23:0] io_in_bits_quo,
    input  logic [23:0] io_in_bits_quo_times_Q,
    input  logic        io_out_ready,
    output logic        io_out_valid,
    output logic [23:0] io_out_bits_ul,
    output logic [23:0] io_out_bits_quo,
    output logic [23:0] io_out_bits_quo_times_Q
);
    logic valid;
    logic [23:0] reg_ul;
    logic [23:0] reg_quo;
    logic [23:0] reg_quo_times_Q;
    logic capture;

    assign capture = io_in_ready && io_in_valid;
    assign io_in_ready = !valid || io_out_ready;
    assign io_out_valid = valid;
    assign io_out_bits_ul = reg_ul;
    assign io_out_bits_quo = reg_quo;
    assign io_out_bits_quo_times_Q = reg_quo_times_Q;

    always_ff @(posedge clock) begin
        if (reset)
            valid <= 1'b0;
        else
            valid <= capture || (!io_out_ready && valid);

        if (capture) begin
            reg_ul <= io_in_bits_ul;
            reg_quo <= io_in_bits_quo;
            reg_quo_times_Q <= io_in_bits_quo_times_Q;
        end
    end
endmodule

module DecoupledStage_2 (
    input  logic        clock,
    input  logic        reset,
    output logic        io_in_ready,
    input  logic        io_in_valid,
    input  logic [22:0] io_in_bits_remainder,
    input  logic [23:0] io_in_bits_quotient,
    input  logic        io_out_ready,
    output logic        io_out_valid,
    output logic [22:0] io_out_bits_remainder,
    output logic [23:0] io_out_bits_quotient
);
    logic valid;
    logic [22:0] reg_remainder;
    logic [23:0] reg_quotient;
    logic capture;

    assign capture = io_in_ready && io_in_valid;
    assign io_in_ready = !valid || io_out_ready;
    assign io_out_valid = valid;
    assign io_out_bits_remainder = reg_remainder;
    assign io_out_bits_quotient = reg_quotient;

    always_ff @(posedge clock) begin
        if (reset)
            valid <= 1'b0;
        else
            valid <= capture || (!io_out_ready && valid);

        if (capture) begin
            reg_remainder <= io_in_bits_remainder;
            reg_quotient <= io_in_bits_quotient;
        end
    end
endmodule

module Barrett (
    input  logic        clock,
    input  logic        reset,
    output logic        io_in_ready,
    input  logic        io_in_valid,
    input  logic [45:0] io_in_bits,
    input  logic        io_out_ready,
    output logic        io_out_valid,
    output logic [22:0] io_out_bits_remainder,
    output logic [23:0] io_out_bits_quotient
);
    logic        stg0_io_in_ready;
    logic        stg0_io_out_valid;
    logic [23:0] stg0_io_out_bits_ul;
    logic [23:0] stg0_io_out_bits_quo;
    logic        stg1_io_in_ready;
    logic        stg1_io_out_valid;
    logic [23:0] stg1_io_out_bits_ul;
    logic [23:0] stg1_io_out_bits_quo;
    logic [23:0] stg1_io_out_bits_quo_times_q;
    logic        stg2_io_in_ready;

    logic [23:0] mult8396807_adder7_shifted_left;
    logic [26:0] quotient_add_hi_shifted;
    logic [27:0] quotient_add_hi_extended;
    logic [27:0] quotient_add_hi_base;
    logic [27:0] quotient_adder7_high;
    logic [34:0] quotient_add_hi_base_extended;
    logic [33:0] quotient_add_hi_q_shifted;
    logic [34:0] quotient_add_hi_q_extended;
    logic [34:0] quotient_add_hi_sum;
    logic [23:0] quotient_adder7_right;
    logic [34:0] quotient_adder7_right_extended;
    logic [34:0] quotient_high;
    logic [47:0] quotient_product;

    logic [33:0] product_q_shifted;
    logic [34:0] product_q_shifted_extended;
    logic [34:0] product_q_base_extended;
    logic [34:0] product_q_subtracted;
    logic [23:0] product_q_right;
    logic [34:0] product_q_right_extended;
    logic [34:0] product_q_high;
    logic [47:0] quotient_times_q_product;
    logic [23:0] rem;
    logic [23:0] rem_minus_q;
    logic [23:0] remainder_selected;
    logic [23:0] quotient_selected;

    assign mult8396807_adder7_shifted_left = io_in_bits[45:22];
    assign quotient_add_hi_shifted = {mult8396807_adder7_shifted_left, 3'h0};
    assign quotient_add_hi_extended = {1'b0, quotient_add_hi_shifted};
    assign quotient_add_hi_base = {4'd0, mult8396807_adder7_shifted_left};
    assign quotient_adder7_high = quotient_add_hi_extended - quotient_add_hi_base;
    assign quotient_add_hi_base_extended = {11'd0, mult8396807_adder7_shifted_left};
    assign quotient_add_hi_q_shifted = {mult8396807_adder7_shifted_left, 10'h0};
    assign quotient_add_hi_q_extended = {1'b0, quotient_add_hi_q_shifted};
    assign quotient_add_hi_sum = quotient_add_hi_base_extended + quotient_add_hi_q_extended;
    assign quotient_adder7_right = {9'd0, quotient_adder7_high[27:13]};
    assign quotient_adder7_right_extended = {11'd0, quotient_adder7_right};
    assign quotient_high = quotient_add_hi_sum + quotient_adder7_right_extended;
    assign quotient_product = {quotient_high, quotient_adder7_high[12:0]};

    assign product_q_shifted = {stg0_io_out_bits_quo, 10'h0};
    assign product_q_shifted_extended = {1'b0, product_q_shifted};
    assign product_q_base_extended = {11'd0, stg0_io_out_bits_quo};
    assign product_q_subtracted = product_q_shifted_extended - product_q_base_extended;
    assign product_q_right = {13'd0, stg0_io_out_bits_quo[23:13]};
    assign product_q_right_extended = {11'd0, product_q_right};
    assign product_q_high = product_q_subtracted + product_q_right_extended;
    assign quotient_times_q_product = {product_q_high, stg0_io_out_bits_quo[12:0]};

    assign rem = stg1_io_out_bits_ul - stg1_io_out_bits_quo_times_q;
    assign rem_minus_q = rem - 24'h7fe001;
    assign remainder_selected = rem[23] ? rem : rem_minus_q;
    assign quotient_selected = rem[23] ? stg1_io_out_bits_quo : stg1_io_out_bits_quo + 24'd1;

    DecoupledStage stg0 (
        .clock(clock),
        .reset(reset),
        .io_in_ready(stg0_io_in_ready),
        .io_in_valid(io_in_valid),
        .io_in_bits_ul(io_in_bits[23:0]),
        .io_in_bits_quo(quotient_product[47:24]),
        .io_out_ready(stg1_io_in_ready),
        .io_out_valid(stg0_io_out_valid),
        .io_out_bits_ul(stg0_io_out_bits_ul),
        .io_out_bits_quo(stg0_io_out_bits_quo)
    );

    DecoupledStage_1 stg1 (
        .clock(clock),
        .reset(reset),
        .io_in_ready(stg1_io_in_ready),
        .io_in_valid(stg0_io_out_valid),
        .io_in_bits_ul(stg0_io_out_bits_ul),
        .io_in_bits_quo(stg0_io_out_bits_quo),
        .io_in_bits_quo_times_Q(quotient_times_q_product[23:0]),
        .io_out_ready(stg2_io_in_ready),
        .io_out_valid(stg1_io_out_valid),
        .io_out_bits_ul(stg1_io_out_bits_ul),
        .io_out_bits_quo(stg1_io_out_bits_quo),
        .io_out_bits_quo_times_Q(stg1_io_out_bits_quo_times_q)
    );

    DecoupledStage_2 stg2 (
        .clock(clock),
        .reset(reset),
        .io_in_ready(stg2_io_in_ready),
        .io_in_valid(stg1_io_out_valid),
        .io_in_bits_remainder(remainder_selected[22:0]),
        .io_in_bits_quotient(quotient_selected),
        .io_out_ready(io_out_ready),
        .io_out_valid(io_out_valid),
        .io_out_bits_remainder(io_out_bits_remainder),
        .io_out_bits_quotient(io_out_bits_quotient)
    );

    assign io_in_ready = stg0_io_in_ready;
endmodule
