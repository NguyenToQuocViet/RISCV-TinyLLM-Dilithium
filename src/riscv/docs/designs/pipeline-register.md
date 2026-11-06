# Pipeline Register — Block Design

**Status:** Proposed
**Owner:** Nguyễn Tô Quốc Việt — RISC-V subsystem owner. The decisions PR-O1..PR-O8 in section 9 are the Owner's of 2026-11-06.
**Parent contract:** [pipeline-register local control](5-stage-baseline-core.md#pipeline-register-local-control) (PR-D1),
[reset architecture](5-stage-baseline-core.md#reset-architecture), and the boundary sections that name each register's
fields: [IF/ID](5-stage-baseline-core.md#ifid-boundary), [ID/EX](5-stage-baseline-core.md#idex-boundary),
[EX/MEM](5-stage-baseline-core.md#exmem-boundary-and-data-request-ownership) and
[MEM data formatting and MEM/WB](5-stage-baseline-core.md#mem-data-formatting-and-memwb-boundary). Control sources:
[hazard control unit](hazard-control-unit.md) (per-register `stall` and `flush`). The per-register carry rule for
the EX/MEM and MEM/WB metadata is in [memory stage](memory-stage.md).
**RTL mapping:** four modules, one per file: `if_id_pipeline` (`rtl/if_id_pipeline.sv`), `id_ex_pipeline`
(`rtl/id_ex_pipeline.sv`), `ex_mem_pipeline` (`rtl/ex_mem_pipeline.sv`) and `mem_wb_pipeline` (`rtl/mem_wb_pipeline.sv`).
This document is neither implementation nor verification evidence.

## 1. Purpose and boundary

One shared format for the four pipeline registers of the baseline. The format is a generic template: it defines
ports, the PR-D1 behavior and the code shape. It does not define any register's fields.

- Success criterion: each register is an instance of this template, and its stored valid and payload follow the
  PR-D1 table in section 5.
- Non-goals: field lists and field types (inherited from the boundary sections above, PR-O7); the HCU equations
  (see [hazard control unit](hazard-control-unit.md)); the core top, which instantiates the four modules and ties
  unused controls; any BASE amendment.
- Producers and consumers: the source stage drives `valid_i` and `<field>_i`; the destination stage reads
  `valid_o` and `<field>_o`; the HCU drives `stall` and `flush`.
- Inherited by reference: the PR-D1 priority, the reset convention and the per-boundary field authority. Local
  refinements defined here: the generic port groups, the `capture` term and the two-block code shape.

## 2. Interface contract

### Clock, reset, and configuration

- `clk`: rising edge. Only `valid_reg` and `payload_reg` are clocked; there is no other state.
- `rst_n`: active-low core reset. `valid_reg` is cleared asynchronously on its assertion, under the
  [reset architecture](5-stage-baseline-core.md#reset-architecture). `payload_reg` has no reset.
- No parameters. Widths come from the field types (section 2, ports).

### Ports and payloads

| Signal | Direction | Type/width | Meaning | Valid when |
| --- | --- | --- | --- | --- |
| `clk` | input | `logic` | Register clock | Always |
| `rst_n` | input | `logic` | Core reset, active low | Always |
| `stall` | input | `logic` | Keep stored valid and payload (from the HCU) | Always |
| `flush` | input | `logic` | Clear stored valid; payload retained (from the HCU) | Always |
| `valid_i` | input | `logic` | Source stage holds a live entry | Always |
| `<field>_i` | input | producer's port type | Source-stage value of the field | Meaningful when `valid_i=1` |
| `valid_o` | output | `logic` | Stored entry is live | Always |
| `<field>_o` | output | same as `<field>_i` | Stored value of the field | Meaningful when `valid_o=1` |

Port groups appear in this order, each with its comment: system (`clk`, `rst_n`), hcu (`stall`, `flush`), source
stage (`valid_i`, then `<field>_i`), destination stage (`valid_o`, then `<field>_o`). Each `<field>_o` has the type
and width of its `<field>_i`, and that type is the producer's port type, enums included (PR-O2). There is one
`<field>_i`/`<field>_o` pair per field; the field list is not in this document (PR-O7).

### Transfer and timing rules

- `valid_o` and `<field>_o` change only at the rising clock edge, or asynchronously on reset for `valid_o`.
- The outputs are registered: no output depends combinationally on an input in the same cycle.
- `stall` and `flush` are sampled at the same edge as `valid_i` and `<field>_i`. Their sources are outside this
  block; section 9 records the core-top ties.

## 3. Internal organization

Two storage blocks, one shared enable term. The generic template below is the shape of `rtl/if_id_pipeline.sv` with
the header removed and the field placeholders substituted. The IF/ID file has two fields, so it has two field lines
in each port group and in the capture line; the template shows one pair, and each field repeats its pair.

```systemverilog
module <stage>_pipeline
    import riscv_pkg::*;
(
    //system interface
    input logic clk,
    input logic rst_n,

    //hcu interface
    input logic stall,
    input logic flush,

    //<source> interface
    input logic valid_i,
    input <type> <field>_i,

    //<destination> interface
    output logic valid_o,
    output <type> <field>_o
);
    logic capture;

    assign capture = valid_i && !stall && !flush;

    always_ff @(posedge clk or negedge rst_n) begin : valid_reg
        if (!rst_n) begin
            valid_o <= 1'b0;
        end else if (flush) begin
            valid_o <= 1'b0;
        end else if (stall) begin
            valid_o <= valid_o; //hold
        end else begin
            valid_o <= valid_i;
        end
    end

    //payload has no reset, PR-D1
    always_ff @(posedge clk) begin : payload_reg
        if (capture) begin
            <field>_o <= <field>_i;
        end
    end
endmodule
```

`<type>` is the producer's port type, taken from the boundary section that owns the field. This document does not
restate it (PR-O7).

Storage is direct: `<field>_o` is the register itself, with no internal copy and no `assign` to the output (PR-O3).
`valid_o` is the only reset state. `capture` is the only intermediate signal (PR-O5). Both `stall` and `flush` exist on
all four modules (PR-O6), even where the core top ties `flush` to 0.

## 4. State and ownership

| State/storage | Meaning and owner | Update event | Hold rule | Reset value or no-reset rationale |
| --- | --- | --- | --- | --- |
| `valid_o` | Control: the stored entry is live; this register | Rising edge (`valid_reg`) | Held when `stall=1` and `flush=0` | Cleared asynchronously by `rst_n=0` |
| `<field>_o` | Payload of the stored entry; this register | Rising edge when `capture=1` | Held whenever `capture=0` | No reset (PR-D1) |

Ownership: each register owns its own `valid_o` and payload. The source stage owns `valid_i` and `<field>_i` only for
the cycle they are presented. A consumer may use `<field>_o` only when `valid_o=1`. The payload of a dead entry has
no defined value:

- At power-up, before the first capture, it is unknown.
- After `flush`, it retains the last captured value, which is defined but not meaningful.
- After reset, `payload_reg` is not gated by `rst_n`. If `capture=1` at an edge during reset, the payload loads; no
  consumer may use it, because `valid_o` is 0.

Consumers therefore qualify every effect with `valid_o`. The cost of the design is this: a consumer that omits the
qualifier can act on stale or unknown payload. Section 8 checks for this.

## 5. Behavioral and next-state rules

Section 5 is the PR-D1 table of [pipeline-register local control](5-stage-baseline-core.md#pipeline-register-local-control),
restated against the two storage blocks. The first matching row decides. The `capture` term is
`valid_i && !stall && !flush`.

| First applicable condition | `valid_reg` branch | Stored valid next | `payload_reg` | Stored payload next |
| --- | --- | --- | --- | --- |
| Reset active (`rst_n=0`) | `if (!rst_n)` | 0, asynchronously | no reset; enable is `capture` | Not reset; loads only if `capture=1` at an edge |
| `flush=1` | `else if (flush)` | 0 | `capture=0` | Retain |
| `stall=1` (`flush=0`) | `else if (stall)` | `valid_o` (hold) | `capture=0` | Retain |
| `valid_i=0` (`stall=0`, `flush=0`) | `else` | `valid_i` = 0 | `capture=0` | Retain |
| Otherwise | `else` | `valid_i` = 1 | `capture=1` | Capture `<field>_i` |

Each row matches PR-D1 exactly. Combined cases:

- **Flush and stall together:** the `flush` branch precedes the `stall` branch, so `valid_o` becomes 0. The payload
  is retained, because `capture=0`. This is PR-D1's "simultaneous flush and stall invalidate it".
- **Reset with flush or stall:** the reset branch precedes both, so `valid_o` is 0 whatever `flush` and `stall` are.
  The payload enable is still `capture`, which is why the reset row says "loads only if `capture=1`".
- **Invalid entry with stall:** `stall` has priority over `valid_i`. A stored live entry is held even when the source
  presents `valid_i=0`.

Under the PR-D1 table, every combination of `stall` and `flush` is either a hold, a clear, or a capture. No row
produces a stored valid of 1 while `flush=1`.

## 6. Reset, cancellation, and exceptional conditions

- **Reset.** `valid_o` clears asynchronously. The payload is not reset, so after reset a stored payload is
  unspecified until its first capture. The reset convention and any selective-reset rule are in the
  [reset architecture](5-stage-baseline-core.md#reset-architecture).
- **Flush (cancellation).** `flush` discards the stored entry by clearing `valid_o`. The payload is retained,
  not zeroed, so the discarded value stays in the register until the next capture. Nothing downstream may read it
  without `valid_o`.
- **Flush and the payload enable.** `capture` contains `!flush`, so `flush` reaches the enable of `payload_reg`.
  In the core top the HCU drives `flush` for IF/ID from `redirect_fire` (`if_id_flush = redirect_fire`), and for
  ID/EX from `redirect_fire` or a load-use with no MEM wait (`id_ex_flush`, [hazard control unit](hazard-control-unit.md#2-interface-contract)).
  Both therefore reach the payload enable of their register. This is a fact about the wiring, not a timing target.
- **Preconditions.** This block assumes nothing about `stall` and `flush` beyond their sampled values. The HCU
  preconditions P1–P3 in [hazard control unit](hazard-control-unit.md#5-behavioral-and-next-state-rules) are the
  source's concern.

## 7. Representative examples or cycle traces

Edge-level traces. `A` and `B` are payload values; `—` is a value that is not used.

| Cycle/edge | Inputs/events | State before (`valid_o`, payload) | Action | State after |
| --- | --- | --- | --- | --- |
| E1 | `valid_i=1`, `stall=0`, `flush=0`, `<field>_i=A` | (0, unknown) | Capture | (1, A) |
| E2 | `valid_i=1`, `stall=1`, `flush=0`, `<field>_i=B` | (1, A) | Hold valid; payload retained | (1, A) |
| E3 | `valid_i=0`, `stall=0`, `flush=0` | (1, A) | Clear valid; payload retained | (0, A) |
| E4 | `valid_i=1`, `flush=1`, `stall=1`, `<field>_i=B` | (1, A) | Flush beats stall: clear valid; payload retained | (0, A) |
| E5 | `valid_i=1`, `flush=0`, `stall=0`, `<field>_i=B` | (0, A) | Capture | (1, B) |
| E6 | `rst_n` falls asynchronously, `valid_i=1`, `stall=0`, `flush=0`, `<field>_i=B` | (1, B) | Clear valid asynchronously; payload enable is `capture`, which is 1 | (0, B) |

E3 shows that a bubble from upstream clears valid and keeps the old payload. E4 shows that flush beats stall, the
PR-D1 ordering. E6 shows that the payload is not gated by reset, so the payload may change during reset when `capture`
is high; `valid_o` is 0 either way. Examples illustrate the rules in section 5; they do not add rules.

## 8. Verification obligations

All rows are planned checks.

| Requirement/invariant | Stimulus or scenario | Expected observation |
| --- | --- | --- |
| PR-D1: flush beats stall | `flush=1` and `stall=1` on an edge with stored valid 1 | `valid_o=0`; payload unchanged |
| PR-D1: reset overrides both | `rst_n=0` with each of `flush`, `stall` at 0 and 1 | `valid_o=0`; payload not reset (may change only through `capture`) |
| PR-D1: invalid capture | `valid_i=0`, `stall=0`, `flush=0` on an edge with stored valid 1 | `valid_o=0`; payload unchanged |
| PR-D1: stall retains | `stall=1`, `flush=0`, `valid_i=1`, `<field>_i` differs from stored | `valid_o` and payload unchanged |
| PR-D1: flush retains payload | `flush=1`, `stall=0`, `valid_i=1`, `<field>_i` differs from stored | `valid_o=0`; payload unchanged |
| PR-D1: capture | `valid_i=1`, `stall=0`, `flush=0` | `valid_o=1`; payload equals `<field>_i` |
| Payload qualification (section 4) | Random initial payload at power-up, with `valid_o=0` on the first cycles; run through the core with bubbles | No architectural effect from a dead entry; a consumer that ignores `valid_o` produces a mismatch against the reference model (falsifies the qualifier) |
| Integration: per-boundary arbitration | Core-level run with the HCU driving `stall`/`flush` per register | Each boundary's observed stall and flush match the HCU's table (see [hazard control unit](hazard-control-unit.md#8-verification-obligations)) |

Expected values follow from section 5 and PR-D1, not from the RTL. The random-payload row is a planned check
proposed for the Owner to adopt; section 9 keeps it OPEN.

No committed test exists for these modules.

## 9. Rationale and open decisions

Settled by the Owner, 2026-11-06:

- **PR-O1. Four modules.** `if_id_pipeline`, `id_ex_pipeline`, `ex_mem_pipeline`, `mem_wb_pipeline`, one per file, not
  one parameterized module. All four follow section 3.
- **PR-O2. Generic interface.** Port groups in the order of section 2; `<field>_o` has the type of `<field>_i`,
  enums included.
- **PR-O3. Stored directly.** No internal copy of each field and no `assign` to the outputs.
- **PR-O4. Two `always_ff` per module.** `valid_reg` on `posedge clk or negedge rst_n` with the chain reset, flush,
  stall (explicit hold). `payload_reg` on `posedge clk` only, no reset, one `if (capture)` with every field and no
  hold lines. Fields sharing one enable form one block.
- **PR-O5. Capture.** One intermediate signal, `capture = valid_i && !stall && !flush`.
- **PR-O6. Both controls on all four.** Every module has `stall` and `flush`, even where the core top ties `flush` to 0.
  The EX/MEM and MEM/WB `flush` inputs are never 1 in BASE; the HCU has no output for them
  ([hazard control unit](hazard-control-unit.md#2-interface-contract)).
- **PR-O7. Field lists stay out.** This document names no field. The boundary sections above are the authority.
- **PR-O8. Reference.** The format descends from an older project's pipeline register, changed to meet PR-D1. The
  design reasons for the differences that matter:
  - A `valid` bit replaces payload zeroing as the bubble encoding, so the payload needs no reset and no zeroing.
  - Because the payload is not cleared, every side effect must be qualified by `valid` (section 4).

Local reasons:

- The shared template keeps the four registers identical, so one review covers all four. The cost is that
  `flush` is present on the two registers whose flush is always 0 in BASE; PR-O6 accepts that.

Open:

- **OPEN: BASE EX/MEM minimum list is shorter than memory-stage.md.** The BASE EX/MEM minimum state does not list one
  metadata field that [memory stage](memory-stage.md), which is Accepted and binding, carries through EX/MEM and
  MEM/WB. This is a text gap in BASE only. Consequence: none for this block; the BASE list is to be aligned at the
  next BASE amendment. Responsible owner: Việt.
- **OPEN: random-payload check.** Section 8 lists a random initial payload check as a planned check, proposed for the
  Owner to adopt. No BASE record states it. Consequence: if it is not adopted, the payload qualification row has no
  evidence. Options: (a) adopt it in BASE's verification plan; (b) keep it as a planned check only. Recommendation:
  (a), since the cost in section 4 comes from the payload not being reset. Responsible owner: Việt.

Can proceed independently: the template (PR-O1..PR-O8) and the PR-D1 rows in section 5 need no further decision. The
traces in section 7 illustrate section 5 and are not a separate contract. No committed test exists for these modules.
Blocked: any readiness claim for the core top and any test of these modules.
