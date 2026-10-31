#------------------------------------------------------------------------------
# Module      : test_register_file
# Description : Pytest runner for directed register file leaf tests.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-31
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner


def test_register_file():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "register_file.sv",
        ],

        hdl_toplevel="register_file",
        build_dir=riscv_dir / "tb" / "sim_build" / "register_file",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="register_file",
        test_module="register_file_cocotb",
    )
