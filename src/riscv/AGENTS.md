# RISC-V Subsystem Agent Guidelines

## Current State

This file governs agent work only within `src/riscv/`. Project-wide repository structure, ownership, Git workflow, review, integration, and release rules are defined in [`../../docs/PROJECT_MANAGEMENT.md`](../../docs/PROJECT_MANAGEMENT.md).

The RISC-V subsystem is being rebuilt from a clean scaffold. Treat only committed project documents, accepted decisions, source, and reproducible evidence as authoritative. Do not infer architecture, internal layout, toolchain, interfaces, or performance targets from the repository name or from prior projects.

Before modifying RISC-V RTL, tests, scripts, build infrastructure, specifications, research artifacts, or internal structure, read [`docs/AGENT_POLICY.md`](docs/AGENT_POLICY.md) and apply its participation categories, Decision-Complete Gate, and Ownership Gap Gate.

## Migration Direction and Document Map

Start with a five-stage core baseline without cache or branch prediction so later additions have a defined comparison point. This orders the work; cache and predictor RTL may be migrated in later increments. The order needs no standalone `core-first` decision record. Each migration increment belongs on a short-lived feature branch and reaches `develop` through review and a Pull Request, as defined by [`../../docs/PROJECT_MANAGEMENT.md`](../../docs/PROJECT_MANAGEMENT.md). Keep the migration history in versioned documents and Git, not in a long-lived branch.

Use each document for its own question:

| Document | Read or update when | Owns |
| --- | --- | --- |
| [`../../README.md`](../../README.md) | Orienting to the project or updating its high-level status. | Project overview and links, not detailed core behavior. |
| [`../../docs/PROJECT_MANAGEMENT.md`](../../docs/PROJECT_MANAGEMENT.md) | Planning branches, ownership, review, integration, or release. | Project-wide workflow and authority. |
| [`../../docs/ROADMAP.md`](../../docs/ROADMAP.md) | Defining or changing a team milestone. | Project direction, version scope, and acceptance criteria; RISC-V work enters it at the project-milestone level. |
| [`../../docs/CHANGELOG.md`](../../docs/CHANGELOG.md) | Recording an accepted development change or release. | Project-level change summary, not per-file migration status. |
| [`docs/AGENT_POLICY.md`](docs/AGENT_POLICY.md) | Assigning agent participation, decision ownership, or implementation mode. | RISC-V AI collaboration boundaries and gates. |
| `docs/MIGRATION.md` (planned) | Reviewing or migrating any old RISC-V RTL, including later cache or predictor work. | Living file-level history: old repository revision and path, review status, disposition, destination, material changes, and evidence. It tracks work; it does not define milestone scope or core behavior. |
| `docs/designs/5-stage-baseline-core.md` (planned) | Drafting, reviewing, implementing, or verifying the five-stage baseline. | Intended core behavior, interfaces, microarchitecture, and verification expectations once accepted by the RISC-V owner. |
| `docs/decisions/` | A material RISC-V-owned choice needs durable rationale and trade-offs beyond the current design contract. | Accepted subsystem decisions; ordinary migration steps and the baseline-first order need no separate record. |

Planned paths are not current authorities until their documents are written, reviewed, and merged. Place RISC-V-internal technical designs under `docs/designs/` as needed; use the same contract role as the five-stage document for later configurations or substantial internal features. Project-wide decisions, shared designs, and system-level architecture follow the root `docs/decisions/`, `docs/designs/`, and `docs/architecture/` authorities in `PROJECT_MANAGEMENT.md`. Escalate shared interfaces and cross-subsystem effects to the project-level owner.

Before starting a RISC-V feature for the next project milestone, confirm that `ROADMAP.md` defines that milestone's scope and acceptance criteria. For each migration increment, inspect the exact old source revision, review its behavior, resolve and document implementation-shaping decisions, then change RTL and verify it. Update `MIGRATION.md` as review status, disposition, destination, changes, or evidence evolve, and include the relevant update in the increment's PR. Keep a design marked `Proposed` until its owner accepts it; a file's existence or old RTL behavior does not establish an accepted contract. Update the owning design when intended behavior changes, and link related documents instead of copying their contents. Preserve established document names; use descriptive lowercase kebab-case names for new RISC-V designs and decisions.

Organize RISC-V RTL by function. Share a source module across five- and seven-stage configurations when its contract matches; name divergent modules distinctly. Use filelists and build profiles to select sources and top modules for each configuration. A filelist does not disable logic instantiated by a selected top module.

## Mandatory Agent Workflow

1. Inspect the applicable instructions, specifications, decisions, source, tests, and Git state.
2. State the requested task envelope and identify whether the RISC-V owner or a project-level authority owns each intended decision.
3. Classify the work under Categories A-D in `docs/AGENT_POLICY.md`.
4. Confirm that every material implementation-shaping decision is documented and owned by the responsible human authority.
5. Obtain the approval required by the assigned category before making functional or persistent changes; the explicit task is sufficient for Category A.
6. Make the smallest coherent change within the accepted scope.
7. Validate with repository-defined commands and report what ran, what passed, and what remains unverified.

Read-only analysis, review, diagnosis, and option comparison may continue while a decision is pending. They do not authorize edits.

## Required Pushback

Stop before implementation when a feature is not decision-complete. Identify the exact missing contract, explain how it can change the implementation, and present bounded alternatives when useful. Do not encode an assumption in RTL, tests, scripts, or documentation and then treat the resulting behavior as accepted intent.

Push back when a request would make the agent both choose a human-owned engineering decision and implement it. Return the unresolved choice to the human with its trade-offs. Silence, vague assent, existing code, and passing tests are not approval of a design decision.

Core or novelty-bearing RTL and explicitly educational work default to **human-authored implementation**: provide explanation, traces, skeletons, TODOs, review, and verification help without completing the functional implementation. Switch to **delegated implementation** only when the human explicitly delegates it after accepting the contract.

## Scope, Evidence, and Accountability

- Keep changes within `src/riscv/` unless the responsible project authority explicitly authorizes cross-subsystem work. Preserve project scope and unrelated user work.
- Follow project-level authorities for shared interfaces, `src/common/`, `src/soc/`, integration behavior, and any change affecting another subsystem.
- Do not add speculative features, abstractions, helpers, files, dependencies, or infrastructure.
- A new persistent artifact must be required by the current task, isolate an accepted boundary, or have a demonstrated present use.
- Compilation is not functional proof. Tests prove only the behavior they actually exercise, under the inspected integration path.
- Never invent commands, measurements, coverage, timing, area, power, performance, novelty, or research conclusions.
- Disclose material AI assistance as required by `docs/AGENT_POLICY.md`.
- Agents may draft proposed specifications and decisions, but only the responsible human owner or project authority may accept them, approve research claims, waive failed evidence, or merge changes.

## Repository Commands

Use only build, lint, simulation, or test commands supported by committed project or RISC-V evidence. If none are defined, report that instead of guessing. When a toolchain is accepted, document its reproducible entry points in the appropriate project location. For documentation-only changes, run `git diff --check` and inspect the complete diff. Do not commit or merge unless explicitly requested.
