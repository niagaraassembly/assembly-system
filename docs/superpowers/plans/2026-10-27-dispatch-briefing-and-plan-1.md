# Assembly System: Dispatch Design Briefing and Implementation Plan 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement Part 9 task by task. Steps use checkbox (`- [ ]`) syntax. Parts 1–8 are the briefing you must read first; Part 9 is the only part you may implement without further owner approval.

**Goal:** Hand a new agent everything decided about the Assembly System so far, separate what the owner decided from what is still open, propose how the remaining parts of the architecture work as one operational system, and specify the first buildable slice (treat, resolve, plan).

**Architecture:** Dispatch is the one executable ("assembly-native") function of the Assembly System. Everything else is a versioned library of reference files plus pointers to external repos and routines. Stages talk to each other through records and events in files, never by calling each other, so each stage can be replaced.

**Tech Stack:** Python 3.9+, standard library only, JSON records, `unittest`. Execution of every scan, file task and join job is delegated to machine-flows (`mach`), never run from this repo.

**Spec:** The Linear document "Assembly System: architecture reading and decisions so far (2026-10-27)" (id `be1586dc-0a72-454b-b6c9-988e61d32dcc`, section "Dispatch design decisions (2026-10-27, later session)"), Linear issue NA-361, and Part 4 of this file (the decision register, which is the binding summary).

Written 2026-10-27 by Claude (Sonnet 5.5) for Morgen Peers, from a long design conversation. Source file: `docs/superpowers/plans/2026-10-27-dispatch-briefing-and-plan-1.md` in the assembly-system repo (uncommitted when this copy was published to Linear; the repo copy is the working version for agents, this Linear document is the shareable copy).

---

# PART 1. Orientation

## 1.1 Who and what
- **Owner:** Morgen Peers, founder of Niagara Assembly ("NA"). Single decision-maker. Every approval below is theirs.
- **Machines:** three work machines. `thinkpad1` (hostname `tpad`, Debian, tight memory and disk; this is where the design work happened), `deb` (Panasonic Toughbook, strong), `macbook1` (MacBook Air, weak). Identity is never taken from the hostname. An agent running on one machine cannot reach the others.
- **machine-flows** (`~/machine-flows`, Syncthing-shared, its `.git` never synced): the owner's system for their machines and AI tools. It owns tool choice, quotas, environments, scheduling and execution. Its CLI is `mach`. Plan 22 (`plans/22-cross-machine-tasking.md`) is its cross-machine tasking design; Linear project "Machine Flows", epic NA-328.
- **Assembly System** (this repo, `~/na/assembly-system`, private GitHub repo `niagaraassembly/assembly-system`): the company-level system. To the company, it is what machine-flows is to the laptops. Linear project "Assembly System" (P-NA-19), team key `NA`.
- **na-research** (`~/na/na-research`): the existing research repo whose "Regional Desks" system already does a version of scan, ingest, review, join and publish. The owner said: use it to understand how joining currently happens, but **the new system is not bound by it**. See Part 7.

## 1.2 Working rules for any agent in this repo
Read `AGENTS.md` in the repo root. In short:
- Never hand-edit `profiles/`, `creations/` or `registry/`. Create and change things only through `bin/assembly`. Never mint or invent an ID.
- No data and no code of other projects in this repo. Profiles hold pointers. No secrets anywhere.
- Preview, then `--apply`. Back up before overwriting.
- Handoff documents are written only by `assembly/handoff.py`.
- machine-flows is read-only from here.
- Python 3.9+, standard library only. Tests first: write the failing test, watch it fail, then implement. Run `python3 -m unittest discover -s tests`.
- **Do not commit, push, merge or create remotes unless the owner asks.** The owner has approved each commit and PR so far explicitly.
- Commit identity (repo-local): `Morgen Peers <97772312+peers8862@users.noreply.github.com>`. The global git identity is a personal address; do not use it. Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Commit messages: `type(scope): message (NA-123)`. PR titles: `[NA-123] Short description`.
- Branch names follow Linear's, e.g. `office/na-361-...`.

## 1.3 Current state of the work (verified 2026-10-27)
| Item | State |
|---|---|
| `main` of assembly-system | v0 only, commit `6ee0f27` |
| PR #1 `feat/record-changes` (NA-355: set, retire, supersede, injection fix) | MERGED 2026-10-28 |
| PR #2 `feat/profile-seed` (NA-356: `--existing`, 35 profiles), stacked on #1 | MERGED 2026-10-28 (after #1) |
| mach PR #5 `feat/bindings-na-360` (machine-flows reads IDs from bindings) | see Linear NA-360; merged 2026-10-28 if the owner's session merge succeeded |
| Tests | 93 passing on `feat/profile-seed` |
| Profiles | 13 repos (`R-0001…R-0013`), 22 units (`U-0001…U-0022`) |
| Merge order | done: #1, then #2 |

Linear issues in project "Assembly System": NA-351 (v0, done), NA-352 (repo, done), NA-355 (change records, in progress), NA-356 (profiles, in progress), NA-353 (handoff v1), NA-354 (handoff v2), NA-357 (bays lifecycle), NA-358 (event feed and notifications), NA-361 (digests design). In project "Machine Flows": epic NA-328 and children (NA-329 inbox hardening, NA-330 contract v1, NA-341–343 delegation router, NA-134 model-router location decision).

---

# PART 2. What is built (ground truth)

## 2.1 Assembly System code (`assembly/`, `kinds/`, `tests/`)
| Piece | What it does |
|---|---|
| `ids.py` | Mints `PREFIX-NNNN` IDs under a lock file. Counters in `registry/counters.json`. Never reuses an ID. |
| `kinds.py` + `kinds/*.json` | A kind is a JSON file: prefix, fields (types `text, enum, link, list, date, int, bool`; `required`, `values`, `target`, `pattern`) and `steps`. Adding a kind is adding a file. |
| `create.py` (`assembly new KIND`) | The one front door. Validates, mints, writes the profile, runs the kind's steps (`handoff` writes a task document; `manual` leaves a checklist line). Progress is written to `creations/<ID>.json` as it happens; states `complete`, `manual-pending`, `partial`; resumable. |
| `records.py` | Profile JSON: `{schema, id, kind, fields, status, ...}` plus an event history (`add_event`). Saved to `profiles/<kind>/<ID>.json`. |
| `change.py` | `set`, `retire`, `supersede`: validated, recorded (old to new, who), bump `rev`; nothing is ever deleted. |
| `handoff.py` | Builds machine-flows prompt documents (see `docs/handoff-v0.md`). Exact `procedure` becomes "run exactly these steps"; otherwise an agent chooses the approach. Non-owner trust or writes force `approval: before-run`. Hardened against frontmatter injection (fail closed). |
| `handback.py` | Reads machine-flows run records read-only (matched by the `as:<ID>` tag) and moves record status: queued→dispatched, running/waiting-approval→running, done→awaiting-confirmation, failed/cancelled→failed. Only `assembly confirm` (owner) sets `answered`. |
| `cli.py` | `kinds, new (--set, --from, --existing, --outbox, --apply), show, list, lint, dispatch, resume, set, retire, supersede, handback, confirm` |

