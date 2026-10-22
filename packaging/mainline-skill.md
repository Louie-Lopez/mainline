---
name: mainline
description: Show, update, or recover a project's full lifecycle with one goal and a stable visual stage axis. Map current work to the existing project stages.
---

# Mainline

Track the user's agreed project from its original goal to its completion criteria. Keep completed, current, and necessary future stages visible. The latest request belongs inside that lifecycle; it does not replace it. Substages expand their parent's scope. Do not invent future work or expand a deliberately bounded task. Write goals, stage names, labels, and descriptions in the user's language.

The view contains one goal sentence and a stable axis. Multiple stages may be active. Clicking a stage selects its goal and optional description; clicking it again returns to the overview. A parent may expand into substages, with one group open at a time. Wide windows use a horizontal axis; narrow windows use a vertical axis. Browsing and refreshes do not call a model or write state. Checking an existing todo writes only that item's completion state.

## Start or resume

Use `mainline.py` beside this file with Python 3.10+ (standard library only). Resolve TOOL to this directory and STATE to an absolute path. Reuse the known state of the same project, including across conversations. A new conversation is not necessarily a new project; an open browser tab alone does not establish project identity. For a new project use `WORKSPACE/.mainline/<id>/state.json`; prefer the actual thread ID when available, otherwise a UUID. The ID names a file, not the project scope. Keep state outside the installed plugin directory.

Read existing state once to resume. For a new project identify its agreed outcome and completion criteria, choose a few stable lifecycle stages (usually 3–6), then locate current work. Do not copy example stages blindly. Clarify only scope uncertainty that materially changes the plan.

```text
python TOOL/mainline.py init --state STATE --task-id ID --mainline "Deliver a reliable application that solves the agreed problem." --stage Define --stage Design --stage Build --stage Validate --stage Deliver
python TOOL/mainline.py start --state STATE
python TOOL/mainline.py read --state STATE --overview
```

`start` binds the current `CODEX_THREAD_ID` to this project's state when available. Otherwise pass `--session-id ID` using the actual current conversation ID; never invent an ID. Reusing a project in a new conversation should reuse its state and bind that conversation, rather than copying the project. Bindings stay in the project's `.mainline/sessions/` directory and a small index under `CODEX_HOME/mainline/sessions/` (default `~/.codex/mainline/sessions/`), outside the plugin. The index keeps the same conversation connected when its working directory changes; it contains only the state path and project ID, not progress or conversation content. For an older project saved outside the conversation's current directory, run `start` once with its known state and actual conversation ID to register it. Never guess a project from a shared directory. Opening a known project requires only `start` and its returned URL; do not read or summarize progress merely to restore its view.

For automatic recovery in Codex, run `python TOOL/mainline.py install-hook` once when the user requests or enables this feature, and again after updating the plugin. It registers the installed tool in the user's Codex hooks, preserves unrelated hooks, and needs the user to trust "Restore Mainline" in `/hooks`. Never edit trust records or bypass review. This works on hosts that do not discover hooks bundled inside a plugin. Once trusted, it restores registered conversations on startup/resume, and recognizes existing `.mainline/<conversation-id>/state.json` paths. Unknown conversations stay quiet. It ignores compaction, forks, and subagents; it does not create projects or background model work. Follow its one-time instruction to restore the view at the next turn, checking for an existing tab first. Do not reopen the panel on subsequent replies or when the user intentionally closes it. Hooks need fresh trust when their definition changes. Disabling this hook leaves normal use available. The standalone skill supports the same optional setup when used in Codex. Do not install Codex hooks for other AI hosts. Disabling or uninstalling Mainline should also disable "Restore Mainline" in `/hooks`.

`start` returns a loopback URL and reuses a verified existing server. If it stopped, restart at its remembered address when available; an occupied remembered port falls back to a free one. In Codex, check the current conversation's browser tabs before opening a view. Reuse the tab at the returned URL (ignore the trailing slash and language query); never call URL-only `open_in_codex` when it is already open. If a UI update needs a reload, reload that existing tab in place. Ordinary progress updates use the page's existing polling and need no reload. If the server changed ports, navigate the verified previous tab for this project to the new URL. Only when no matching tab exists should `open_in_codex` open the bottom panel once. If tab inventory is unavailable, keep the known view or show the URL instead of opening blindly. Queued is not proof that a panel opened. Do not reopen after an intentional close or on routine replies. The browser must reach the server's machine; remote/cloud environments need an explicitly configured connection.

## Update only meaningful changes

