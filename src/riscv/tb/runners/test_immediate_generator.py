#------------------------------------------------------------------------------
# Module      : test_immediate_generator
# Description : Pytest runner for directed immediate generator leaf tests.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-31
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner


def test_immediate_generator():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "immediate_generator.sv",
        ],

        hdl_toplevel="immediate_generator",
        build_dir=riscv_dir / "tb" / "sim_build" / "immediate_generator",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="immediate_generator",
        test_module="immediate_generator_cocotb",
    )
