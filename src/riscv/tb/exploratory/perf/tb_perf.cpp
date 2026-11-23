//------------------------------------------------------------------------------
// File        : tb_perf.cpp
// Description : Verilator benchmark bench for core_top. Two ideal OBI memories
//               (gnt=1, response one cycle later, one outstanding), MMIO timer,
//               putchar and TEST_STATUS, plus pipeline event counters read from
//               internal nets. Stats cover the window between the first and the
//               last timer read.
// Author      : Claude Code (Anthropic)
// Date        : 2026-11-20
//------------------------------------------------------------------------------

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "Vcore_top.h"
#include "Vcore_top___024root.h"
#include "verilated.h"

static const uint32_t MEM_SIZE    = 0x20000;
static const uint32_t CODE_END    = 0x10000;   // instr port: 0x0 .. 0xFFFF
static const uint32_t DATA_BASE   = 0x10000;   // data port: 0x1_0000 .. 0x1_FFFF
static const uint32_t MMIO_TIMER  = 0x1FFF4;   // read: cycle counter
static const uint32_t MMIO_PUTC   = 0x1FFF8;   // write: low byte to stdout
static const uint32_t MMIO_STATUS = 0x1FFFC;   // write: end of run

struct Counters {
    uint64_t cycles = 0, retired = 0, load_use = 0, mem_wait = 0, redirects = 0, id_empty = 0, d_access = 0;
};

static uint8_t mem[MEM_SIZE];

static uint32_t rd32(uint32_t a) {
    a &= ~3u;
    return mem[a] | (mem[a + 1] << 8) | (mem[a + 2] << 16) | ((uint32_t)mem[a + 3] << 24);
}

