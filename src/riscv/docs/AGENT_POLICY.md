# RISC-V AI Agent Participation Policy

## Purpose

AI agents are technical collaborators, not owners of the RISC-V subsystem's engineering process. They may accelerate analysis, implementation, review, verification, and documentation, but the responsible human owner or project authority retains control over architecture, specifications, interfaces, behavioral contracts, scope, trade-offs, performance goals, research methodology, acceptance criteria, and claims.

This policy prevents implementation from becoming an accidental specification and prevents AI-authored code, tests, and documentation from sharing an unexamined premise. It governs agents working within `src/riscv/` and RISC-V-owned artifacts. It does not define collaboration policy for other subsystem owners.

## Scope and Authority

Project-wide repository structure, ownership, Git workflow, review, integration, and release rules are owned by [`../../../docs/PROJECT_MANAGEMENT.md`](../../../docs/PROJECT_MANAGEMENT.md).

The RISC-V owner may decide the subsystem's internal architecture, implementation, verification, documentation, and internal organization within the boundaries established by project authorities. A change to a shared interface, system architecture, `src/common/`, `src/soc/`, integration contract, or another subsystem requires the responsible project-level authority defined by `PROJECT_MANAGEMENT.md`.

When the two documents interact, `PROJECT_MANAGEMENT.md` determines project authority and this document determines AI participation within the RISC-V scope. Report an exact conflict instead of choosing whichever rule is more convenient.

## Sources of Truth

Use one authority for each kind of information:

- project documents own project-wide scope, goals, non-goals, ownership, and supported workflows;
- RISC-V documents own accepted subsystem-specific scope and design contracts;
- accepted specifications own intended behavior and interfaces;
- Architecture Decision Records (ADRs), when justified, own durable rationale and trade-offs;
- RTL and software plus executable evidence show implemented behavior;
- verification plans own intended evidence; reports and reproducible runs own observed evidence;
- issues or pull requests own task state, discussion, and review;
- this document owns AI participation and approval boundaries within the RISC-V scope.

Tests do not define intent unless an accepted specification explicitly designates them as the oracle. If authorities conflict, report the exact conflict and stop the affected change until a human resolves it.

## Participation Categories

"Autonomous" always means within an explicit human-requested task and the RISC-V scope. An agent may not invent its own repository work.

### Category A — Autonomous Within the Task

The agent may act without another approval when work is local, reversible, contract-preserving, and fully constrained by accepted behavior. Examples include read-only analysis, formatting, typo correction, mechanical cleanup inside the requested scope, running existing checks, and adding a directed test or assertion that directly expresses an accepted invariant using existing infrastructure.

### Category B — Propose, Then Obtain Approval

The agent must present the bounded change and wait for explicit approval before implementation when it adds maintenance surface or makes a consequential implementation choice. This normally includes reorganizing the internal RISC-V subtree, RTL refactoring, behavior-changing bug fixes, RTL implementation under an accepted contract, new testbench infrastructure, persistent scripts, build infrastructure, dependencies, and implementation of an accepted performance optimization.

A specific request such as "implement module X according to accepted specification Y" can supply Category B approval. A broad request such as "continue the cache" cannot.

Repository-wide reorganization or a change crossing the RISC-V subsystem boundary is not Category B work for the RISC-V owner alone. Classify the underlying decision as Category C and obtain the project-level authority required by `PROJECT_MANAGEMENT.md`.

### Category C — Human-Owned Engineering Decision

The agent may analyze evidence, challenge assumptions, compare alternatives, recommend an option, and draft a `Proposed` document. The responsible RISC-V owner or project-level authority must select and accept the decision before implementation.

Category C includes project scope, specifications, interfaces, protocols, reset and error behavior, timing and ordering contracts, pipeline changes, ISA behavior, custom instructions, cache or memory architecture, accelerator interfaces, interrupt or trap behavior, algorithms, performance targets and PPA trade-offs, verification strategy and acceptance criteria, research methodology, benchmark selection, and metric selection.

