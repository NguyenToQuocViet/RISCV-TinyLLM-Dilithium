// Author: Nguyen Hung
// License: Nguyen Hung
module norm_check (
    input  logic [2:0]  sec_lvl,
    input  logic [1:0]  mode,
    input  logic        validi,
    input  logic [95:0] di,
    output logic        rej
);
    localparam logic [1:0] G2_SUB_BETA = 2'd0;
    localparam logic [1:0] G1_SUB_BETA = 2'd1;
    localparam logic [22:0] Q = 23'd8380417;
    localparam logic [22:0] GAMMA1_LVL2 = 23'd131072;
    localparam logic [22:0] GAMMA1_LVL35 = 23'd524288;
    localparam logic [22:0] GAMMA2_LVL2 = 23'd95232;
    localparam logic [22:0] GAMMA2_LVL35 = 23'd261888;

    logic [22:0] gamma1;
    logic [22:0] gamma2;
    logic [22:0] beta;
    logic [22:0] cond_upper;
    logic [22:0] cond_lower;
    logic [3:0] rej_lane;

    always_comb begin
        if (sec_lvl == 2) begin
            gamma1 = GAMMA1_LVL2;
            gamma2 = GAMMA2_LVL2;
            beta = 23'd78;
        end else begin
            gamma1 = GAMMA1_LVL35;
            gamma2 = GAMMA2_LVL35;
            beta = (sec_lvl == 3) ? 23'd196 : 23'd120;
        end

        case (mode)
            G2_SUB_BETA: begin
                cond_upper = gamma2 - beta;
                cond_lower = Q - (gamma2 - beta);
            end
            G1_SUB_BETA: begin
                cond_upper = gamma1 - beta;
                cond_lower = Q - (gamma1 - beta);
            end
            default: begin
                cond_upper = gamma2;
                cond_lower = Q - gamma2;
            end
        endcase

        rej_lane = '0;
        for (int i = 0; i < 4; i++)
            if ((di[24*i +: 24] >= cond_upper) &&
                (di[24*i +: 24] <= cond_lower))
                rej_lane[i] = validi;
        rej = |rej_lane;
    end
endmodule
