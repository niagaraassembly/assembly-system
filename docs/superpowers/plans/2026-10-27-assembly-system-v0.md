# Assembly System v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The Assembly System's first working slice: one central creation action that mints IDs and records profiles for anything new (including questions and goals), plus a versioned handoff to machine-flows and a read-only handback from its run records.

**Architecture:** A standalone Python package (`assembly/`) with data-driven kinds (`kinds/<kind>.json`), JSON profiles under `profiles/<kind>/`, a creation record per new thing (`creations/<ID>.json`) that tracks each step so a half-finished creation is visible and resumable, a handoff emitter that writes machine-flows prompt documents (deterministic body, no interpretation needed), and a handback reader that looks at machine-flows run records. It never imports or calls `mach`; files only.

**Tech Stack:** Python 3.9+ standard library only (the Mac runs 3.9; no `tomllib`, no PyYAML), `unittest`, JSON.

**Spec:** Linear document "Assembly System: architecture reading and decisions so far (2026-10-27)" in project Assembly System; machine-flows `plans/22-cross-machine-tasking.md` (tasking contract, NA-330) and `plans/08-mach-cli.md` section 3.6 (prompt-document keys).

## Global Constraints

- Assembly System mints every ID; other systems only refer to them. IDs never reused. Format `<PREFIX>-<NNNN>` (`Q-0001`).
- Data and code of the things it profiles do **not** live in this repo; profiles hold pointers only.
- Preview first, `--apply` to write. Exit codes: 0 ok, 1 warnings, 2 failure.
- Handoff files use the machine-flows v0 key set only (unknown keys are rejected by `mach run`): required `mach,type,title,goal,tool,output`; optional `permission,path,machine,due,approval,tags,model`. Task-to-record link and handoff version travel in `tags` (`as:<ID>`, `as-v0`).
- No secrets in any record or task document. Nothing writes outside this repo except the outbox path the owner names.
- Handback is read-only on machine-flows.
- Trust rule: instructions not from the owner (`trust` = derived or external) never run write work without an approval gate (`approval: before-run`).

## Review Focus

- Question text containing newlines, `---`, quotes or non-ASCII must not break a task document's frontmatter (single-line title/goal, body carries the full text).
- Two creations at the same moment must get different IDs.
- A crash between creation steps must resume without re-minting the ID or duplicating handoff files.
- Missing required fields, bad enum values and unknown fields must produce errors naming the field, with nothing written.
- A missing or unreadable run record or runs folder must not crash handback (the failure `mach queue` has).

---

### Task 1: Kind registry

**Files:** Create `assembly/__init__.py`, `assembly/kinds.py`, `kinds/{question,goal,service,unit,repo,dataset,bay}.json`; Test `tests/test_kinds.py`

**Interfaces:**
- Produces: `Field(name,type,required,values,target,description)`, `Kind(name,prefix,description,fields,steps)`, `load_kinds(kinds_dir: Path) -> Dict[str, Kind]`, `validate_fields(kind: Kind, values: Dict[str, Any]) -> List[str]` (error strings naming the field), `FIELD_TYPES = ("text","enum","link","list","date","int","bool")`.
- Kind file shape: `{"kind","prefix","description","fields":[{"name","type","required","values","target","description"}],"steps":[{"id","do":"handoff|manual","template","text","when":{field:value}}]}`; `write-profile` is implicit and always first.

- [ ] **Step 1:** Tests: `test_all_seven_kinds_load` (names question, goal, service, unit, repo, dataset, bay; unique prefixes Q,G,S,U,R,D,B); `test_question_fields_inferred_from_design` (has `text, goal, service, lens, region, horizon, raised_by, origin, trust, sensitivity, intake, cadence, bay, store, reviews, checks, due, procedure, execution`... see kind file); `test_missing_required_names_field`; `test_bad_enum_names_field_and_allowed_values`; `test_unknown_field_rejected`; `test_link_field_must_look_like_id_of_target_prefix` (e.g. `goal: "G-0001"` ok, `"Q-0001"` not).
- [ ] **Step 2:** Run `python3 -m unittest tests.test_kinds -v`; expect FAIL (module missing).
- [ ] **Step 3:** Implement `kinds.py` and the seven kind files. Question lens enum is `law,land,companies,products,processes,programs`; horizon `historic,current,both`; intake `scan,file`; cadence `once,daily,weekly,monthly`; trust `owner,derived,external`; sensitivity `private,generic,public`.
- [ ] **Step 4:** Run tests; expect PASS.