**Kinds today (prefix):** question `Q`, goal `G`, service `S`, unit `U`, repo `R`, dataset `D`, bay `B`.
**Statuses today (record level):** `new → dispatched → running → awaiting-confirmation → answered | failed | retired`.

**Important:** the question fields, the six lens values, the status list and the unit `stage` list were **inferred by the assistant** from the architecture graphic (the owner said "we can infer what a question should have available… by the rest of the total design"). They were never individually approved. Several are now known to be wrong or incomplete (Part 4.4).

## 2.2 machine-flows pieces Assembly depends on
- Prompt documents in `files/inbox/prompts/` (frontmatter schema `mach: 1`; required keys `mach, type, title, goal, tool, output`; optional `permission, path, machine, due, approval, tags, model`); `mach run --inbox`; run records `files/runs/YYYY/MM/<id>/run.md` + `input.md`.
- `subsystems/na/bindings.toml` (generated): per-machine repo paths and roles keyed by Assembly IDs. mach PR #5 teaches `mach subsystem` to read it. The old `subsystems/na/subsystem.toml` is untouched and still drives routing.
- Known issue: `mach queue` crashes on a stale run record (NA-329).

---

# PART 3. The architecture graphic: every element and where it stands

**Caveat for the reader:** the diagram was an image attached in the conversation; it is not in this repo and the assistant cannot show it again. The element list below was transcribed in the conversation. **Ask the owner to re-attach the image** before trusting any placement claim, especially the red items.

Flow as transcribed: Regional → Assembly → Services (Internal / External) → Goals (Companies / Users) → Questions (Historic / Current) → six lenses (Law, Land, Companies, Products, Processes, Programs) → **DISPATCH** → Scan (Automation) / File (Manual, APIs) → Join (Registries; Digests) → Stores (Databases; Reviews) → Bays (Branches; Reviews) → Move (Timers; Checks) → Notifications → **Line** (promises: View, Read, Make, Save, Acts). Stores loop back through APIs to File. Red underlined items are events or hand-off records: Identities, Demand, Compose, Convert, Digests, Reviews, Checks, Notifications. Aim: very resilient, standalone, modifiable microservices.

| # | Element | Status | Where it is covered |
|---|---|---|---|
| 1 | Regional | Partly: `region` is a free-text field | 6.1 |
| 2 | Assembly (the library) | **Decided in principle** (D20), structure proposed | 6.2 |
| 3 | Services: Internal / External | Kind exists; external participation decided in principle | 6.3 |
| 4 | Goals: Companies / Users | Kind exists; conversion to questions decided in principle | 6.4 |
| 5 | Questions: Historic / Current | **Largely decided** (D24–D31); kind needs v2 | 6.5, Plan 1 |
| 6 | Six lenses | Enum exists; role in routing proposed | 6.6 |
| 7 | **Dispatch** | **Decided to sketch level**; unbuilt | 6.7, Plan 1 (first slice) |
| 8 | Scan (Automation) | Unaddressed on the Assembly side; na-research is a precedent | 6.8 |
| 9 | File (Manual, APIs) | Unaddressed beyond principle (D33) | 6.9 |
| 10 | Join: Registries, Digests | Digest concept decided (D21, D29, D34); Join contract unaddressed | 6.10, 6.11 |
| 11 | Stores: Databases, Reviews | Dataset kind (pointer) only | 6.12 |
| 12 | Bays: Branches, Reviews | Bay kind (v0); lifecycle unbuilt (NA-357) | 6.13 |
| 13 | Move: Timers, Checks | Unaddressed | 6.14 |
| 14 | Notifications | Message classes decided on the machine-flows side; Assembly side unaddressed (NA-358) | 6.15 |
| 15 | Line: View, Read, Make, Save, Acts | Promises recorded on units; meaning unaddressed | 6.16 |
| 16 | Stores → APIs → File loop | Unaddressed | 6.9 |
| 17 | Red events | Mapping is the assistant's reading | 6.17 |

---

# PART 4. Decision register (what the owner said, kept separate from what the assistant said)

Sources: **Stated** = the owner said it. **Affirmed** = the assistant proposed, the owner agreed. **Corrected** = the owner corrected an assistant statement. Anything not in this part is an assistant proposal and needs approval.

## 4.1 Foundations
| ID | Decision | Source |
|---|---|---|
| D1 | The Assembly System is its own code base profiling the code bases, products, projects and datasets in its purview, as machine-flows is to the laptops. | Stated |
| D2 | Profiles live in the Assembly System; data and code do not. | Stated |
| D3 | Dispatch is the main point of interaction. | Stated |
| D4 | The Assembly System mints **all** IDs; machine-flows only refers to them. | Stated |
| D5 | Anything new, including questions and goals, is created through one centralized creation action that captures more than an ID. | Stated |
| D6 | Bays are time-limited accumulation branches (for example a weekly branch holding the daily regional news scan findings) that are checked, then merged into the main databases/CSVs. | Stated |
| D7 | Linear is the coordination hub for Niagara Assembly work (project "Assembly System"). machine-flows' own future work, including a localhost review website, is flagged in machine-flows plans, not Linear. | Stated |
| D8 | The "ready" signal for a pipeline step is the owner confirming a digest. | Stated |
| D9 | Tool, quota and environment knowledge belongs to machine-flows. The Assembly System says what is needed, never which tool. | Stated |
| D10 | Message classes: notice, decision card, review pack. In-app replies by button for short choices; longer structured, styled presentations for reviews (email, possibly a localhost site). | Stated / Affirmed |
| D11 | Handoff should need no agent interpretation where possible; some tasks need deeper agent work and that is fine. Handoff and handback will go through several versions (v0 built; v1, v2 planned). | Stated / Affirmed |
| D12 | The graphic: the top half is conceptual/administrative framing; the middle and bottom are a repeated routine for ingesting, joining, digesting, reviewing and pushing into a business "line". External apps affirm/extend/add goals, not only call an API. The aim is resilient, standalone, modifiable microservices. | Stated |
| D13 | Private repo, local checkout at `~/na/assembly-system`. | Affirmed |

