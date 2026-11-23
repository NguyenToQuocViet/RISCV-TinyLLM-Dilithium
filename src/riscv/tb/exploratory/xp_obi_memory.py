#------------------------------------------------------------------------------
# Module      : xp_obi_memory
# Description : One-port OBI memory model (core-verification section 5.2):
#               scripted grant delay and response latency, access log,
#               asynchronous flush on reset, injection hooks for self-tests.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer

SAMPLE_NS = 4  # sample point: 4 ns after the falling edge, 1 ns before the rising edge


def policy(values):
    # value per transaction index; the last value repeats; a callable is used as is
    if callable(values):
        return values
    values = list(values) if isinstance(values, (list, tuple)) else [values]
    return lambda i: values[min(i, len(values) - 1)]


class ObiMemory:
    def __init__(self, dut, port, base, size, fill, gnt_delay=0, latency=1):
        self.dut, self.port, self.base, self.size, self.fill = dut, port, base, size, fill
        self.words = {}
        self.gnt_delay = policy(gnt_delay)
        self.latency = policy(latency)
        self.log = []        # accepted requests: dict(edge, addr, we, be, wdata, rdata)
        self.responses = []  # delivered responses: dict(edge, rdata, unexpected)
        self.pending = None  # dict(rdata, left)
        self.waiting = 0     # edges with req=1, gnt=0 for the presented request
        self.index = 0       # accepted transaction count
        self.edge = 0
        self.inject = 0      # unexpected rvalid pulses still to drive
        self.inject_after_response = 0
        self.allow_second = False
        self.withhold = False
        self.never_grant = False
        self.sentinel = 0xBAD0_0001
        self._rvalid_now = 0
        self._unexpected_now = False

    def sig(self, name):
        return getattr(self.dut, f"{self.port}_{name}")

    def load(self, addr, words):
        for k, w in enumerate(words):
            self.words[addr + 4 * k] = w

    def read(self, addr):
        return self.words.get(addr & ~3, self.fill)

    def start(self):
        self.sig("gnt").value = 0
        self.sig("rvalid").value = 0
        self.sig("rdata").value = 0
        self.tasks = [cocotb.start_soon(self._run()), cocotb.start_soon(self._reset_watch())]

    def stop(self):
        for t in self.tasks:
            t.cancel()

    def flush(self):
        self.pending = None
        self.waiting = 0
        self.inject = 0
        self.inject_after_response = 0
        self._rvalid_now = 0
        self.sig("rvalid").value = 0
        self.sig("gnt").value = 0

    async def _reset_watch(self):
        while True:
            await FallingEdge(self.dut.rst_n)
            self.flush()

    def _drive(self):
        # outputs for the coming rising edge, decided at the falling edge
        rst = int(self.dut.rst_n.value)
        self._unexpected_now = False
        rvalid, rdata = 0, 0
        if rst and self.pending and self.pending["left"] == 1 and not self.withhold:
            rvalid, rdata = 1, self.pending["rdata"]
        elif rst and self.inject:
            rvalid, rdata, self._unexpected_now = 1, self.sentinel, True
            self.inject -= 1
        free = self.pending is None or rvalid == 1 or self.allow_second
        gnt = int(rst and free and not self.never_grant and self.waiting >= self.gnt_delay(self.index))
        self.sig("gnt").value = gnt
        self.sig("rvalid").value = rvalid
        if rvalid:
            self.sig("rdata").value = rdata
        self._rvalid_now = rvalid

    def _snapshot(self):
        # what the DUT sees at the coming rising edge (inputs change only at falling edges)
        return {f: int(self.sig(f).value) for f in ("req", "gnt", "addr", "we", "be", "wdata", "rdata")}

    def _commit(self, snap):
        # the edge update; rst_n is read at the edge itself, so a reset that falls
        # after the sample point still cancels the handshake
        self.edge += 1
        if not int(self.dut.rst_n.value):
            self.waiting = 0
            return
        req, gnt = snap["req"], snap["gnt"]
        rvalid = self._rvalid_now
        if rvalid:
            self.responses.append(dict(edge=self.edge, rdata=snap["rdata"], unexpected=self._unexpected_now))
            if not self._unexpected_now:
                self.pending = None
                if self.inject_after_response:
                    self.inject += self.inject_after_response
                    self.inject_after_response = 0
        elif self.pending:
            self.pending["left"] -= 1
        if req and gnt:
            addr, we, be, wdata = snap["addr"], snap["we"], snap["be"], snap["wdata"]
            rdata = self.read(addr)
            if we:
                old = self.read(addr)
                mask = sum(0xFF << (8 * b) for b in range(4) if (be >> b) & 1)
                self.words[addr & ~3] = (old & ~mask) | (wdata & mask)
            self.log.append(dict(edge=self.edge, addr=addr, we=we, be=be, wdata=wdata, rdata=rdata))
            self.pending = dict(rdata=rdata, left=self.latency(self.index))
            self.index += 1
            self.waiting = 0
        elif req:
            self.waiting += 1

    async def _run(self):
        while True:
            await FallingEdge(self.dut.clk)
            self._drive()
            await Timer(SAMPLE_NS, unit="ns")
            snap = self._snapshot()
            await RisingEdge(self.dut.clk)
            self._commit(snap)
