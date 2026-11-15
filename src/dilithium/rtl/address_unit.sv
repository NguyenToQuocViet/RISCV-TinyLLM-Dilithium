// Author: Nguyen Hung
// License: Nguyen Hung
module address_unit (
    input  logic       clk,
    input  logic       rst,
    input  logic [2:0] mode,
    input  logic [1:0] mode_resolver,
    input  logic       en,
    output logic [5:0] ram_nat,
    output logic [5:0] ram_addr,
    output logic [7:0] twiddle_addr1,
    output logic [7:0] twiddle_addr2,
    output logic [7:0] twiddle_addr3,
    output logic [7:0] twiddle_addr4,
    output logic       ntt_round_done,
    output logic       done
);
    localparam logic [2:0] FORWARD_NTT_MODE = 3'd0;
    localparam logic [2:0] INVERSE_NTT_MODE = 3'd1;
    localparam logic [2:0] MULT_MODE        = 3'd2;
    localparam logic [2:0] ADD_MODE         = 3'd3;
    localparam logic [2:0] SUB_MODE         = 3'd4;

    logic [5:0] j = '0;
    logic [5:0] k = '0;
    logic [5:0] i = 6'd1;
    logic [3:0] l = '0;
    logic [6:0] k_next;
    logic [5:0] addri_resolver;
    logic [5:0] addro_resolver;
    logic [2:0] fw_ntt_pattern;

    address_resolver addr_resolve (
        .mapping(mode_resolver),
        .addri(addri_resolver),
        .addro(addro_resolver)
    );

    twiddle_resolver twiddle_resolve (
        .clk(clk),
        .rst(rst),
        .mode(mode),
        .en(en),
        .k(k),
        .s(l),
        .twiddle_addr1(twiddle_addr1),
        .twiddle_addr2(twiddle_addr2),
        .twiddle_addr3(twiddle_addr3),
        .twiddle_addr4(twiddle_addr4)
    );

    always_comb begin
        case (l[2:1])
            2'd0:    fw_ntt_pattern = 3'd4;
            2'd1:    fw_ntt_pattern = 3'd2;
            2'd2:    fw_ntt_pattern = 3'd0;
            default: fw_ntt_pattern = 3'd4;
        endcase

        addri_resolver = '0;
        k_next = '0;
        case (mode)
            ADD_MODE,
            MULT_MODE,
            SUB_MODE: begin
                addri_resolver = j;
            end
            FORWARD_NTT_MODE: begin
                addri_resolver = j + k;
                k_next = k + (7'd1 << fw_ntt_pattern);
            end
            INVERSE_NTT_MODE: begin
                addri_resolver = j + k;
                k_next = k + (7'd1 << l);
            end
            default: begin end
        endcase

        ram_addr = addro_resolver;
        ram_nat = addri_resolver;
    end

    always_ff @(posedge clk) begin
        done <= 1'b0;
        ntt_round_done <= 1'b0;

        if (rst) begin
            j <= '0;
            k <= '0;
            l <= '0;
            i <= (mode == INVERSE_NTT_MODE) ? 6'd1 : '0;
        end else if (en) begin
            case (mode)
                MULT_MODE,
                ADD_MODE,
                SUB_MODE: begin
                    if (j == 6'd63) begin
                        j <= '0;
                        done <= 1'b1;
                    end else begin
                        j <= j + 6'd1;
                    end
                end
                INVERSE_NTT_MODE: begin
                    if (k_next < 7'd64)
                        k <= k_next[5:0];
                    else begin
                        k <= '0;
                        j <= j + 6'd1;
                    end

                    if (i == '0) begin
                        j <= '0;
                        k <= '0;
                    end

                    if (i == 6'd63) begin
                        ntt_round_done <= 1'b1;
                        i <= '0;
                        if (l == 4'd6) begin
                            done <= 1'b1;
                        end else begin
                            l <= l + 4'd2;
                        end
                    end else begin
                        i <= i + 6'd1;
                    end
                end
                FORWARD_NTT_MODE: begin
                    if (k_next < 7'd64)
                        k <= k_next[5:0];
                    else begin
                        k <= '0;
                        j <= j + 6'd1;
                    end

                    if (i == 6'd63) begin
                        ntt_round_done <= 1'b1;
                        i <= '0;
                        j <= '0;
                        if (l == 4'd6) begin
                            done <= 1'b1;
                        end else begin
                            l <= l + 4'd2;
                        end
                    end else begin
                        i <= i + 6'd1;
                    end
                end
                default: begin end
            endcase
        end
    end
endmodule
