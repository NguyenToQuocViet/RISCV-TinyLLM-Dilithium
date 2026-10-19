module redirect_unit
    import riscv_pkg::*;
(
    input logic [DATA_WIDTH-1:0] alu_result,
    input logic branch_condition,
    input control_flow_t control_flow,

    input logic advance_allowed,
    input logic instruction_valid,

    output logic redirect_fire,
    output logic [ADDR_WIDTH-1:0] redirect_target
);
    logic redirect_req;

    always_comb begin : redirect_unit
        //default
        redirect_req = 1'h0;
        redirect_target = alu_result;

        case (control_flow)
            CF_NONE: begin
                redirect_req = 1'h0;
            end

            CF_BRANCH: begin
                redirect_req = branch_condition;
            end

            CF_JAL: begin
                redirect_req = 1'h1;
            end

            CF_JALR: begin
                redirect_req = 1'h1;
                redirect_target = {alu_result[DATA_WIDTH-1:1], 1'b0};
            end
        endcase
    end

    assign redirect_fire = redirect_req && instruction_valid && advance_allowed;

endmodule
