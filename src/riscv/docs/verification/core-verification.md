# Core verification: general document (core_top)

**Status:** Accepted by Việt on 2026-11-12
**Date:** 2026-11-12 | **Brief:** 006-vplan-sheet (content of 005-core-verification-plan) | **Approval:** approved by Owner 2026-11-12

## 1. Purpose and files

- The test rows of the core verification plan are in the sheet [VERIFICATION_PLAN.xlsx](VERIFICATION_PLAN.xlsx), sheet `TESTS`. This document holds everything else: oracle sources, column meanings, folders, the `tb/common/` pieces, build flow, completion rules, ISA-suite adaptation, exclusions, manifests, order of work and open items.
- The workbook is for the whole subsystem. The core rows and the rows of the existing leaf and stage tests are migrated (Brief 006, Brief 009). Rows for the blocks without a test come when each block's plan is made.
- This document contains no row table. A row is added or changed in the sheet only.
- Origin: the rows come unchanged from sections 6.1 to 6.11 of `.handoff/verification/plans/core_top.md` (Brief 005). No row or requirement was added.

## 2. Oracle sources and SOURCE short names

Expected values come from these records and the Owner decisions below, never from the RTL or from an existing test output.

- `BASE`: [5-stage-baseline-core.md](../designs/5-stage-baseline-core.md), Status `Accepted by Nguyễn Tô Quốc Việt on 2026-10-15`, R2 reset amendment accepted 2026-10-21.
- `core-top.md`: [core-top.md](../designs/core-top.md), `Accepted by Việt on 2026-11-10`. Register-output net names come from CORE-D5 and are contract-visible, so a test may observe them.
- `pipeline-register.md`: [pipeline-register.md](../designs/pipeline-register.md), Accepted.
- `execute-stage.md`: [execute-stage.md](../designs/execute-stage.md), Accepted.
- `RST-D1`: [reset-strategy.md](../decisions/reset-strategy.md), `Accepted by Việt on 2026-10-21`.
- The Status line of `hazard-control-unit.md` was not read. The sheet uses that record only through the accepted `core-top.md`.

The `SOURCE` column of the sheet cites a clause as a short name, optionally followed by a qualifier that names a table, row or paragraph (for example `HCU §6 Load-use row`). Every short name used in the sheet:

| Short name | Meaning |
| --- | --- |
| `VS` | `BASE` section "Verification strategy and ownership" |
| `VS-g1` to `VS-g7` | the seven mandatory scenario groups of `VS` (1 instruction semantics, 2 dependencies, 3 pipeline control, 4 instruction OBI, 5 data OBI, 6 reset, 7 MMIO and FENCE) |
| `VS-tie` | the common-top paragraph of `VS` (CORE_PROFILE, CI and IRQ tie-off) |
| `HC` | `BASE` "Harness completion and timeout contract" |
| `AG1` to `AG6` | the six conditions of `BASE` "Objective acceptance gate"; `AG3` ISA layer, `AG4` checker negative self-tests, `AG6` exploratory tests not mandatory |
| `MEMV` | `BASE` core-level OBI memory model paragraphs (code region `0x0000_0000` to `0x0000_FFFF`, data region `0x0001_0000` to `0x0001_FFFF`, fetch range check) |
| `MB` | `BASE` Core memory boundary, including the OBI baseline configuration |
| `RA` | `BASE` Reset architecture |
| `ORV` | `BASE` OBI response validity and reset |
| `IFC` | `BASE` Instruction fetch capacity and transaction states |
| `SR` | `BASE` Stale instruction responses after redirect |
| `DTC` | `BASE` Data transaction completion |
| `MDF` | `BASE` MEM data formatting and MEM/WB boundary |
| `FLD` | `BASE` Forwarding and load-use hazards |
| `RFT` | `BASE` Register-file timing and WB-to-ID bypass |
| `PCP` | `BASE` Pipeline-control priority |
| `PRL` | `BASE` Pipeline-register local control |
| `ASE` | `BASE` Architectural side effects |
| `IST` | `BASE` Instruction semantic table and EX computation contract |
| `MMIO` | `BASE` MMIO, FENCE, and integration obligations |
| `Redirect event` | `BASE` paragraph of that name, as cited by Brief 005 |
| `CT3`, `CT4`, `CT6`, `CT7`, `CT9` | `core-top.md` section 3 ports, 4 net names, 6 behavior, 7 trace of a response with a redirect, 9 planned checks |
| `CORE-D1` | `core-top.md` decision CORE-D1 (unsupported `CORE_PROFILE` fails elaboration) |
| `PR6`, `PR-E7`, `PR9` | `pipeline-register.md` section 6 condition table, its trace edge E7, its section 9 "Payload qualification" |
| `EX OPEN` | the OPEN item of `execute-stage.md`: nothing shows EX under the R2 asynchronous reset |
| `HCU` | `hazard-control-unit.md`. A qualifier names the table row: `HCU §6` is its priority table, cited as the table authority by `CT6` and `CT9`. `HCU-D5` is the decision label as cited in Brief 005 (MEM wait over load-use) |
| `IF-A1`, `IF-A2` | fetch-control decision labels as cited in Brief 005 (frontend progress with independent ports; redirect target timing). The record defining them was not opened by this agent |
| `DEC` | the decode table with `rs1_used` and `rs2_used`, as cited in Brief 005. Its record was not opened by this agent |
| `OD-1111` | Owner decision of 2026-11-11 on the random-payload check (below) |
| `RST-D1` | see the list above |

