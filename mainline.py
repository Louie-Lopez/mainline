"""A project axis with optional explicit todos. Python standard library only."""

import argparse
import copy
import base64
from contextlib import contextmanager
import errno
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
from socketserver import TCPServer
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler
import uuid


STATE_FIELDS = {
    "task_id", "stages", "stage_statuses", "updated_at", "revision",
}
POINTER_FIELDS = {"task_id", "stages", "current_stage", "completed", "updated_at", "revision"}
LEGACY_FIELDS = {
    "task_id", "mainline", "completion_criterion", "current_action",
    "next_action", "verified_results", "updated_at", "revision",
}
LOCAL_HTTP = build_opener(ProxyHandler({}))


def absolute_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("state must be an absolute path")
    return path.resolve()


def nonempty(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")


def validate_time(value, field):
    nonempty(value, field)
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")


def validate_state(state):
    if is_legacy(state):
        raise ValueError("Legacy state: explicitly migrate with replan --stage ... --current ... --reason ...")
    if not isinstance(state, dict) or not (
            set(state) - {"mainline", "substages", "stage_labels", "stage_mainlines", "stage_details", "stage_todos", "branches"} == STATE_FIELDS
            or set(state) - {"mainline"} == POINTER_FIELDS):
        raise ValueError("Missing or unknown state fields")
    nonempty(state["task_id"], "task_id")
    if "mainline" in state:
        nonempty(state["mainline"], "mainline")
    if normalize_stages(state["stages"]) != state["stages"]:
        raise ValueError("Stage names must not have surrounding whitespace")
    if "current_stage" in state:
        if type(state["current_stage"]) is not int or not 0 <= state["current_stage"] < len(state["stages"]):
            raise ValueError("current_stage must be a valid stage index")
        if type(state["completed"]) is not bool:
            raise ValueError("completed must be a boolean")
        if state["completed"] and state["current_stage"] != len(state["stages"]) - 1:
            raise ValueError("Legacy state can only finish at the last stage")
        # Preserve the old pointer's semantics only during compatibility migration.
        state = dict(state)
        index, completed = state.pop("current_stage"), state.pop("completed")
        state["stage_statuses"] = [
            "done" if completed or i < index else "active" if i == index else "pending"
            for i in range(len(state["stages"]))
        ]
    statuses = state["stage_statuses"]
    if (not isinstance(statuses, list) or len(statuses) != len(state["stages"])
            or any(status not in ("pending", "active", "done") for status in statuses)):
        raise ValueError("stage_statuses must match stages and contain only pending, active, or done")
    validate_labels(state)
    validate_stage_mainlines(state)
    validate_stage_details(state)
    validate_todos(state)
    substages = state.get("substages", {})
    if not isinstance(substages, dict):
        raise ValueError("substages must map parent stages to child groups")
    for parent, group in substages.items():
        if parent not in state["stages"]:
            raise ValueError(f"Unknown parent stage: {parent}")
        if not isinstance(group, dict) or set(group) - {"stage_labels", "stage_mainlines", "stage_details", "stage_todos"} != {"stages", "stage_statuses"}:
            raise ValueError("Substages allow only stages, statuses, labels, goals, and details; maximum two levels")
        if normalize_stages(group["stages"]) != group["stages"]:
            raise ValueError("Substage names must not have surrounding whitespace")
        child_statuses = group["stage_statuses"]
        if (not isinstance(child_statuses, list) or len(child_statuses) != len(group["stages"])
                or any(status not in ("pending", "active", "done") for status in child_statuses)):
            raise ValueError("Substage statuses must match stages and contain only pending, active, or done")
        if statuses[state["stages"].index(parent)] != aggregate_status(child_statuses):
            raise ValueError(f"Parent stage {parent} is derived from substages; update them with status --parent")
        validate_labels(group)
        validate_stage_mainlines(group)
        validate_stage_details(group)
        validate_todos(group)
        if state.get("stage_labels", {}).get(parent) != aggregate_label(group):
            raise ValueError(f"The label for parent stage {parent} must be derived from active substages")
    if type(state["revision"]) is not int or state["revision"] < 1:
        raise ValueError("revision must be a positive integer")
    validate_time(state["updated_at"], "updated_at")
    branches = state.get("branches", {})
    if not isinstance(branches, dict):
        raise ValueError("branches must map stable IDs to routes")
    for identity, branch in branches.items():
        validate_branch_id(identity)
        required = {"name", "parent", "mainline", "stages", "stage_statuses"}
        optional = {"substages", "stage_labels", "stage_mainlines", "stage_details", "stage_todos", "archived"}
        if not isinstance(branch, dict) or set(branch) - optional != required:
            raise ValueError("Branches require a name, parent, goal, and stages; nested branches are not supported")
        for field in ("name", "parent", "mainline"):
            nonempty(branch[field], "branch " + field)
            if branch[field] != branch[field].strip() or len(branch[field].splitlines()) != 1:
                raise ValueError("Branch names, parents, and goals must be single-line text")
        if branch["parent"] not in state["stages"]:
            raise ValueError("Branch parent must be an existing mainline stage")
        if "archived" in branch and type(branch["archived"]) is not bool:
            raise ValueError("archived must be a boolean")
        route = {key: value for key, value in branch.items() if key not in {"name", "parent", "archived"}}
        validate_state(dict(route, task_id=state["task_id"], revision=state["revision"], updated_at=state["updated_at"]))
    return state


def validate_branch_id(identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", identity) or identity == "main":
        raise ValueError("Branch ID must start with a lowercase letter, use letters/digits/hyphens, and be at most 64 characters; main is reserved")


class StateConflict(ValueError):
    pass


def validate_todos(group):
    todos = group.get("stage_todos", {})
    if not isinstance(todos, dict):
        raise ValueError("stage_todos must map stages to todo lists")
    for stage, listing in todos.items():
        if (stage not in group["stages"] or not isinstance(listing, dict)
                or set(listing) != {"ordered", "items"} or type(listing["ordered"]) is not bool
                or not isinstance(listing["items"], list) or not listing["items"]):
            raise ValueError("Todos require an existing stage, ordered flag, and nonempty items")
        ids = set()
        for item in listing["items"]:
            if (not isinstance(item, dict) or set(item) != {"id", "text", "done"}
                    or not isinstance(item["id"], str) or not re.fullmatch(r"[a-f0-9]{12}", item["id"])
                    or item["id"] in ids or type(item["done"]) is not bool
                    or not isinstance(item["text"], str) or not item["text"].strip()
                    or len(item["text"]) > 500 or len(item["text"].splitlines()) != 1):
                raise ValueError("Invalid todo item")
            ids.add(item["id"])


def todo_state(path, stage, *, parent=None, branch=None, add=None, done=None, pending=None,
               ordered=None, revision=None, task_id=None):
    root, old = read_scope(path, branch)
    if task_id is not None and root["task_id"] != task_id:
        raise StateConflict("Project identity changed")
    if revision is not None and (type(revision) is not int or root["revision"] != revision):
        raise StateConflict("State changed; refresh before updating the todo")
    updated = copy.deepcopy(old)
    group = updated
    if parent is not None:
        if parent not in updated.get("substages", {}):
            raise ValueError("Unknown substage parent")
        group = updated["substages"][parent]
    stage = group["stages"][stage_index(group["stages"], stage)]
    listing = group.get("stage_todos", {}).get(stage, {"ordered": False, "items": []})
    if not add and not done and not pending and ordered is None:
        raise ValueError("Specify a todo addition, completion, reopening, or list order")
    changes = {}
    for ids, value in ((done or [], True), (pending or [], False)):
        for identity in ids:
            if identity in changes or not any(item["id"] == identity for item in listing["items"]):
                raise ValueError("Unknown or conflicting todo ID")
            changes[identity] = value
    for item in listing["items"]:
        if item["id"] in changes:
            item["done"] = changes[item["id"]]
    for text in add or []:
        nonempty(text, "todo text")
        listing["items"].append({"id": uuid.uuid4().hex[:12], "text": text.strip(), "done": False})
    if ordered is not None:
        listing["ordered"] = ordered
    group.setdefault("stage_todos", {})[stage] = listing
    validate_todos(group)
    return commit_scope(path, root, updated, branch)


def preserve_todos(old, updated):
    """Never discard user reminders when rearranging stages."""
    if any(name not in updated["stages"] for name in old.get("stage_todos", {})):
        raise ValueError("Cannot remove a stage containing todos; retain that stage")
    if old.get("stage_todos"):
        updated["stage_todos"] = old["stage_todos"]
    for group in old.get("substages", {}).values():
        if group.get("stage_todos"):
            raise ValueError("Cannot clear substages containing todos; retain the existing subdivision")


def read_scope(path, branch=None, *, writing=True):
    root = read_state(path)
    if branch is None:
        return root, root
    validate_branch_id(branch)
    if branch not in root.get("branches", {}):
        raise ValueError(f"Unknown branch: {branch}")
    route = root["branches"][branch]
    if writing and route.get("archived", False):
        raise ValueError("Restore the archived branch before updating it")
    return root, route


def commit_scope(path, root, route, branch=None):
    if branch is None:
        return commit_state(path, root, route)
    branches = dict(root["branches"])
    branches[branch] = route
    return commit_state(path, root, dict(root, branches=branches))


def overview_state(state):
    overview = {key: value for key, value in state.items() if key not in {"branches", "stage_todos"}}
    if state.get("substages"):
        overview["substages"] = {name: {key: value for key, value in group.items() if key != "stage_todos"}
                                 for name, group in state["substages"].items()}
    if state.get("branches"):
        overview["branch_index"] = {
            identity: {key: route[key] for key in ("name", "parent", "archived") if key in route}
            for identity, route in state["branches"].items()
        }
    return overview


def branch_state(path, identity, *, name=None, parent=None, mainline=None, stages=None, current=None, archive=False, restore=False):
    validate_branch_id(identity)
    old = read_state(path)
    branches = dict(old.get("branches", {}))
    existing = branches.get(identity)
    if archive or restore:
        if archive and restore or any(value is not None for value in (name, parent, mainline, stages, current)):
            raise ValueError("Archive/restore cannot be combined with route edits")
        if existing is None:
            raise ValueError(f"Unknown branch: {identity}")
        route = dict(existing)
        route.pop("archived", None)
        if archive:
            route["archived"] = True
    elif existing is not None:
        if stages is not None or current is not None:
            raise ValueError("Branch already exists; use status or replan --branch to change its stages")
        if existing.get("archived", False):
            raise ValueError("Restore the archived branch before updating it")
        route = dict(existing)
        for key, value in (("name", name), ("parent", parent), ("mainline", mainline)):
            if value is not None:
                nonempty(value, "branch " + key)
                route[key] = value.strip()
    else:
        for value, field in ((name, "--name"), (parent, "--parent"), (mainline, "--mainline")):
            nonempty(value, field + " for a new branch")
        stages = normalize_stages(stages)
        selected = {0} if current is None else selected_indices(stages, current)
        route = {"name": name.strip(), "parent": parent.strip(), "mainline": mainline.strip(),
                 "stages": stages, "stage_statuses": ["active" if i in selected else "pending" for i in range(len(stages))]}
    branches[identity] = route
    return commit_state(path, old, dict(old, branches=branches))


def aggregate_status(statuses):
    if all(status == "done" for status in statuses):
        return "done"
    if all(status == "pending" for status in statuses):
        return "pending"
    return "active"


def validate_stage_mainlines(group):
    mainlines = group.get("stage_mainlines", {})
    if not isinstance(mainlines, dict):
        raise ValueError("stage_mainlines must map stage names to one-sentence goals")
    for name, mainline in mainlines.items():
        if name not in group["stages"]:
            raise ValueError(f"Unknown stage for goal: {name}")
        nonempty(mainline, "stage goal")
        if mainline.splitlines() != [mainline]:
            raise ValueError("Stage goals must be nonempty single-line text")


def validate_stage_details(group):
    details = group.get("stage_details", {})
    if not isinstance(details, dict):
        raise ValueError("stage_details must map stage names to descriptions")
    for name, text in details.items():
        if name not in group["stages"]:
            raise ValueError(f"Unknown stage for description: {name}")
        nonempty(text, "stage description")


def validate_label(label):
    nonempty(label, "label")
    if len(label) > 12 or label != label.strip() or any(character in label for character in "\r\n\t"):
        raise ValueError("label must be a single-line phrase of 1-12 characters without surrounding whitespace")


def validate_labels(group):
    labels = group.get("stage_labels", {})
    if not isinstance(labels, dict):
        raise ValueError("stage_labels must map stage names to short phrases")
    for name, label in labels.items():
        if name not in group["stages"] or group["stage_statuses"][group["stages"].index(name)] != "active":
            raise ValueError("Only active stages can have labels")
        validate_label(label)


def aggregate_label(group):
    labels = group.get("stage_labels", {})
    active = [labels.get(name) for name, status in zip(group["stages"], group["stage_statuses"])
              if status == "active"]
    return active[0] if active and active[0] and all(label == active[0] for label in active) else None


def with_labels(group, labels):
    result = dict(group)
    result.pop("stage_labels", None)
    if labels:
        result["stage_labels"] = labels
    return result


def clear_labels(group, indices):
    names = {group["stages"][index] for index in indices}
    return with_labels(group, {name: label for name, label in group.get("stage_labels", {}).items()
                               if name not in names})


def sync_parent_labels(state):
    labels = dict(state.get("stage_labels", {}))
    for parent, group in state.get("substages", {}).items():
        labels.pop(parent, None)
        label = aggregate_label(group)
        if label:
            labels[parent] = label
    return with_labels(state, labels)


def is_legacy(state):
    return isinstance(state, dict) and set(state) in (LEGACY_FIELDS, LEGACY_FIELDS | {"timeline"})


def normalize_stages(stages):
    if not isinstance(stages, list) or not stages:
        raise ValueError("At least one stage is required")
    for stage in stages:
        nonempty(stage, "stage name")
    names = [stage.strip() for stage in stages]
    if len(set(names)) != len(names):
        raise ValueError("Stage names must be unique")
    return names


def stage_index(stages, current):
    nonempty(current, "current")
    try:
        return stages.index(current.strip())
    except ValueError as exc:
        raise ValueError(f"Unknown stage: {current}") from exc


def selected_indices(stages, current):
    names = normalize_stages([current] if isinstance(current, str) else current)
    return {stage_index(stages, name) for name in names}


def read_state(path):
    return validate_state(json.loads(Path(path).read_text(encoding="utf-8")))


def atomic_json(path, data, create=False):
    path = Path(path)
    if create and path.exists():
        raise FileExistsError(f"Refusing to overwrite existing state: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    # Updates compare state under a lock; Windows rename also refuses replacing
    # an existing file on initial creation, including a concurrent creation race.
    if create:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing state: {path}")
        if os.name == "nt":
            os.rename(temporary, path)
        else:
            os.replace(temporary, path)
    else:
        os.replace(temporary, path)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def init_state(path, task_id, stages, current=None, mainline=None):
    stages = normalize_stages(stages)
    selected = {0} if current is None else selected_indices(stages, current)
    state = validate_state({
        "task_id": task_id, "stages": stages,
        "stage_statuses": ["active" if i in selected else "pending" for i in range(len(stages))],
        "updated_at": now(), "revision": 1,
    })
    if mainline is not None:
        nonempty(mainline, "mainline")
        state["mainline"] = mainline.strip()
    atomic_json(path, state, create=True)
    return state


def commit_state(path, old, state):
    if state == old:
        return old
    state["updated_at"] = now()
    state["revision"] = old["revision"] + 1
    validate_state(state)
    with startup_lock(path, suffix=".write.lock"):
        if read_state(path) != old:
            raise StateConflict("State changed; retry the update against the latest state")
        atomic_json(path, state)
    return state


def position_state(path, current, *, branch=None):
    root, old = read_scope(path, branch)
    selected = selected_indices(old["stages"], current)
    statuses = ["active" if i in selected else "pending" if status == "active" else status
                for i, status in enumerate(old["stage_statuses"])]
    changed = [i for i, status in enumerate(statuses) if status != old["stage_statuses"][i]]
    state = clear_labels(dict(old, stage_statuses=statuses), changed)
    return commit_scope(path, root, sync_parent_labels(state), branch)


def status_state(path, *, active=None, done=None, pending=None, parent=None, label=None, branch=None):
    root, old = read_scope(path, branch)
    group = old
    if parent is not None:
        parent = old["stages"][stage_index(old["stages"], parent)]
        if parent not in old.get("substages", {}):
            raise ValueError(f"Parent stage {parent} has no substages")
        group = old["substages"][parent]
    changes = {}
    for status, names in (("active", active), ("done", done), ("pending", pending)):
        if names is None:
            continue
        for name in normalize_stages([names] if isinstance(names, str) else names):
            index = stage_index(group["stages"], name)
            if index in changes:
                raise ValueError(f"Cannot assign multiple statuses to the same stage: {name}")
            changes[index] = status
    if not changes:
        raise ValueError("status requires at least one of --active, --done, or --pending")
    target = None
    if label is not None:
        validate_label(label)
        active_indices = [index for index, status in changes.items() if status == "active"]
        if len(active_indices) != 1:
            raise ValueError("--label requires exactly one --active stage in this update")
        target = group["stages"][active_indices[0]]
        if parent is None and target in old.get("substages", {}):
            raise ValueError("Parent labels are derived from substages; use status --parent to label a substage")
    statuses = [changes.get(i, status) for i, status in enumerate(group["stage_statuses"])]
    updated = clear_labels(dict(group, stage_statuses=statuses), changes)
    if target is not None:
        updated = with_labels(updated, dict(updated.get("stage_labels", {}), **{target: label}))
    if parent is not None:
        return commit_substages(path, old, parent, updated, root=root, branch=branch)
    return commit_scope(path, root, sync_parent_labels(updated), branch)


def commit_substages(path, old, parent, group, *, root=None, branch=None):
    substages = dict(old.get("substages", {}))
    substages[parent] = group
    statuses = list(old["stage_statuses"])
    statuses[old["stages"].index(parent)] = aggregate_status(group["stage_statuses"])
    state = dict(old, substages=substages, stage_statuses=statuses)
    return commit_scope(path, old if root is None else root, sync_parent_labels(state), branch)


def subdivide_state(path, parent, stages, current=None, reason=None, *, branch=None):
    root, old = read_scope(path, branch)
    parent = old["stages"][stage_index(old["stages"], parent)]
    stages = normalize_stages(stages)
    selected = None if current is None else selected_indices(stages, current)
    existing = old.get("substages", {}).get(parent)
    if existing is not None and existing["stages"] == stages:
        if selected is None:
            return root
        statuses = ["active" if i in selected else "pending" if status == "active" else status
                    for i, status in enumerate(existing["stage_statuses"])]
        changed = [i for i, status in enumerate(statuses) if status != existing["stage_statuses"][i]]
        group = clear_labels(dict(existing, stage_statuses=statuses), changed)
    else:
        if existing is not None:
            nonempty(reason, "--reason for changing existing substages")
        parent_status = old["stage_statuses"][old["stages"].index(parent)]
        if selected is not None:
            statuses = ["active" if i in selected else "pending" for i in range(len(stages))]
        elif parent_status == "active":
            statuses = ["active"] + ["pending"] * (len(stages) - 1)
        else:
            statuses = [parent_status] * len(stages)
        group = {"stages": stages, "stage_statuses": statuses}
        if existing is not None:
            preserve_todos(existing, group)
    return commit_substages(path, old, parent, group, root=root, branch=branch)


def finish_state(path, *, branch=None):
    root, old = read_scope(path, branch)
    statuses = old["stage_statuses"]
    if any(status != "done" for status in statuses[:-1]) or statuses[-1] not in ("active", "done"):
        raise ValueError("finish requires every earlier stage done and the last stage active or done")
    state = with_labels(dict(old, stage_statuses=["done"] * len(statuses)), {})
    return commit_scope(path, root, sync_parent_labels(state), branch)


def describe_state(path, mainline=None, *, stage=None, parent=None, details=None, branch=None):
    if mainline is None and details is None:
        raise ValueError("describe requires --mainline or --details")
    if mainline is not None:
        nonempty(mainline, "mainline")
    if details is not None:
        if not isinstance(details, str):
            raise ValueError("details must be text; an empty string clears the description")
        if stage is None:
            raise ValueError("--details requires --stage")
    if parent is not None and stage is None:
        raise ValueError("--parent requires --stage")
    root, old = read_scope(path, branch)
    if stage is None:
        return commit_scope(path, root, dict(old, mainline=mainline.strip()), branch)
    group = old
    if parent is not None:
        parent = old["stages"][stage_index(old["stages"], parent)]
        if parent not in old.get("substages", {}):
            raise ValueError(f"Parent stage {parent} has no substages")
        group = old["substages"][parent]
    stage = group["stages"][stage_index(group["stages"], stage)]
    updated = dict(group)
    if mainline is not None:
        mainlines = dict(group.get("stage_mainlines", {}))
        mainlines[stage] = mainline.strip()
        updated["stage_mainlines"] = mainlines
    if details is not None:
        descriptions = dict(group.get("stage_details", {}))
        if details.strip():
            descriptions[stage] = details.strip()
        else:
            descriptions.pop(stage, None)
        updated.pop("stage_details", None)
        if descriptions:
            updated["stage_details"] = descriptions
    if parent is None:
        return commit_scope(path, root, updated, branch)
    substages = dict(old["substages"])
    substages[parent] = updated
    return commit_scope(path, root, dict(old, substages=substages), branch)


def replan_state(path, stages, current, reason, *, branch=None):
    nonempty(reason, "reason for a substantial scope change")
    stages = normalize_stages(stages)
    selected = selected_indices(stages, current)
    statuses = ["active" if i in selected else "pending" for i in range(len(stages))]
    if branch is not None:
        root, old = read_scope(path, branch)
        route = {key: old[key] for key in ("name", "parent", "mainline")}
        route.update(stages=stages, stage_statuses=statuses)
        preserve_todos(old, route)
        return commit_scope(path, root, route, branch)
    original = Path(path).read_bytes()
    old = json.loads(original.decode("utf-8"))
    legacy = is_legacy(old)
    if legacy:
        nonempty(old["task_id"], "task_id")
        if type(old["revision"]) is not int or old["revision"] < 1:
            raise ValueError("Invalid legacy revision")
    else:
        old = validate_state(old)
        if any(route["parent"] not in stages for route in old.get("branches", {}).values()):
            raise ValueError("Replan would remove a branch parent; retain that stage or reanchor the branch with branch --id ID --parent STAGE first")
        if (old["stages"] == stages and old["stage_statuses"] == statuses
                and "substages" not in old and "stage_labels" not in old
                and "stage_mainlines" not in old and "stage_details" not in old):
            return old
    state = validate_state({
        "task_id": old["task_id"], "stages": stages, "stage_statuses": statuses,
        "updated_at": now(), "revision": old["revision"] + 1,
    })
    if "mainline" in old:
        nonempty(old["mainline"], "mainline")
        state["mainline"] = old["mainline"]
    if "branches" in old:
        state["branches"] = old["branches"]
    preserve_todos(old, state)
    validate_state(state)
    if legacy:
        backup = Path(path).with_name(f"{Path(path).stem}.legacy-{uuid.uuid4().hex}.json")
        with backup.open("xb") as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
    with startup_lock(path, suffix=".write.lock"):
        if Path(path).read_bytes() != original:
            raise StateConflict("State changed; retry replan against the latest state")
        atomic_json(path, state)
    return state


def runtime_path(path):
    return Path(path).with_suffix(".runtime.json")


def make_server(state_path, port=0):
    state_path = absolute_path(state_path)
    initial = read_state(state_path)
    bound_task = initial["task_id"]
    cache = {"state": initial}
    cache_lock = threading.Lock()
    todo_token = secrets.token_urlsafe(32)
    card = Path(__file__).with_name("card.html")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def json_response(self, data, status=200):
            self.respond(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")

        def local_request(self):
            host = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            if (self.headers.get_all("Host") != [host]
                    or (origin is not None and origin != "http://" + host)):
                self.json_response({"error": "local origin required"}, 403)
                return False
            return True

        def do_GET(self):
            if not self.local_request():
                return
            route = urlsplit(self.path).path
            if route == "/health":
                self.json_response({"task_id": bound_task, "state_path": str(state_path)})
            elif route == "/state":
                with cache_lock:
                    error = None
                    try:
                        latest = read_state(state_path)
                        if latest["task_id"] != bound_task:
                            raise ValueError("Task identity changed; refusing to display another task")
                        cache["state"] = latest
                    except (OSError, ValueError, TypeError) as exc:
                        error = f"Read failed; showing last known state: {exc}"
                    self.json_response({"state": cache["state"], "error": error})
            elif route == "/todo-token":
                self.json_response({"token": todo_token})
            elif route == "/":
                try:
                    self.respond(200, card.read_bytes(), "text/html; charset=utf-8")
                except OSError:
                    self.json_response({"error": "card.html is not available"}, 503)
            else:
                self.json_response({"error": "not found"}, 404)

        def do_POST(self):
            if not self.local_request():
                return
            if self.command != "POST" or self.path != "/todo":
                self.json_response({"error": "read only"}, 405)
                return
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if (self.headers.get("Origin") != origin
                    or not secrets.compare_digest(self.headers.get("X-Mainline-Token", ""), todo_token)):
                self.json_response({"error": "local view token required"}, 403)
                return
            try:
                if (self.headers.get_content_type() != "application/json"
                        or self.headers.get("Transfer-Encoding") is not None
                        or len(self.headers.get_all("Content-Length", [])) != 1
                        or not 0 < int(self.headers["Content-Length"]) <= 8192):
                    raise ValueError("Expected a small JSON request")
                self.connection.settimeout(2)
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if (not isinstance(data, dict) or set(data) != {"stage", "parent", "branch", "id", "done", "revision"}
                        or type(data["done"]) is not bool or type(data["revision"]) is not int
                        or not isinstance(data["id"], str)):
                    raise ValueError("Only an existing todo can be checked or unchecked")
                result = todo_state(state_path, data["stage"], parent=data["parent"], branch=data["branch"],
                                    done=[data["id"]] if data["done"] else None,
                                    pending=None if data["done"] else [data["id"]],
                                    revision=data["revision"], task_id=bound_task)
                self.json_response({"state": result, "error": None})
            except StateConflict as exc:
                self.json_response({"error": str(exc)}, 409)
            except (ValueError, TypeError, KeyError) as exc:
                self.json_response({"error": str(exc)}, 400)
            except (OSError, RuntimeError):
                self.json_response({"error": "Could not save todo; refresh and retry"}, 503)

        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST

    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address = os.name != "nt"

        def server_bind(self):
            if os.name == "nt":
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            # The loopback address needs no reverse DNS, which can delay startup.
            TCPServer.server_bind(self)
            self.server_name, self.server_port = self.server_address

    server = LocalServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.task_id = bound_task
    server.state_path = state_path
    return server


def recorded_runtime(state_path):
    """Read only a local runtime record belonging to this exact state file."""
    try:
        runtime = json.loads(runtime_path(state_path).read_text(encoding="utf-8"))
        if runtime.get("state_path") != str(state_path):
            return None
        url = urlsplit(runtime["url"])
        if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
                or url.username or url.password or url.path not in ("", "/")
                or url.query or url.fragment):
            return None
        return runtime
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def resume_server(state_path, port=0):
    previous = recorded_runtime(state_path)
    preferred = port or (urlsplit(previous["url"]).port if previous else 0)
    try:
        return make_server(state_path, preferred)
    except OSError as exc:
        # A requested port remains strict; only an unavailable remembered port falls back.
        if port or not preferred or exc.errno not in (errno.EADDRINUSE, errno.EACCES, 10048, 10013):
            raise
        return make_server(state_path, 0)


def serve(state_path, port=0):
    state_path = absolute_path(state_path)
    server = resume_server(state_path, port)
    runtime = {"pid": os.getpid(), "url": f"http://127.0.0.1:{server.server_port}",
               "state_path": str(state_path)}
    atomic_json(runtime_path(state_path), runtime)
    print(json.dumps(runtime, ensure_ascii=False), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


def discover(state_path, task_id):
    try:
        runtime = recorded_runtime(state_path)
        if runtime is None:
            return None
        with LOCAL_HTTP.open(runtime["url"].rstrip("/") + "/health", timeout=0.3) as response:
            health = json.load(response)
        if health == {"task_id": task_id, "state_path": str(state_path)}:
            return runtime
    except (OSError, ValueError, KeyError, TypeError, URLError):
        pass
    return None


@contextmanager
def startup_lock(state_path, suffix=".start.lock"):
    # OS locks are released even if the launcher exits unexpectedly.
    with Path(state_path).with_suffix(suffix).open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + 6
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another Mainline launch is still in progress")
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def start(state_path, port=0):
    state_path = absolute_path(state_path)
    read_state(state_path)
    with startup_lock(state_path):
        return start_locked(state_path, port)


def start_locked(state_path, port=0):
    state_path = absolute_path(state_path)
    state = read_state(state_path)
    existing = discover(state_path, state["task_id"])
    if existing:
        return {**existing, "reused": True}
    log_path = state_path.with_suffix(".server.log")
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "serve", "--state",
             str(state_path), "--port", str(port)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=flags, close_fds=True, start_new_session=os.name != "nt",
        )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        runtime = discover(state_path, state["task_id"])
        if runtime and runtime.get("pid") == process.pid:
            return {**runtime, "reused": False}
        if process.poll() is not None:
            raise RuntimeError(f"Server failed to start; log: {log_path}")
        time.sleep(0.05)
    process.terminate()
    raise RuntimeError(f"Server did not become ready within 5 seconds; log: {log_path}")


def valid_session_id(identity):
    return isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", identity) is not None


def session_index(session_id):
    root = absolute_path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return root / "mainline" / "sessions" / (session_id + ".json")


def save_binding(destination, binding):
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Serialize the comparison and replacement: another launcher reading this
    # file can otherwise prevent os.replace on Windows.
    with startup_lock(destination, suffix=".write.lock"):
        try:
            if json.loads(destination.read_text(encoding="utf-8")) == binding:
                return
        except (OSError, ValueError):
            pass
        atomic_json(destination, binding)


def bind_session(state_path, session_id):
    if not valid_session_id(session_id):
        raise ValueError("Invalid session ID")
    state_path = absolute_path(state_path).resolve()
    state = read_state(state_path)
    store = next((parent for parent in state_path.parents if parent.name == ".mainline"),
                 state_path.parent / ".mainline")
    binding = {"state_path": str(state_path), "task_id": state["task_id"]}
    # Keep the workspace record for portability and a user index for changed cwd.
    for destination in (store / "sessions" / (session_id + ".json"), session_index(session_id)):
        save_binding(destination, binding)


def session_state(event):
    if not isinstance(event, dict) or (event.get("hook_event_name") != "SessionStart"
            or event.get("source") not in ("startup", "resume")
            or event.get("agent_id") or event.get("agent_type")):
        return None
    identity, cwd = event.get("session_id"), event.get("cwd")
    if not valid_session_id(identity) or not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return None
    cwd = Path(cwd).resolve()
    # Exact conversation IDs only. Never pick a project's newest/only state by guesswork.
    registered = session_index(identity)
    if registered.is_file():
        data = json.loads(registered.read_text(encoding="utf-8"))
        path = absolute_path(data["state_path"])
        return path if read_state(path)["task_id"] == data["task_id"] else None
    for workspace in (cwd, *cwd.parents):
        store = workspace / ".mainline"
        binding = store / "sessions" / (identity + ".json")
        if binding.is_file():
            data = json.loads(binding.read_text(encoding="utf-8"))
            path = absolute_path(data["state_path"]).resolve()
            if not path.is_relative_to(workspace) or read_state(path)["task_id"] != data["task_id"]:
                return None
            return path
        # Existing installations commonly use the thread ID as the state directory.
        path = store / identity / "state.json"
        if path.is_file():
            path = path.resolve()
            if not path.is_relative_to(workspace) or read_state(path)["task_id"] != identity:
                return None
            return path
    return None


def recover_session(event):
    state_path = session_state(event)
    if state_path is None:
        return None
    result = start(state_path)
    try:
        save_binding(session_index(event["session_id"]),
                     {"state_path": str(state_path), "task_id": read_state(state_path)["task_id"]})
    except OSError:
        pass  # A read-only index must not prevent an otherwise valid recovery.
    return {"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": (
            "Mainline auto-restore is enabled for this conversation. Its saved project is ready at "
            + result["url"]
            + ". At the next turn, check this conversation's existing browser tabs first. "
            "If this URL is already open (ignore trailing slash and language query), reuse that tab; "
            "do not open another by URL. Refresh the existing tab only after a UI update or when stale. "
            "If confirmed absent, use open_in_codex once in the bottom panel. "
            "If tab inventory is unavailable, keep the known view or show the URL instead of opening blindly. "
            "Only restore the view; do not read, summarize, or change project progress. "
            "Do not reopen on routine later turns or after an intentional close."
        ),
    }}


def install_recovery_hook(codex_home=None):
    """Register the installed plugin's recovery command in Codex's supported user hooks."""
    root = absolute_path(codex_home or os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    path = root / "hooks.json"
    raw = path.read_bytes() if path.exists() else None
    data = json.loads(raw.decode("utf-8-sig")) if raw is not None else {}
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise ValueError("Existing hooks.json must contain a hooks object")
    code = "import runpy;runpy.run_path(" + repr(str(Path(__file__).resolve())) + ",run_name='__main__')"
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    runner = ' -c "import base64;exec(base64.b64decode(\'' + encoded + '\'))" recover'
    handler = {"type": "command", "command": "python3" + runner,
               "commandWindows": "python" + runner, "timeout": 15,
               "statusMessage": "Restore Mainline", "additionalContextLimit": 300}
    group = {"matcher": "^(startup|resume)$", "hooks": [handler]}
    groups = data.setdefault("hooks", {}).setdefault("SessionStart", [])
    if not isinstance(groups, list) or any(not isinstance(value, dict) for value in groups):
        raise ValueError("Existing SessionStart hooks must be a list of groups")
    # Replace only our previous registration; keep every unrelated hook and its order.
    found = next((i for i, value in enumerate(groups)
                  if len(value.get("hooks", [])) == 1
                  and value["hooks"][0].get("statusMessage") == "Restore Mainline"
                  and "base64.b64decode" in value["hooks"][0].get("command", "")
                  and value["hooks"][0]["command"].endswith(' recover')), None)
    if found is not None and groups[found] == group:
        return {"hooks_file": str(path), "changed": False, "review": "Use /hooks to check trust"}
    if found is None:
        groups.append(group)
    else:
        groups[found] = group
    root.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        backup = path.with_name("hooks.mainline-backup-" + uuid.uuid4().hex[:8] + ".json")
        backup.write_bytes(raw)
    newline = "\r\n" if raw and b"\r\n" in raw else "\n"
    text = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").replace("\n", newline)
    payload = text.encode("utf-8-sig" if raw and raw.startswith(b"\xef\xbb\xbf") else "utf-8")
    temporary = path.with_name(".hooks-" + uuid.uuid4().hex + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return {"hooks_file": str(path), "changed": True, "review": "Trust Restore Mainline in /hooks"}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("recover", help="Handle a trusted SessionStart hook on stdin")
    commands.add_parser("install-hook", help="Register automatic recovery; user trust is still required").add_argument("--codex-home")
    for command in ("init", "position", "status", "subdivide", "finish", "describe", "replan", "read", "branch", "todo", "serve", "start"):
        sub = commands.add_parser(command)
        sub.add_argument("--state", required=True)
        if command in ("position", "status", "subdivide", "finish", "describe", "replan", "read", "todo"):
            sub.add_argument("--branch")
        if command == "todo":
            sub.add_argument("--stage", required=True)
            sub.add_argument("--parent")
            for action in ("add", "done", "pending"):
                sub.add_argument("--" + action, action="append")
            order = sub.add_mutually_exclusive_group()
            order.add_argument("--ordered", dest="ordered", action="store_true")
            order.add_argument("--unordered", dest="ordered", action="store_false")
            sub.set_defaults(ordered=None)
        if command == "read":
            sub.add_argument("--overview", action="store_true")
        if command == "branch":
            sub.add_argument("--id", required=True)
            sub.add_argument("--name")
            sub.add_argument("--parent")
            sub.add_argument("--mainline")
            sub.add_argument("--stage", action="append")
            sub.add_argument("--current", action="append")
            visibility = sub.add_mutually_exclusive_group()
            visibility.add_argument("--archive", action="store_true")
            visibility.add_argument("--restore", action="store_true")
        if command in ("serve", "start"):
            sub.add_argument("--port", type=int, default=0)
        if command == "start":
            sub.add_argument("--session-id", help="Bind this conversation to the saved project")
        if command == "init":
            sub.add_argument("--task-id", required=True)
        if command in ("init", "describe"):
            sub.add_argument("--mainline")
        if command == "describe":
            sub.add_argument("--stage")
            sub.add_argument("--parent")
            sub.add_argument("--details")
        if command in ("init", "replan", "subdivide"):
            sub.add_argument("--stage", action="append", required=True)
        if command in ("init", "position", "replan", "subdivide"):
            sub.add_argument("--current", action="append", required=command in ("position", "replan"))
        if command in ("status", "subdivide"):
            sub.add_argument("--parent", required=command == "subdivide")
        if command == "status":
            sub.add_argument("--label")
            for status in ("active", "done", "pending"):
                sub.add_argument("--" + status, action="append")
        if command in ("replan", "subdivide"):
            sub.add_argument("--reason", required=command == "replan")
    args = parser.parse_args()
    if args.command == "recover":
        try:
            result = recover_session(json.load(sys.stdin))
            if result is not None:
                print(json.dumps(result, ensure_ascii=False))
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            print("Mainline recovery skipped: " + str(exc), file=sys.stderr)
        return 0  # Recovery must not block a conversation or rewrite progress.
    try:
        if args.command == "install-hook":
            print(json.dumps(install_recovery_hook(args.codex_home), ensure_ascii=False))
            return 0
        path = absolute_path(args.state)
        if args.command == "init":
            result = init_state(path, args.task_id, args.stage, args.current, args.mainline)
        elif args.command == "position":
            result = position_state(path, args.current, branch=args.branch)
        elif args.command == "status":
            result = status_state(path, active=args.active, done=args.done, pending=args.pending,
                                  parent=args.parent, label=args.label, branch=args.branch)
        elif args.command == "subdivide":
            result = subdivide_state(path, args.parent, args.stage, args.current, args.reason, branch=args.branch)
        elif args.command == "finish":
            result = finish_state(path, branch=args.branch)
        elif args.command == "describe":
            result = describe_state(path, args.mainline, stage=args.stage, parent=args.parent, details=args.details, branch=args.branch)
        elif args.command == "todo":
            result = todo_state(path, args.stage, parent=args.parent, branch=args.branch,
                                add=args.add, done=args.done, pending=args.pending, ordered=args.ordered)
        elif args.command == "replan":
            result = replan_state(path, args.stage, args.current, args.reason, branch=args.branch)
        elif args.command == "branch":
            result = branch_state(path, args.id, name=args.name, parent=args.parent, mainline=args.mainline,
                                  stages=args.stage, current=args.current, archive=args.archive, restore=args.restore)
        elif args.command == "read":
            if args.overview and args.branch is not None:
                raise ValueError("Choose --overview or --branch, not both")
            result = read_state(path)
            if args.overview:
                result = overview_state(result)
        elif args.command == "serve":
            serve(path, args.port)
            return 0
        else:
            identity = args.session_id or os.environ.get("CODEX_THREAD_ID")
            if identity:
                bind_session(path, identity)
            result = start(path, args.port)
        branch = args.id if args.command == "branch" else getattr(args, "branch", None)
        if branch is not None:
            if branch not in result.get("branches", {}):
                raise ValueError(f"Unknown branch: {branch}")
            result = {"branch": branch, "revision": result["revision"], **result["branches"][branch]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
