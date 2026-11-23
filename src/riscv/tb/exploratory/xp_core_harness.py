#------------------------------------------------------------------------------
# Module      : xp_core_harness
# Description : core_top harness (core-verification sections 5.4, 5.6, 7):
#               two ObiMemory models, per-cycle trace, monitors M1..M7,
#               fetch range check, completion ABI and three watchdogs.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer

from xp_monitors import Monitors
from xp_obi_memory import ObiMemory, SAMPLE_NS
from xp_rv32i import NOP, addi, jal, lui, sw

CODE_BASE, CODE_SIZE = 0x0000_0000, 0x1_0000
DATA_BASE, DATA_SIZE = 0x0001_0000, 0x1_0000
TEST_STATUS = 0x0001_FFFC
DATA_FILL = 0xD0D0_D0D0

PORT_FIELDS = ("req", "gnt", "addr", "we", "be", "wdata", "rvalid", "rready", "rdata")
NETS = ("if_id_reg_valid", "if_id_reg_pc", "if_id_reg_instruction", "id_ex_reg_valid", "id_ex_reg_pc",
        "id_ex_reg_imm", "id_ex_reg_rd", "ex_mem_reg_valid", "ex_mem_reg_ex_result", "ex_mem_reg_rd",
        "ex_mem_reg_mem_en", "mem_wb_reg_valid", "mem_wb_reg_rd", "mem_wb_reg_ex_result",
        "mem_wb_reg_load_result", "mem_wait", "rf_write_fire", "redirect_fire", "redirect_target",
        "advance_allowed", "fetch_accept", "fetch_valid", "fetch_pc", "wb_data", "load_result",
        "if_id_stall", "if_id_flush", "id_ex_stall", "id_ex_flush", "ex_mem_stall", "ex_mem_flush",
        "mem_wb_stall", "mem_wb_flush", "ci_cmd_valid", "ci_cmd_op", "ci_cmd_target", "ci_cmd_desc",
        "id_ex_reg_mem_en", "id_ex_reg_mem_write", "id_ex_reg_reg_write", "id_ex_reg_control_flow",
        "ex_mem_reg_reg_write", "ex_mem_reg_mem_write", "mem_wb_reg_reg_write", "mem_wb_reg_wb_src")
REG_INSTANCES = ("if_id", "id_ex", "ex_mem", "mem_wb")
_active = []


def finish(status=1):
    # status store to TEST_STATUS, 8 NOP padding, self-loop (core-verification section 6)
    return [addi(31, 0, status), lui(30, 0x20), sw(31, -4, 30)] + [NOP] * 8 + [jal(0, 0)]


