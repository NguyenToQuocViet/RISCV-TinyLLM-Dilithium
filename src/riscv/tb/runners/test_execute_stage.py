#------------------------------------------------------------------------------
# Module      : test_execute_stage
# Description : EX wrapper and registered-harness runners with Verilator.
# Author      : OpenAI Codex
# Date        : 2026-10-19
#------------------------------------------------------------------------------

from pathlib import Path
from cocotb_tools.runner import get_runner


def run_execute_stage(hdl_toplevel, test_module):
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")
    sources = [
        riscv_dir / "rtl" / name
        for name in (
            "riscv_pkg.sv", "forwarding_unit.sv", "operand_mux.sv",
            "alu.sv", "branch_comparator.sv", "link_adder.sv",
            "result_mux.sv", "redirect_unit.sv", "execute_stage.sv",
        )
    ]
    if hdl_toplevel == "execute_stage_harness":
        sources.append(riscv_dir / "tb" / "harnesses" / "execute_stage_harness.sv")

    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        build_dir=riscv_dir / "tb" / "sim_build" / hdl_toplevel,
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
    )


def test_execute_stage():
    run_execute_stage("execute_stage", "execute_stage_cocotb")


def test_execute_stage_pipeline():
    run_execute_stage("execute_stage_harness", "execute_stage_pipeline_cocotb")
