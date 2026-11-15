// Author: Nguyen Hung
// License: Nguyen Hung
module butterfly (
    input  logic              clk,
    input  logic              rst,
    input  logic [2:0]        mode,
    input  logic              validi,
    input  logic signed [23:0] aj,
    input  logic signed [23:0] ajlen,
    input  logic [23:0]       zeta,
    output logic [23:0]       bj,
    output logic [23:0]       bjlen,
    output logic              valido
);
    localparam logic [23:0] DILITHIUM_Q = 24'd8380417;
    localparam logic [2:0] FORWARD_NTT_MODE = 3'd0;
    localparam logic [2:0] INVERSE_NTT_MODE = 3'd1;
    localparam logic [2:0] MULT_MODE        = 3'd2;
    localparam logic [2:0] ADD_MODE         = 3'd3;
    localparam logic [2:0] SUB_MODE         = 3'd4;

    logic [23:0] aj1 = '0;
    logic [23:0] ajlen1 = '0;
    logic [23:0] aj2 = '0;
    logic [23:0] ajlen2_fntt = '0;
    logic [23:0] ajlen2_intt = '0;
    logic [23:0] ajlen2_modm;
    logic [23:0] aj3 [0:4];
    logic [45:0] mult_result;
    logic [23:0] ajlen3 = '0;
    logic [23:0] aj4 = '0;
    logic [23:0] ajlen4 = '0;
    logic [23:0] ajlen4_sub = '0;
    logic [23:0] aj5 = '0;
    logic [23:0] ajlen5 = '0;
    logic [23:0] adda;
    logic [23:0] addb;
    logic [23:0] suba;
    logic [23:0] subb;
    logic [23:0] adder;
    logic [23:0] sub_tmp;
    logic [23:0] subtractor;
    logic [9:0] valid_sr = '0;
    logic [23:0] multa;
    logic [23:0] multb;
    logic [23:0] zeta_delay;
    logic [23:0] zeta_delay2;
    logic [2:0] modei;

    logic barrett_readyi;
    logic barrett_validi;
    logic [45:0] barrett_datai;
    logic barrett_readyo;
    logic barrett_valido;
    logic [22:0] barrett_remainder;
    logic [23:0] barrett_quotient;

    Barrett reducer (
        .clock(clk),
        .reset(rst),
        .io_in_ready(barrett_readyi),
        .io_in_valid(barrett_validi),
        .io_in_bits(barrett_datai),
        .io_out_ready(barrett_readyo),
        .io_out_valid(barrett_valido),
        .io_out_bits_remainder(barrett_remainder),
        .io_out_bits_quotient(barrett_quotient)
    );

    initial begin
        aj3[0] = '0;
        aj3[1] = '0;
        aj3[2] = '0;
        aj3[3] = '0;
        aj3[4] = '0;
    end

    always_comb begin
        adda = '0;
        addb = '0;
        suba = '0;
        subb = '0;
        valido = 1'b0;
        barrett_readyo = 1'b1;
        multa = ajlen2_fntt;
        multb = (modei == INVERSE_NTT_MODE) ? zeta_delay2 : zeta_delay;

        if (mode == INVERSE_NTT_MODE)
            valido = valid_sr[8];
        else if (mode == MULT_MODE || mode == FORWARD_NTT_MODE)
            valido = valid_sr[7];
        else
            valido = valid_sr[3];

        case (modei)
            FORWARD_NTT_MODE: begin
                adda = aj3[4];
                addb = ajlen3;
                suba = aj3[4];
                subb = ajlen3;
                multa = ajlen2_fntt;
            end
            INVERSE_NTT_MODE: begin
                multa = ajlen2_intt;
                adda = aj1;
                addb = ajlen1;
                suba = aj1;
                subb = ajlen1;
            end
            MULT_MODE: begin
                multa = ajlen2_modm;
                adda = aj4;
                addb = ajlen3;
            end
            ADD_MODE: begin
                adda = ajlen1;
                addb = zeta_delay;
                suba = ajlen4;
                subb = DILITHIUM_Q;
            end
            SUB_MODE: begin
                adda = ajlen1;
                addb = DILITHIUM_Q;
                suba = aj4;
                subb = ajlen4_sub;
            end
            default: begin end
        endcase

        barrett_validi = 1'b1;
        adder = adda + addb;
        mult_result = multb * ajlen2_intt;
        sub_tmp = suba + DILITHIUM_Q;
        subtractor = (subb > suba) ? sub_tmp - subb : suba - subb;
    end

    always_ff @(posedge clk) begin
        if (rst)
            valid_sr <= '0;
        else
            valid_sr <= {valid_sr[8:0], validi};

        modei <= mode;
        zeta_delay <= (mode == INVERSE_NTT_MODE) ? DILITHIUM_Q - zeta : zeta;
        zeta_delay2 <= zeta_delay;
        aj1 <= aj;
        ajlen1 <= ajlen;
        barrett_datai <= mult_result;
        bj <= (aj5 >= DILITHIUM_Q) ? aj5 - DILITHIUM_Q : aj5;
        bjlen <= (ajlen5 >= DILITHIUM_Q) ? ajlen5 - DILITHIUM_Q : ajlen5;
        ajlen3 <= barrett_remainder;
        ajlen4 <= adder;
        ajlen4_sub <= zeta_delay;

        case (mode)
            FORWARD_NTT_MODE: begin
                aj2 <= aj;
                ajlen2_intt <= ajlen;
                ajlen5 <= subtractor;
                aj5 <= adder;
            end
            INVERSE_NTT_MODE: begin
                aj2 <= adder;
                ajlen2_intt <= subtractor;
                if (aj3[4][0])
                    aj5 <= (aj3[4] >> 1) + (DILITHIUM_Q + 1) / 2;
                else
                    aj5 <= aj3[4] >> 1;
                if (ajlen3[0])
                    ajlen5 <= (ajlen3 >> 1) + (DILITHIUM_Q + 1) / 2;
                else
                    ajlen5 <= ajlen3 >> 1;
            end
            MULT_MODE: begin
                aj2 <= aj;
                aj4 <= aj3[3];
                ajlen2_intt <= ajlen;
                ajlen5 <= adder;
            end
            ADD_MODE: begin
                ajlen5 <= (ajlen4 > DILITHIUM_Q) ? subtractor : ajlen4;
            end
            SUB_MODE: begin
                aj4 <= (ajlen1 < zeta_delay) ? adder : ajlen1;
                ajlen5 <= subtractor;
            end
            default: begin end
        endcase

        aj3[0] <= aj2;
        aj3[1] <= aj3[0];
        aj3[2] <= aj3[1];
        aj3[3] <= aj3[2];
        aj3[4] <= aj3[3];
    end
endmodule
