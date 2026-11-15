// Author: Nguyen Hung
// License: Nguyen Hung
module decomp_map1 (
    input  logic [2:0]  sec_lvl,
    input  logic [22:0] din,
    output logic [5:0]  dout
);
    logic [16:0] dout_32;
    logic [44:0] dout_88;

    always_comb begin
        dout_32[0] = 1'b1;
        dout_32[1] = (din >= 23'd261889);
        dout_32[2] = (din >= 23'd785665);
        dout_32[3] = (din >= 23'd1309441);
        dout_32[4] = (din >= 23'd1833217);
        dout_32[5] = (din >= 23'd2356993);
        dout_32[6] = (din >= 23'd2880769);
        dout_32[7] = (din >= 23'd3404545);
        dout_32[8] = (din >= 23'd3928321);
        dout_32[9] = (din >= 23'd4452097);
        dout_32[10] = (din >= 23'd4975873);
        dout_32[11] = (din >= 23'd5499649);
        dout_32[12] = (din >= 23'd6023425);
        dout_32[13] = (din >= 23'd6547201);
        dout_32[14] = (din >= 23'd7070977);
        dout_32[15] = (din >= 23'd7594753);
        dout_32[16] = (din >= 23'd8118529);

        dout_88[0] = 1'b1;
        dout_88[1] = (din >= 23'd95233);
        dout_88[2] = (din >= 23'd285697);
        dout_88[3] = (din >= 23'd476161);
        dout_88[4] = (din >= 23'd666625);
        dout_88[5] = (din >= 23'd857089);
        dout_88[6] = (din >= 23'd1047553);
        dout_88[7] = (din >= 23'd1238017);
        dout_88[8] = (din >= 23'd1428481);
        dout_88[9] = (din >= 23'd1618945);
        dout_88[10] = (din >= 23'd1809409);
        dout_88[11] = (din >= 23'd1999873);
        dout_88[12] = (din >= 23'd2190337);
        dout_88[13] = (din >= 23'd2380801);
        dout_88[14] = (din >= 23'd2571265);
        dout_88[15] = (din >= 23'd2761729);
        dout_88[16] = (din >= 23'd2952193);
        dout_88[17] = (din >= 23'd3142657);
        dout_88[18] = (din >= 23'd3333121);
        dout_88[19] = (din >= 23'd3523585);
        dout_88[20] = (din >= 23'd3714049);
        dout_88[21] = (din >= 23'd3904513);
        dout_88[22] = (din >= 23'd4094977);
        dout_88[23] = (din >= 23'd4285441);
        dout_88[24] = (din >= 23'd4475905);
        dout_88[25] = (din >= 23'd4666369);
        dout_88[26] = (din >= 23'd4856833);
        dout_88[27] = (din >= 23'd5047297);
        dout_88[28] = (din >= 23'd5237761);
        dout_88[29] = (din >= 23'd5428225);
        dout_88[30] = (din >= 23'd5618689);
        dout_88[31] = (din >= 23'd5809153);
        dout_88[32] = (din >= 23'd5999617);
        dout_88[33] = (din >= 23'd6190081);
        dout_88[34] = (din >= 23'd6380545);
        dout_88[35] = (din >= 23'd6571009);
        dout_88[36] = (din >= 23'd6761473);
        dout_88[37] = (din >= 23'd6951937);
        dout_88[38] = (din >= 23'd7142401);
        dout_88[39] = (din >= 23'd7332865);
        dout_88[40] = (din >= 23'd7523329);
        dout_88[41] = (din >= 23'd7713793);
        dout_88[42] = (din >= 23'd7904257);
        dout_88[43] = (din >= 23'd8094721);
        dout_88[44] = (din >= 23'd8285185);

        dout = '0;
        if (sec_lvl == 3'd2) begin
            case (1'b1)
                dout_88[44]: dout = 6'd0;
                dout_88[43]: dout = 6'd43;
                dout_88[42]: dout = 6'd42;
                dout_88[41]: dout = 6'd41;
                dout_88[40]: dout = 6'd40;
                dout_88[39]: dout = 6'd39;
                dout_88[38]: dout = 6'd38;
                dout_88[37]: dout = 6'd37;
                dout_88[36]: dout = 6'd36;
                dout_88[35]: dout = 6'd35;
                dout_88[34]: dout = 6'd34;
                dout_88[33]: dout = 6'd33;
                dout_88[32]: dout = 6'd32;
                dout_88[31]: dout = 6'd31;
                dout_88[30]: dout = 6'd30;
                dout_88[29]: dout = 6'd29;
                dout_88[28]: dout = 6'd28;
                dout_88[27]: dout = 6'd27;
                dout_88[26]: dout = 6'd26;
                dout_88[25]: dout = 6'd25;
                dout_88[24]: dout = 6'd24;
                dout_88[23]: dout = 6'd23;
                dout_88[22]: dout = 6'd22;
                dout_88[21]: dout = 6'd21;
                dout_88[20]: dout = 6'd20;
                dout_88[19]: dout = 6'd19;
                dout_88[18]: dout = 6'd18;
                dout_88[17]: dout = 6'd17;
                dout_88[16]: dout = 6'd16;
                dout_88[15]: dout = 6'd15;
                dout_88[14]: dout = 6'd14;
                dout_88[13]: dout = 6'd13;
                dout_88[12]: dout = 6'd12;
                dout_88[11]: dout = 6'd11;
                dout_88[10]: dout = 6'd10;
                dout_88[9]: dout = 6'd9;
                dout_88[8]: dout = 6'd8;
                dout_88[7]: dout = 6'd7;
                dout_88[6]: dout = 6'd6;
                dout_88[5]: dout = 6'd5;
                dout_88[4]: dout = 6'd4;
                dout_88[3]: dout = 6'd3;
                dout_88[2]: dout = 6'd2;
                dout_88[1]: dout = 6'd1;
                default:    dout = 6'd0;
            endcase
        end else begin
            case (1'b1)
                dout_32[16]: dout = 6'd0;
                dout_32[15]: dout = 6'd15;
                dout_32[14]: dout = 6'd14;
                dout_32[13]: dout = 6'd13;
                dout_32[12]: dout = 6'd12;
                dout_32[11]: dout = 6'd11;
                dout_32[10]: dout = 6'd10;
                dout_32[9]: dout = 6'd9;
                dout_32[8]: dout = 6'd8;
                dout_32[7]: dout = 6'd7;
                dout_32[6]: dout = 6'd6;
                dout_32[5]: dout = 6'd5;
                dout_32[4]: dout = 6'd4;
                dout_32[3]: dout = 6'd3;
                dout_32[2]: dout = 6'd2;
                dout_32[1]: dout = 6'd1;
                default:    dout = 6'd0;
            endcase
        end
    end
endmodule
