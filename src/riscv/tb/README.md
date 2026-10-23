# RISC-V block tests

```text
tb/
├── runners/        # Pytest entry points: build RTL and launch cocotb
├── testcases/      # Cocotb stimulus, checking helpers and reference models
├── harnesses/      # Test-only RTL for registered boundary stimulus
└── sim_build/      # Generated simulator files and result XML, grouped by block
```

Run from `src/riscv` using its virtual environment:

```bash
rtk proxy .venv/bin/python -m pytest -v -s
rtk proxy .venv/bin/python -m pytest tb/runners/test_forwarding_unit.py -v -s
```

[`pytest.ini`](../pytest.ini) selects the runner directory and adds `testcases/`
to Python's import path. Cocotb's runner forwards that path to the simulator,
so testcase modules are found without relying on the simulation working directory.

For each new block, place `test_<block>.py` in `runners/` and its cocotb module
in `testcases/`. The runner resolves the RISC-V root with
`Path(__file__).resolve().parents[2]`, compiles into `tb/sim_build/<block>/`,
and names the testcase module in `runner.test(test_module=...)`.

Leave `test_dir` unset: cocotb runs in the build directory and writes
`test_<block>.result.xml` there when invoked through pytest. Generated files
are ignored by [`tb/.gitignore`](.gitignore). Each rerun replaces that block's
result XML; these files are current run output, not an archived verification report.

## EX composition verification

The owner approved this directed plan on 2026-10-19 against
[EX D3](../docs/designs/execute-stage.md#6-verification-and-delivery-boundaries).
`test_execute_stage.py` runs two tops with the existing Verilator/cocotb setup:

| Top / test module | Planned checks |
| --- | --- |
| `execute_stage` / `execute_stage_cocotb` | Ten register operations, nine immediate operations, LUI/AUIPC, eight load/store EX paths, all six branches taken/not-taken, JAL/JALR target and link, forwarding destinations/priority/guards, redirect gates, consecutive control changes, FENCE and control-checker diagnostics |
| `execute_stage_harness` / `execute_stage_pipeline_cocotb` | Normal capture and metadata association, three-cycle holds and redirect release, held WB forwarding at release, MEM-load exclusion followed by WB availability, bubble/explicit EX kill, synchronous reset during hold and recovery |

Directed expected results are manual constants. The shared helpers only initialize,
drive and check ports; they do not compute a golden result. All inputs are binary.
The control checker rejects reserved selectors only on live instructions using
them; negative checker self-tests catch the expected assertion without sending
an illegal live instruction through the DUT as an accepted case.

The harness registers ID/EX stimulus, independently supplied MEM/WB producer
facts and captured EX/MEM results/metadata. It does not feed its captured results
back as producers. A tag tracks instruction identity; the tag is test-only.
`hold` freezes these registers; reset clears validity without resetting payload.
`flush_ex` explicitly kills the current EX entry; it does not implement the
frontend/ID flush caused by that entry's own redirect. Tests sample redirect
before each rising edge and captured data after sequential updates settle.
The load-use bubble and modeled memory-response release are supplied stimulus;
there is no OBI responder, load formatter or implemented hazard controller here.

Acceptance for this test scope requires both new tops and all four existing leaf
regressions to pass. This establishes EX composition under supplied boundary
control, not decoder, full-core pipeline control, OBI, FPGA or timing correctness.

```bash
rtk proxy .venv/bin/python -m pytest tb/runners/test_execute_stage.py -v -s
rtk proxy .venv/bin/python -m pytest -v -s
```

Verification checkpoint, 2026-10-19 (Asia/Ho_Chi_Minh): all six pytest entry
points passed, covering 47 cocotb tests (11 wrapper, 6 registered harness,
30 existing leaf tests). The EX tops were rerun after the final reserved-selector
vectors were added and passed again. Base RTL revision: `82e8f06`; new tests
were uncommitted at the run. Python 3.14.8, cocotb 2.1.0, pytest 9.1.1,
Verilator 5.046. No functional RTL change or waived failure.
Local [run metadata and source hashes](sim_build/execute_stage/verification.json),
[full regression log](sim_build/execute_stage/regression.log) and
[final EX rerun log](sim_build/execute_stage/targeted.log) are ignored artifacts.

## Data OBI controller verification

Việt approved the directed leaf plan on 2026-10-23 against
[DOC D2](../docs/designs/data-obi-controller.md). The nine groups cover idle
qualification, payload routing, grant delays of 0/3/120 cycles, delayed response
and duplicate suppression, combinational wait release, consecutive owners,
unexpected responses, reset during transactions and reset with a stopped clock.
Grant delay counts rising edges with `req=1, gnt=0` before acceptance.

The Python stimulus retains the parent owner/payload through completion, replaces
it after the consuming edge, clears valid on shared reset and supplies an already
conditioned reset release. It does not implement or verify a reset synchronizer.
Grant stimulus is predetermined, not derived combinationally from request.
Checks use explicit control expectations and public ports, not private RTL state.

The normal simulation checks unexpected-response handling with an explicitly
expected checker diagnostic. Four separate checker self-tests inject a response
while idle, waiting for grant, at first grant and after completion. Each inner
simulation must fail with the specific protocol diagnostic; pytest accepts only
that failure, verified from its result XML. A missing diagnostic, unrelated
failure or missing XML fails the self-test. Artifacts stay in
`tb/sim_build/data_obi_controller/`.

```bash
rtk proxy .venv/bin/python -m pytest tb/runners/test_data_obi_controller.py
```

This scope verifies the controller leaf under supplied parent/bus obligations;
it does not establish MEM/WB capture, full-pipeline control, memory-side grant
generation, physical timing or system reset recovery.
The stopped-clock test observes public output suppression and subsequent
recovery. With parent valid held zero during reset, public outputs do not
independently expose when the private ownership bit clears; that asynchronous
reset structure is also checked by RTL inspection.

Verification checkpoint, 2026-10-23 (Asia/Ho_Chi_Minh): the command above passed
all five pytest entries: nine directed cocotb tests and four checker self-tests
whose inner simulations failed with the intended diagnostic. BASE RTL revision
was `9f1aed7`; the new tests were uncommitted. Python 3.14.8, cocotb 2.1.0,
pytest 9.1.1 and Verilator 5.046. No RTL change or waived failure. Result XMLs
are in the ignored artifact directory above; a full regression was not run.
