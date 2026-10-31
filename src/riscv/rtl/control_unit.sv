//------------------------------------------------------------------------------
// Module      : control_unit
// Description : Recognize the 38 RV32I operations and produce ID control values.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-10-30
//------------------------------------------------------------------------------

module control_unit
    import riscv_pkg::*;
(
    input logic [INSTR_WIDTH-1:0] instruction,

    output logic rs1_used,
    output logic rs2_used,

    output alu_src_a_t alu_src_a,
    output alu_src_b_t alu_src_b,
    output alu_op_t alu_op,
    output branch_kind_t branch_kind,
    output result_src_t result_src,
    output control_flow_t control_flow,

    output mem_type_t mem_type,
    output logic mem_write,
    output logic mem_en,

    output logic reg_write,
    output logic wb_src
);
    logic [4:0] opc;
    logic [2:0] funct3;
    logic [6:0] funct7;
    logic supported;

    assign opc    = instruction[6:2];
    assign funct3 = instruction[14:12];
    assign funct7 = instruction[31:25];

    //legality L1-L9
    always_comb begin : legality
        //default
        supported = 1'b0;

        if (instruction[1:0] == 2'b11) begin
            case (opc)
                OPC_LUI, OPC_AUIPC, OPC_JAL: begin
                    supported = 1'b1;
                end

                OPC_JALR: begin
                    if (funct3 == 3'b000) begin
                        supported = 1'b1;
                    end
                end

                OPC_BRANCH: begin
                    if (funct3 != 3'b010 && funct3 != 3'b011) begin
                        supported = 1'b1;
                    end
                end

                OPC_LOAD: begin
                    case (funct3)
                        3'b000, 3'b001, 3'b010, 3'b100, 3'b101: begin
                            supported = 1'b1;
                        end

                        default: begin
                            supported = 1'b0;
                        end
                    endcase
                end

                OPC_STORE: begin
                    case (funct3)
                        3'b000, 3'b001, 3'b010: begin
                            supported = 1'b1;
                        end

                        default: begin
                            supported = 1'b0;
                        end
                    endcase
                end

                OPC_OP_IMM: begin
                    case (funct3)
                        3'b001: begin
                            supported = (funct7 == 7'b0000000);
                        end

                        3'b101: begin
                            supported = (funct7 == 7'b0000000) || (funct7 == 7'b0100000);
                        end

                        default: begin
                            supported = 1'b1;
                        end
                    endcase
                end

                OPC_OP: begin
                    case (funct7)
                        7'b0000000: begin
                            supported = 1'b1;
                        end

                        7'b0100000: begin
                            supported = (funct3 == 3'b000) || (funct3 == 3'b101);
                        end

                        default: begin
                            supported = 1'b0;
                        end
                    endcase
                end

                OPC_MISC_MEM: begin
                    if (funct3 == 3'b000) begin
                        supported = 1'b1;
                    end
                end

                default: begin
                    supported = 1'b0;
                end
            endcase
        end
    end

    //control values per class
    always_comb begin : decode
        //default
        rs1_used     = 1'b0;
        rs2_used     = 1'b0;
        reg_write    = 1'b0;
        mem_en       = 1'b0;
        control_flow = CF_NONE;
        wb_src       = 1'b0;
        alu_op       = ALU_ADD;
        alu_src_a    = ALU_A_RS1;
        alu_src_b    = ALU_B_RS2;
        result_src   = RESULT_ALU;
        branch_kind  = BR_EQ;
        mem_write    = 1'b0;
        mem_type     = MEM_BYTE;

        case (opc)
            OPC_LUI: begin
                reg_write = 1'b1;
                alu_src_a = ALU_A_ZERO;
                alu_src_b = ALU_B_IMM;
            end

            OPC_AUIPC: begin
                reg_write = 1'b1;
                alu_src_a = ALU_A_PC;
                alu_src_b = ALU_B_IMM;
            end

            OPC_JAL: begin
                reg_write    = 1'b1;
                control_flow = CF_JAL;
                alu_src_a    = ALU_A_PC;
                alu_src_b    = ALU_B_IMM;
                result_src   = RESULT_PC_PLUS_4;
            end

            OPC_JALR: begin
                rs1_used     = 1'b1;
                reg_write    = 1'b1;
                control_flow = CF_JALR;
                alu_src_b    = ALU_B_IMM;
                result_src   = RESULT_PC_PLUS_4;
            end

            OPC_BRANCH: begin
                rs1_used     = 1'b1;
                rs2_used     = 1'b1;
                control_flow = CF_BRANCH;
                alu_src_a    = ALU_A_PC;
                alu_src_b    = ALU_B_IMM;
                //enum codes equal funct3
                branch_kind  = branch_kind_t'(funct3);
            end

            OPC_LOAD: begin
                rs1_used  = 1'b1;
                reg_write = 1'b1;
                mem_en    = 1'b1;
                wb_src    = 1'b1;
                alu_src_b = ALU_B_IMM;
                //enum codes equal funct3
                mem_type  = mem_type_t'(funct3);
            end

            OPC_STORE: begin
                rs1_used  = 1'b1;
                rs2_used  = 1'b1;
                mem_en    = 1'b1;
                alu_src_b = ALU_B_IMM;
                mem_write = 1'b1;
                //enum codes equal funct3
                mem_type  = mem_type_t'(funct3);
            end

            OPC_OP_IMM: begin
                rs1_used  = 1'b1;
                reg_write = 1'b1;
                alu_src_b = ALU_B_IMM;

                case (funct3)
                    3'b000: begin
                        alu_op = ALU_ADD;
                    end

                    3'b001: begin
                        alu_op = ALU_SLL;
                    end

                    3'b010: begin
                        alu_op = ALU_SLT;
                    end

                    3'b011: begin
                        alu_op = ALU_SLTU;
                    end

                    3'b100: begin
                        alu_op = ALU_XOR;
                    end

                    3'b101: begin
                        alu_op = instruction[30] ? ALU_SRA : ALU_SRL;
                    end

                    3'b110: begin
                        alu_op = ALU_OR;
                    end

                    //3'b111
                    default: begin
                        alu_op = ALU_AND;
                    end
                endcase
            end

            OPC_OP: begin
                rs1_used  = 1'b1;
                rs2_used  = 1'b1;
                reg_write = 1'b1;

                case (funct3)
                    3'b000: begin
                        alu_op = instruction[30] ? ALU_SUB : ALU_ADD;
                    end

                    3'b001: begin
                        alu_op = ALU_SLL;
                    end

                    3'b010: begin
                        alu_op = ALU_SLT;
                    end

                    3'b011: begin
                        alu_op = ALU_SLTU;
                    end

                    3'b100: begin
                        alu_op = ALU_XOR;
                    end

                    3'b101: begin
                        alu_op = instruction[30] ? ALU_SRA : ALU_SRL;
                    end

                    3'b110: begin
                        alu_op = ALU_OR;
                    end

                    //3'b111
                    default: begin
                        alu_op = ALU_AND;
                    end
                endcase
            end

            OPC_MISC_MEM: begin
                alu_op = ALU_ADD;
            end

            default: begin
                alu_op = ALU_ADD;
            end
        endcase

        //side-effect guard
        reg_write = reg_write && supported;
        mem_en    = mem_en && supported;
        if (!supported) begin
            control_flow = CF_NONE;
        end
    end

endmodule