Owner decisions recorded here (the Briefs state them; no accepted record carries them yet):

- 2026-11-11, random payload: while valid=0, a random payload causes no side effect. Targets: forwarding, HCU load-use, RF write enable, data `req`, redirect. `pipeline-register.md` still lists this as OPEN and as "not adopted" (`OD-1111`).
- 2026-11-12, reset synchronizer: keep its group 6 rows, mark them `Blocked` until design delivers `reset_synchronizer`. Until then the harness drives the conditioned `rst_n` directly: assertion is asynchronous, release follows the clock.
- 2026-11-12, ISA suite: riscv-arch-test (ACT 4.0), signatures from the Sail reference model. Facts from the GitHub README, copied from Brief 005 and not checked here: `sail_riscv_sim` prebuilt binary release; RISCOF deprecated; Spike and Sail not installed; BASE has no CSR, ECALL or MRET.
- 2026-11-12, golden model and constrained random: deferred. No random row is mandatory except the five random-payload rows.
- 2026-11-12, harness: existing tests stay; new tests use a small helper module in `tb/common/`; the core harness comes first (the order of work is superseded, see section 11).
- 2026-11-12, file format and location of the plan: this sheet and this document, in `docs/verification/`.
- 2026-11-12, structural rows (OI-7): T-04 (extension logic absent), T-06 (connectivity) and T-07 (lint and synthesis) need RTL elaboration or the hierarchy script, which the verification tab is denied. They go to the design tab, and their evidence is a design-tab Report. T-03 (profile elaboration) stays with the verification worker.

## 3. The sheet

One sheet, `TESTS`, header row frozen, no other sheet, no dropdown, no colour. Rows are sorted by `GROUP` in the order of work (`Direct`, `Integrated`, `Harness`, `Core`, `SW`, `ISA`, `Exploratory`), and keep their relative order inside a group. Columns in this order (13):

| Column | Meaning and allowed values |
| --- | --- |
| `ID` | Stable row ID from the Brief 005 plan (`G1-01`, `G4-08a`, `PQ-1`, `X-01`, `A-01`). A row that bundled independent variants is split with a letter suffix (`G2-01a`, `G2-01b`). A bare parent ID in this document means all its split rows. Leaf and stage rows use `D-<BLK>-NN` and `I-<STG>-NN`: `<BLK>` is the block's short name in its spec (`ALU`, `BC`, `CU`, `DOC`, `FU`, `IMM`, `LF`, `RU`, `RF`, `RQF`, `FB`, `FCU`, `FOI`, `LA`, `OM`, `RM`, `PR`, `HCU`), `<STG>` is `IF`, `ID`, `EX`, `MEM` or `WB`; `NN` numbers the tests of the block in file order. A block with no test has one placeholder row `D-<BLK>-00` or `I-<STG>-00` with `SUB ITEM 1` = `not planned yet`, `SOURCE` = its spec file, `STATUS` = `Planned` and every other column blank. Its detailed rows come when that block's plan is made |
| `GROUP` | The test layer. One of `Direct`, `Integrated`, `Core`, `SW`, `ISA`, `Harness`, `Exploratory`. `SW`: an assembly program on `core_top` (Brief 005 "core program"). `Core`: cocotb drives `core_top` ports and nets, monitors, structural checks (Brief 005 "core directed", "SVA monitor", "structural"). `Harness`: checker and harness self-tests X-01 to X-10. `ISA`: A-01, A-02. `Direct`: a test on one leaf module (the 10 leaf test files). `Integrated`: a test on a stage (`execute_stage`, `execute_stage_pipeline`, `memory_stage`, `writeback_stage`). No `Exploratory` row exists yet |
| `ITEM` | The feature: the BASE scenario group or topic (Instruction semantics, Dependencies, Pipeline control, Instruction OBI, Data OBI, Reset, MMIO and FENCE, Tie-off and profile, Random payload, Checker self-test, ISA suite) |
| `SUB ITEM 1` | The distinction inside the item |
| `SUB ITEM 2` | The variant of the distinction (a sink, a branch, a lane, a port) |
| `METHOD` | `Direct`: cocotb drives `core_top` ports. `Program`: an assembly program and its signature. `Assertion`: a monitor (section 5.5). `Structural`: a script or elaboration, no stimulus |
| `TEST SEQUENCE` | Compact steps: assembly snippets or call-like steps (`data rvalid latency=40`). Values written as `V` or `T` are labels of the program; `x`-registers are those named in the row |
| `PASS CONDITION` | Literal expected values or a relation traced to the clause in `SOURCE`. Nets are the `CT4` names. "signature" means the data-region words compared with literals at the call site |
| `SOURCE` | The clause the PASS CONDITION comes from, as a short name from section 2. A `D-` or `I-` row names its spec file and the section the test cites (`control-unit.md §5.3 rows LUI, AUIPC, JAL, JALR; §7`); a test that cites no clause reads `<spec file> (no clause cited)` |
| `TEST` | The test function name (`D-` and `I-` rows: `<file stem>::<function>`, for example `alu_cocotb::test_add`). Split rows of one parent share the parent's test function, and the variant is a parameter of that function. T-04, T-06 and T-07 read `design tab: <check>`: the design tab runs them (OI-7) |
| `OWNER` | Who owns the test. `Việt` for every test made under his direction, whoever typed the code. `Claude` only for exploratory rows Claude plans and runs without his review. Existing tests whose header names `OpenAI Codex` keep `OpenAI Codex`. Blank on a row until Việt assigns it |
| `DEADLINE` | The date the Owner sets for the item to be done, format `yyyy-mm-dd`. Blank on every migrated row: Việt sets it |
| `STATUS` | `Planned`, `Blocked`, `Pass` or `Fail`. `Blocked` is used only for G6-S1 to G6-S3 (`reset_synchronizer` not delivered) and A-01, A-02 (Sail not installed). Every other migrated row is `Planned` |