## 4.2 Dispatch and questions (this design session)
| ID | Decision | Source |
|---|---|---|
| D20 | Dispatch is the one assembly-native function that ties things together. The rest of Assembly is reference and guidance files, externalized repos and routines: templates, agent-designed prompts for workflows, joining rules, dataset "spin" designs, timer information, notification preferences. | Stated |
| D21 | A scan's digest and a file submission's digest are each a review point, automated or manual. Results are relayed back to Dispatch, which updates the dispatches it emitted. | Stated |
| D22 | A question's route is **not stated** in the question. The way it is dispatched, its metadata (including complexity and relevance to several registries) and its associated digest templates enable routing without an explicit destination. | Stated |
| D23 | Binding a question to a Bay is a way to limit where ingestion results can arrive (the surface). | Stated, as "interesting"; treat as direction, not final |
| D24 | A question's submitter stamps it minimally with enough metadata to route it correctly. A later step expands it: high-level tags from which accurate groups of labels are inferred, plus a UI submit/reply step that asks quick questions, completing the treatment in a mixed automatic and manual effort. | Stated |
| D25 | Vocabulary is not free-form. It is based on the data architecture and service designs. Dispatch may flag and draft taxonomy changes. **Only the owner approves proposals.** | Stated |
| D26 | Questions are **standing** (many, shaping scans) or **time-limited**. They are combined into synthesized scan or file prompts, together with the timeframes and effort levels requested. | Stated |
| D27 | Bundles group by **region and cadence**. Sources vary within a bundle. A bundle is defined by its combination of metadata, not by question count, so a single-question bundle is valid. The dispatch record is per bundle. | Stated |
| D28 | A time-limited question can fire its own extra run. | Stated, "not a big or finalizing claim" |
| D29 | Digests do not report per question (not feasible or desirable). Results go back to Dispatch through **assessment scanners** that mark the bundle with kinds of success criteria: quantity now (how many results surfaced against what the scan set out to find), quality later, shaped by the shaping prompts. A Join's fields, rules and naming are known in advance, so expected result formats can exist ahead of time as standing spreadsheets or templates. Logged as NA-361. | Stated |
| D30 | A question can feed two or more intelligence pools. Dispatch resolves a set of pools, not one route. | Stated |
| D31 | Questions are internal or external in origin, and historic or current in time. "Current" means: a point (a day, usually the present); a recent past period; or a period that extends into the past and includes the present (this quarter; a program that started two years ago and expires soon). Future is excluded here (it is projection) and belongs elsewhere in the diagram. | Stated |
| D32 | External questions and their results keep provenance (where they came from), pass through Join (parsed, given IDs, contributing to totals) and stay stamped. | Stated |
| D33 | Visibility of results to other askers depends on arrangements, relationships and the business lines results feed. Some external questions are processed as a research service. Others (the crucial kind for this platform) are **gap questions**: a regional actor, in partnership with the Assembly System, solves a data or service gap. Such a company, injecting data by API at Scan/File, is invited to distill what it enables into one or more bundles of questions. The injection's purpose is to incorporate and harmonize its field and value identities with ours. | Stated |
| D34 | Field-and-value mapping is presented as a **digest for approval**, shaped by the rules and formats of Join. The Join act then mints IDs where needed and makes aligning record writes; **those go to a second review point before Stores**. | Stated |
| D35 | Dispatch uses pre-formulated analytical prompts together with the AI agent's general abilities to create an anticipated context, a "surround of meaning", for a scan, file or API linkage. It gives reception and digest formulation a running start and technical context. | Stated |
| D36 | Current practices in na-research are reference, not binding. | Stated |

## 4.3 Working names the owner did not object to (not decisions)
"treatment" (the expand-and-complete step), "bundle", "surround", "assessment scanner", "arrangement", "gap question", "research-service question". Rename freely, but ask first.

## 4.4 Corrections: do not repeat these assistant mistakes
| Assistant said or built | Owner's correction |
|---|---|
| A question carries `store` and `bay` as destinations. | Routing comes from metadata plus digest templates; destinations are not stated on the question. (`bay` and `store` on `kinds/question.json` should become hints at most.) |
| Each digest reports a coverage status per question. | Not feasible or desirable. Report per bundle through assessment scanners. (NA-361) |
| A question has one route. | It can feed several pools. |
| Bundle questions that share sources. | Bundle by region and cadence; sources vary within a bundle. |
| Trust level is the axis for external questions. | Think internal vs external first. (Trust remains a safety control, derived from origin; see 6.5.) |
| Bay is a hard limit as a separate bundling rule. | With region and cadence as the grouping, the bay mostly follows. Treat it as the surface allow-list. |
| Whether one confirmation both accepts a digest and approves the join. | Two decisions: the digest approval comes before Join; Join's writes get their own review before Stores. |
| Explaining the answer with labels like "(your words)". | Dropped. In chat, state things plainly. This document is the exception because the owner asked for the distinction. |

---

# PART 5. How the pieces interlock (one-page model)

```
 PEOPLE / APPS ───────────────► (D12) services, goals, "demand"
   │ stamp (minimal tags)
   ▼
 QUESTION  ──treat──►  labels + provenance + quick questions to owner/submitter (decision cards)
   │ treated = every required label known
   ▼
 DISPATCH (the one executable part)
   resolve:  question labels + library rules  → set of intelligence POOLS (D30)
   bundle:   resolved questions → bundles by region + cadence (+ splits on origin, sensitivity, trust, effort)
   surround: pre-built analytical prompts + agent  → anticipated context, frozen on the dispatch (D35)
   emit:     handoff (to machine-flows)  or  filing request (to people / API client)
   receive:  results arrive; register arrivals
   assess:   assessment scanners mark the bundle (quantity now, quality later) (D29)
   digest:   review point #1 (auto or owner): findings + proposed field/value mapping (D34)
   hand on:  accepted digest → JOIN
 JOIN (rules from library; mints IDs via Assembly) → proposed change-set
   review point #2 (D34)  → STORES (main) via BAY (weekly branch) → MOVE (timers, checks) → NOTIFICATIONS → LINE
 STORES ──API──► FILE (loop): internal derived intake, provenance extended
```

Rules that hold the whole thing together:
1. **Records, not calls.** A stage reads records and writes records plus events. No stage imports another's code to get work done. Any stage can be replaced if it honors its record contract.
2. **Every operation is idempotent** under a key (for example `bundle-key + period`). Re-running changes nothing and duplicates nothing.
3. **Everything that matters is frozen at emit time:** template versions, prompt versions, bundle composition, resolved pools, surround. A digest can be explained afterwards.
4. **Human gates are few and named:** vocabulary changes, digest approval, join review, bay merge, publication. Everything else is automatic or advisory.
5. **Provenance is a chain of minted IDs** carried everywhere: party → goal → question → dispatch → results → joined record.
6. **Fail closed** on trust, sensitivity and approval. Never infer them silently.
7. **Preview, then apply**, as everywhere in this owner's systems.
8. **Execution belongs to machine-flows.** Dispatch emits what is needed, with an effort level and a window, never a tool.

---

# PART 6. Proposals for every element not yet decided (point for point)

Everything in this part is a **proposal**. Items marked **[OWNER]** need an explicit owner decision before building.

## 6.1 Regional
- Add kind `region` (prefix `RG`): `name`, `parent` (link to region), `definition` (how membership is decided: counties/jurisdiction list), `time_zone`, `status_note`.
- Region is part of the bundle key (D27). The question's `region` text field becomes a link to a region profile.
- Reuse na-research's identifier convention (`us-ny-western-new-york`, `ca-on-niagara-brant`) as a **public slug** field on the region profile, with the minted `RG-NNNN` as the stable ID. Existing region IDs there become aliases. Owner's memory of definitions (Western NY = Syracuse west to the Niagara River, south to the PA border, classified by county) belongs in the profile's `definition`.

## 6.2 Assembly (the library)
A directory `library/` in this repo, versioned in git, holding reference files only:
```
library/vocab/terms.json            governed vocabulary (tags, labels) with maps_to links
library/rules/expansion.json        tag → label inference rules
library/rules/required.json         labels required before a question is dispatchable
library/rules/pools.json            labels → pool set
library/rules/bundle.json           bundle key, split fields, size cap
library/rules/cadence.json          cadence → due predicate (provisional)
library/prompts/shaping/<id>/vN.md  shaping prompts (bundle → scan/file structure)
library/prompts/surround/<id>/vN.md surround-of-meaning prompts
library/templates/digest/<id>/vN.json   digest templates
library/join/<pool>/vN.json         join contracts (fields, naming, match keys, ID-minting rules)
library/formats/<pool>/vN.csv       standing result templates (header rows)
library/timers/…  library/notify/…  timer sets and notification preferences
```
Each file has a version and is referenced by (path, version). Pointers to external repos/routines live here as small `*.pointer.json` files, never copies. Every library file that Dispatch uses at emit time is recorded on the dispatch record with its version (frozen).
Vocabulary terms must map to something real (`maps_to` such as `field:question.lens=companies`, `id:S-0003`, `kind:pool`); `assembly lint` fails a term that maps to nothing. **[OWNER]** approves any new or retired term (D25).

