#------------------------------------------------------------------------------
# Module      : test_data_obi_controller
# Description : Pytest runner for directed data OBI controller tests.
# Author      : Codex
# Date        : 2026-10-23
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner


def test_data_obi_controller():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "data_obi_controller.sv",
        ],

        hdl_toplevel="data_obi_controller",
        build_dir=riscv_dir / "tb" / "sim_build" / "data_obi_controller",
        timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel="data_obi_controller",
        test_module="data_obi_controller_cocotb",
    )
