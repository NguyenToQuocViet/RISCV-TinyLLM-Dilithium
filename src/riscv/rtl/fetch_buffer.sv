//------------------------------------------------------------------------------
// Module      : fetch_buffer
// Description : Three-slot fetch ring with entry lifecycle, redirect kill, OBI
//               presentation and delivery of the oldest ready instruction.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-04
//------------------------------------------------------------------------------

module fetch_buffer
    import riscv_pkg::*;
(
    input logic clk,
    input logic rst_n,

    input logic kill,
    input logic alloc_valid,
    input logic [ADDR_WIDTH-1:0] alloc_pc,

    input logic fetch_accept,

    input logic request_fire,
    input logic raw_response_transfer,
    input logic [INSTR_WIDTH-1:0] response_data,

    output logic alloc_fire,

    output logic present_valid,
    output logic [ADDR_WIDTH-1:0] present_pc,

    output logic fetch_valid,
    output logic [ADDR_WIDTH-1:0] fetch_pc,
    output logic [INSTR_WIDTH-1:0] fetch_instruction
);
    //FIFO 3 slots
    logic [ADDR_WIDTH-1:0]  pc [FETCH_DEPTH];
    logic [INSTR_WIDTH-1:0] instruction [FETCH_DEPTH];
    logic killed [FETCH_DEPTH];
    life_t life [FETCH_DEPTH];

    //pointers
    logic [1:0] head_ptr;   //next slot to alloc
    logic [1:0] tail_ptr;   //oldest ENTRY -> FREE slot (out instr)
    logic [1:0] issue_ptr;  //oldest QUEUED -> issue to OBI

    //ring idx helpers
    function automatic logic [1:0] next_slot (
        input logic [1:0] slot
    );
        logic [1:0] result;

        if (slot == 2'd2) begin
            result = 2'd0;
        end else begin
            result = slot + 2'd1;
        end

        return result;
    endfunction

    function automatic logic [1:0] prev_slot (
        input logic [1:0] slot
    );
        logic [1:0] result;

        if (slot == 2'd0) begin
            result = 2'd2;
        end else begin
            result = slot - 2'd1;
        end

        return result;
    endfunction

    //combinational read
        //to IF/ID
    assign fetch_valid          = (life[tail_ptr] == LIFE_READY);
    assign fetch_pc             = pc[tail_ptr];
    assign fetch_instruction    = instruction[tail_ptr];

        //to OBI
    assign present_valid    = (life[issue_ptr] == LIFE_QUEUED);
    assign present_pc       = pc[issue_ptr];

    //internal ring status
    logic [1:0] prv;
    logic outst;
    logic full;

    assign prv      = prev_slot(issue_ptr);
    assign outst    = (life[prv] == LIFE_OUTSTANDING);
    assign full     = (life[head_ptr] != LIFE_FREE);

    //events write
    logic fetch_fire;
    logic response_fire;
    logic killed_resp;
    logic tail_free;

    assign fetch_fire       = fetch_valid && fetch_accept;
    assign response_fire    = outst && raw_response_transfer;
    assign killed_resp      = response_fire && killed[prv];
    assign tail_free        = fetch_fire || killed_resp;

    //to controller
    assign alloc_fire       = alloc_valid && (!full || tail_free);

    //kill edge
    logic kept_out;
    logic kept_q;
    logic [1:0] nxt;
    logic [1:0] restart_slot;

    assign kept_out     = outst && !response_fire;
    assign kept_q       = present_valid;
    assign nxt          = next_slot(issue_ptr);
    assign restart_slot = kept_q ? nxt : issue_ptr;

    //head pointer
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            head_ptr <= '0;
        end else if (kill) begin
            head_ptr <= restart_slot;
        end else if (alloc_fire) begin
            head_ptr <= next_slot(head_ptr);
        end
    end

    //issue pointer
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            issue_ptr <= '0;
        end else if (request_fire) begin
            issue_ptr <= nxt;
        end
    end

    //tail pointer
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tail_ptr <= '0;
        end else if (kill) begin
            if (kept_out) begin
                tail_ptr <= prv;
            end else begin
                tail_ptr <= issue_ptr;
            end
        end else if (tail_free) begin
            tail_ptr <= next_slot(tail_ptr);
        end
    end

    //slot lifecycle
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int slot = 0; slot < FETCH_DEPTH; slot++) begin
                life[slot] <= LIFE_FREE;
            end
        end else if (kill) begin
            //prv, issue and nxt are all three slots
            if (kept_out) begin
                life[prv] <= LIFE_OUTSTANDING;
            end else begin
                life[prv] <= LIFE_FREE;
            end

            if (kept_q && request_fire) begin
                life[issue_ptr] <= LIFE_OUTSTANDING;
            end else if (kept_q) begin
                life[issue_ptr] <= LIFE_QUEUED;
            end else begin
                life[issue_ptr] <= LIFE_FREE;
            end

            life[nxt] <= LIFE_FREE;
        end else begin
            if (response_fire && !killed[prv]) begin
                life[prv] <= LIFE_READY;
            end

            if (request_fire) begin
                life[issue_ptr] <= LIFE_OUTSTANDING;
            end

            if (tail_free) begin
                life[tail_ptr] <= LIFE_FREE;
            end

            //last: may reuse the slot freed on this edge
            if (alloc_fire) begin
                life[head_ptr] <= LIFE_QUEUED;
            end
        end
    end

    //killed marks
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int slot = 0; slot < FETCH_DEPTH; slot++) begin
                killed[slot] <= 1'b0;
            end
        end else if (kill) begin
            killed[prv]       <= kept_out;
            killed[issue_ptr] <= kept_q;
            killed[nxt]       <= 1'b0;
        end else if (tail_free) begin
            killed[tail_ptr] <= 1'b0;
        end
    end

    //pc payload (no reset)
    always_ff @(posedge clk) begin
        if (alloc_fire) begin
            pc[head_ptr] <= alloc_pc;
        end
    end

    //instruction payload (no reset)
    always_ff @(posedge clk) begin
        if (response_fire) begin
            instruction[prv] <= response_data;
        end
    end
endmodule
