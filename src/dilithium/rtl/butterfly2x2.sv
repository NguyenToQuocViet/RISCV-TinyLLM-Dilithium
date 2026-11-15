// Author: Nguyen Hung
// License: Nguyen Hung
module butterfly2x2 (
    input  logic              clk,
    input  logic              rst,
    input  logic [2:0]        mode,
    input  logic              validi,
    input  logic [24*4-1:0]   datai,
    input  logic [24*4-1:0]   zetai,
    input  logic [24*4-1:0]   acci,
    output logic [24*4-1:0]   datao,
    output logic              valido
);
    localparam logic [2:0] FORWARD_NTT_MODE = 3'd0;
    localparam logic [2:0] INVERSE_NTT_MODE = 3'd1;
    localparam logic [2:0] MULT_MODE        = 3'd2;
    localparam logic [2:0] ADD_MODE         = 3'd3;
    localparam logic [2:0] SUB_MODE         = 3'd4;

    logic [23:0] z0, z1, z2, z3;
    logic [23:0] z2_sr [0:8];
    logic [23:0] z3_sr [0:8];
    logic [23:0] a0, b0, c0, d0;
    logic [23:0] a1, b1, c1, d1;
    logic [23:0] a2, b2, c2, d2;
    logic [23:0] a3, b3, c3, d3;
    logic valido_1_1, valido_1_2, valido_2_1, valido_2_2;
    logic validi_1_1, validi_1_2, validi_2_1, validi_2_2;

    always_comb begin
        a0 = datai[24*0 +: 24];
        b0 = datai[24*1 +: 24];
        c0 = datai[24*2 +: 24];
        d0 = datai[24*3 +: 24];
        z0 = zetai[24*0 +: 24];
        z1 = zetai[24*1 +: 24];
        z2 = z2_sr[5];
        z3 = z3_sr[5];
        validi_1_1 = validi;
        validi_1_2 = validi;
        validi_2_1 = validi;
        validi_2_2 = validi;

        datao[24*0 +: 24] = a3;
        datao[24*1 +: 24] = b3;
        datao[24*2 +: 24] = c3;
        datao[24*3 +: 24] = d3;

        case (mode)
            MULT_MODE,
            ADD_MODE,
            SUB_MODE: begin
                datao[24*0 +: 24] = b3;
                datao[24*1 +: 24] = b1;
                datao[24*2 +: 24] = d3;
                datao[24*3 +: 24] = d1;
                z0 = zetai[24*0 +: 24];
                z1 = zetai[24*1 +: 24];
                z2 = zetai[24*2 +: 24];
                z3 = zetai[24*3 +: 24];
            end
            FORWARD_NTT_MODE: begin
                validi_2_1 = valido_1_1;
                validi_2_2 = valido_1_2;
                z2 = z2_sr[7];
                z3 = z3_sr[7];
            end
            INVERSE_NTT_MODE: begin
                validi_2_1 = valido_1_1;
                validi_2_2 = valido_1_2;
                z2 = z2_sr[8];
                z3 = z3_sr[8];
            end
            default: begin end
        endcase

        a2 = a1;
        c2 = b1;
        case (mode)
            MULT_MODE,
            ADD_MODE,
            SUB_MODE: begin
                a2 = acci[24*0 +: 24];
                a0 = acci[24*1 +: 24];
                c2 = acci[24*2 +: 24];
                c0 = acci[24*3 +: 24];
                b2 = datai[24*0 +: 24];
                d2 = datai[24*2 +: 24];
            end
            default: begin
                b2 = c1;
                d2 = d1;
            end
        endcase

        valido = valido_2_1 && valido_2_2;
    end

    butterfly bf1_1 (
        .clk(clk), .rst(rst), .mode(mode), .validi(validi_1_1),
        .aj(a0), .ajlen(b0), .zeta(z0), .bj(a1), .bjlen(b1), .valido(valido_1_1)
    );
    butterfly bf1_2 (
        .clk(clk), .rst(rst), .mode(mode), .validi(validi_1_2),
        .aj(c0), .ajlen(d0), .zeta(z1), .bj(c1), .bjlen(d1), .valido(valido_1_2)
    );
    butterfly bf2_1 (
        .clk(clk), .rst(rst), .mode(mode), .validi(validi_2_1),
        .aj(a2), .ajlen(b2), .zeta(z2), .bj(a3), .bjlen(b3), .valido(valido_2_1)
    );
    butterfly bf2_2 (
        .clk(clk), .rst(rst), .mode(mode), .validi(validi_2_2),
        .aj(c2), .ajlen(d2), .zeta(z3), .bj(c3), .bjlen(d3), .valido(valido_2_2)
    );

    initial begin
        for (int i = 0; i < 9; i++) begin
            z2_sr[i] = '0;
            z3_sr[i] = '0;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 9; i++) begin
                z2_sr[i] <= '0;
                z3_sr[i] <= '0;
            end
        end else begin
            z2_sr[0] <= zetai[24*2 +: 24];
            z3_sr[0] <= zetai[24*3 +: 24];
            for (int i = 1; i < 9; i++) begin
                z2_sr[i] <= z2_sr[i - 1];
                z3_sr[i] <= z3_sr[i - 1];
            end
        end
    end
endmodule
