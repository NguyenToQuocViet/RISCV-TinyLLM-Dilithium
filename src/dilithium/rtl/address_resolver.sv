// Author: Nguyen Hung
// License: Nguyen Hung
module address_resolver (
    input  logic [1:0] mapping,
    input  logic [5:0] addri,
    output logic [5:0] addro
);
    localparam logic [1:0] DECODE_TRUE = 2'd0;
    localparam logic [1:0] ENCODE_TRUE = 2'd1;
    localparam logic [1:0] STANDARD = 2'd2;

    always_comb begin
        case (mapping)
            DECODE_TRUE: addro = {addri[3:0], addri[5:4]};
            ENCODE_TRUE: addro = {addri[1:0], addri[5:2]};
            STANDARD:    addro = addri;
            default:     addro = addri;
        endcase
    end
endmodule
