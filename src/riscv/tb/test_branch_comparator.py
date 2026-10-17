#------------------------------------------------------------------------------
# Module      : test_branch_comparator
# Description : Pytest runner for the branch comparator with Verilator.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-17
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner

def test_branch_comparator():
    riscv_dir = Path(__file__).resolve().parents[1]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "branch_comparator.sv",
        ],

        hdl_toplevel="branch_comparator",
        build_dir=riscv_dir / "tb" / "sim_build" / "branch_comparator",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="branch_comparator",
        test_module="branch_comparator_cocotb",
        test_dir=riscv_dir / "tb",
    )