class Core:
    def __init__(self, dut, program, data=None, igrant=0, ilat=1, dgrant=0, dlat=1,
                 grant_limit=200, response_limit=200, total_limit=3000, keep_trace=True):
        self.dut = dut
        self.keep_trace = keep_trace  # False for long SW runs: monitors still run, no per-cycle history
        self.imem = ObiMemory(dut, "instr", CODE_BASE, CODE_SIZE, 0x0000_0000, igrant, ilat)
        self.dmem = ObiMemory(dut, "data", DATA_BASE, DATA_SIZE, DATA_FILL, dgrant, dlat)
        self.imem.load(CODE_BASE, program)
        for addr, word in (data or {}).items():
            self.dmem.words[addr] = word
        self.mon = Monitors()
        self.trace = []  # pre-edge sample per rising edge, index = edge number - 1
        self.edge = 0    # rising edges observed since boot
        self.limits = dict(grant=grant_limit, response=response_limit, total=total_limit)
        self.status = None  # set by the observer: "pass", "fail", or a failure name
        self.status_store = None
        self.complete_edge = None
        self.fail_edge = None
        self._wait = {p: 0 for p in ("instr", "data")}
        self._resp_age = {p: 0 for p in ("instr", "data")}
        self._out = {p: 0 for p in ("instr", "data")}
        self.clock = None

    # ---- setup -------------------------------------------------------------
    def stop(self):
        self.imem.stop()
        self.dmem.stop()
        self.observer.cancel()
        self.clock.stop()

    async def boot(self, reset_edges=2, **inputs):
        dut = self.dut
        await Timer(1, unit="ns")  # leave a ReadOnly phase of a previous run
        while _active:
            _active.pop().stop()
        dut.rst_n.value = 0
        dut.ci_cmd_ready.value = inputs.get("ci_cmd_ready", 0)
        dut.ci_cmd_result.value = inputs.get("ci_cmd_result", 0)
        dut.irq_external.value = inputs.get("irq_external", 0)
        self.imem.start()
        self.dmem.start()
        self.clock = Clock(dut.clk, 10, unit="ns")
        self.clock.start(start_high=False)
        self.observer = cocotb.start_soon(self._observe())
        _active.append(self)
        for _ in range(reset_edges):
            await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.rst_n.value = 1

    # ---- observation -------------------------------------------------------
    def sample(self):
        dut = self.dut
        s = {"rst_n": int(dut.rst_n.value)}
        for port in ("instr", "data"):
            for f in PORT_FIELDS:
                s[f"{port}_{f}"] = int(getattr(dut, f"{port}_{f}").value)
        for net in NETS:
            s[net] = int(getattr(dut, net).value)
        for r in REG_INSTANCES:
            s[f"{r}_valid_i"] = int(getattr(dut, f"{r}_reg").valid_i.value)
        return s

    async def _observe(self):
        while True:
            await FallingEdge(self.dut.clk)
            await Timer(SAMPLE_NS, unit="ns")
            s = self.sample()
            if self.keep_trace:
                self.trace.append(s)
            self.edge += 1
            edge = self.edge
            self.mon.step(edge, s)
            if self.status is None:
                self._checks(edge, s)

    def _checks(self, edge, s):
        if not s["rst_n"]:
            self._wait = {p: 0 for p in self._wait}
            self._resp_age = {p: 0 for p in self._resp_age}
            self._out = {p: 0 for p in self._out}
            return
        # fetch range check (MEMV), independent of gnt
        if s["instr_req"] and not (CODE_BASE <= s["instr_addr"] < CODE_BASE + CODE_SIZE):
            self.status = "range violation"
            self.fail_edge = edge
            return
        for p in ("instr", "data"):
            self._wait[p] = self._wait[p] + 1 if s[f"{p}_req"] and not s[f"{p}_gnt"] else 0
            if self._wait[p] > self.limits["grant"]:
                self.status = "grant limit"
            if s[f"{p}_rvalid"] and self._out[p]:
                self._out[p] -= 1
            if s[f"{p}_req"] and s[f"{p}_gnt"]:
                self._out[p] += 1
            self._resp_age[p] = self._resp_age[p] + 1 if self._out[p] else 0
            if self._resp_age[p] > self.limits["response"]:
                self.status = "response limit"
        if edge > self.limits["total"]:
            self.status = "total-cycle limit"
        # completion ABI: identify the status store at acceptance, complete on its response
        if self.status_store is not None and s["data_rvalid"]:
            value = self.status_store
            self.status_store = None
            self.complete_edge = edge
            self.status = {1: "pass", 2: "fail"}.get(value, "convention violation")
            return
        if s["data_req"] and s["data_gnt"] and s["data_we"] and (s["data_addr"] & ~3) == TEST_STATUS:
            if s["data_be"] != 0xF:
                self.status = "convention violation"
            else:
                self.status_store = s["data_wdata"]

    # ---- running -----------------------------------------------------------
    async def run(self, max_edges=None):
        # wait for completion or a watchdog, then let the completion edge settle
        limit = max_edges or self.limits["total"] + 10
        for _ in range(limit):
            if self.status is not None:
                break
            await FallingEdge(self.dut.clk)
        await ReadOnly()
        return self.status

    async def cycles(self, n):
        for _ in range(n):
            await FallingEdge(self.dut.clk)

    def word(self, addr):
        return self.dmem.read(addr)

    async def until(self, cond, max_edges=500):
        # stop 4.5 ns after a falling edge (0.5 ns before the rising edge) once cond(sample) holds
        for _ in range(max_edges):
            await FallingEdge(self.dut.clk)
            await Timer(SAMPLE_NS, unit="ns")
            await Timer(500, unit="ps")
            if cond(self.trace[-1]):
                return len(self.trace)
        raise AssertionError("scenario anchor not reached")

    def data_edges(self):
        # (accept edge, response edge) per data transaction, in order
        resp = [r["edge"] for r in self.dmem.responses if not r["unexpected"]]
        return [(a["edge"], resp[k] if k < len(resp) else None) for k, a in enumerate(self.dmem.log)]

    def retire(self):
        # rd of every rf_write_fire edge, in order
        return [s["mem_wb_reg_rd"] for s in self.trace if s["rst_n"] and s["rf_write_fire"]]

    # ---- trace queries -----------------------------------------------------
    def edges(self, **cond):
        # edge numbers whose pre-edge sample matches every name=value
        return [k + 1 for k, s in enumerate(self.trace) if all(s[n] == v for n, v in cond.items())]

    def at(self, edge):
        return self.trace[edge - 1]
