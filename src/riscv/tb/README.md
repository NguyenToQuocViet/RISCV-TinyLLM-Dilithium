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

## Testbench conventions

These conventions implement the
[owner-readable verification policy](../docs/AGENT_POLICY.md#owner-readable-testbenches).
They govern new and edited tests; they do not claim that every historical test
has been reviewed against them.

Header authorship and Git identity follow
[Authorship and Commit Identity](../docs/AGENT_POLICY.md#authorship-and-commit-identity);
the local `docs/RTL_CONVENTIONS.md` defines the four-field header format.

- Present a short plan with testcase name, intent, stimulus and expected
  behavior, together with the proposed helper structure. Implement the approved
  scope; adding random stimulus or a framework is a separate decision.
- Group tests by function or scenario. Use short English comments that state
  the intent of the following stimulus; assertions must check that intent.
- For directed tests, supply manually determined expected values explicitly at
  the call site. A helper may drive inputs, wait for settling and compare with
  those values; it must not generate the directed oracle from a golden model
  or DUT outputs. Normalize bit width/signed representation when needed without
  changing the expected bit pattern.
- When random testing is approved, compare against a separately reviewed,
  contract-derived golden model and preserve the seed for reproduction.
  Direct testing remains suitable on its own when it covers the approved plan.
- Keep helpers small and single-purpose. Reset and literal output checks are
  useful examples, not a required helper count. Prefer explicit assignments and
  repeated edge/check sequences over generic drivers or transaction helpers
  that hide the scenario. Keep runners focused on build and test launch.
- Use native cocotb `Clock` and edge/phase triggers. In clocked directed tests,
  normally drive external stimulus at falling edges for rising-edge sampling.
  Show combinational checks before the consuming edge and registered-result
  checks after updates settle; `RisingEdge()` alone does not ensure settling.
- Model a parent register's advance at its actual accepted rising edge, in
  `ReadWrite()` when using Python-supplied parent updates, then observe settled
  outputs with `ReadOnly()`. Holding a completed owner until the next falling
  edge changes the modeled protocol. Make reset or other deliberate timing
  exceptions explicit. The block contract determines the actual event timing.
- Check observable DUT outputs and subsequent behavior. A flag supplied by the
  testbench about its own stimulus is not independent evidence of DUT protocol
  state. If a protocol monitor is required, derive legality from accepted
  protocol history; keep intentional violation tests and checker self-tests
  distinct from DUT handling tests. Record their separate results and limits.

## WB leaf verification

Việt approved this minimal directed plan on 2026-10-27 against
[WB D2](../docs/designs/writeback-stage.md). The top is `writeback_stage`,
using the existing Verilator/cocotb setup.

| Test | Scope |
| --- | --- |
| `test_result_selection` | EX/load selection, zero/all-one/MSB patterns, an EX-prepared jump link and changes to the unselected input |
| `test_write_qualification` | All 16 valid/advance/write-intent/zero-destination combinations, `rd=31`, and allow → deny advance → allow with stable payload |

Expected outputs are manual literals. One helper drives all seven inputs,
waits 1 ns for combinational settling and checks only `wb_data` and
`rf_write_fire`. No clock or reset is required. Data is checked even when
RF writes are suppressed. Completion requires both cocotb tests to pass.

```bash
rtk proxy .venv/bin/python -m pytest tb/runners/test_writeback_stage.py -v -s
```

Artifacts stay in `tb/sim_build/writeback_stage/`. This scope verifies the WB
leaf; it does not establish MEM/WB retention/capture, RF storage/forwarding,
full-pipeline retirement or physical timing.

Verification checkpoint, 2026-10-27 (Asia/Ho_Chi_Minh): the command above passed
one pytest entry running both cocotb tests, with 10 selection vectors and 19
qualification vectors. Base RTL revision: `198584d`; the new tests were
uncommitted at the run. Python 3.14.8, cocotb 2.1.0, pytest 9.1.1 and Verilator
5.046. No RTL change or waived failure; a full regression was not run.
Result XML: `tb/sim_build/writeback_stage/test_writeback_stage.result.xml` (ignored).

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

## MEM composition verification

Việt approved this minimal directed wrapper plan on 2026-10-24 against
[MEM D3](../docs/designs/memory-stage.md). The top is `memory_stage`, without
pipeline registers or a new RTL harness. Existing leaf suites retain their
separate corner-case coverage.

| Test | Scope |
| --- | --- |
| `test_access_paths` | One transaction for each of LB/LBU/LH/LHU/LW/SB/SH/SW; aligned request address, byte enables, write intent/store payload, original-address load lane and extension |
| `test_wait_and_successors` | Load → store → load; first grant delayed by three ungranted edges, response delayed by four waiting edges; stable request, no reissue and same-edge parent advance |
| `test_idle_and_reset` | Bubble/non-memory qualification, reset while outstanding with parent valid cleared, then a fresh load |

Expected values are manual literals. Helpers only reset inputs or compare
control/request outputs. The handshake sequence stays visible in each test;
memory inputs change on falling edges, and Python models parent replacement
at the response rising edge using `ReadWrite()`. Load results are checked before
that edge while the original instruction is still present. Stores have no
required `load_result` value. No random stimulus or golden model is used.

```bash
rtk proxy .venv/bin/python -m pytest tb/runners/test_memory_stage.py
```

This scope checks wrapper wiring and coordination under supplied parent and
bus obligations. It does not close core-level alignment/type/protocol checker
obligations or establish MEM/WB capture, WB retirement, full-pipeline control,
system-reset recovery or physical timing.

Verification checkpoint, 2026-10-24 (Asia/Ho_Chi_Minh): the command above passed
one pytest entry running all three cocotb tests. Base RTL revision: `fec7a2e`;
the new tests were uncommitted at the run. Python 3.14.8, cocotb 2.1.0,
pytest 9.1.1 and Verilator 5.046. No RTL changed; a full regression was not run.
Result XML: `tb/sim_build/memory_stage/test_memory_stage.result.xml` (ignored).

## Data OBI controller verification

Việt approved the directed leaf plan on 2026-10-23 against
[DOC D2](../docs/designs/data-obi-controller.md). The nine groups cover idle
qualification, payload routing, grant delays of 0/3/120 cycles, delayed response
and duplicate suppression, combinational wait release, consecutive owners,
unexpected responses, reset during transactions and reset with a stopped clock.
Grant delay counts rising edges with `req=1, gnt=0` before acceptance.

Việt requested a direct-test rewrite on 2026-10-24. Only `reset_dut()` and
`check_control()` remain as helpers. Memory-side inputs are driven on falling
edges. Initial parent stimulus is prepared on falling edges; once a transaction
is live, its parent owner/payload is retained through the response edge. At that
rising edge, `ReadWrite()` models the EX/MEM register update in the same timestep,
then `ReadOnly()` samples the settled outputs. Parent advance must not be delayed
until the following falling edge, which would re-present the old instruction.
Response valid still drops on a falling edge. The consecutive-instruction test
checks a memory successor, a valid non-memory successor and a bubble.
Grant stimulus is predetermined, not derived
combinationally from request. Expected values are explicit; tests do not read
private RTL state or compute expectations from DUT outputs.

The stopped-clock reset test deliberately asserts reset and clears parent valid
without an edge, as an exception to the normal stimulus discipline. Reset release
is driven at a falling edge with the clock running; this leaf test does not
implement or verify the parent reset synchronizer or reset-distribution timing.

Unexpected-response tests directly check draining, unchanged wait/ownership and
subsequent valid traffic for idle, waiting-for-grant, first-grant and duplicate
responses. They do not assert/catch a protocol diagnostic. The manual
`response_expected` checker and its four runner self-tests have been removed.
The BASE requirement for a protocol monitor and negative self-tests
remains pending a separately reviewed implementation; passing this directed
suite does not close that obligation. Artifacts stay in
`tb/sim_build/data_obi_controller/`; old negative-case XMLs are historical output,
not evidence for the rewritten suite.

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

Historical checkpoint, 2026-10-23 (Asia/Ho_Chi_Minh), before the rewrite: the
command above passed all five pytest entries: nine directed cocotb tests and four checker self-tests
whose inner simulations failed with the intended diagnostic. BASE RTL revision
was `9f1aed7`; the new tests were uncommitted. Python 3.14.8, cocotb 2.1.0,
pytest 9.1.1 and Verilator 5.046. No RTL change or waived failure. Result XMLs
are in the ignored artifact directory above; a full regression was not run.

Rewrite checkpoint, 2026-10-24 (Asia/Ho_Chi_Minh): the same command passed one
pytest entry running all nine directed cocotb tests. Base RTL revision:
`82e9dc2`; the rewrite was uncommitted. Tool versions are unchanged from the
historical checkpoint. No RTL changed. Protocol-monitor diagnostics and negative
self-tests remain pending; this result covers directed DUT behavior only.

Parent-boundary correction, 2026-10-24: the initial rewrite checkpoint above
predates the correction from falling-edge parent replacement to same-timestep
response-edge advance. After correcting every normal completion path, the same
command passed all nine directed tests again. RTL is unchanged; this remains a
Python-supplied parent boundary, not verification of real EX/MEM registers or
full-pipeline control.

## ID leaf verification

Việt approved the three directed leaf plans on 2026-10-31 against
[RF D1](../docs/designs/register-file.md),
[IMM D2](../docs/designs/immediate-generator.md) and
[CU D2](../docs/designs/control-unit.md) (all `Accepted`). The tops are
`register_file`, `immediate_generator` and `control_unit`, using the existing
Verilator/cocotb setup and no harness. Depth is the happy path only.

| Top | Tests |
| --- | --- |
| `register_file` (clocked, 10 ns) | `test_write_read_all`, `test_data_width`, `test_write_isolation`, `test_bypass_each_port`, `test_bypass_both_ports`, `test_read_during_write`, `test_no_bypass_without_fire`, `test_x0_read`, `test_x0_write_ignored`, `test_consecutive_writes` |
| `immediate_generator` (combinational) | `test_i_format`, `test_s_format`, `test_b_format`, `test_u_format`, `test_j_format`, `test_shift_immediates` (12 section 7 vectors), plus `test_selection_other_classes` (JALR, LW, AUIPC; Owner addition beyond section 8) |
| `control_unit` (combinational) | `test_upper_and_jump_ops`, `test_branch_ops`, `test_load_ops`, `test_store_ops`, `test_op_imm_ops`, `test_op_ops`, `test_fence` (38 operation words), `test_rejecting_words` (15 section 7 words) |

Expected values are manual literals at the call site, each traced to a contract
clause or plan row in the testcase. Enum codes in the CU tests are literals with
the enum name in a comment, taken from the accepted leaf records. The RF drives
inputs at falling edges and samples reads 1 ns later; a write commits at the
rising edge. IMM and CU drive one word, wait 1 ns and compare. Don't-care
outputs are never compared. No random stimulus, golden model or scoreboard is
used. Completion requires all 25 cocotb tests to pass.

```bash
rtk proxy .venv/bin/python -m pytest tb/runners/test_register_file.py tb/runners/test_immediate_generator.py tb/runners/test_control_unit.py -v -s
```

Artifacts stay in `tb/sim_build/{register_file,immediate_generator,control_unit}/`.
CU C1 (the exhaustive 2^17 sweep of the guarded enables and its predicate) is
deferred by the Owner and stays PENDING; this pass does not close it. The L9
rejecting row (`FENCE.I`) cannot fail at the CU leaf: the `FENCE` enables equal
the guard values (CU sections 5.2 and 5.3), so L9 rejection is not observable
here; the row is kept for section 7 / C2 completeness. The pass
covers the stated vectors only: it does not exercise the not-checked fields
(`rd`, `rs1`, `rs2`, FENCE fields, HINT, alignment), words outside the listed
ones, `x0`-adjacent corner sweeps, unwritten-register reads or X/Z inputs. It
does not establish `decode_stage` integration, hazards, EX/MEM/WB consumption
of the control outputs, timing or whole-core behavior.

Verification checkpoint, 2026-10-31 (Asia/Ho_Chi_Minh): the command above passed
three pytest entries running 25 cocotb tests (10 RF, 7 IMM, 8 CU). Base RTL
revision: `9e316b1`; the new tests were uncommitted at the run (the contract
documents under `docs/designs/` also had uncommitted edits). Python 3.14.8,
cocotb 2.1.0, pytest 9.1.1 and Verilator 5.046. No RTL change or waived failure;
a full regression was not run. Result XML:
`tb/sim_build/<block>/test_<block>.result.xml` (ignored).