### Task 2: ID minting and profile store

**Files:** Create `assembly/ids.py`, `assembly/records.py`; Test `tests/test_ids_records.py`

**Interfaces:**
- Consumes: `Kind` from Task 1.
- Produces: `mint(root: Path, prefix: str) -> str`; `parse_id(s: str) -> Tuple[str, int]` (raises `ValueError`); `new_record(kind: Kind, id: str, fields: Dict[str, Any]) -> Dict`; `save(root: Path, rec: Dict) -> Path` (atomic, sorted keys); `load(root: Path, id: str, kinds: Dict[str, Kind]) -> Dict`; `list_ids(root: Path, kind_name: str) -> List[str]`; `add_event(rec: Dict, event: str, detail: str = "") -> None`.
- Record: `{"schema":1,"id","kind","fields","status":"new","created","history":[{"at","event","detail"}]}`.

- [ ] **Step 1:** Tests: `test_mint_sequential_and_padded` (Q-0001, Q-0002); `test_mint_never_reuses_after_record_deleted`; `test_mint_unique_under_threads` (20 threads, 20 distinct IDs); `test_parse_id_rejects_garbage`; `test_save_load_roundtrip`; `test_save_is_atomic_no_tmp_left`.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement: counters in `registry/counters.json`, lock via `os.open(O_CREAT|O_EXCL)` on `registry/.lock` with retry; mint takes `max(counter, highest existing profile)+1`. **Step 4:** Run; expect PASS.

### Task 3: Creation action

**Files:** Create `assembly/create.py`; Test `tests/test_create.py`

**Interfaces:**
- Consumes: Tasks 1, 2; `assembly.handoff.emit_for_step` (Task 5; stubbed by a fake in tests).
- Produces: `plan_create(root, kinds, kind_name, values) -> Dict` (`{"kind","errors","steps","fields"}`, no writes, no mint); `apply_create(root, kinds, kind_name, values, outbox: Path) -> Dict` (returns the creation record); `resume_create(root, kinds, id: str, outbox: Path) -> Dict`. Creation record `creations/<ID>.json`: `{"id","kind","state","steps":[{"id","do","status","detail"}]}`, state in `complete|manual-pending|partial`.

- [ ] **Step 1:** Tests: `test_plan_writes_nothing`; `test_apply_mints_writes_profile_and_records_steps`; `test_invalid_values_write_nothing_and_no_id_burned`; `test_resume_after_failed_handoff_does_not_remint` (monkeypatch emit to fail once); `test_manual_steps_leave_state_manual_pending`; `test_apply_twice_same_draft_makes_two_things` (creation is not idempotent by content; resume is by ID).
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. After every step rewrite the creation record, so a crash leaves the true state. **Step 4:** Run; expect PASS.

### Task 4: CLI

**Files:** Create `assembly/cli.py`, `bin/assembly`; Test `tests/test_cli.py`

**Interfaces:**
- Produces: `main(argv: Optional[List[str]] = None, root: Optional[Path] = None) -> int`. Commands: `kinds [KIND]`, `new KIND [--set k=v]... [--from FILE.json] [--outbox DIR] [--apply]`, `show ID`, `list [KIND]`, `lint`, `dispatch ID [--outbox DIR] [--apply]`, `handback [--runs DIR] [--apply]`, `confirm ID`. Root from `ASSEMBLY_ROOT` or the repo directory.

- [ ] **Step 1:** Tests: `test_new_without_apply_previews_and_writes_nothing` (exit 0, no files); `test_new_apply_creates_question` (stdout contains `Q-0001`); `test_new_invalid_exit_2_names_field`; `test_show_and_list`; `test_lint_flags_broken_link`.
- [ ] **Step 2-4:** Run fail, implement with `argparse`, run pass. `--set` values: `a=b`; list fields comma-separated.

### Task 5: Handoff emitter (version 0)

**Files:** Create `assembly/handoff.py`; Test `tests/test_handoff.py`, `tests/test_conformance_mach.py`

