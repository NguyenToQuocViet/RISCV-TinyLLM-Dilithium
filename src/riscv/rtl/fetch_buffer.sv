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
    assign alloc_fire       = kill || (alloc_valid && (!full || tail_free));

    //kill edge
    logic kept_out;
    logic kept_q;
    logic [1:0] target_slot;

    assign kept_out     = outst && !response_fire;
    assign kept_q       = present_valid;
    assign target_slot  = kept_q ? next_slot(issue_ptr) : issue_ptr;

    //control state
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            head_ptr    <= '0;
            issue_ptr   <= '0;
            tail_ptr    <= '0;

            for (int slot = 0; slot < FETCH_DEPTH; slot++) begin
                life[slot]      <= LIFE_FREE;
                killed[slot]    <= 1'b0;
            end
        end else if (kill) begin
            //free every slot, then restore kept entries and the target
            for (int slot = 0; slot < FETCH_DEPTH; slot++) begin
                life[slot]      <= LIFE_FREE;
                killed[slot]    <= 1'b0;
            end

            if (kept_out) begin
                life[prv]       <= LIFE_OUTSTANDING;
                killed[prv]     <= 1'b1;
            end

            if (kept_q) begin
                life[issue_ptr]     <= request_fire ? LIFE_OUTSTANDING : LIFE_QUEUED;
                killed[issue_ptr]   <= 1'b1;
            end

            life[target_slot]   <= LIFE_QUEUED;
            killed[target_slot] <= 1'b0;

            head_ptr    <= next_slot(target_slot);
            tail_ptr    <= kept_out ? prv : issue_ptr;

            if (request_fire) begin
                issue_ptr   <= next_slot(issue_ptr);
            end
        end else begin
            if (response_fire) begin
                life[prv]   <= killed[prv] ? LIFE_FREE : LIFE_READY;
            end

            if (request_fire) begin
                life[issue_ptr] <= LIFE_OUTSTANDING;
                issue_ptr       <= next_slot(issue_ptr);
            end

            if (tail_free) begin
                life[tail_ptr]      <= LIFE_FREE;
                killed[tail_ptr]    <= 1'b0;
                tail_ptr            <= next_slot(tail_ptr);
            end

            //last: may reuse the slot freed on this edge
            if (alloc_fire) begin
                life[head_ptr]      <= LIFE_QUEUED;
                killed[head_ptr]    <= 1'b0;
                head_ptr            <= next_slot(head_ptr);
            end
        end
    end

    //payload (no reset)
    always_ff @(posedge clk) begin
        if (alloc_fire) begin
            pc[kill ? target_slot : head_ptr]   <= alloc_pc;
        end

        if (response_fire && !killed[prv] && !kill) begin
            instruction[prv]    <= response_data;
        end
    end
endmodule
