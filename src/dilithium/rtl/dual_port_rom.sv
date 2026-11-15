// Author: Nguyen Hung
// License: Nguyen Hung
module dual_port_rom #(
    parameter int WIDTH = 96,
    parameter int LENGTH = 1024,
    parameter string INIT_FILE = ""
) (
    input  logic                      clk,
    input  logic                      en,
    input  logic [$clog2(LENGTH)-1:0] addra,
    input  logic [$clog2(LENGTH)-1:0] addrb,
    output logic [WIDTH-1:0]          doa,
    output logic [WIDTH-1:0]          dob
);
    (* rom_style = "distributed" *) logic [WIDTH-1:0] ram [0:LENGTH-1];

    always_ff @(posedge clk) begin
        if (en) begin
            doa <= ram[addra];
            dob <= ram[addrb];
        end
    end

    initial begin
        if (INIT_FILE != "")
            $readmemh(INIT_FILE, ram);
        else
            for (int i = 0; i < LENGTH; i++)
                ram[i] = '0;
    end
endmodule
