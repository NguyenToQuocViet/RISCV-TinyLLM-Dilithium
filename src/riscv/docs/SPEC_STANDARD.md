# Block Spec Standard

| Field | Value |
| --- | --- |
| Description | Fixes the structure, writing rules, decision IDs, length, process and PDF layout of every block spec. |
| Last modified | 2026-11-07 |
| Status | Accepted by Việt on 2026-11-06 |
| Owner | Nguyễn Tô Quốc Việt |
| RTL | None, because this standard governs specs, not RTL. |
| Parent | None, because this standard has no parent document. |

## 1. Overview

- A block spec states what one block does at its ports.
- Specs are written in English.
- The `.md` file is the source.
- The PDF is the form that people read, built from the `.md` by the script in section 8.
- Every PDF looks the same and differs only in content, so a reader who knows one PDF knows all of them.
- The model for voice and depth is the gold sample, linked in section 9.
- Two document types exist.
  - The Block Spec is defined here.
  - The Architecture Spec covers BASE and the CI and IRQ extensions. It shares the header and PDF look, and it is not yet defined (see Decisions and Open Items).

## 2. Header

- The title line is `# <block name>`, followed by a two-column table with the columns Field and Value.
- The fields appear in this order.

| Field | Value |
| --- | --- |
| Description | One sentence, identical to the RTL header Description. |
| Last modified | Date of the last change, `YYYY-MM-DD`. |
| Status | Starts with one of Draft, Proposed, Accepted or Superseded. |
| Owner | The person who mainly designs and approves the spec. |
| RTL | The RTL file and module, or None with a reason. |
| Parent | The documents this spec builds on, as links, or None with a reason. |

## 3. Sections

- Every block spec has the ten sections below, in this order.
- Each section must be present. A section with no content reads `None`, followed by a reason.

| # | Section | Question it answers | Form |
| --- | --- | --- | --- |
| 1 | Overview | What the block is responsible for, and what it does not do | Bullets |
| 2 | Block Design | Who the block talks to, and on which side | Diagram only |
| 3 | Interface | Which ports exist, and what each carries | Table: Signal, Dir, Width, Peer, Description |
| 4 | Internal Structure | Which sub-blocks it contains | Bullets, or None |
| 5 | State | Which registers it holds, and how each resets and updates | Table: Register, Reset value, Updater, or None |
| 6 | Behavior | What each output is under each condition, and which condition wins when events coincide | Condition table, then bullets for reasons |
| 7 | Timing and Control | When outputs are valid, and what reset, stall and flush do | Bullets for timing; "When valid" table; "Reset, stall, flush" table; one trace |
| 8 | Assumptions and Corner Cases | What the block relies on, and what happens when two events meet | Assumption table; corner-case table |
| 9 | Verification | Which checks are planned, and whether they exist | Planned-checks table; test status bullet |
| 10 | Decisions and Open Items | Why the design is what it is, and what is unsettled | Decision table; history line; old ID map; open items |

| Diagram side | Carries |
| --- | --- |
| Left | Inputs, each labeled with its peer |
| Right | Outputs, each labeled with its peer |
| Top | Clock and reset |
| Bottom | Control from the HCU |
| Many ports | Signals grouped by peer on each side |

- A script generates the diagram from the Interface table. Until the script exists, the diagram is drawn by hand.
- The Timing and Control section gives one trace, for the hardest behavior only. Its pre-state is defined in a bullet before the table.

## 4. Writing Rules

- Every block spec follows these twelve rules.

