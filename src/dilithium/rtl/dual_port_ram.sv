// Author: Nguyen Hung
// License: Nguyen Hung
module dual_port_ram #(
    parameter int WIDTH = 96,
    parameter int LENGTH = 1024,
    parameter string INIT_FILE = ""
) (
    input  logic                      clka,
    input  logic                      clkb,
    input  logic                      ena,
    input  logic                      enb,
    input  logic                      wea,
    input  logic                      web,
    input  logic [$clog2(LENGTH)-1:0] addra,
    input  logic [$clog2(LENGTH)-1:0] addrb,
    input  logic [WIDTH-1:0]          dia,
    input  logic [WIDTH-1:0]          dib,
    output logic [WIDTH-1:0]          doa,
    output logic [WIDTH-1:0]          dob
);
    logic [WIDTH-1:0] ram [0:LENGTH-1];

    initial begin
        if (INIT_FILE != "")
            $readmemh(INIT_FILE, ram);
        else
            for (int i = 0; i < LENGTH; i++)
                ram[i] = '0;
    end

    always @(posedge clka) begin
        if (ena) begin
            if (wea)
                ram[addra] <= dia;
            doa <= ram[addra];
        end
    end

    always @(posedge clkb) begin
        if (enb) begin
            if (web)
                ram[addrb] <= dib;
            dob <= ram[addrb];
        end
    end
endmodule
