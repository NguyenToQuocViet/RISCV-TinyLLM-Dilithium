#------------------------------------------------------------------------------
# Module      : xp_monitors
# Description : Monitors M1..M7 (core-verification section 5.5) as pure rules on
#               one pre-edge sample per cycle, so self-tests can feed synthetic
#               samples. Each rule logs (edge, rule, detail).
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

PORTS = ("instr", "data")
REGS = ("if_id", "id_ex", "ex_mem", "mem_wb")
CONSTANTS = dict(instr_we=0, instr_be=0xF, instr_wdata=0, instr_rready=1, data_rready=1, ci_cmd_valid=0,
                 ci_cmd_op=0, ci_cmd_target=0, ci_cmd_desc=0, ex_mem_flush=0, mem_wb_flush=0)
RESET_CLEAR = ("if_id_reg_valid", "id_ex_reg_valid", "ex_mem_reg_valid", "mem_wb_reg_valid", "instr_req",
               "data_req", "mem_wait", "rf_write_fire", "redirect_fire")


class Monitors:
    def __init__(self):
        self.violations = []
        self.outstanding = {p: 0 for p in PORTS}
        self.prev = None

    def log(self, edge, rule, detail):
        self.violations.append((edge, rule, detail))

    def step(self, edge, s):
        # s: pre-edge sample (values the DUT sees at this rising edge)
        p = self.prev
        rst = s["rst_n"]
        for port in PORTS:
            req, gnt, rvalid = s[f"{port}_req"], s[f"{port}_gnt"], s[f"{port}_rvalid"]
            # M1 request stability: a waiting request keeps req and payload until gnt
            if p is not None and rst and p["rst_n"] and p[f"{port}_req"] and not p[f"{port}_gnt"]:
                fields = ("addr", "we", "be", "wdata")
                if not req or any(s[f"{port}_{f}"] != p[f"{port}_{f}"] for f in fields):
                    self.log(edge, "M1", port)
            if not rst:
                self.outstanding[port] = 0
                continue
            # M3 unexpected response, M2 outstanding limit
            if rvalid and s[f"{port}_rready"]:
                if self.outstanding[port] == 0:
                    self.log(edge, "M3", port)
                else:
                    self.outstanding[port] -= 1
            if req and gnt:
                self.outstanding[port] += 1
                if self.outstanding[port] > 1:
                    self.log(edge, "M2", port)
        # M4 no effect from an invalid entry
        if s["rf_write_fire"] and not s["mem_wb_reg_valid"]:
            self.log(edge, "M4", "rf_write_fire")
        if s["data_req"] and not s["ex_mem_reg_valid"]:
            self.log(edge, "M4", "data_req")
        if s["redirect_fire"] and not s["id_ex_reg_valid"]:
            self.log(edge, "M4", "redirect_fire")
        # M5 valid follows the condition table across the previous edge
        if p is not None:
            for r in REGS:
                if not p["rst_n"] or not rst:
                    exp = 0
                elif p[f"{r}_flush"]:
                    exp = 0
                elif p[f"{r}_stall"]:
                    exp = p[f"{r}_reg_valid"]
                else:
                    exp = p[f"{r}_valid_i"]
                if s[f"{r}_reg_valid"] != exp:
                    self.log(edge, "M5", r)
        # M6 constant outputs
        for name, value in CONSTANTS.items():
            if s[name] != value:
                self.log(edge, "M6", name)
        # M7 reset clear
        if not rst:
            for name in RESET_CLEAR:
                if s[name]:
                    self.log(edge, "M7", name)
        self.prev = s

    def rules(self):
        return [v[1] for v in self.violations]