static void print_stats(const char *tag, const Counters &c) {
    uint64_t lost = c.cycles - c.retired;
    uint64_t rest = lost - c.load_use - c.mem_wait;
    printf("%s cycles=%llu retired=%llu cpi=%.4f lost=%llu load_use=%llu mem_wait=%llu "
           "redirects=%llu redirect_fetch_other=%llu cyc_per_redirect=%.3f id_empty=%llu d_access=%llu\n",
           tag, (unsigned long long)c.cycles, (unsigned long long)c.retired,
           c.retired ? (double)c.cycles / c.retired : 0.0, (unsigned long long)lost,
           (unsigned long long)c.load_use, (unsigned long long)c.mem_wait,
           (unsigned long long)c.redirects, (unsigned long long)rest,
           c.redirects ? (double)rest / c.redirects : 0.0, (unsigned long long)c.id_empty,
           (unsigned long long)c.d_access);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <image.bin> [max_cycles] [trap_pc ...]\n", argv[0]);
        return 3;
    }
    uint64_t max_cycles = argc > 2 ? strtoull(argv[2], nullptr, 0) : 200000000ull;
    // compiler trap PCs (ebreak on dead paths): any one reaching EX is an error
    std::vector<uint32_t> trap_pcs;
    for (int i = 3; i < argc; ++i) trap_pcs.push_back((uint32_t)strtoul(argv[i], nullptr, 0));

    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 3; }
    size_t n = fread(mem, 1, MEM_SIZE, f);
    fclose(f);
    if (n == 0) { fprintf(stderr, "empty image\n"); return 3; }

    Verilated::commandArgs(argc, argv);
    Vcore_top *top = new Vcore_top;
    auto *r = top->rootp;

    // reset: 5 cycles with all responses low
    top->clk = 0; top->rst_n = 0;
    top->instr_gnt = 0; top->instr_rvalid = 0; top->instr_rdata = 0;
    top->data_gnt = 0; top->data_rvalid = 0; top->data_rdata = 0;
    top->ci_cmd_ready = 0; top->ci_cmd_result = 0; top->irq_external = 0;
    top->eval();
    for (int i = 0; i < 5; ++i) { top->clk = 1; top->eval(); top->clk = 0; top->eval(); }
    top->rst_n = 1;
    top->eval();

    bool i_pend = false, d_pend = false;
    uint32_t i_rdata = 0, d_rdata = 0;
    Counters all, at_first, at_last;
    int timer_reads = 0;
    int status = -1;
    int err = 0;

    while (all.cycles < max_cycles) {
        // drive this cycle's inputs, then let the combinational outputs settle
        top->clk = 0;
        top->instr_gnt = 1; top->instr_rvalid = i_pend; top->instr_rdata = i_rdata;
        top->data_gnt = 1;  top->data_rvalid = d_pend;  top->data_rdata = d_rdata;
        top->eval();

        // event counters for the coming edge
        bool adv = r->core_top__DOT__advance_allowed;
        bool mwait = r->core_top__DOT__mem_wait;
        all.cycles++;
        if (r->core_top__DOT__mem_wb_reg_valid && adv) all.retired++;
        if (mwait) all.mem_wait++;
        if (r->core_top__DOT__hcu__DOT__load_use && !mwait) all.load_use++;
        if (r->core_top__DOT__redirect_fire) all.redirects++;
        if (!r->core_top__DOT__if_id_reg_valid) all.id_empty++;

        if (r->core_top__DOT__id_ex_reg_valid)
            for (uint32_t t : trap_pcs)
                if (r->core_top__DOT__id_ex_reg_pc == t) {
                    fprintf(stderr, "ERROR trap pc 0x%08x reached EX at cycle %llu\n", t,
                            (unsigned long long)all.cycles);
                    err = 1;
                }
        if (err) break;

        // responses are consumed this edge (rready is tied high in BASE)
        if ((i_pend && !top->instr_rready) || (d_pend && !top->data_rready)) {
            fprintf(stderr, "ERROR rready low with a pending response at cycle %llu\n",
                    (unsigned long long)all.cycles);
            err = 1; break;
        }
        i_pend = false; d_pend = false;

        if (top->instr_req) {
            uint32_t a = top->instr_addr;
            if (a >= CODE_END) {
                fprintf(stderr, "ERROR fetch outside code region addr=0x%08x cycle=%llu\n",
                        a, (unsigned long long)all.cycles);
                err = 1; break;
            }
            i_pend = true; i_rdata = rd32(a);
        }
        if (top->data_req) {
            uint32_t a = top->data_addr;
            if (a < DATA_BASE || a >= MEM_SIZE) {
                fprintf(stderr, "ERROR data access outside data region addr=0x%08x cycle=%llu\n",
                        a, (unsigned long long)all.cycles);
                err = 1; break;
            }
            uint32_t w = a & ~3u;
            d_pend = true; d_rdata = 0;
            all.d_access++;
            if (top->data_we) {
                uint32_t wd = top->data_wdata, be = top->data_be;
                if (w == MMIO_PUTC) {
                    for (int b = 0; b < 4; ++b)
                        if ((be >> b) & 1) { putchar((wd >> (8 * b)) & 0xFF); break; }
                } else if (w == MMIO_STATUS) {
                    status = (int)wd;
                } else {
                    for (int b = 0; b < 4; ++b)
                        if ((be >> b) & 1) mem[w + b] = (wd >> (8 * b)) & 0xFF;
                }
            } else if (w == MMIO_TIMER) {
                d_rdata = (uint32_t)all.cycles;
                at_last = all;
                if (timer_reads++ == 0) at_first = all;
            } else {
                d_rdata = rd32(w);
            }
        }

        top->clk = 1;
        top->eval();
        if (status >= 0) break;
    }
    fflush(stdout);

    if (!err && status < 0) {
        fprintf(stderr, "ERROR watchdog: no TEST_STATUS after %llu cycles\n",
                (unsigned long long)all.cycles);
        err = 1;
    }
    printf("\nTB_END status=%d timer_reads=%d trap_pcs_watched=%zu\n", status, timer_reads,
           trap_pcs.size());
    print_stats("TB_TOTAL", all);
    if (timer_reads >= 2) {
        Counters w;
        w.cycles = at_last.cycles - at_first.cycles;
        w.retired = at_last.retired - at_first.retired;
        w.load_use = at_last.load_use - at_first.load_use;
        w.mem_wait = at_last.mem_wait - at_first.mem_wait;
        w.redirects = at_last.redirects - at_first.redirects;
        w.id_empty = at_last.id_empty - at_first.id_empty;
        w.d_access = at_last.d_access - at_first.d_access;
        print_stats("TB_WINDOW", w);
    }
    top->final();
    delete top;
    if (err) return 3;
    return status == 2 ? 2 : (status == 1 || status == 0) ? 0 : 1;
}
