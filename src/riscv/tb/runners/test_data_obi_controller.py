#------------------------------------------------------------------------------
# Module      : test_data_obi_controller
# Description : Directed controller tests and unexpected-response checker tests.
# Author      : Codex
# Date        : 2026-10-23
#------------------------------------------------------------------------------

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from cocotb_tools.runner import get_runner


def build_data_obi_controller():
    riscv_dir = Path(__file__).resolve().parents[2]
    runner = get_runner("verilator")

    runner.build(
        sources=[
            riscv_dir / "rtl" / "riscv_pkg.sv",
            riscv_dir / "rtl" / "data_obi_controller.sv",
        ],

        hdl_toplevel="data_obi_controller",
        build_dir=riscv_dir / "tb" / "sim_build" / "data_obi_controller",
        timescale=("1ns", "1ps"),
    )
    return runner


def test_data_obi_controller():
    runner = build_data_obi_controller()
    runner.test(
        hdl_toplevel="data_obi_controller",
        test_module="data_obi_controller_cocotb",
        extra_env={"OBI_NEGATIVE_CASE": ""},
    )


@pytest.mark.parametrize("negative_case", ["idle", "waiting", "first_grant", "duplicate"])
def test_unexpected_response_monitor(negative_case, request):
    runner = build_data_obi_controller()

    #the inner simulation must fail for the injected protocol violation
    with pytest.raises(SystemExit) as failure:
        runner.test(
            hdl_toplevel="data_obi_controller",
            test_module="data_obi_controller_cocotb",
            test_filter=r"\.test_unexpected_response$",
            extra_env={"OBI_NEGATIVE_CASE": negative_case},
        )
    assert failure.value.code == 1

    #an unrelated simulator/checker failure must not count as success
    results = runner.build_dir / f"{request.node.name}.result.xml"
    tests = ET.parse(results).getroot().findall(".//testcase")
    assert len(tests) == 1
    assert tests[0].get("name") == "test_unexpected_response"
    failures = tests[0].findall("failure")
    assert len(failures) == 1
    assert tests[0].find("error") is None
    assert tests[0].find("skipped") is None
    diagnostic = ET.tostring(failures[0], encoding="unicode")
    assert f"Unexpected OBI response: {negative_case}" in diagnostic
