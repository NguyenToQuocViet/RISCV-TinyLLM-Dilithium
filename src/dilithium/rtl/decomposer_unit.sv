// Author: Nguyen Hung
// License: Nguyen Hung
module decomposer_unit #(
    parameter int OUTPUT_W = 4,
    parameter int COEFF_W = 24
) (
    input  logic                        rst,
    input  logic                        clk,
    input  logic [2:0]                  sec_lvl,
    input  logic                        valid_i,
    output logic                        ready_i,
    input  logic [OUTPUT_W*COEFF_W-1:0] di,
    output logic [OUTPUT_W*COEFF_W-1:0] doa,
    output logic [OUTPUT_W*COEFF_W-1:0] dob,
    output logic                        valid_o,
    input  logic                        ready_o
);
    logic [OUTPUT_W-1:0] valid_coeff_o;
    logic [OUTPUT_W-1:0] ready_i_sub;

    assign valid_o = &valid_coeff_o;
    assign ready_i = |ready_i_sub;

    generate
        for (genvar i = 0; i < OUTPUT_W; i++) begin : gen_coeff_decomposer
            coeff_decomposer coeff_decomp (
                .rst(rst),
                .clk(clk),
                .valid_i(valid_i),
                .ready_i(ready_i_sub[i]),
                .sec_lvl(sec_lvl),
                .di(di[COEFF_W*i +: COEFF_W]),
                .doa(doa[COEFF_W*i +: COEFF_W]),
                .dob(dob[COEFF_W*i +: COEFF_W]),
                .valid_o(valid_coeff_o[i]),
                .ready_o(ready_o)
            );
        end
    endgenerate
endmodule