Hierarchy columns follow the ICTC style: `GROUP`, `ITEM` and `SUB ITEM 1` are blank when they repeat the row above, counted after the sort by `GROUP`. Filter or sort on a copy, because a re-sorted sheet loses the blanks' meaning.

The Brief 005 "Existing" column (which `tb/testcases` test already covers a row) is not in the sheet. A leaf test covers the leaf under supplied inputs only; a core row adds integration.

## 4. Folders, tiers and the exploratory workflow

```text
tb/
├── runners/ testcases/ harnesses/ sim_build/   existing leaf and EX/MEM composition tests, unchanged
├── common/        harness, helpers, monitors (section 5)
├── regression/    mandatory core tests that drive ports or nets, and checker self-tests
├── integration/   programs/*.S and their signature tests
├── exploratory/   Claude's bug-hunting rows; deferred random and golden model go here first
└── riscv_arch/    riscv-arch-test adaptation (section 8)
```

- New code never imports from the existing helper files, and the existing tests are not moved or rewritten.
- Folder per sheet `ITEM`: Instruction semantics, Dependencies and MMIO and FENCE go to `integration/`; Pipeline control puts its `Program` rows in `integration/` and the others in `regression/`; Instruction OBI, Data OBI, Reset, Tie-off and profile, Random payload and Checker self-test go to `regression/`; ISA suite goes to `riscv_arch/`. The two manifests of the acceptance gate (section 10) are the `regression/` and `integration/` test lists.
- No stage-harness row is needed: every behavior is observable at `core_top` ports, at contract-visible nets, or in the program signature. A stage harness is added only with a stated reason.
- Direct-layer gaps (no `tb/testcases` file exists): `fetch_stage` and its three children, `decode_stage`, the four pipeline registers, `hazard_control_unit`, `core_top`. Each of them except `core_top` has a placeholder row in the sheet (section 3); the leaf tests are made when each block's plan is made, and the `core_top` rows are the core rows.
- Collection by pytest is open (OI-6): `tb/README.md` says `pytest.ini` selects the runner directory; `pytest.ini` itself was outside this agent's read scope.
- Attribution of new files (`AGENT_POLICY`, Authorship): a file Claude writes carries `Author: Claude Code (Anthropic)` and `Reviewer: Viet Nguyen To Quoc`; a file Việt writes carries Việt's name. The header layout is `docs/RTL_CONVENTIONS.md`, which this document does not restate.

Exploratory workflow (Owner, 2026-11-12):

1. Claude reads the specs and the sheet and looks for weak points.
2. Claude adds its own rows to the sheet with `GROUP=Exploratory` and `OWNER=Claude`.
3. Claude runs them without Owner review and reports the results.

No exploratory row exists yet. Exploratory tests are not mandatory (`AG6`).

## 5. `tb/common/` pieces (one job each)

