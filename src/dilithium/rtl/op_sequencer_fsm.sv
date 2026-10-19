// op_sequencer_fsm.sv

module op_sequencer_fsm (
    input  logic       clk,
    input  logic       rst_n,

    input  logic       start,
    input  logic [1:0] mode,          // see mode_e below
    input  logic       stage_done,    // pulse from the active sub-FSM

    output logic [2:0] state,         // see state_e below
    output logic       busy,
    output logic       done
);

    typedef enum logic [1:0] {
        MODE_FULL_SCHEME = 2'd0,
        MODE_ONLY_GEN    = 2'd1,
        MODE_ONLY_SIGN   = 2'd2,
        MODE_ONLY_VERIFY = 2'd3
    } mode_e;

    typedef enum logic [2:0] {
        S_IDLE,
        S_KEYGEN,
        S_SIGN,
        S_VERIFY,
        S_DONE
    } state_e;

    state_e cur, nxt;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) cur <= S_IDLE;
        else        cur <= nxt;
    end

    always_comb begin
        nxt = cur;
        unique case (cur)
            S_IDLE: begin
                if (start) begin
                    unique case (mode)
                        MODE_FULL_SCHEME, MODE_ONLY_GEN: nxt = S_KEYGEN;
                        MODE_ONLY_SIGN:                  nxt = S_SIGN;
                        MODE_ONLY_VERIFY:                nxt = S_VERIFY;
                        default:                          nxt = S_IDLE;
                    endcase
                end
            end

            S_KEYGEN: begin
                if (stage_done) begin
                    nxt = (mode == MODE_FULL_SCHEME) ? S_SIGN : S_DONE;
                end
            end

            S_SIGN:   if (stage_done) nxt = S_DONE;   // ends FullScheme & OnlySign
            S_VERIFY: if (stage_done) nxt = S_DONE;

            S_DONE: if (!start) nxt = S_IDLE;         // host deasserts start

            default: nxt = S_IDLE;
        endcase
    end

    assign state = cur;   // state_e is encoded on 3 bits
    assign busy  = (cur != S_IDLE) && (cur != S_DONE);
    assign done  = (cur == S_DONE);

endmodule
