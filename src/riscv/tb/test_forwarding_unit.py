#------------------------------------------------------------------------------
# Module      : test_forwarding_unit
# Description : Pytest runner for the forwarding unit with Verilator.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-19
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner

def test_forwarding_unit():
    riscv_dir = Path(__file__).resolve().parents[1]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "forwarding_unit.sv",
        ],

        hdl_toplevel="forwarding_unit",
        build_dir=riscv_dir / "tb" / "sim_build" / "forwarding_unit",
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="forwarding_unit",
        test_module="forwarding_unit_cocotb",
        test_dir=riscv_dir / "tb",
    )
