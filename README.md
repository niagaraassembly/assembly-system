# Assembly System

The company-level system for Niagara Assembly. It is its own code base and holds a **profile** of every
code base, product, project, dataset, goal and question in the company's purview: what it is, what it
relies on, where it sits in the Assembly Architecture, and what it promises. Data and code **do not live
here**; profiles hold pointers only.

It is to the company what machine-flows is to the owner's laptops. machine-flows executes work on the
machines and tools; the Assembly System decides what exists and what needs doing, and hands tasks over.

## What v0 does

- **One front door for anything new** (`assembly new KIND`): mints the ID (only this system mints IDs), captures
  a profile, and runs the kind's steps (hand a task to machine-flows, or leave a checklist item for a person).
  Questions and goals are "new" things like any other.
- **Handoff v0**: writes a machine-flows prompt document (`docs/handoff-v0.md`) whose body is deterministic, so
  no interpretation is needed to pick it up. Work that needs an agent is marked so.
- **Changes**: `set`, `retire` and `supersede` go through the same validation, record old -> new and who in the history,
  and bump `rev`; `dispatch` then writes a revised task document beside the earlier one.
- **Handback v0**: reads machine-flows run records (read-only) and updates records; the owner confirms
  (`assembly confirm`) before anything counts as answered.

Not yet: contract v1 (first-class keys), a deterministic shell runner, event feed, notifications, review pack,
Linear or GitHub provisioning, profiles for the existing company repos. See `docs/design.md`.

## Use

```
bin/assembly kinds [KIND]                       # what can be created, and each kind's fields
bin/assembly new question --set text="..." --set lens=law --set trust=owner \
    --set sensitivity=private --set intake=scan             # preview
bin/assembly new question ... --outbox ~/machine-flows/files/inbox/prompts --apply
bin/assembly set ID --set k=v [--unset k] [--actor NAME] [--apply]   # change a record: validated, recorded, bumps rev
bin/assembly retire ID --reason TEXT [--apply]             # nothing is ever deleted; retired records are read-only
bin/assembly supersede OLD --by NEW [--apply]              # retire OLD and link NEW to it
bin/assembly list [KIND] | show ID | lint
bin/assembly resume ID [--outbox DIR]                      # finish a partial creation (no new ID)
bin/assembly dispatch ID [--outbox DIR] [--apply]          # (re)write the task document
bin/assembly handback [--runs DIR] [--apply]               # read machine-flows run records
bin/assembly confirm ID                                    # owner: a finished run is accepted
```

Run the tests: `python3 -m unittest discover -s tests` (Python 3.9+, standard library only; the conformance
tests use the real `mach run --dry-run` when `mach` is installed).

## Local questions workspace

The website now lives in [niagaraassembly/assembly-site](https://github.com/niagaraassembly/assembly-site).
Its HTTP adapter and browser assets are separate from this core. See its README for launch and configuration.

Assembly owns question drafts, kinds, IDs, validation, immutable original text/source links, history and backups.
The question kind's `capture.metadata` list controls which schema fields the capture interface may edit.
Draft capture never emits handoffs during creation, resume or dispatch.

Use `ASSEMBLY_ROOT` to select a record store outside the checkout. A local ignored `.assembly-record-root`
file can redirect this checkout's CLI to an existing absolute record directory; explicit root/environment
settings take precedence. Migrated runtime data stays outside Git; the local pre-migration files are a
rollback copy and are no longer active when the redirect is present.

```sh
ASSEMBLY_ROOT=~/na/local-data/assembly bin/assembly list question
bin/assembly new question --draft --set text="What can this region make?"  # preview
bin/assembly new question --draft --from /path/to/question.json --apply
```

The JSON file is a field object such as `{"text": "Full original text", "title": "Optional title"}`.
Metadata edits use `set`; originals develop through separately linked questions. Promotion to executable
work and final Mach integration remain separate future steps.

## Layout

`assembly/` code · `kinds/*.json` what each kind of thing carries (add a kind by adding a file) ·
`profiles/<kind>/<ID>.json` records · `creations/<ID>.json` per-creation progress · `registry/` ID counters ·
`outbox/` default place for task documents · `docs/` design and contracts.
