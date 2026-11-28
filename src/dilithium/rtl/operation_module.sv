// Author: Nguyen Hung
// License: Apache-2.0
`timescale 1ns/1ps

module operation_module #(
    parameter string ZETAS_INIT_FILE = "zetas.txt"
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  logic [2:0]  mode,
    input  logic [1:0]  encode_mode,
    output logic        done,
    output logic [5:0]  addra1,
    output logic [5:0]  addrb1,
    input  logic [95:0] doa1,
    input  logic [95:0] dob1,
    output logic        web1,
    output logic [95:0] dib1,
    output logic [5:0]  addra2,
    output logic [5:0]  addrb2,
    input  logic [95:0] doa2,
    output logic        web2,
    output logic [95:0] dib2
);
    localparam logic [2:0] FORWARD_NTT_MODE = 3'd0;
    localparam logic [2:0] INVERSE_NTT_MODE = 3'd1;
    localparam logic [2:0] MULT_MODE = 3'd2;
    localparam logic [2:0] ADD_MODE = 3'd3;
    localparam logic [2:0] SUB_MODE = 3'd4;

    logic validi_bf, valido_bf;
    logic [95:0] datai_bf, zetai_bf, acci_bf, datao_bf;
    logic done_latch, pause, done_delay;
    logic [3:0] pause_ctr;
    logic en_addr, rst_addr;
    logic [5:0] ram_addr, ram_nat;
    logic [7:0] twiddle_addr [0:3];
    logic ntt_round_done, done_addr;
    logic en_twiddle;
    logic [23:0] do1_twiddle, do2_twiddle, do3_twiddle, do4_twiddle;
    logic en_pipo;
    logic [95:0] out_pipo;
    logic en_fifo, rst_fifo;
    logic [95:0] data_in, new_value, data_out;
    logic running, bram_delay, pause_delay;
    logic [5:0] addr1_sr [0:23];
    logic [7:0] valid_sr;

    assign new_value = mode == INVERSE_NTT_MODE ? datao_bf : '0;
    assign data_in = mode == FORWARD_NTT_MODE ? doa1 : '0;

    address_unit addr (
        .clk, .rst(rst_addr), .mode, .mode_resolver(encode_mode), .en(en_addr),
        .ram_nat, .ram_addr, .twiddle_addr1(twiddle_addr[0]), .twiddle_addr2(twiddle_addr[1]),
        .twiddle_addr3(twiddle_addr[2]), .twiddle_addr4(twiddle_addr[3]), .ntt_round_done, .done(done_addr)
    );
    dual_port_rom #(.WIDTH(24), .LENGTH(256), .INIT_FILE(ZETAS_INIT_FILE)) twiddle_ram1 (
        .clk, .en(en_twiddle), .addra(twiddle_addr[0]), .addrb(twiddle_addr[1]),
        .doa(do1_twiddle), .dob(do2_twiddle)
    );
    dual_port_rom #(.WIDTH(24), .LENGTH(256), .INIT_FILE(ZETAS_INIT_FILE)) twiddle_ram2 (
        .clk, .en(en_twiddle), .addra(twiddle_addr[2]), .addrb(twiddle_addr[3]),
        .doa(do3_twiddle), .dob(do4_twiddle)
    );
    butterfly2x2 bf_circuit (
        .clk, .rst, .mode, .validi(validi_bf), .datai(datai_bf), .zetai(zetai_bf), .acci(acci_bf),
        .datao(datao_bf), .valido(valido_bf)
    );
    NTT_PIPO delay_twiddle (
        .clk, .en(en_pipo), .datai({do4_twiddle, do3_twiddle, do2_twiddle, do1_twiddle}), .data0(out_pipo)
    );
    ntt_fifo fifo (
        .clk, .rst(rst_fifo), .en(en_fifo), .mode, .data_in, .new_value, .data_out
    );

    always_comb begin
        addra1 = '0; addrb1 = '0; web1 = 1'b0; dib1 = '0;
        addra2 = '0; addrb2 = '0; web2 = 1'b0; dib2 = '0;
        validi_bf = 1'b0; datai_bf = '0; zetai_bf = '0; acci_bf = '0;
        en_addr = 1'b0; en_twiddle = 1'b0; en_fifo = 1'b0; en_pipo = 1'b0;
        rst_addr = rst || start;
        rst_fifo = rst;

        case (mode)
            FORWARD_NTT_MODE: begin
                en_addr = running && !done_latch && !pause && !ntt_round_done;
                addra1 = ram_addr;
                datai_bf = data_out; zetai_bf = out_pipo; validi_bf = valid_sr[5];
                addrb1 = addr1_sr[21]; web1 = valido_bf; dib1 = datao_bf;
                if (pause && valid_sr[5:0] == 0)
                    rst_fifo = 1'b1;
                en_twiddle = 1'b1;
                en_fifo = valid_sr[5:0] != 0;
                en_pipo = valid_sr[5:0] != 0;
            end
            INVERSE_NTT_MODE: begin
                en_addr = running && !done_latch && !pause;
                addra1 = ram_addr;
                datai_bf = doa1; zetai_bf = {do4_twiddle, do3_twiddle, do2_twiddle, do1_twiddle};
                validi_bf = bram_delay && !done && !done_delay && !pause_delay;
                addrb1 = addr1_sr[22]; web1 = valid_sr[3]; dib1 = data_out;
                en_twiddle = 1'b1;
                en_fifo = valido_bf || valid_sr[3:0] != 0;
            end
            MULT_MODE: begin
                en_addr = running && !done_latch;
                addra1 = ram_addr; addra2 = ram_nat; addrb1 = ram_addr;
                datai_bf = doa1;
                zetai_bf = {doa2[71:48], doa2[23:0], doa2[95:72], doa2[47:24]};
                acci_bf = dob1;
                validi_bf = bram_delay && !done_latch && !done;
                addrb2 = addr1_sr[8]; web2 = valido_bf; dib2 = datao_bf;
            end
            ADD_MODE,
            SUB_MODE: begin
                en_addr = running && !done_latch;
                addra1 = ram_addr; addra2 = ram_addr;
                datai_bf = doa1;
                zetai_bf = {doa2[71:48], doa2[23:0], doa2[95:72], doa2[47:24]};
                validi_bf = bram_delay && !done_latch && !done;
                addrb2 = addr1_sr[4]; web2 = valido_bf; dib2 = datao_bf;
            end
            default: begin end
        endcase
    end

    always_ff @(posedge clk) begin
        done <= 1'b0;
        bram_delay <= running;
        pause_delay <= pause;
        done_delay <= done_latch;

        if (rst) begin
            running <= 1'b0;
            done_latch <= 1'b0;
            pause <= 1'b0;
            pause_ctr <= '0;
            valid_sr <= '0;
            addr1_sr <= '{default: '0};
        end else begin
            if (running || (mode == FORWARD_NTT_MODE && valido_bf)) begin
                addr1_sr[0] <= ram_addr;
                for (int i = 0; i < 23; i++)
                    addr1_sr[i+1] <= addr1_sr[i];
            end

            case (mode)
                FORWARD_NTT_MODE: begin
                    done_latch <= done_addr || done_latch;
                    if (ntt_round_done) begin
                        pause <= 1'b1;
                        pause_ctr <= '0;
                    end else if (pause) begin
                        pause_ctr <= pause_ctr + 1'b1;
                        pause <= pause_ctr != 6;
                    end
                    valid_sr <= (running && !done_addr && !done_latch && !pause && !ntt_round_done) ?
                                {valid_sr[6:0], 1'b1} : {valid_sr[6:0], 1'b0};
                    if (done_addr)
                        running <= 1'b0;
                    if (start)
                        running <= 1'b1;
                    else if (done_latch && !valido_bf) begin
                        done <= 1'b1;
                        done_latch <= 1'b0;
                    end
                end
                INVERSE_NTT_MODE: begin
                    done_latch <= done_addr || done_latch;
                    if (ntt_round_done) begin
                        pause <= 1'b1;
                        pause_ctr <= '0;
                    end else if (pause) begin
                        pause_ctr <= pause_ctr + 1'b1;
                        pause <= pause_ctr != 4;
                    end
                    if (running)
                        valid_sr <= {valid_sr[6:0], valido_bf};
                    if (start)
                        running <= 1'b1;
                    else if (done_latch && valid_sr[3:0] == 0) begin
                        running <= 1'b0;
                        done <= 1'b1;
                        done_latch <= 1'b0;
                    end
                end
                MULT_MODE,
                ADD_MODE,
                SUB_MODE: begin
                    done_latch <= done_addr || done_latch;
                    valid_sr <= (running && !done_addr && !done_latch) ?
                                {valid_sr[6:0], 1'b1} : {valid_sr[6:0], 1'b0};
                    if (start)
                        running <= 1'b1;
                    else if (done_latch && valid_sr[6:0] == 0) begin
                        running <= 1'b0;
                        done <= 1'b1;
                        done_latch <= 1'b0;
                    end
                end
                default: begin end
            endcase
        end
    end
endmodule