## 6.3 Services: Internal / External, and arrangements
- `service` kind exists (`direction` internal/external).
- Add kind `party` (prefix `P`): a company, user or process that raises goals and questions (`party_kind`, `origin` internal/external, `status_note`). Goals link to a party instead of the `raised_by` enum.
- Add kind `arrangement` (prefix `A`): the relationship between the Assembly System and one external party. Fields: `party`, `class` (`research-service` | `gap-partner`), `visibility` rules (who may see which results), `lines` (business lines results flow into), `intake` (pointers to intake contract and mapping), `terms_note`. This is the object D33 says visibility depends on. **[OWNER]** confirm the name and the fields.
- External participation steps (agree how a party affirms, extends or adds goals, beyond API access) stay `manual` in the kind until an onboarding flow exists (6.9).

## 6.4 Goals
- Keep `goal`. Replace the manual "convert" step with `assembly new question --from-goal G-NNNN`, which copies party, service and lens hints into the question and sets the provenance chain link. Conversion remains a human-led act; the command only creates and links.

## 6.5 Questions (v2; first buildable slice is in Plan 1)
Add fields:
- `tags` (list): the submitter's minimal stamp.
- `window_kind` (`point` | `trailing` | `enclosing`), with `window_start`, `window_end` (date), `trailing_days` (int). Historic questions use an explicit `window_start`/`window_end`. (D31)
- `lifespan` (`standing` | `limited`) and `expires` (date). Distinct from the period the question is about. (D26, D31)
- `effort` (`skim` | `standard` | `deep`). Assembly states effort; machine-flows decides the tool. (D26, D9)
- `question_class` (`research-service` | `gap`). (D33)
- `origin` already exists (`internal` | `external`).
Remove as destinations (keep as optional hints): `bay`, `store` (D22, D23 pending).
New record block `treatment` (written only by the treat command, never by `set`):
`{"state": "stamped|treated", "labels": [{"name","value","source":"submitter|rule|answer","rule":"R-…"}], "gaps": [...]}`.
Statuses: keep the handoff-driven `status` field untouched in Plan 1 (it keeps working for questions created without tags). From Plan 2 the run lifecycle moves to dispatch records, and a question's own lifecycle becomes `active | paused | expired | retired | superseded` (a standing question is never "answered").
Safety: question text enters synthesized prompts, so **external** questions always require approval before a run (already enforced by handoff v0 via trust) and their text is flattened wherever it is rendered.

## 6.6 Lenses
Law, Land, Companies, Products, Processes, Programs stay an enum on the question. Role: each lens narrows which **pools** a question can feed (`pools.json` rules key on lens plus tags). The lens also selects the lens-specific section of a shaping prompt. A question that needs more than one lens is two questions linked by a goal (keeps the model simple). **[OWNER]** confirm this last rule.

## 6.7 Dispatch (the executable core)
Modules (all pure functions over records plus the library; no network):
| Module | Command (first form) | Does |
|---|---|---|
| `treat` | `assembly treat Q` / `assembly answer Q` | expand tags, find gaps, record provenance, make decision cards |
| `resolve` | `assembly resolve Q` | labels + rules → pools; refuse untreated questions |
| `bundle` | `assembly plan --on DATE` | group resolved questions into bundles; preview only |
| `surround` | (Plan 2) | build and freeze the anticipated context via an agent task handed to machine-flows |
| `emit` | `assembly dispatch emit BUNDLE` (Plan 2) | create the dispatch record, write handoff or filing request |
| `receive` | `assembly dispatch receive` (Plan 3) | register arrivals, read result manifests |
| `assess` | (Plan 3) | run assessment scanners over arrivals |
| `digest` | (Plan 3) | render digest from template; owner approves |
| `control` | `hold / retry / cancel / status` (Plan 2–3) | operate on dispatches |
| `tick` | `assembly tick --on DATE` (Plan 5) | idempotently create due dispatches; run by a machine-flows scheduled job |

**Dispatch record** (new kind `dispatch`, prefix `DP`, created through the front door): `bundle_key`, `period`, `questions` (IDs), `pools` (union), `frozen` (library file versions), `surround` (ref), `handoffs` (IDs of task documents), `state`, `assessment`, `digest` (ref), `history`.
**Dispatch states:** `resolved → surrounded → emitted → running → received → assessed → in-review → approved | rework | rejected → handed-on`. Dispatch stops at `handed-on` (D3 and the diagram: Join is the next stage).
**Idempotency key:** `(bundle_key, period, extra_n)`. An extra run (D28) increments `extra_n`.
**Bundle key:** `(region, cadence, intake, origin, sensitivity, trust, effort_class)`. Size cap default 12 questions per bundle (library-configurable). Different keys never share a bundle. Reason for each field: region/cadence per D27; intake because scan and file are different work; origin/trust because external question text is untrusted prompt input and external runs need approval; sensitivity because outputs must not be exposed to inappropriate pools, people or tools; effort because deep and skim runs should not be forced to one depth.
**Surround** (Plan 2): a frozen artifact `surround.json` produced by a low-effort agent task: expected entity kinds, expected fields and likely mappings, volume range, known pools and recent history, risks. Stored apart from observed results, with its prompt version, so the digest can show deviations without being nudged toward the prediction.

