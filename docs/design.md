# Design notes

Source of truth for intent: the Linear document "Assembly System: architecture reading and decisions so far
(2026-10-27)" in project Assembly System. This file records what v0 implements.

**Decided by the owner:** the Assembly System is its own code base profiling what is in its purview; profiles live here;
data and code do not; Dispatch is the main point of interaction; it mints all IDs; anything new, including questions
and goals, is created through one central action; bays are time-limited accumulation branches.

**Creation action.** `assembly new KIND` validates against `kinds/KIND.json`, mints the ID, writes the profile, then runs the
kind's steps: `handoff` (write a task document) or `manual` (a checklist line for a person). Every step's status is
rewritten to `creations/<ID>.json` as it happens, so a crash leaves the true state. States: `complete`, `manual-pending`
(only people's steps remain), `partial` (a step failed or is pending; resume by re-running the step).

**Question fields** were inferred from the architecture: the goal and service it descends from, its lens (law, land,
companies, products, processes, programs), region, historic/current horizon, who raised it, intake (scan or file),
cadence, target bay and store, reviews and checks, trust and sensitivity, due date, an optional exact procedure.

**Record status:** new -> dispatched -> running -> awaiting-confirmation -> answered (owner), or failed; retired.

**Overlap with machine-flows:** units, repos and datasets are defined here and referenced by ID there; machine-flows keeps
where things are checked out on each machine and which tool leads them.
