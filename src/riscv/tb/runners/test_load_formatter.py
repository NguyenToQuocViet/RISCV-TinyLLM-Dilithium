#------------------------------------------------------------------------------
# Module      : test_load_formatter
# Description : Pytest runner for the load formatter with Verilator.
# Author      : Codex
# Date        : 2026-10-23
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner

def test_load_formatter():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "load_formatter.sv",
        ],

        hdl_toplevel="load_formatter",
        build_dir=riscv_dir / "tb" / "sim_build" / "load_formatter",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="load_formatter",
        test_module="load_formatter_cocotb",
    )