### 5.1 Helper module `common/helpers.py` (Owner decision, 2026-11-12)

| Helper | Single job |
| --- | --- |
| `start_clock(dut, period_ns)` | start the native cocotb `Clock` on `clk` |
| `reset_dut(dut, edges)` | hold `rst_n` low for `edges` rising edges with the clock running, release at a falling edge |
| `drive(dut, **ports)` | assign the named ports; names are the contract names and stay visible at the call site |
| `expect(dut, **ports)` | compare the named ports with literals passed at the call site; the message names the port and cycle |

Reset timing that a test must control (between edges, clock stopped, mid-sequence) is written in the test with `drive(dut, rst_n=0)` at the chosen time, so the sequence stays visible.

### 5.2 Memory model `common/obi_memory.py`

- `ObiMemory` serves one OBI port. Fields: region bounds, byte storage, grant policy, response policy, access log (cycle, address, `we`, `be`, `wdata`, response data), reset behavior. One instance for the code region (read-only use) and one for the data region. Separate storage, no arbiter (`MEMV`).
- Latency policies, each a small function returning grant delays and response latencies: `fixed(n)`, `scripted([n0, n1, ...])`, `seeded(seed, low, high)`. A seeded policy logs its seed. Grant delay counts rising edges with `req=1, gnt=0` before acceptance. Response latency counts rising edges from acceptance to `rvalid`. Minimum response latency is 1 (OI-9).
- Grant is predetermined by the policy, never derived combinationally from `req` (`COMB_GNT=False`, `ORV`).
- One outstanding transaction per port. The model may grant the next request on the edge of the previous response (`IFC`), never while a response is still pending.
- Reset: the model watches `rst_n`. On assertion, without a clock edge, it drives `rvalid=0` and drops every pending transaction; it never answers a pre-reset transaction (`RA`, `ORV`). On an edge sampling `rst_n=0` it accepts nothing and returns no result.
- Unprogrammed code words read `0x0000_0000` (an illegal word, so running past a program is a visible error). Unprogrammed data words read a fixed pattern chosen per test run and logged.
- Injection hooks, for self-tests only and off by default: `inject_unexpected_response`, `allow_second_outstanding`, `withhold_response`.

### 5.3 Image and build pieces

| Piece | Single job |
| --- | --- |
| `common/image.py: load_image(hexfile)` | parse the `objcopy -O verilog` byte hex (stdlib only), split by address into code and data bytes, fail on a byte outside the two regions or inside `TEST_STATUS` |
| `common/link.ld` | the linker script of section 6 |
| `common/start.S` | `_start` at `0x0000_0000`: set `sp`, jump to the program body (rv32i base instructions only) |
| `common/check_ops.py` | stimulus validation: disassemble an ELF and fail when a mnemonic lies outside the 38 BASE operations |

### 5.4 Core harness `common/core_harness.py`

- `run_core(dut, image, config)`: wires `core_top`, the two `ObiMemory` instances, the completion watcher (section 7), the three watchdogs and the fetch range check; runs until completion or a watchdog; returns the status, the signature words read after the completion edge settled, and the logs.
- `config` is the per-test limits and policies: grant policy, response policy, grant limit, response limit, total-cycle limit, seeds. It lives in the test file, version controlled, and is copied into the evidence (`HC`).
- Fetch range check: on every edge sampling `rst_n=1` and `instr_req=1`, `instr_addr` must lie in `0x0000_0000` to `0x0000_FFFF`, independent of `gnt`. A violation fails the test immediately (`MEMV`).
- Emulated peripheral `common/mmio_peripheral.py`: a test fixture on the data port for group 7. Its register block sits in the data region at the test-local base `0x0001_8000`, disjoint from fixture data and `TEST_STATUS` (a test choice; `MMIO` allows documented test-local addresses). Registers: `W` (write counter: each store adds 1 to a count, the stored value is logged) and `R` (pop register: each load returns the next value of a scripted list and advances it). No IRQ source and no accelerator frontend (`VS-g7`).

### 5.5 Monitors `common/monitors.py`

Sampling functions in Python, one rule each. They log violations; a test fails on any logged violation unless it declares the expected one at the call site (`expect_violations=[...]`). Plan acceptance is the Owner approval of this list; no scoreboard is proposed.

