#------------------------------------------------------------------------------
# Module      : test_exploratory
# Description : One pytest runner for every exploratory cocotb module.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

RISCV_DIR = Path(__file__).resolve().parents[2]


def core_sources():
    lines = (RISCV_DIR / "core_top.f").read_text().split()
    return [RISCV_DIR / line for line in lines if line.endswith(".sv")]


def rtl(*names):
    return [RISCV_DIR / "rtl" / "riscv_pkg.sv"] + [RISCV_DIR / "rtl" / n for n in names]


FETCH = ["fetch_controller_unit.sv", "fetch_buffer.sv", "fetch_obi_interface.sv",
         "prefetch_unit.sv", "fetch_stage.sv"]
DECODE = ["register_file.sv", "immediate_generator.sv", "control_unit.sv", "decode_stage.sv"]
CORE_ARGS = ["--public-flat-rw"]

# test module -> (toplevel, sources, verilator build args)
BLOCKS = {
    "link_adder_cocotb": ("link_adder", rtl("link_adder.sv"), []),
    "result_mux_cocotb": ("result_mux", rtl("result_mux.sv"), []),
    "operand_mux_cocotb": ("operand_mux", rtl("operand_mux.sv"), []),
    "fetch_buffer_cocotb": ("fetch_buffer", rtl("fetch_buffer.sv"), []),
    "fetch_obi_interface_cocotb": ("fetch_obi_interface", rtl("fetch_obi_interface.sv"), []),
    "pipeline_register_cocotb@if_id": ("if_id_pipeline", rtl("if_id_pipeline.sv"), []),
    "pipeline_register_cocotb@id_ex": ("id_ex_pipeline", rtl("id_ex_pipeline.sv"), []),
    "pipeline_register_cocotb@ex_mem": ("ex_mem_pipeline", rtl("ex_mem_pipeline.sv"), []),
    "pipeline_register_cocotb@mem_wb": ("mem_wb_pipeline", rtl("mem_wb_pipeline.sv"), []),
    "hazard_control_unit_cocotb": ("hazard_control_unit", rtl("hazard_control_unit.sv"), []),
    "fetch_stage_cocotb": ("fetch_stage", rtl(*FETCH), []),
    "decode_stage_cocotb": ("decode_stage", rtl(*DECODE), []),
    "harness_selftest_cocotb": ("core_top", None, CORE_ARGS),
    "core_pipeline_control_cocotb": ("core_top", None, CORE_ARGS),
    "core_instr_obi_cocotb": ("core_top", None, CORE_ARGS),
    "core_data_obi_cocotb": ("core_top", None, CORE_ARGS),
    "core_reset_cocotb": ("core_top", None, CORE_ARGS),
    "core_tieoff_cocotb": ("core_top", None, CORE_ARGS),
    "core_payload_cocotb": ("core_top", None, CORE_ARGS),
    "sw_programs_cocotb": ("core_top", None, CORE_ARGS),
    "isa_rv32ui_cocotb": ("core_top", None, CORE_ARGS),
}


@pytest.mark.parametrize("profile", [0, 1, 2, 3])
def test_profile_elaboration(profile):
    # T-03a..d: CORE_PROFILE 0 (BASE) elaborates; 1, 2 and 3 must fail elaboration (CORE-D1)
    build_dir = RISCV_DIR / "tb" / "sim_build" / f"xp_profile_{profile}"
    runner = get_runner("verilator")
    try:
        runner.build(sources=core_sources(), hdl_toplevel="core_top", build_dir=build_dir,
                     parameters={"CORE_PROFILE": profile}, timescale=("1ns", "1ps"), always=True)
        built = True
    except (SystemExit, Exception):
        built = False
    assert built == (profile == 0), f"CORE_PROFILE={profile}: built={built}"


@pytest.mark.parametrize("key", list(BLOCKS))
def test_exploratory(key):
    module = key.split("@")[0]
    if not (Path(__file__).parent / f"{module}.py").exists():
        pytest.skip(f"{module}.py not written")
    toplevel, sources, args = BLOCKS[key]
    sources = sources or core_sources()
    build_dir = RISCV_DIR / "tb" / "sim_build" / f"xp_{toplevel}"
    runner = get_runner("verilator")
    runner.build(sources=sources, hdl_toplevel=toplevel, build_dir=build_dir,
                 build_args=args, timescale=("1ns", "1ps"))
    runner.test(hdl_toplevel=toplevel, test_module=module,
                results_xml=str(build_dir / f"{key.replace('@', '_')}.xml"))
