// Author: Nguyen Hung
// License: Apache-2.0
module keccak_bytepad #(
    parameter int W = 64
) (
    input  logic [W-1:0]     din_input,
    output logic [W-1:0]     din_output,
    input  logic [W/8-1:0]   sel_pad_location,
    input  logic [W/8-1:0]   sel_din,
    input  logic             last_word,
    input  logic [1:0]       mode,
    input  logic [W-1:0]     dout_input,
    output logic [W-1:0]     dout_output,
    input  logic [W/8-1:0]   sel_dout,
    input  logic             last_out_word
);
    logic [7:0] pad_byte [0:W/8-1];
    logic [7:0] first_byte, first_last_byte;

    always_comb begin
        first_byte = (mode inside {2'b10, 2'b11}) ? 8'h1f : 8'h06;
        first_last_byte = (mode inside {2'b10, 2'b11}) ? 8'h9f : 8'h86;
        for (int i = 0; i < W/8; i++) begin
            if (i == 0) begin
                unique case ({last_word, sel_pad_location[0]})
                    2'b00: pad_byte[i] = 8'h00;
                    2'b01: pad_byte[i] = first_byte;
                    2'b10: pad_byte[i] = 8'h80;
                    default: pad_byte[i] = first_last_byte;
                endcase
            end else begin
                pad_byte[i] = sel_pad_location[i] ? first_byte : 8'h00;
            end
            din_output[8*i +: 8] = sel_din[i] ? din_input[8*i +: 8] : pad_byte[i];
            dout_output[8*i +: 8] = last_out_word && sel_dout[i] ? dout_input[8*i +: 8] :
                                     last_out_word ? 8'h00 : dout_input[8*i +: 8];
        end
    end
endmodule
