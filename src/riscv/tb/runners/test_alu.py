#------------------------------------------------------------------------------
# Module      : test_alu
# Description : Pytest runner for building and simulating the ALU with Verilator.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-16
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner

def test_alu():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "alu.sv",
        ],

        hdl_toplevel="alu",
        build_dir=riscv_dir / "tb" / "sim_build" / "alu",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="alu",
        test_module="alu_cocotb",
    )
