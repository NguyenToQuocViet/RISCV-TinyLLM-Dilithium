#------------------------------------------------------------------------------
# Module      : test_writeback_stage
# Description : Pytest runner for directed WB leaf tests.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-27
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner


def test_writeback_stage():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "writeback_stage.sv",
        ],
        hdl_toplevel="writeback_stage",
        build_dir=riscv_dir / "tb" / "sim_build" / "writeback_stage",
        timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel="writeback_stage",
        test_module="writeback_stage_cocotb",
    )
