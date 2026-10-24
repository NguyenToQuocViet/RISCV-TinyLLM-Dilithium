#------------------------------------------------------------------------------
# Module      : test_memory_stage
# Description : Pytest runner for directed MEM composition tests.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-24
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner


def test_memory_stage():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "request_formatter.sv",
            riscv_dir / "rtl" / "data_obi_controller.sv",
            riscv_dir / "rtl" / "load_formatter.sv",
            riscv_dir / "rtl" / "memory_stage.sv",
        ],

        hdl_toplevel="memory_stage",
        build_dir=riscv_dir / "tb" / "sim_build" / "memory_stage",
        timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel="memory_stage",
        test_module="memory_stage_cocotb",
    )