| # | Rule |
| --- | --- |
| 1 | Understand before writing. If the mechanism cannot be explained, it goes to open items. |
| 2 | Every line earns its place. |
| 3 | One fact sits in one place. Elsewhere, link to it. |
| 4 | Each section states its conclusion first. |
| 5 | Dependency order: define before use, with no forward reference. |
| 6 | A reason appears only when it is real. Join it inside the sentence with `because` or `so`. A plain fact stands alone. Never use a `Reason:` label. Test: does the second half explain why the first half is true or required? |
| 7 | Use tables for enumerable content. Every other line is a `-` bullet with one atomic claim. Use sub-bullets only for dependency. Write no prose paragraphs. |
| 8 | Write in the present tense and the active voice, with a block or signal as subject. Keep each sentence to 25 words or fewer. |
| 9 | One concept, one word. Use the signal and block names from the Interface table. |
| 10 | Use `must` for a requirement and `may` for an option. Do not hedge. |
| 11 | Write no process talk and no filler: no status checks, no references to the task, no "this section describes", no "note that". Put history only in Decisions and Open Items. |
| 12 | Write no RTL in a spec: no code, no boolean output equation, no operator, no internal signal name. State behavior at the ports, in condition tables and sentences. |

- Rule 12 has one reason, stated once: a test derived from copied RTL only confirms the RTL equals itself.

## 5. Decision IDs

- Decision IDs take the form `<BLOCK>-D<n>`, for example `HCU-D1`.
- A rewrite that changes IDs must map each old ID in Decisions and Open Items, because other documents cite the old IDs.

## 6. Length

- Soft limits apply to the length of a block spec.

| Block kind | Limit |
| --- | --- |
| Leaf with fewer than 8 ports | 2-3 pages |
| Larger leaf or stateful block | 3-5 pages |
| Wrapper or stage | 2-4 pages |

- A spec that exceeds its limit must state the reason in Decisions and Open Items.

## 7. Process

| Step | Action |
| --- | --- |
| 1 | The writer gives an outline: for each section, the claims in dependency order, each with its reason. |
| 2 | The Owner reads and approves the outline. |
| 3 | The writer writes the prose only after approval. |
| 4 | A person reads every line, because machine checks alone passed a version with eight errors. |

## 8. PDF

- A spec is built with `scripts/spec_pdf/build.sh docs/designs/<name>.md`.
- The output goes to `docs/pdf/`, which is not committed.
- The layout is A4 with 2 cm margins and Liberation Serif 11 pt.

## 9. Gold Sample

- The gold sample is [the hazard control unit spec](designs/hazard-control-unit.md).

## 10. Decisions and Open Items

| ID | Decision | Where | Reason |
| --- | --- | --- | --- |
| STD-D1 | Specs are in English. The `.md` is the source; the PDF is for people. | [Overview](#1-overview) |  |
| STD-D2 | Two document types: Block Spec and Architecture Spec. | [Overview](#1-overview) | BASE and the extensions need sections the block spec does not have. |
| STD-D3 | Header is a Field and Value table with six fields. | [Header](#2-header) | Plain lines render as one paragraph. |
| STD-D4 | Ten fixed sections, always present. | [Sections](#3-sections) | Fixed order lets a reader find each question in the same place. |
| STD-D5 | Twelve writing rules. | [Writing Rules](#4-writing-rules) | Existing specs ranged from 1x to 8x in spec-to-RTL ratio and read as lists of facts. |
| STD-D6 | Decision IDs `<BLOCK>-D<n>`, with old IDs mapped on rewrite. | [Decision IDs](#5-decision-ids) | Other documents cite the IDs. |
| STD-D7 | Soft length limits per block kind. | [Length](#6-length) | Depth must follow block complexity, not the date a spec was written. |
| STD-D8 | Outline approval before prose, then a person reads every line. | [Process](#7-process) | Machine checks alone passed a version with eight errors. |
| STD-D9 | PDF built by script, with a fixed layout. | [PDF](#8-pdf) | Every PDF looks the same. |

- History: 2026-11-06, the Owner settled these decisions, and this standard records them. 2026-11-07, the Owner widened the leaf length limits.
- Old ID map: none, because this standard renumbers no IDs.
- Open items:
  - The Architecture Spec format for BASE and the CI and IRQ extensions is not defined.
  - The diagram script is not written, so diagrams are drawn by hand.
  - Existing specs do not yet follow this standard, because migration is a separate task.
