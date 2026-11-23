#------------------------------------------------------------------------------
# File        : trace_to_xlsx.py
# Description : Pack per-cycle trace CSVs of tb_perf into one xlsx, one sheet
#               per program, raw values of the redirect-related signals only
#               (the CSV keeps every signal). PC cells carry the objdump text.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-23
#------------------------------------------------------------------------------
# Use: trace_to_xlsx.py <out.xlsx> <objdump> <SHEET>:<trace.csv>:<prog.elf> ...

import csv
import re
import subprocess
import sys

from openpyxl import Workbook
from openpyxl.styles import Font

LIFE = "FQOR"   # 0 FREE, 1 QUEUED, 2 OUTSTANDING, 3 READY


def disasm(objdump, elf):
    out = subprocess.run([objdump, "-d", "--no-show-raw-insn", elf], check=True,
                         capture_output=True, text=True).stdout
    text = {}
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+(.*)", line)
        if m:
            text[int(m.group(1), 16)] = re.sub(r"\s+", " ", m.group(2).split("#")[0]).strip()
    return text


def view(asm):
    def pc(name):
        return lambda r: f"{int(r[name], 16):04x} {asm.get(int(r[name], 16), '')}"

    def raw(name):
        return lambda r: int(r[name]) if not r[name].startswith("0x") else f"{int(r[name], 16):04x}"

    return [
        ("cycle", raw("cycle")),
        ("instr_req", raw("instr_req")),
        ("instr_addr", pc("instr_addr")),
        ("instr_rvalid", raw("instr_rvalid")),
        ("killed_resp", raw("killed_resp")),
        ("life[0..2]", lambda r: "".join(LIFE[int(r[f"life{i}"])] for i in range(3))),
        ("killed[0..2]", lambda r: "".join(r[f"killed{i}"] for i in range(3))),
        ("fetch_valid", raw("fetch_valid")),
        ("fetch_pc", pc("fetch_pc")),
        ("if_id_flush", raw("if_id_flush")),
        ("if_id_reg_valid", raw("if_id_reg_valid")),
        ("if_id_reg_pc", pc("if_id_reg_pc")),
        ("id_ex_flush", raw("id_ex_flush")),
        ("id_ex_reg_valid", raw("id_ex_reg_valid")),
        ("id_ex_reg_pc", pc("id_ex_reg_pc")),
        ("redirect_fire", raw("redirect_fire")),
        ("redirect_target", raw("redirect_target")),
    ]


def main():
    out, objdump, specs = sys.argv[1], sys.argv[2], sys.argv[3:]
    wb = Workbook()
    wb.remove(wb.active)
    for spec in specs:
        name, csv_path, elf = spec.split(":")
        cols = view(disasm(objdump, elf))
        with open(csv_path) as f:
            f.readline()
            rows = list(csv.DictReader(f))
        ws = wb.create_sheet(name)
        ws.append(["values during the cycle, before the rising edge; "
                   "life: F free, Q queued, O outstanding, R ready; PC cells show the instruction at that "
                   "address even when the stage is not valid"])
        ws.append([h for h, _ in cols])
        for c in ws[2]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append([f(r) for _, f in cols])
        for i, (h, _) in enumerate(cols):
            letter = ws.cell(2, i + 1).column_letter
            ws.column_dimensions[letter].width = 26 if h.endswith(("pc", "addr")) else max(len(h), 6) + 1
        ws.freeze_panes = "B3"
    wb.save(out)
    print("xlsx", out, " ".join(f"{s.title}={s.max_row - 2}x{s.max_column}" for s in wb.worksheets))


if __name__ == "__main__":
    main()
