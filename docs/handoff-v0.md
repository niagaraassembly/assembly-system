# Handoff and handback, version 0

## Handoff (Assembly System -> machine-flows)

A task is a Markdown prompt document in the machine-flows mach inbox format, using only the keys
`mach run` accepts today (checked by `tests/test_conformance_mach.py` against the real validator):

| Key | Value written |
| --- | --- |
| `mach`, `type` | `1`, `task` |
| `title`, `goal` | single-line, quotes and backslashes removed; the full text is in the body as a quote |
| `tool`, `output` | `auto`, `stdout` |
| `permission` | `write` only when the record says `writes: true`, else `read-only` |
| `approval` | `before-run` when the work writes **or** the trust label is not `owner`; else `none` |
| `machine`, `due` | from the record (`any` by default) |
| `tags` | `assembly`, `as:<ID>`, `as-v0`, `as-exec:exact\|agent`, `as-trust:<t>`, `as-sens:<s>`, and `as-rev:<n>` once a record has been changed |

- `as-exec:exact`: the record has a `procedure`; the body says "Run exactly these steps, in order, and nothing
  else" and lists them. No interpretation is needed to pick it up.
- `as-exec:agent`: no procedure; the body states the question and context and says an agent must choose the approach
  within the stated permission. Some work will always need this.
- The link back to the record is the `as:<ID>` tag; the task is matched on handback by that tag.
- File name `<created date>-as-<id>-<step>.md` (`...-r<n>.md` after a change), stable across days; rewriting identical content is a no-op,
  different content under the same name is refused.

## Handback (machine-flows -> Assembly System)

Read-only. For each record in `dispatched`, `running`, `awaiting-confirmation` or `failed`, find machine-flows run
records (`files/runs/YYYY/MM/<run>/run.md`) whose `input.md` carries `as:<ID>`; the latest decides:

| Run status | Record status |
| --- | --- |
| queued | dispatched |
| running, waiting-approval | running |
| done | awaiting-confirmation |
| failed, cancelled | failed |

`answered` is set only by `assembly confirm` (the owner). Unreadable run folders are skipped and counted, never fatal.

## Versions ahead

- **v1:** replace the tags with first-class contract keys agreed with machine-flows (NA-330): external task ID, work
  class (never a tool), sensitivity, trust, acceptance check; result schema with cost and "why this tool".
- **v2:** a deterministic runner for `as-exec:exact` tasks, so exact steps need no agent at all; event feed and
  notifications from machine-flows replace polling run folders.

## Hardening (what `check_task` and `build_task` enforce)

- Free text never reaches the frontmatter unquoted: `title`, `goal`, `path` are flattened to one line; `machine` must match
  `[A-Za-z0-9][A-Za-z0-9._-]*` (validated at creation and refused again at build time); `due` must be a date.
- Unknown `trust` or `sensitivity` values fail closed (`external`, `private`).
- Body text taken from a record (region, procedure steps, checks) is flattened to one line, so it cannot open a new section;
  quotes in procedure steps are preserved.
- `check_task` parses strictly (a repeated key is an error, so a later line cannot override `approval`) and requires
  `approval: before-run` whenever the trust tag is not `owner` or the permission is `write`.
