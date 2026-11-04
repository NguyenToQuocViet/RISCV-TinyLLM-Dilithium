// Author: Nguyen Hung
// License: Nguyen Hung
module countern #(
    parameter int N = 2,
    parameter int STEP = 1,
    parameter int STYLE = 1
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         load,
    input  logic         en,
    input  logic [N-1:0] data_i,
    output logic [N-1:0] data_o
);
    localparam int COUNTER_STYLE_1 = 1;
    localparam int COUNTER_STYLE_2 = 2;
    localparam int COUNTER_STYLE_3 = 3;

    logic [N-1:0] count;
    logic [N-1:0] increment;
    logic [N-1:0] reset_value;

    always_comb begin
        increment = '0;
        reset_value = '0;
        case (STYLE)
            COUNTER_STYLE_1: begin
                increment = STEP;
                reset_value = data_i;
            end
            COUNTER_STYLE_2: increment = data_i;
            COUNTER_STYLE_3: begin
                increment = data_i;
                reset_value = data_i;
            end
            default: begin end
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst)
            count <= reset_value;
        else if (load)
            count <= data_i;
        else if (en)
            count <= count + increment;
    end

    always_comb data_o = count;
endmodule