One coordinating agent maintains lifecycle progress. Subagents report findings; the coordinator verifies and records actual progress. The user can separately check existing todos in the view. Keep known scope and progress in context: do not read, reconcile, or replan on every reply. Read again only when resuming unknown state, resolving a contradiction, or when asked to check. Update only when a stage's state or kind of work meaningfully changes. Small actions and side questions do not add nodes. Never mark work done just to demonstrate progress.

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
python TOOL/mainline.py describe --state STATE --parent Build --stage View --mainline "Make current work clear at a glance." --details "Covers stage status, optional substages, and layout at different panel widths."
```

A goal explains what a stage achieves, not its current activity label. Missing stage goals fall back to the nearest parent/project goal. Optional `--details` explains only the stage's scope and contents: what this part of the project covers; it requires `--stage` and may be updated alone. Missing details stay hidden and never borrow parent text; an empty string clears them. Only the selected stage's details appear. Do not include completion criteria, progress reports, next actions, or lists of things to do. Leave details empty when they add nothing useful; do not force headings or a fixed template. Revise details only when their scope or contents change, not with routine progress.

Choose the description's form from its actual logic. Keep a connected explanation as prose; use blank lines between distinct paragraphs. Use `1. ` lines only when the content has a genuine sequence, `- ` lines for independent points, and two-space indentation only for genuine child points. Mix a short introduction with a list when helpful. The viewer renders these explicit markers; it does not infer structure. Prefer a few short sentences or items. Remove repetition before adding structure; do not force headings, parallel categories, or nested lists onto a simple explanation. Do not turn the description into an activity log. Literal newlines belong in the `--details` argument; HTML and other Markdown are displayed as text.

## Todos only on the user's explicit request

Never create todos automatically, infer them from next steps, or extract them from stage descriptions. Todos are specific things the user asks to remember, not a breakdown or duplicate of the stage description. Removing actions from a description does not authorize adding them as todos. Add a todo only when the user explicitly asks to record one in the corresponding stage. If that stage is unclear, clarify the destination. New and existing projects have no todos by default. Enabling this feature does not authorize populating any project.

The page starts on the mainline and its description view. The Stage details / To-dos (环节说明 / 待办) switch changes only the area below the axis and keeps that choice while browsing stages. Overview groups todos by stage; a selected parent includes its substages; a selected substage shows its own items. A branch shows only its own todos. Completed items stay recorded under a collapsed section. Checking a todo never completes its stage, and completing a stage never checks its todos. No priority, deadline, reminder, or per-turn reconciliation.

```text
python TOOL/mainline.py todo --state STATE --stage Validate --add "Verify recovery in another project."
python TOOL/mainline.py todo --state STATE --stage Validate --done ITEM_ID
python TOOL/mainline.py todo --state STATE --stage Validate --pending ITEM_ID
```

Use `--parent STAGE` for a substage, and `--branch ID` for a branch. Use `--ordered` only when the requested items must be done in sequence; otherwise leave them unordered. Repeated `--add` arguments keep the user's requested order. Read the relevant saved items to obtain IDs only when needed. Existing todos are preserved during normal progress updates; replanning cannot silently remove stages or substages that contain them. Only update completion when the user marks it, or the explicitly requested action is actually verified complete. A concurrent edit is rejected instead of overwriting newer progress; reread and reapply only the intended change.

## Keep distinct routes only when needed

Default to the mainline. Use substages for sequential or parallel work within the same approach. Create a branch only when the user explicitly requests one, or clearly different approaches need to be preserved and pursued separately. A brief comparison or quick experiment usually stays in its current stage. Branches are optional, anchored to a mainline stage, and never created merely to record a side question. Do not automatically launch agents or ongoing work for them.

```text
python TOOL/mainline.py branch --state STATE --id local --parent Build --name "Local processing" --mainline "Keep personal information on the device." --stage Organize --stage Search --stage Verify
python TOOL/mainline.py status --state STATE --branch local --done Organize --active Search --label Fixing
python TOOL/mainline.py read --state STATE --branch local
```

Use stable lowercase IDs for commands and names in the user's language for display. Branches have their own goal, stages, labels, descriptions, and optional substages. `status`, `position`, `subdivide`, `describe`, `replan`, and `finish` accept `--branch ID`; `--parent` still means a substage parent within that route. Branch completion never changes the mainline or other routes. After choosing an approach, update the mainline explicitly according to actual progress; there is no automatic merge.

Resume with `read --overview`: it returns mainline progress and a small branch index without branch contents. Read only the route needed with `read --branch ID` when its state is not already known. Scoped commands return that route rather than every branch. The page initially shows the mainline; click the small branch entry to switch views. Reloading returns to the mainline. Viewing and switching do not write progress or call a model.

Use `branch --id ID --archive` to hide an unused route while retaining all its progress, and `branch --id ID --restore` to bring it back. Restore before updating an archived route. `branch --id ID --parent STAGE` can reanchor a route to another existing mainline stage; `--name` and `--mainline` update its wording. Stage changes still require `replan --branch ID --reason`. Mainline replanning preserves branches and refuses to remove a stage that still anchors one. No nested branches or automatic copying of the whole project.

## Recovery

Resume from the goal, frozen stages, and statuses, then consult original requirements and actual outputs as needed. This record helps orientation; it does not replace task evidence or independently verify the agent's claims. The old single-pointer format is read compatibly. Old event-log state requires explicit replan with backup.

On a dimmed/stale view, check `/state` for its error. If the current CLI can read state but the server rejects new fields, verify its process, command line, and state path, then restart that exact server at the same port. Updating Python requires restarting an existing server; refreshing the page only reloads HTML. Preserve state and never replan merely to fix a service error.
