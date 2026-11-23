#------------------------------------------------------------------------------
# Module      : test_fetch_controller_unit
# Description : Pytest runner for the fetch controller
# Author      : Viet Nguyen To Quoc
# Date        : 2026-11-16
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner

def test_fetch_controller_unit():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "fetch_controller_unit.sv",
        ],

        hdl_toplevel="fetch_controller_unit",
        build_dir=riscv_dir / "tb" / "sim_build" / "fetch_controller_unit",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="fetch_controller_unit",
        test_module="fetch_controller_unit_cocotb",
    )