## 6.8 Scan (Automation)
- Assembly side: the **shaping prompt** (library) turns a bundle plus its surround plus the pool's result format into a scan prompt document (window, region, sources hints, questions with a local ref each, output contract). It never names a tool.
- **Result contract** every scan task must satisfy (a new requirement on handoff v1, NA-353): write a `result-manifest.json` beside its output: `{dispatch, bundle_key, window, files[{path, sha256, rows}], counts{by kind}, started, finished, status, notes, cost?}`. Dispatch's `receive` and the assessment scanners read only this manifest, never the free-form output.
- Scan **recipes** are pointers to existing routines (for example na-research's scan prompt and `na` CLI). Assembly never reimplements them; it wraps them.
- Output lands in the bay's staging area (6.13), never directly in a store.

## 6.9 File (Manual, APIs) and the Stores→API→File loop
- Filing request: a decision card or task asking a person or an API client to supply data in a named **standing result template** (`library/formats/<pool>`), with the window and bundle reference.
- **Intake location** is a pointer on the arrangement or pool (data does not live in this repo). Arrivals are registered by manifest (file, hash, row count, submitter, bundle). An **intake service** that receives API pushes is a separate code base (a `unit`) that only writes arrival manifests; Dispatch never touches its internals.
- **Gap-partner onboarding flow:** profile the party (`party`), agree the `arrangement`, party distills its service into one or more question bundles through the front door, party connects its API, first submissions produce a **mapping digest** (their fields and values proposed against ours: aliases, `NEW` where no match). The owner approves the digest (D34). Approved mappings become alias records in the registry (data, outside this repo) and a version of the party's intake contract.
- **Loop:** an internal store exporting through an API becomes a File arrival with origin `internal`, with provenance `derived_from` the source store/dispatch. Same path, same review points.

## 6.10 Join (Registries)
- A **join contract** per pool (library): target fields and types, naming conventions, match keys, evidence rules, when an entity counts as new, how aliases are recorded, which fields are never overwritten.
- Join is **deterministic code wherever possible**; an agent may propose fuzzy matches but proposals are advisory. Never merge on name alone when a collision is plausible. Keep duplicates as separate candidates linked by `duplicate_of`; do not silently merge. (Both are existing practice in na-research and are worth keeping.)
- **Output of a join run is a change-set** (proposed writes: new records, alias links, updates, each with provenance stamp), staged in the bay. It is never written straight to a store.
- **Entity IDs** (companies, products, programs and so on) are minted by the Assembly System too (D4). That needs a bulk, offline-safe mint: `assembly mint --namespace E --count N` reserving a block recorded in `registry/`. See open decision O3.
- Totals (counts by pool, by origin party, by period) are computed from the stamped records, never maintained by hand.

## 6.11 Digests
- **Digest template** (library, versioned) declares: which labels it applies to; the automated checks (counts, duplicates, missing fields, format conformance); who reviews (`auto` | `owner`); the message class (notice, decision card, review pack); and its outcomes (`accept`, `rework`, `reject`) with `accept` naming the next step.
- **Two digest points** (D21, D34): digest 1 after arrival (findings, assessment, proposed mapping); review 2 after Join (the change-set). Same mechanism, different template.
- **Assessment scanners** (D29): small deterministic programs in the library. First one: quantity, comparing counts in `result-manifest.json` with the surround's expectations. Quality scorers come after the shaping prompts exist. Results are attached to the bundle, not to questions.
- Rework creates a **new dispatch revision** linked to the original (extra run key), not an edit of the old one. NA-361 holds the remaining digest questions.

## 6.12 Stores
- A store is a `dataset` profile (pointer). The data lives elsewhere (CSV in a data repo, a database, files).
- Only approved change-sets write to a store, and every written record carries its provenance stamp. Reads for Lines go through a store's API.
- Reviews at this stage: merge review (6.13). A store's main branch is only changed by the bay merge.

## 6.13 Bays
- A bay is a **branch of a store**: the diagram places Bays after Stores because bays accumulate time-boxed results before merging into the main store (D6). The existing na-research weekly branch (`news/<YYYY>-Www`) is exactly this pattern.
- Lifecycle (NA-357): `planned → open → accumulating → closed → reviewing → merged → archived`. A timer opens the next bay (for example weekly per region) through the front door. A bay carries its **surface**: the regions, pools and dispatch classes allowed to write into it (D23). Any write outside the surface is refused at join time.
- Bay review (checks plus the owner) precedes merge; the merge is the last human gate before main (or the PR merge in a git-backed store).
- Period convention: reuse na-research's news week (Sunday start, named by the ISO week of the following Monday, America/Toronto) so existing branches match.

## 6.14 Move (Timers; Checks)
- **Timers** = the schedule that creates work and advances states: dispatch ticks, bay open/close, merge windows, publication. They live in `library/timers`. Assembly decides *what is due* (pure function of date and records); **machine-flows runs the scheduler** (its scheduled-jobs register is the right home). `assembly tick --on DATE` is idempotent.
- **Checks** = named acceptance checks. Each is an exact procedure (deterministic) or a scanner; gates call checks by name. Check results are events.
- **Move** therefore is not a stage with data of its own; it is the engine that fires transitions between stages when timers say so and checks pass.

## 6.15 Notifications
- Every state change that needs a person emits an event; the library's notification preferences map event kind to message class, channel and recipient. Message files are written to an outbox; **machine-flows delivers** (email, phone push) and returns delivery/reply events (NA-358). In-app button replies come back as events that call `assembly answer` / `confirm` / digest outcomes.
- Short choices = decision cards; findings summaries = notices; big reviews = review packs (possibly a localhost review site, which is machine-flows' backlog item, not Linear).

## 6.16 Line
- A Line is a business line: a `unit` (product or service) whose **promises** are `view, read, make, save, acts`. Proposed meaning: **View** = presents data; **Read** = retrieval through an API; **Make** = creates new items from data; **Save** = persists a user's creation; **Acts** = performs actions on the user's behalf. **[OWNER]** confirm these meanings.
- A Line draws from pools through stores. `assembly line check LINE` reports whether each promised capability is backed by a live pool/store and whether the arrangement rules allow the visibility it exposes. Code for Lines lives in its own repos; Assembly holds the profile only.

## 6.17 Red events (best-effort reading)
| Event | Reading | Where it lands |
|---|---|---|
| Identities | An ID minted or a profile created | creation event in the front door (exists) |
| Demand | A goal or question raised by a party | `party → goal` creation event |
| Convert | A goal converted into questions; also a mapping converting their fields to ours | `--from-goal`; mapping digest |
| Compose | A bundle composed; also a Line composing outputs from pools | bundle/surround events; line check |
| Digests, Reviews, Checks, Notifications | exactly as named | 6.11–6.15 |
Confirm against the diagram.

## 6.18 Where operational state lives **[OWNER]**
Profiles change slowly and belong in git. Dispatch records, digests, change-sets and events are high-volume. Options: (A) everything in this repo, committed; (B) week-partitioned append-only files under `ops/<week>/`, committed in bulk by one serialized runner (the pattern na-research uses for its ledger and ops log); (C) a separate state folder outside git, synced. **Recommendation: B.** Never let many writers commit individually.

## 6.19 machine-flows contract (handoff v1, NA-353; needs agreement with the owner and NA-330)
First-class keys instead of tags: external task ID (`as:<ID>`), dispatch ID, bundle key, work class (never a tool), effort, window, sensitivity, trust, acceptance check, expected result manifest path. Result schema: manifest above plus cost and "why this tool". Event feed instead of polling (NA-358). v2 (NA-354): deterministic runner for exact tasks.

## 6.20 Security and resilience
- External text is data: never executed, flattened wherever rendered, trust fail-closed, approval before run.
- Sensitivity separates bundles and gates which tools and environments machine-flows may use.
- No secrets in any record. Provenance and entitlement checked at Line exposure.
- Resilience: idempotent keys; crash-safe progress files (`creations/` pattern extended to dispatches); every stage resumable; a failed run re-splits a bundle instead of re-running everything; the stage contract (6.7) lets any component be replaced.
- Observability: `assembly status` summarizes dispatches by state, overdue items, and what waits on the owner.

---

# PART 7. Relationship to na-research (current joining, not binding)

What exists today in `na-research` (read 2026-10-27; owner said it informs but does not bind):
- **Regions and desks:** `intel/regions.csv`, `research/ops/region_profiles.csv`, region IDs like `us-ny-western-new-york`; desks, zones; news weeks Sunday–Saturday in America/Toronto.
- **Scan:** `research/news/prompts/scan.md` rendered by `scan_prompt.py` with placeholders (region, sectors, window start = previous scan end, sources checklist, open follow-ups, finish steps by tool capability). Tools (Codex, Grok) write one **findings packet** per run to `research/news/packets/<week>/<region>/<UTC>-<tool>.json` (schema `packet.schema.json`); `na packet check` validates.
- **Ingest (≈ Receive):** `na ingest`: serialized, idempotent, quarantines bad packets, dedupes by canonical URL, proposes `duplicate_of` but never merges, allocates IDs in one serialized runner, runs entity matching and validation.
- **Entity matching (≈ Join proposal):** versioned score formula (name, alias, domain, location, parent, activity, corroboration); scores are advisory; collisions require review; new `E####` IDs only during reviewed integration.
- **Review (≈ digest/reviews):** daily digest per desk with default-keep triage ticks in a weekly Linear issue; workbook and a localhost Review Desk with decision codes A/E/R/D/F/H/X/N; decisions in `review_decisions.csv`.
- **Join/Stores:** Saturday resolution `plan_integration` / `apply_integration` promotes approved records to `intel/*.csv` (canonical), with a ledger; the weekly PR merge is the last gate.
- **Bay:** the rolling weekly branch `news/<YYYY>-Www` with one draft PR.
- **Move/Notifications:** `automations.csv` schedules, GitHub Actions cron, ops log with severities, email digests, Slack.
- **Line:** HeavyMap export, WNY site export, newsletters, register pages.

Mapping and gaps:
| Assembly concept | Closest today | Gap the Assembly System adds |
|---|---|---|
| Question | follow-up task row (`F`/`X`) | first-class questions, standing vs limited, time windows, tags, provenance |
| Bundle | region × tool scan | grouping by metadata, effort, trust/sensitivity |
| Shaping prompt | `scan.md` template | library-governed, versioned, frozen per dispatch |
| Result manifest | packet JSON | cross-pool, tool-neutral manifest |
| Digest/assessment | daily digest + calibration | per-bundle success criteria, mapping digest |
| ID minting | serialized runner inside na-research | central minting for all IDs (D4) |
| Provenance | `found_by` (tool, run) | origin party chain |
| External actors/API intake | none | arrangements, intake contracts, harmonization |

**Recommendation:** treat Regional Desks as the **reference implementation of one pool and one line** (companies/events → WNY and Niagara-Brant desks). Wrap it. Do not rewrite it. Migrate ID minting last and behind an alias table. Note why central minting matters: `pull_and_review.sh --batch` plus `renumber_scan_ids.py` exist only because parallel branches collide on distributed ID allocation.

---

# PART 8. Open decisions for the owner (with recommendation)

| # | Decision | Recommendation |
|---|---|---|
| O1 | Names: treatment, bundle, surround, arrangement, party, pool | Keep unless rejected |
| O2 | Add kinds `region` (RG), `party` (P), `arrangement` (A), `pool` (PL), `dispatch` (DP), `template` (T) | Yes, in that order of need; Plan 1 adds only `pool` |
| O3 | Entity ID minting: Assembly mints blocks; na-research keeps `E####` and `IEVT-` until a migration with an alias table | Yes |
| O4 | Where operational state lives (6.18) | B |
| O5 | One question, one lens (6.6) | Yes |
| O6 | Meaning of Line promises (6.16) | Confirm |
| O7 | Bundle size cap and effort splits (defaults: 12 questions; effort is skim, standard or deep) | Start with the defaults; tune with data |
| O8 | Cadence due-rules: daily every day; weekly Sunday; monthly the 1st; once = unscheduled. Provisional until the timer design | Accept as provisional |
| O9 | Who may approve digest outcomes besides the owner | Owner only, for now |
| O10 | Whether `bay` and `store` stay as optional hints on the question | Keep as hints, ignored by resolve in Plan 1 |
| O11 | Future-dated questions: where do projections live | Out of scope here; owner to place in the diagram |

---

# PART 9. Implementation Plan 1: Treat, Resolve, Plan (preview-only Dispatch)

Scope check: this plan delivers one working, testable slice and writes **no** handoffs, digests, joins, bays or timers. Later plans (Part 10) depend on it. It touches only `kinds/`, a new `library/`, and new modules; existing behavior must stay intact.

## Global Constraints
- Python 3.9+, standard library only (`zoneinfo` is in 3.9).
- Existing 93 tests must still pass; questions created **without** `tags` follow the old path unchanged.
- No ID is ever invented; new profiles only through `assembly new`.
- Rendered text from any record is flattened to one line (use the `_flat` approach in `assembly/handoff.py`).
- Treat/answer/resolve/plan are **preview by default**; only `--apply` writes (treat, answer). `resolve` and `plan` never write.
- Do not commit or push. Do not edit `profiles/` by hand; the test suite builds temporary roots.
- First read: `assembly/kinds.py`, `assembly/records.py`, `assembly/create.py`, `assembly/cli.py`, `assembly/handoff.py`, `tests/test_cli.py` (patterns for temporary roots).

## Review Focus (deliberately tested)
1. A tag that is not in the vocabulary (typo) becomes a **gap**, never silently dropped.
2. Two rules giving different values to one label produce a **conflict gap**, not a silent winner.
3. External question text containing newlines, `---` or markdown headings never reaches a decision card or plan line unflattened.
4. Expired, retired, superseded and paused questions never appear in a plan.
5. Running `treat --apply` twice leaves identical state and adds no duplicate history events; `answer` can only fill a gap, never override a labelled value.
6. Week arithmetic matches na-research (Sunday starts the news week).
7. Trust, sensitivity and approval are never set by a rule; a rule may only *propose* them.

## File structure
```
kinds/question.json            modify: v2 fields
kinds/pool.json                create: PL
library/vocab/terms.json       create (seed)
library/rules/expansion.json   create (seed)
library/rules/required.json    create (seed)
library/rules/pools.json       create (seed)
library/rules/bundle.json      create (seed)
library/rules/cadence.json     create (seed)
assembly/library.py            create: load + lint library files
assembly/period.py             create: week arithmetic and windows
assembly/treat.py              create: Treatment engine
assembly/resolve.py            create: Route
assembly/bundle.py             create: Bundle, plan
assembly/cli.py                modify: treat, answer, resolve, plan, lint hook
tests/test_question_v2.py, test_library.py, test_period.py, test_treat.py, test_resolve.py, test_bundle.py, test_cli_dispatch_preview.py
docs/design.md, README.md      modify at the end
```

### Task 1: Question kind v2 and the pool kind
**Files:** Modify `kinds/question.json`; Create `kinds/pool.json`; Test `tests/test_question_v2.py`.
**Interfaces:** Produces new question fields `tags`(list), `window_kind`(enum point|trailing|enclosing), `window_start`(date), `window_end`(date), `trailing_days`(int), `lifespan`(enum standing|limited), `expires`(date), `effort`(enum skim|standard|deep), `question_class`(enum research-service|gap). Kind `pool` prefix `PL`: `name`(text, required), `lens`(list of lens values), `registry`(text pointer), `store`(link→dataset), `description`(text), `status_note`(text). `bay` and `store` stay optional on question and are described as hints.
- [ ] **Step 1: Write failing tests** `test_question_v2.py`: (a) `load_kinds` exposes the nine new fields with the stated types and enum values; (b) `new_record`-level validation accepts a question with `tags=["news","wny"]`, `window_kind="trailing"`, `trailing_days=7`; (c) rejects `effort="huge"`; (d) the `pool` kind mints `PL-0001` via the existing creation path; (e) `lifespan="limited"` without `expires` is **allowed** at creation (treatment reports it as a gap, not creation).
- [ ] **Step 2:** `python3 -m unittest tests.test_question_v2 -v`. Expected: FAIL (fields missing).
- [ ] **Step 3: Edit the JSON kinds.** Keep every existing field and step. Change the descriptions of `bay` and `store` to say they are hints.
- [ ] **Step 4:** run the new tests, then the whole suite. Expected: all pass (93 + new).
- [ ] **Step 5: Do not commit** (owner commits). Record in the ledger.

### Task 2: Library loader and vocabulary lint
**Files:** Create `assembly/library.py`, seed `library/vocab/terms.json`, `library/rules/*.json`; Test `tests/test_library.py`.
**Interfaces:** `load_json_dir(root: Path, rel: str) -> dict`; `load_vocab(root: Path) -> Vocab` where `Vocab.terms: Dict[str, Term]`; `Term(term, kind, maps_to, status, alias_of, since)`; `lint_library(root: Path, kinds: Dict[str, Kind]) -> List[str]` returns error strings.
- [ ] **Step 1: Failing tests:** `test_term_without_maps_to_fails_lint`; `test_maps_to_unknown_field_fails_lint` (e.g. `field:question.nope=x`); `test_maps_to_known_enum_value_passes` (`field:question.lens=companies`); `test_deprecated_term_requires_alias_to_an_active_term`; `test_duplicate_term_fails`; `test_alias_resolves_to_active_term` (`Vocab.resolve("wny") == "us-ny-western-new-york"` using a seeded alias).
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3: Implement** the three functions. `maps_to` grammar: `field:<kind>.<field>=<value>` (field must exist; for enums the value must be in `values`), `id:<ID>` (profile must exist), `kind:<kind>` (kind must exist), `lib:<relative path>` (file must exist). Seed vocabulary with only terms backed by existing enums: the six lenses, `historic`, `current`, `scan`, `file`, `daily`, `weekly`, `monthly`, `internal`, `external`, plus tag `news`.
- [ ] **Step 4:** run tests. Expected: PASS. Hook `lint_library` into `assembly lint` (a failing library is a failing lint).
- [ ] **Step 5:** ledger line.

### Task 3: Period arithmetic
**Files:** Create `assembly/period.py`; Test `tests/test_period.py`.
**Interfaces:** `week_id(day: date) -> str` (news week: ISO week of `day + 1 day`, e.g. `2026-W42`); `week_bounds(week: str) -> Tuple[date, date]` (Sunday, Saturday); `resolve_window(window_kind: str, on: date, start: Optional[date], end: Optional[date], trailing_days: Optional[int]) -> Tuple[date, date]`.
- [ ] **Step 1: Failing tests:** `week_id(date(2026,10,11)) == "2026-W42"`; `week_id(date(2026,10,17)) == "2026-W42"`; `week_id(date(2026,10,18)) == "2026-W43"`; `week_id(date(2026,10,27)) == "2026-W44"`; `week_bounds("2026-W42") == (date(2026,10,11), date(2026,10,17))`; `resolve_window("point", on)` returns `(on, on)`; `resolve_window("trailing", on, trailing_days=7)` returns `(on-6 days, on)`; `resolve_window("enclosing", on, start, end)` raises `ValueError` when `on` is outside `[start, end]` and returns `(start, end)` otherwise; `resolve_window("trailing", on)` without `trailing_days` raises.
- [ ] **Step 2:** run. Expected: FAIL (module missing).
- [ ] **Step 3: Implement.** Semantics copy `na-research/research/news/weeks.py` (read it for the exact rule); no time-zone handling in this task (dates only).
- [ ] **Step 4:** run. Expected: PASS.
- [ ] **Step 5:** ledger line.

### Task 4: Treatment engine (pure)
**Files:** Create `assembly/treat.py`; seed `library/rules/expansion.json`, `required.json`; Test `tests/test_treat.py`.
**Interfaces:**
```
@dataclass Label: name, value, source ("submitter"|"rule"|"answer"), rule (Optional[str])
@dataclass Gap: name, reason ("missing"|"conflict"|"unknown-tag"|"proposal"), options (List[str]), detail (str)
@dataclass Treatment: labels: List[Label]; gaps: List[Gap]; state ("stamped"|"treated")
treat(rec: dict, kinds, vocab: Vocab, expansion: dict, required: dict) -> Treatment
apply_answer(treatment: Treatment, name: str, value: str, kinds) -> Treatment
PROPOSE_ONLY = ("trust", "sensitivity", "approval")
```
Rule file shape: `{"rules":[{"id":"R-news","when":{"tags_all":["news"],"fields":{}},"then":{"intake":"scan","lens":"companies"},"propose":{"sensitivity":"public"}}]}`. `required.json`: `{"all":["lens","region","horizon","intake","trust","sensitivity","effort"],"standing":["cadence"],"limited":["expires"],"by_lens":{}}`.
- [ ] **Step 1: Failing tests:** `test_expands_tags_into_labels_with_rule_provenance`; `test_submitter_fields_become_labels_with_source_submitter`; `test_unknown_tag_is_a_gap_unknown_tag` (Review Focus 1); `test_conflicting_rules_produce_conflict_gap` (2); `test_rule_cannot_set_trust_it_becomes_a_proposal_gap` (7); `test_missing_required_label_is_a_gap_with_enum_options`; `test_standing_question_requires_cadence_limited_requires_expires`; `test_no_gaps_means_state_treated`; `test_treat_is_idempotent` (same input, equal output); `test_apply_answer_fills_a_gap_with_source_answer`; `test_apply_answer_refuses_to_override_an_existing_label` (5); `test_answer_value_must_be_valid_for_enum`.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3: Implement** `treat` as a deterministic fold in rule-file order; conflicts detected when two rules (not the submitter) disagree; submitter-stamped values beat rules only when equal, otherwise conflict gap. Options for a gap come from the field's enum `values`.
- [ ] **Step 4:** run; then full suite. Expected: PASS.
- [ ] **Step 5:** ledger line.

### Task 5: `treat` and `answer` commands with persistence and decision cards
**Files:** Modify `assembly/cli.py`; modify `assembly/records.py` only if needed to save `treatment`; Create `outbox/cards` writer inside `assembly/treat.py`; Test `tests/test_cli_dispatch_preview.py`.
**Interfaces:** `assembly treat Q [--apply] [--outbox DIR]`; `assembly answer Q --set name=value [--apply]`. `treatment` is stored at `rec["treatment"] = {"state", "labels":[...], "gaps":[...]}`; each applied change appends one history event via `add_event(rec, "treat"|"answer", detail)`. A **decision card** is a Markdown file `outbox/cards/<Q-ID>-<n>.md` with one numbered question per gap, choices as options, text flattened (Review Focus 3).
- [ ] **Step 1: Failing tests:** preview prints labels and gaps and writes nothing; `--apply` writes `treatment` and one history event; running `--apply` twice adds no second event (5); `answer` for a gap fills it and moves state to `treated` when no gaps remain; `answer` for an already-set label exits non-zero with a message pointing to `assembly set`; a question whose `text` contains `"\n---\n# Heading"` produces a card where the text is one line (3); a record of a retired question is refused.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3: Implement** the two commands reusing the existing preview/apply plumbing in `cli.py`.
- [ ] **Step 4:** run tests and the whole suite. Expected: PASS.
- [ ] **Step 5:** ledger line.

### Task 6: Resolve
**Files:** Create `assembly/resolve.py`, seed `library/rules/pools.json`; add `assembly resolve Q`; Test `tests/test_resolve.py`.
**Interfaces:** `@dataclass Route: question, pools: List[str], intake, region, cadence, origin, sensitivity, trust, effort, window: Tuple[date,date], notes: List[str]`; `resolve(rec, kinds, pools_rules, on: date) -> Route`; raises `Unresolvable(errors: List[str])`. `pools.json`: `{"rules":[{"id":"P1","when":{"lens":"companies","tags_any":["news"]},"pools":["PL-0001"]}]}` (pool IDs must exist as profiles; lint checks).
- [ ] **Step 1: Failing tests:** an untreated question raises `Unresolvable`; a treated question returns the union of pools from all matching rules (D30); no matching rule yields `Unresolvable` with the text "no pool"; a pool ID that does not exist makes `lint_library` fail; the window is resolved via `period.resolve_window`; `bay`/`store` fields are ignored (O10); retired, superseded and expired questions raise `Unresolvable` (4).
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3: Implement.** `assembly resolve Q [--on YYYY-MM-DD]` prints a flattened summary and never writes.
- [ ] **Step 4:** run. Expected: PASS.
- [ ] **Step 5:** ledger line.

### Task 7: Bundle and plan
**Files:** Create `assembly/bundle.py`, seed `library/rules/bundle.json`, `cadence.json`; add `assembly plan --on DATE`; Test `tests/test_bundle.py`.
**Interfaces:** `@dataclass Bundle: key: Tuple, period: str, questions: List[str], pools: List[str], window: Tuple[date,date]`; `bundle_key(route) -> Tuple[str,...]` = `(region, cadence, intake, origin, sensitivity, trust, effort)`; `group(routes: List[Route], cap: int) -> List[Bundle]`; `due(cadence: str, on: date, rules: dict) -> bool`; `plan(root, kinds, on: date) -> List[Bundle]`.
- [ ] **Step 1: Failing tests:** same key groups together regardless of question order (deterministic output ordering); different `origin` or `sensitivity` or `trust` or `effort` never share a bundle; sources are not part of the key (two questions differing only in `path` or tags share a bundle); a single question forms a valid bundle (D27); over-cap groups split into numbered bundles deterministically; `due("daily", any day)` true, `due("weekly", Sunday)` true and Monday false, `due("monthly", 1st)` true, `due("once", …)` follows the rule file; paused/expired/retired never planned (4); a standing question appears every due day; a `limited` question appears until `expires` then drops out; period equals `week_id(on)`.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3: Implement.** `plan` calls `resolve` for each active treated question; unresolvable ones are listed in a separate "needs attention" section with reasons, never dropped silently.
- [ ] **Step 4:** run. Expected: PASS.
- [ ] **Step 5:** ledger line.

### Task 8: End-to-end check, docs, Linear
**Files:** Modify `README.md`, `docs/design.md`, `AGENTS.md` (add "library files are reference only; never put data in `library/`"); Test `tests/test_cli_dispatch_preview.py` (add one end-to-end test).
- [ ] **Step 1: Failing end-to-end test:** in a temporary root, create a pool, then a question with only `text`, `trust`, `tags=["news"]`, `region`, `cadence="daily"`, `lifespan="standing"`; run treat (gaps appear), answer the gaps, treat again (state `treated`), resolve (pool found), plan for a date (one bundle containing that question, period from `week_id`).
- [ ] **Step 2:** run. Expected: FAIL until all earlier tasks are in; then PASS.
- [ ] **Step 3: Docs.** README gets the four commands and a "not yet" list that now says: surround, emit, receive, assess, digest, join, bays, timers. `docs/design.md` points to this file's Part 4 as the decision register.
- [ ] **Step 4: Full suite and lint:** `python3 -m unittest discover -s tests` and `bin/assembly lint`. Expected: all pass; lint clean.
- [ ] **Step 5: Linear.** Create issues in project "Assembly System" for Plans 2–8 (Part 10), link NA-361, NA-353, NA-354, NA-357, NA-358. Update NA-361 with the open Digests questions from 6.11. Do not commit; leave the working tree for the owner.

### Self-review (done at writing time)
Spec coverage: D22, D24–D27, D30, D31 map to Tasks 1–7; D25 to Task 2; D28/D29/D32–D35 are intentionally deferred (Plans 2–7). Type names are consistent across tasks (`Treatment`, `Route`, `Bundle`, `Vocab`). Proportion: tasks give signatures and test names, not bodies.

---

# PART 10. Roadmap after Plan 1 (each needs its own plan and the owner's go-ahead)

| Plan | Delivers | Depends on | Linear |
|---|---|---|---|
| 2 | Dispatch record (`dispatch` kind), shaping prompts, surround, emit; handoff v1 contract with machine-flows; question lifecycle (`active/paused/expired`) | Plan 1; NA-353; NA-330; O2, O4 | NA-353 + new |
| 3 | Receive, result manifest, assessment scanners (quantity), digest templates, digest approval, rework | Plan 2; NA-361 closed | NA-361 + new |
| 4 | Join contracts, deterministic join runner producing change-sets, bulk ID minting, mapping digest, join review | Plan 3; O3 | new |
| 5 | Bays lifecycle, stores write path, Move: timers and checks, `tick` run by machine-flows | Plan 4 | NA-357 + new |
| 6 | Notifications and event feed, message classes, in-app replies | Plan 2; machine-flows NA-336/339 | NA-358 |
| 7 | `party` and `arrangement` kinds, gap-partner onboarding, file intake contract, API intake unit, visibility rules, provenance chain enforcement | Plan 3–4 | new |
| 8 | Line profiles, promises check, visibility at the Line, reference migration of Regional Desks to the new flow | Plan 5–7 | new |

Total shape: Plan 1 is small and local. Plans 2–4 are the core. Plans 5–8 are broad and should be re-scoped with the owner after Plan 3, when real digests exist.

---

# PART 11. Instructions for the receiving agent

1. Read Parts 1–5 in full, then Part 4 again. Treat Part 4 as binding and everything else as proposal.
2. Ask the owner to re-attach the architecture graphic before relying on Part 3.
3. Do not build anything beyond Plan 1 without an explicit go-ahead. Do not rename anything in Part 4.3 without asking.
4. Resolve the open decisions in Part 8 with the owner one at a time (one question per message, plain language, no jargon); record answers in the Linear document, not only in chat.
5. When you finish a task, run the whole suite, read the output, and report failures by name.
6. If you find that a decision here conflicts with the code, say so and stop; do not guess.

Appendix: useful commands
```
python3 -m unittest discover -s tests                 # all tests
bin/assembly lint                                      # profile and library lint
bin/assembly list question | show Q-0001
bin/assembly new question --set text="…" --set trust=owner … # preview; add --apply to write
```