| Monitor | Rule (clause) |
| --- | --- |
| `M1 request_stable` | per port: from the first asserted `req` until `gnt`, `req`, address, `we`, `be`, `wdata` do not change (`IFC`, `MB`) |
| `M2 outstanding_limit` | per port: `current_outstanding + request_fire - response_fire` never exceeds 1 (`IFC`, `ORV`) |
| `M3 unexpected_response` | per port: `rvalid && rready` with no outstanding transaction and `rst_n=1` is reported (`ORV`) |
| `M4 no_effect_from_invalid` | `rf_write_fire` implies `mem_wb_reg_valid`; `data_req` implies `ex_mem_reg_valid`; `redirect_fire` implies `id_ex_reg_valid` (`ASE`, `RA`, `CT4`) |
| `M5 valid_hold_flush` | each pipeline register's next valid follows `PR6`: reset clears, `flush` clears, `stall` retains, otherwise captures `valid_i` (`PRL`) |
| `M6 constant_outputs` | `instr_we=0`, `instr_be=4'b1111`, `instr_wdata=0`, `instr_rready=1`, `data_rready=1`, `ci_cmd_valid=0`, `ci_cmd_op=0`, `ci_cmd_target=0`, `ci_cmd_desc=0`, `ex_mem_flush=0`, `mem_wb_flush=0` (`OBI baseline configuration` in `MB`, `VS-tie`, `CT3`, `CT4`) |
| `M7 reset_clear` | while `rst_n=0`: all four pipeline valids 0, `instr_req=0`, `data_req=0`, `mem_wait=0`, `rf_write_fire=0`, `redirect_fire=0` (`RA`, `ASE`) |

An SVA version of any rule is an alternative implementation, not an extra requirement (OI-11).

### 5.6 Timing rules (core level)

- Memory-side inputs (`instr_gnt`, `instr_rvalid`, `instr_rdata`, `data_gnt`, `data_rvalid`, `data_rdata`) and the CI/IRQ inputs change at falling edges. Clock period 10 ns (test choice; no contract value).
- Protocol events (`request_fire`, `response_fire`) are sampled just before each rising edge, from the values the DUT sees at that edge. The sample uses the same `rst_n` rule as `ORV`.
- Registered nets and signatures are read after the edge's sequential updates settle: `ReadWrite()` then `ReadOnly()`.
- Reset timing exceptions are stated in the row: assertion between edges, clock stopped, release at a falling edge (direct drive) or by the synchronizer.
- Each directed OBI test gives the cycle script as a predicted trace in the test (`AGENT_POLICY`, evidence section), and asserts the scenario precondition from observed port events before it checks the result, so the check cannot pass vacuously.

## 6. Program build flow

- Toolchain: `/opt/Xilinx/2026.1/Vitis/gnu/riscv/lin/bin/riscv64-unknown-elf-gcc`. Check by `verification-main`, 2026-11-12, files in its scratchpad `gcc_check/`; not re-run by this agent:
  - it reports `riscv32-xilinx-elf-gcc` 13.4.0 and has the `rv32i/ilp32` multilib;
  - `-march=rv32i -mabi=ilp32 -nostdlib -nostartfiles -Wl,--build-id=none -T t.ld` builds a 5-instruction file, and `objdump` shows `00100293 addi` and an `sw` to `0x1FFFC`;
  - the wrapper passes `--gc-sections` by default, so without `ENTRY(_start)` or `KEEP` in the linker script the ELF has no sections;
  - without `--build-id=none` a GNU note lands at `0x0`;
  - `objcopy -O verilog` gives a byte hex from `@00000000`.
- Fixed flags: `-march=rv32i -mabi=ilp32 -nostdlib -nostartfiles -Wl,--build-id=none -T common/link.ld`. `link.ld` has `ENTRY(_start)` and `KEEP(*(.text.init))`.
- Linker regions: `CODE` origin `0x0000_0000`, length `0x1_0000`; `DATA` origin `0x0001_0000`, length `0xFFFC`. `TEST_STATUS = 0x0001_FFFC` is outside both, so no ordinary data or stack byte can reach the reserved word (`HC`). Stack top is `0x0001_FFFC`; the first push writes `0x0001_FFF8`.
- Padding and terminal control flow (`MEMV`): after the last executed instruction a program holds at least 8 legal `NOP`s (`addi x0, x0, 0`), then a self-loop `jal x0, 0`. Derivation: when the status `SW` waits in MEM, three younger instructions can sit in IF/ID, ID/EX and EX, and `FETCH_DEPTH=3` more entries can be fetched, six words in all; 8 leaves a margin of two. The range-check self-test (X-06) puts a program at the end of the code region to show the check bites.
- Image loading: `objcopy -O verilog` hex parsed by `load_image` with the Python standard library; no new Python dependency. Built images go to `tb/sim_build/<test>/`; ELF and hex are not committed.
- Operation gate (stimulus validation): `check_ops.py` fails the build of any program that uses a mnemonic outside the 38 BASE operations. `-march=rv32i` should also make the assembler reject CSR and `fence.i` text (unverified for this toolchain).
- Oracle location: expected signature words are literals in the Python test, at the call site, each with its clause. The `.S` program writes `32'd1` to `TEST_STATUS` when it reaches its end; the status marks completion, and the verdict is signature plus monitors (`HC`: PASS does not override a failed signature).
- Assembly may use `li`, `la`, `call` (they expand to `LUI`, `ADDI`, `AUIPC`, `JALR`). Each expands within the 37 operations, and `check_ops.py` confirms it.
- Toolchain is a dependency choice (OI-3).
- The workbook is written with openpyxl 3.1.5, installed into `.venv` by Brief 006. The writing script is kept outside the repo.

