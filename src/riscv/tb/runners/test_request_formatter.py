#------------------------------------------------------------------------------
# Module      : test_request_formatter
# Description : Pytest runner for the request formatter with Verilator.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-23
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner

def test_request_formatter():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "request_formatter.sv",
        ],

        hdl_toplevel="request_formatter",
        build_dir=riscv_dir / "tb" / "sim_build" / "request_formatter",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="request_formatter",
        test_module="request_formatter_cocotb",
    )
