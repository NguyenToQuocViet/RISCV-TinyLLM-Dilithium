//------------------------------------------------------------------------------
// Module      : fetch_controller_unit
// Description : Owns next_fetch_pc, the fetch entry ring and lifecycle, kill recovery
//               and the write and read controls of fetch_buffer.
// Author      : Viet Nguyen To Quoc
// Date        : 2026-11-06
//------------------------------------------------------------------------------

module fetch_controller_unit
    import riscv_pkg::*;
(
    input logic clk,
    input logic rst_n,

    input logic redirect_fire,
    input logic [ADDR_WIDTH-1:0] redirect_target,

    input logic fetch_accept,

    input logic request_fire,
    input logic raw_response_transfer,

    output logic present_valid,
    output logic fetch_valid,

    output logic pc_write,
    output logic [1:0] pc_write_slot,
    output logic [ADDR_WIDTH-1:0] pc_write_data,

    output logic instruction_write,
    output logic [1:0] instruction_write_slot,

    output logic [1:0] present_slot,
    output logic [1:0] fetch_slot
);
    logic [ADDR_WIDTH-1:0] next_fetch_pc;

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

    logic kill;
    logic alloc_fire;

    assign kill = redirect_fire;

    //to OBI and IF/ID
    assign fetch_valid      = (life[tail_ptr] == LIFE_READY);
    assign present_valid    = (life[issue_ptr] == LIFE_QUEUED);

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
    assign alloc_fire       = !full || tail_free;

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

    //next fetch address
    always_ff @(posedge clk or negedge rst_n) begin : fcu
        if (!rst_n) begin
            next_fetch_pc <= PC_RESET_VEC;
        end else if (redirect_fire) begin
            next_fetch_pc <= redirect_target;
        end else if (alloc_fire) begin
            next_fetch_pc <= next_fetch_pc + 32'd4;
        end else begin
            next_fetch_pc <= next_fetch_pc; //hold
        end
    end

    //to buffer
    assign pc_write                 = alloc_fire;
    assign pc_write_slot            = head_ptr;
    assign pc_write_data            = next_fetch_pc;
    assign instruction_write        = response_fire;
    assign instruction_write_slot   = prv;
    assign present_slot             = issue_ptr;
    assign fetch_slot               = tail_ptr;
endmodule
