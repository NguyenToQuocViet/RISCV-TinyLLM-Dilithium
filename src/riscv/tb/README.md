# RISC-V block tests

```text
tb/
├── runners/        # Pytest entry points: build RTL and launch cocotb
├── testcases/      # Cocotb stimulus, checking helpers and reference models
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