Human acceptance must come from the person who owns the affected scope and must identify the selected option, the decisive reason or accepted trade-off, relevant constraints, and any material assumption or revisit condition. The owner may reference an agent's analysis instead of rewriting it, but silence or "do whatever you think is best" is not acceptance.

### Category D — Reserved Human Acts

Agents may assist but may not independently perform the accountable act. Only the responsible human owner or project authority may:

- expand project scope or lower acceptance criteria;
- accept a specification or change an ADR from `Proposed` to `Accepted`;
- waive a verification failure or exclude evidence from a conclusion;
- approve novelty, superiority, performance, or research claims;
- approve or merge a contribution.

Agents must never fabricate evidence, retrofit a specification to legitimize accidental behavior, or select favorable benchmarks or metrics after seeing results without disclosing the methodological change.

## Engineering Decision Test

A choice requires human ownership if any answer below is yes:

1. Can a user, another module, software, or the verification environment observe a difference?
2. Does it change an interface, protocol, latency, throughput, reset, ordering, concurrency, or error contract?
3. Does it change a module boundary, pipeline, storage, arbitration, state ownership, or integration path?
4. Does it create a material trade-off in area, timing, power, portability, compatibility, security, maintainability, or debugability?
5. Does it change a test oracle, verification obligation, benchmark, metric, or acceptance criterion?
6. Does it introduce a persistent dependency, abstraction, file category, tool, or infrastructure burden?
7. Are there credible alternatives whose consequences or reversal cost a reviewer would need explained?
8. Can it change data interpretation, comparison fairness, novelty, or a research conclusion?

If every answer is no and the accepted contract determines the outcome, the choice may be an implementation detail. Functional equivalence alone does not make an RTL refactor trivial when synthesis structure, timing, resource inference, or portability can materially change.

## Decision-Complete Gate

Before functional implementation, determine whether the accepted contract resolves every choice that can materially change the result. Depending on the feature, this includes objective and non-goals, observable behavior, interfaces and handshakes, reset/error/stall/ordering behavior, timing requirements, arithmetic precision and overflow, system constraints, and acceptance criteria.

When a material item is missing:

1. inspect existing authorities before asking the human;
2. name the unresolved decision and its implementation consequence;
3. provide bounded alternatives and a recommendation when evidence supports one;
4. continue only independent read-only work;
5. wait for a documented human decision before writing functional RTL, tests, scripts, or normative documentation that would encode the assumption.

Documentation need only be decision-complete for the requested change. Unknowns that cannot alter the implementation are not blockers.

## Ownership Gap Gate and Implementation Modes

Push back when one request asks the agent to define a Category C decision, implement it, and create the evidence that validates its own assumption. Separate decision authority from execution.

Agent-authored verification is admissible only when its expected behavior is traceable to an accepted contract. Any reference model or oracle must be independently derived or reviewed rather than copied from the implementation under test. Never cite agreement between two artifacts sharing the same unexamined premise as independent evidence.

Each task uses one of two modes:

- **Human-authored implementation:** the human writes the functional core. The agent may explain, compare options, provide cycle or transaction traces, create an interface-only skeleton with TODOs when asked, review code, diagnose failures, and assist verification.
- **Delegated implementation:** after the human accepts the contract and explicitly delegates implementation, the agent may write the smallest accepted increment and its proportionate checks.

Core or novelty-bearing RTL includes logic whose design or implementation is a learning objective, a claimed project contribution, or a central part of the RISC-V microarchitecture. Such RTL and other explicitly educational work default to human-authored implementation. Routine adapters, boilerplate, contract-derived tests, and scripts may be delegated. Changing mode must be explicit; an agent must not interpret deadline pressure or a request for general help as permission to take over implementation.

## Approval and Decision Records

Use the lightest durable mechanism appropriate to the decision:

