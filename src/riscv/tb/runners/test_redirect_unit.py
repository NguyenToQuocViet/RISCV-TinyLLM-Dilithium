#------------------------------------------------------------------------------
# Module      : test_redirect_unit
# Description : Pytest runner for the redirect unit with Verilator.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-19
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner

def test_redirect_unit():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "redirect_unit.sv",
        ],

        hdl_toplevel="redirect_unit",
        build_dir=riscv_dir / "tb" / "sim_build" / "redirect_unit",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="redirect_unit",
        test_module="redirect_unit_cocotb",
    )
