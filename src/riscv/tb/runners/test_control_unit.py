#------------------------------------------------------------------------------
# Module      : test_control_unit
# Description : Pytest runner for directed control unit leaf tests.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-31
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner


def test_control_unit():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "control_unit.sv",
        ],

        hdl_toplevel="control_unit",
        build_dir=riscv_dir / "tb" / "sim_build" / "control_unit",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="control_unit",
        test_module="control_unit_cocotb",
    )