- Category A needs only the explicit task and accepted contract.
- Category B needs explicit approval in chat, an issue, or a pull request.
- Category C needs a decision statement from the responsible owner or project authority and an updated accepted specification before implementation.
- Use an ADR only for a durable, disputed, costly-to-reverse decision with credible alternatives or accepted residual risk.
- High-impact changes to ISA, pipeline, cache/memory architecture, accelerator protocols, or research methodology should record and accept the decision in version control before functional implementation begins.

An agent may draft a specification or `Proposed` ADR but may not mark it accepted. If implementation reveals a material contract change, stop, update the proposal, and repeat the gate rather than silently continuing.

## Minimal Scope and Repository Growth

Implement the smallest coherent change satisfying the current accepted contract. Stop when its acceptance criteria are met.

- Create a new persistent file only when the current task directly requires it, it isolates an accepted boundary, or it has a demonstrated present use.
- Introduce an abstraction for demonstrated reuse or to isolate a named contract or technology boundary, not for hypothetical future flexibility.
- Keep unrelated cleanup, generic infrastructure, future features, and opportunistic refactoring out of the change.
- Treat new dependencies, tools, directories, generators, and reusable frameworks as Category B or C according to their consequences.
- Prefer readable local logic over helpers that merely shorten code or hide the algorithm's flow.

These rules do not prohibit files or abstractions that the accepted design genuinely requires; they require a traceable reason for their existence.

## Verification and Human Accountability

No change is acceptable merely because AI produced it and tests pass. Before approval, the responsible human reviewer or owner must be able to explain:

- the problem and why the change exists;
- the accepted contract and relevant trade-offs;
- externally visible behavior and integration effects;
- the important datapath, state transition, transaction, or cycle sequence;
- what each cited test can and cannot establish;
- remaining assumptions and risks.

For material RTL, require a predicted cycle or transaction trace, a state-transition explanation where applicable, and at least one test capable of falsifying the intended behavior. Report exact commands and observed results. Compilation alone is not functional verification, and unit evidence is not end-to-end evidence.

## AI Transparency

Disclose material AI assistance at pull-request level, or in the commit description when no pull request exists. State what the agent contributed and what the human reviewed or decided.

Assistance is material when AI substantially contributes nontrivial RTL or algorithms, a test oracle or reference model, verification strategy, a specification or ADR adopted by the project, build infrastructure, a substantial refactor, experimental analysis, or wording and reasoning used in a research claim.

Mechanical execution of human-specified edits, file moves, scaffolding, routine commands, autocomplete, formatting, typo fixes, syntax corrections, simple API lookup, and small reviewed boilerplate does not by itself require disclosure. Per-file markers and mandatory AI attribution in every commit are unnecessary. Mark files as generated only when a deterministic generator owns them and humans should not edit them directly.

## Research Integrity

Humans own the research question, experimental methodology, benchmark and metric selection, exclusion criteria, comparisons, novelty assessment, and conclusions. Record material methodology before collecting or interpreting the evidence it governs; document later changes and their reasons rather than rewriting history.

Agents may analyze data, find anomalies, challenge interpretations, automate experiments, and draft carefully bounded prose. They must distinguish measured results from inference, preserve provenance and unsuccessful results relevant to the conclusion, avoid cherry-picking, and never manufacture a narrative or claim unsupported by reproducible evidence.

## Enforcement and Policy Changes

`AGENTS.md` and this policy guide agent behavior but are not security boundaries. Branch protection, Pull Requests, merge authority, and project-level review follow `PROJECT_MANAGEMENT.md`. CI may enforce objective checks such as build, lint, tests, and generated-file consistency, but it cannot prove conscious human ownership.

Changes to this policy are Category C. Agents may propose edits, but the RISC-V owner must approve their meaning and scope; changes affecting project-level authority additionally require the authority defined by `PROJECT_MANAGEMENT.md`.