**Interfaces:**
- Consumes: record dict, `Kind`.
- Produces: `HANDOFF_VERSION = 0`; `build_task(rec: Dict, kind: Kind, step: Dict) -> Tuple[str, str]` (filename, markdown); `check_task(md: str) -> List[str]` (errors against the v0 key set and enums); `emit(md: str, filename: str, outbox: Path) -> Path` (same content = no-op, different content at same name = error); `emit_for_step(root, rec, kind, step, outbox) -> Path`.
- Document rules: `tool: auto`, `output: stdout`, `machine` from the record or `any`; `tags: [assembly, as:<ID>, as-v0, as-exec:exact|agent, as-trust:<t>, as-sens:<s>]`; `as-exec:exact` iff the record has a non-empty `procedure`, and then the body says "Run exactly these steps, in order, and nothing else" followed by the numbered steps verbatim; otherwise `as-exec:agent`. Title and goal are single-line (newlines and `---` collapsed); full text in the body. `permission: write` only when the record says `writes: true`; if `trust` is not `owner` and `permission` is write, `approval: before-run` is forced.

- [ ] **Step 1:** Tests: `test_exact_vs_agent_tag`; `test_hostile_text_cannot_break_frontmatter` (newline, `---`, quotes, non-ASCII in question text; `check_task` returns `[]` and the frontmatter has exactly the expected keys); `test_derived_trust_write_forces_before_run`; `test_emit_idempotent_and_refuses_overwrite_with_different_content`; `test_check_task_rejects_unknown_key`; conformance: if `mach` is on PATH, `mach run <file> --dry-run` exits 0 (otherwise skip).
- [ ] **Step 2-4:** Run fail, implement, run pass.

### Task 6: Handback reader

**Files:** Create `assembly/handback.py`; Test `tests/test_handback.py`

**Interfaces:**
- Produces: `parse_frontmatter(text: str) -> Dict[str, Any]` (flat `key: value`, inline lists, quoted strings); `find_runs(runs_root: Path, ref: str) -> List[Dict]` (each: `run_id,status,machine,tool,actual_tool,created,updated`; matched by `as:<ref>` in the sibling `input.md` tags; unreadable runs are skipped and counted in the second return value → signature `-> Tuple[List[Dict], int]`); `apply_handback(root, kinds, runs_root) -> List[str]` (log lines). Status mapping: `queued→dispatched`, `running|waiting-approval→running`, `done→awaiting-confirmation`, `failed|cancelled→failed`; `answered` only through `confirm`.

- [ ] **Step 1:** Tests: `test_find_runs_by_tag`; `test_unreadable_run_skipped_not_crash`; `test_missing_runs_root_returns_empty`; `test_apply_updates_status_and_history_once` (running twice adds no duplicate event); `test_done_goes_to_awaiting_confirmation_not_answered`.
- [ ] **Step 2-4:** Run fail, implement, run pass.

### Task 7: Docs and first real record

**Files:** Create `README.md`, `AGENTS.md`, `docs/design.md`, `docs/handoff-v0.md`, `.gitignore`

- [ ] **Step 1:** Write the four documents: what the Assembly System is and is not (pointers only); the creation action and its states; handoff v0 key set and tags, and the versions ahead (v1 = first-class contract keys from machine-flows NA-330: external ID, work class, sensitivity, trust, acceptance; v2 = deterministic shell runner for `as-exec:exact`); the handback status mapping; rules for agents.
- [ ] **Step 2:** Create the first real question through the CLI as a demo in a temp root (not committed): a weekly Law/Land scan question; emit its task document to a temp outbox; run `mach run --dry-run` on it. Expected: exit 0.
- [ ] **Step 3:** Run the whole suite: `python3 -m unittest discover -s tests -v`; expect all PASS. Do not commit (the owner has not asked); leave the tree for review.

## Self-review

Spec coverage: ID minting and central creation (Tasks 2, 3), questions and goals as new things (Task 1 kinds), profiles in the repo and pointers only (Task 1, 7), handoff matching machine-flows keys so no interpretation is needed (Task 5), agent-needed tasks flagged `as-exec:agent` (Task 5), handback and the owner's confirmation as the "ready" signal (Task 6), versions (Task 7). Types: `Kind`, `Field`, `load_kinds`, `validate_fields`, `mint`, `new_record`, `emit_for_step` are named identically wherever used. Out of scope for v0 and recorded as follow-ups: contract v1 fields, deterministic runner, event feed, notifications and digest classes, GitHub repo creation, Linear provisioning automation, migration of the machine-flows `na` subsystem manifest into profiles plus bindings.
