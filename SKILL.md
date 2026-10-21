---
name: mainline
description: Show, update, or recover a project's full lifecycle with one goal and a stable visual stage axis. Map current work to the existing project stages.
---

# Mainline

Track the user's agreed project from its original goal to its completion criteria. Keep completed, current, and necessary future stages visible. The latest request belongs inside that lifecycle; it does not replace it. Substages expand their parent's scope. Do not invent future work or expand a deliberately bounded task. Write goals, stage names, labels, and descriptions in the user's language.

The view contains one goal sentence and a stable axis. Multiple stages may be active. Clicking a stage selects its goal and optional description; clicking it again returns to the overview. A parent may expand into substages, with one group open at a time. Wide windows use a horizontal axis; narrow windows use a vertical axis. UI clicks and refreshes do not call a model or write state.

## Start or resume

Use `mainline.py` beside this file with Python 3.10+ (standard library only). Resolve TOOL to this directory and STATE to an absolute path. Reuse the known state of the same project, including across conversations. A new conversation is not necessarily a new project; an open browser tab alone does not establish project identity. For a new project use `WORKSPACE/.mainline/<id>/state.json`; prefer the actual thread ID when available, otherwise a UUID. The ID names a file, not the project scope. Keep state outside the installed plugin directory.

Read existing state once to resume. For a new project identify its agreed outcome and completion criteria, choose a few stable lifecycle stages (usually 3–6), then locate current work. Do not copy example stages blindly. Clarify only scope uncertainty that materially changes the plan.

```text
python TOOL/mainline.py init --state STATE --task-id ID --mainline "Deliver a reliable application that solves the agreed problem." --stage Define --stage Design --stage Build --stage Validate --stage Deliver
python TOOL/mainline.py start --state STATE
python TOOL/mainline.py read --state STATE
```

`start` returns a loopback URL and reuses a verified existing server. In Codex, use `open_in_codex` with a browser target, preferably the current chat's bottom panel, when available. Otherwise show the URL. Queued is not proof that a panel opened. Do not reopen it for routine updates. The browser must reach the server's machine; remote/cloud environments need an explicitly configured connection.

## Update only meaningful changes

One coordinating agent writes each state file. Subagents report findings; the coordinator verifies and records actual progress. Keep known scope and progress in context: do not read, reconcile, or replan on every reply. Read again only when resuming unknown state, resolving a contradiction, or when asked to check. Update only when a stage's state or kind of work meaningfully changes. Small actions and side questions do not add nodes. Never mark work done just to demonstrate progress.

Each stage is independently `pending`, `active`, or `done`; reopening and parallel work are allowed. Prefer `status`, which changes only named stages:

```text
python TOOL/mainline.py status --state STATE --done Define --done Design --active Build --active Validate
python TOOL/mainline.py status --state STATE --done Build
python TOOL/mainline.py status --state STATE --active Validate --label Verifying
```

Optional `--label` replaces the default active badge with a 1–12 character phrase, such as `Fixing`, `Verifying`, or `Needs input`. It requires exactly one `--active` in that update. Use the user's language. Explicitly updating a leaf without a label clears its old label; untouched stages retain theirs. Leaving active clears the label. No per-turn label churn or background model monitoring.

`position --current A --current B` replaces the active set: unselected active stages return to pending; completed stages remain done unless selected to reopen. It does not infer completion. Use `finish` only when the whole agreed project meets its completion criteria, all earlier stages are done, and the last stage is active or done. Finishing a local request is not finishing the project.

## Expand a stage when useful

```text
python TOOL/mainline.py subdivide --state STATE --parent Build --stage Data --stage Interface --stage View --current Interface --current View
python TOOL/mainline.py status --state STATE --parent Build --done Data --active Interface --label Fixing
```

At most two levels. Substages must cover the parent's necessary work, not just the latest request, because they determine parent completion. New subdivision inherits the parent's status: all done, all pending, or the first child active unless `--current` specifies otherwise. A parent is done when all children are done, pending when all are pending, and active otherwise (including partial completion without active children). Update children, not an inconsistent parent state. A parent inherits a label only when all active children share the same nonempty label.

Keep stage names/order fixed. Changing existing substages requires `subdivide --reason`. Use `replan --stage ... --current ... --reason ...` only for a substantial scope change or to correct an axis confirmed to have been wrongly narrowed. Replan clears old substages and stage metadata; remap verified progress and goals to the corrected lifecycle. Do not repeatedly rewrite the plan.

## Goals and selected-stage descriptions

The project goal stays stable when the task changes or the user clicks a stage. Change it with `describe --state STATE --mainline TEXT` only when the agreed objective or wording changes. Set a stage's one-sentence goal when its scope is established:

```text
python TOOL/mainline.py describe --state STATE --stage Build --mainline "Turn the agreed design into a working implementation."
python TOOL/mainline.py describe --state STATE --parent Build --stage View --mainline "Make current work clear at a glance." --details "Show stage status and optional substages. Adapt to the available panel width."
```

A goal explains what a stage achieves, not its current activity label. Missing stage goals fall back to the nearest parent/project goal. Optional `--details` adds 1–3 useful sentences about scope, contents, or outputs; it requires `--stage` and may be updated alone. Missing details stay hidden and never borrow parent text; an empty string clears them. Only the selected stage's details appear. Avoid repeating status or adding descriptions without useful content. Stable scope needs no repeated reads or writes.

## Recovery

Resume from the goal, frozen stages, and statuses, then consult original requirements and actual outputs as needed. This record helps orientation; it does not replace task evidence or independently verify the agent's claims. The old single-pointer format is read compatibly. Old event-log state requires explicit replan with backup.

On a dimmed/stale view, check `/state` for its error. If the current CLI can read state but the server rejects new fields, verify its process, command line, and state path, then restart that exact server at the same port. Updating Python requires restarting an existing server; refreshing the page only reloads HTML. Preserve state and never replan merely to fix a service error.