## 7. Completion ABI and watchdogs (`HC`)

- Completion is an accepted `SW` to `0x0001_FFFC`: `32'd1` PASS, `32'd2` FAIL. Any other value, or `SB`/`SH` to any byte of the word, is a test-convention violation and fails the test.
- The harness identifies the status-store from its accepted address-phase payload and keeps that identity until the matching `data_response_fire`. Address acceptance alone, or an unexpected response, does not complete the test.
- On the expected response edge, registers and data memory are sampled only after that edge's updates have settled (`ReadWrite()` then `ReadOnly()`), so an older WB write retiring on that edge is included.
- Every test declares a grant-delay limit, a response-latency limit and a total-cycle limit. The memory models honor the configured policies; the watchdogs fail the test when a bound is exceeded and name which one. These are test-environment limits, not core hardware.
- The per-test configuration goes into the evidence (section 10).

## 8. riscv-arch-test adaptation (Owner decision 2026-11-12)

Facts are those the Brief copied from the GitHub README (ACT 4.0; Sail reference; `sail_riscv_sim` prebuilt release; RISCOF deprecated; Spike and Sail not installed). This agent had no web access and did not check them. Rows: A-01, A-02.

- Source and pin: a riscv-arch-test checkout pinned by commit in the `riscv_arch` manifest. Reference signatures come from `sail_riscv_sim`, version recorded in the manifest. Sail is not installed (OI-1).
- Test selection: the RV32I base tests, restricted to the 37 operations plus `FENCE`. A test is applicable when it uses only those operations and no trap behavior.
- Halt: the model's halt macro becomes `SW` of `32'd1` to `0x0001_FFFC` (`HC`). Boot at `0x0000_0000` with the section 6 start code.
- Signature: placed in the data region below `TEST_STATUS`. At the completion edge, after settle, the harness dumps the signature range and compares it with the Sail signature file. The verdict is status 1 and signature equal; a PASS status does not override a mismatch (`HC`).
- Skips, each mapped to behavior BASE puts out of scope (`AG3`); the exact list is produced when the pinned tests are reviewed, and the category names below are the expected ones:
  - CSR, ECALL, EBREAK, MRET, WFI tests: out of BASE (`Supported instruction scope`);
  - misaligned load/store tests: misaligned accesses are outside BASE;
  - misaligned jump and branch target tests: `IALIGN=32` and no exception mechanism;
  - `FENCE.I` and other extension tests (M, A, C, F, Zb*): unlisted extensions;
  - tests that need a trap vector or a trap handler: no trap mechanism.
- Open: whether the test macros themselves need Zicsr or a trap handler is unverified (OI-2). If they do, every test fails to build for BASE until the macros are adapted, and the adaptation, not the skips, is the work.
- A pass here does not establish full RV32I compliance and does not replace the microarchitectural rows (`VS`).

## 9. Exclusions

- `redirect` beating a simultaneous load-use indication (`PCP`): cannot arise, because a load-use needs a load in EX and a redirect needs a branch or jump in EX (HCU assumption P2).
- IRQ source, pending/acknowledge controller, accelerator-management frontend (`VS-g7`, `MMIO`): not part of BASE acceptance.
- Data-port address range check: `MEMV` states only the fetch check; the plan adds none (OI-10).
- Metastability, MTBF, recovery/removal timing, physical reset distribution (`VS-g6`, `RA`): not provable in digital simulation.
- Misaligned access, unsupported or illegal encodings, CSR, ECALL, EBREAK, MRET: outside BASE; no row feeds an illegal live instruction as an accepted case.
- Constrained random and the golden model (`AG` closure flow 2, 3): deferred by the Owner (OI-5).
- Numeric RTL coverage thresholds: `VS` sets none.
- Full cross-product of instruction, stall, redirect and latency: not required (`VS`); broad combinations belong to deferred random.
- Vivado half of the profile check (`CT9`): belongs to core-top; `make synth` evidence is recorded in T-07, run by the design tab (OI-7).
- Exploratory bug-hunting tests: not mandatory (`AG6`); see section 4.

## 10. Acceptance manifests and evidence fields (`AG`)

Version-controlled manifests, plain text, one entry per line, never chosen at run time (format is OI-4):

| Manifest | Content |
| --- | --- |
| regression manifest | every `regression/` test of the sheet, with its config (policies, seeds, limits) |
| integration manifest | every `integration/` program test of the sheet, with its config |
| `riscv_arch` manifest | pinned suite commit, Sail version, applicable tests, skips with reasons |
| required assertions and checkers | `M1` to `M7`, the fetch range check, the completion rules, the watchdogs, and the self-tests X-01 to X-10 |

Evidence record per acceptance run, three result classes kept separate (DUT checks, stimulus validation such as G6-14 and `check_ops.py`, checker self-tests):

- Git revision and whether the tree was dirty;
- simulator and tool versions (Verilator, cocotb, pytest, Python, gcc);
- exact commands, run with the `rtk proxy` prefix;
- random seeds, including the random-payload seeds and the T-02 pattern seed;
- per-test delay bounds and watchdog limits;
- `AG1` to `AG6` status, each with its test list;
- skips with reasons; waived failures (none unless the Owner waives, Category D).

## 11. Order of work

Owner decision, 2026-11-12: a block's internal logic must be right before its surroundings are tested. This supersedes the earlier 2026-11-12 decision "core harness first". The sheet rows are sorted in the same order: Direct, Integrated, Harness, Core, SW, ISA, Exploratory.

1. Owner reviews this document and the sheet, assigns `OWNER` and `DEADLINE` per row, and settles the open items marked blocking: OI-3 (toolchain), OI-4 (manifest format), OI-6 (collection and net access).
2. Direct: every leaf module. The `D-` rows of the sheet cover the 10 leaf test files. Specs in `docs/designs` with no test file in `tb/testcases` (checked against both listings on 2026-11-12) have a placeholder row `D-<BLK>-00`: `fetch_buffer`, `fetch_controller_unit`, `fetch_obi_interface`, `link_adder`, `operand_mux`, `result_mux`, `pipeline_register`, `hazard_control_unit`. No owner is assigned to them here, and their detailed rows are added when each block's plan is made.
3. Integrated: each stage, IF, ID, EX, MEM, WB. The `I-` rows cover the existing stage tests: `execute_stage` and `execute_stage_pipeline` (`I-EX`), `memory_stage` (`I-MEM`), `writeback_stage` (`I-WB`), unchanged.
   - Without a test: `fetch_stage`, `decode_stage`, with placeholder rows `I-IF-00` and `I-ID-00`. No owner is assigned, and their detailed rows are added when each stage's plan is made.
4. Core harness and its Harness self-tests. Build `tb/common/`: `helpers.py`, `obi_memory.py`, `image.py`, `core_harness.py`, then `link.ld`, `start.S`, `check_ops.py`; smoke program: padding plus `SW` PASS only. Then X-06 to X-08 (with G6-14, which is stimulus validation of the models), so the harness cannot pass vacuously, then monitors `M1` to `M7` with X-01 to X-05, X-09, X-10.
5. Core: rows of `GROUP=Core`. Group 3 and group 5 rows; group 4 rows with scripted latency; group 6 in direct-drive mode, including G6-13; T-01 to T-03 and T-05 (T-04, T-06 and T-07 are run by the design tab, OI-7); PQ-1 to PQ-5 once OI-6 is settled; G6-S1 to G6-S3 when design delivers `reset_synchronizer`.
6. SW: rows of `GROUP=SW`. Group 1 and 2 programs first, then group 7 with the peripheral fixture, then the program rows of groups 3, 4 and 6.
7. ISA: `riscv_arch` after OI-1 and OI-2.
8. Manifests, evidence record, acceptance run.
9. After the directed regression passes: Owner decides the deferred golden model and random (OI-5).

## 12. Open items

Each item names its consequence, options and a recommendation. Responsible is the Owner (Việt) unless stated.

- OI-1 Sail install. Consequence: no reference signatures, so A-01 cannot run. Options: (a) install the prebuilt `sail_riscv_sim` release, version pinned in the manifest; (b) build it from source; (c) drop the ISA layer and rely on directed programs. Recommendation: (a). New tool, Owner-only.
- OI-2 Test macros and Zicsr or trap handler. Consequence: unverified; if the macros need either, no test builds for BASE. Options: (a) inspect the pinned ACT macros, then (b) write a BASE macro set (halt, signature, no trap code); (c) skip the affected tests and map each skip. Recommendation: (a) then (b). The inspection needs a download, which this plan does not do.
- OI-3 Program toolchain. Consequence: build flow depends on a vendor install path. Options: (a) the Vitis gcc as checked, version pinned in the manifest; (b) a hand encoder in Python; (c) install a standalone riscv-gnu-toolchain. Recommendation: (a). A hand encoder shares the premise of the tests it feeds.
- OI-4 Manifest format. Consequence: a persistent file category. Options: (a) plain text lists; (b) JSON; (c) a Python module. Recommendation: (a), stdlib only.
- OI-5 Golden model and constrained random (Owner, 2026-11-12). Consequence: closure flow steps 2 to 6 of `AG` stay open. Options: (a) an independent semantic model for architectural random, built after the directed regression passes; (b) directed only. Recommendation: decide after the directed regression passes. No random row is mandatory now except PQ-1 to PQ-5.
- OI-6 Net access and test collection. Consequence: the rows that read contract-visible nets, deposit payload (PQ) or run monitors need net visibility in Verilator, and `pytest.ini` selects only the runner directory (read from `tb/README.md`, `pytest.ini` not opened). Options: (a) `--public-flat-rw` and cocotb `deposit` for payload, new runners in each tier folder with `pytest.ini` extended; (b) a thin SystemVerilog wrapper exposing the nets; (c) use only ports and drop the net-level rows. Recommendation: (a), because (b) adds a harness file and (c) drops the PQ rows the Owner adopted. Unverified: Verilator 5.046 behavior with these flags.
- OI-7 Structural checks. Settled (Owner, 2026-11-12): T-04 (extension logic absent), T-06 (connectivity) and T-07 (lint and synthesis) need RTL elaboration or the hierarchy script, which the verification tab is denied. They go to the design tab, and their evidence is a design-tab Report. T-03 (profile elaboration) stays with the verification worker.
- OI-8 `reset_synchronizer` contract. Consequence: G6-S1 cannot state a release bound: `RST-D1` says two stages "initially" and no record gives a cycle count. Options: (a) design writes the synchronizer spec with the release latency, then the rows assert it; (b) assert only "low until the clock has run, then high". Recommendation: (a). Responsible: design.
- OI-9 Minimum response latency of the models. Consequence: sets whether a same-cycle response is ever driven. Options: (a) minimum 1 rising edge after acceptance; (b) allow 0. Recommendation: (a); the records use "one-cycle response latency" as the fastest case.
- OI-10 Data-port range check. Consequence: a program that strays outside the data region is not caught by the harness. Options: (a) none, as `MEMV` states; (b) add a data range check, which adds a requirement beyond the records. Recommendation: (a).
- OI-11 Monitors in Python or SVA. Consequence: an SVA monitor needs Verilator assertion support (unverified) and cannot take synthetic samples for its self-test. Options: (a) Python monitors; (b) SVA through `bind`; (c) both. Recommendation: (a), with SVA added once a trial run shows the construct set works.

Contract and record gaps (no change made here):

- `pipeline-register.md` still shows the random-payload check as "not adopted" and OPEN; `execute-stage.md` still shows the EX asynchronous-reset item as OPEN. The Owner decisions are recorded only here and in the Briefs. Responsible: design to update the records.
- `BASE` calls invalid-entry payload "unspecified" (`RA`), and `PR-E7` shows it unchanged on reset. G6-12 relies on `PR-E7`.
- No record gives the `reset_synchronizer` release latency (OI-8).
- The `FETCH_DEPTH=3` capacity check in G4-07 relies on in-order allocation of entries, stated in `IFC`.

## 13. Choices made without the Owner

- Row folders (section 4): program rows of the integration items in `integration/`, port and net rows in `regression/`. Basis: the folder roles in `VS`.
- Padding of 8 words: derived from the pipeline depth and `FETCH_DEPTH=3` (section 6), within `MEMV`'s "suitable padding".
- Clock period 10 ns; falling-edge stimulus; sampling rule: `tb/README.md` conventions.
- Fill patterns (illegal word for unprogrammed code, fixed pattern for data): test choice, logged.
- MMIO fixture base `0x0001_8000`: `MMIO` allows documented test-local addresses.
- Helper names and file names in `tb/common/`: `VERIFICATION_CONVENTIONS.md` naming (verbs for helpers).
- Redirect target timing in G4-08g asserts a bound only, because `SR` says "at the earliest".
- Sheet migration (Brief 006): split rows share their parent's test function; the stimulus snippets (registers, small literals such as `0x11`, `x2=0x100`) are the author's illustrative choices and every expected value is a relation or a literal computed from them.

## 14. Not established by this plan

This is a plan. No test, harness or program exists, no simulator was run, and the gcc result in section 6 was reported by `verification-main` and not re-run here. Reading the plan or the sheet does not show that any row can pass. The expected observations are traced to the cited clauses; the records not read in full (the `hazard-control-unit.md` Status line, `pipeline-register.md` sections 1 to 5, the CI and IRQ contracts, the records behind `IF-A1`, `IF-A2` and `DEC`) are cited only through the accepted records that point to them. A future pass of these rows would establish the BASE scenarios at the core-level harness only. It would not establish full RV32I compliance, SoC or DDR integration, FPGA operation, timing closure, area, power or physical reset behavior.
