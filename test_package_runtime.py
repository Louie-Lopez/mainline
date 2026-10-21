"""Exercise the packaged runtime, including the detached launcher, on any OS."""

import argparse
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
from urllib.request import build_opener, ProxyHandler
import uuid
import zipfile

from build_plugin import ROOT, build


def check_runtime(skill_dir, run):
    script = (Path(skill_dir) / "mainline.py").resolve()
    state = (run / "project with spaces 中文" / "state.json").resolve()
    http = build_opener(ProxyHandler({}))
    task_id = "packaged-runtime-" + uuid.uuid4().hex

    def cli(*args):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(script), *args, "--state", str(state)],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def get(route):
        with http.open(first["url"] + route, timeout=2) as response:
            return response.read()

    names = ["Define", "Build", "Validate", "Deliver"]
    cli("init", "--task-id", task_id, "--mainline", "Keep the complete project visible.",
        *[part for name in names for part in ("--stage", name)])
    cli("status", "--done", "Define", "--active", "Build", "--active", "Validate")
    cli("subdivide", "--parent", "Build", "--stage", "State", "--stage", "View",
        "--current", "State", "--current", "View")
    cli("status", "--parent", "Build", "--active", "View", "--label", "修复错误")
    cli("describe", "--parent", "Build", "--stage", "View",
        "--mainline", "Make the current stage clear.", "--details", "Show parallel work.")
    first = cli("start")  # The launcher exits; its detached server must survive.
    health = {"task_id": task_id, "state_path": str(state)}
    try:
        assert first["reused"] is False
        assert json.loads(get("/health")) == health
        for query in ("", "?lang=en", "?lang=zh"):
            assert get("/" + query) == script.with_name("card.html").read_bytes()
        second = cli("start")
        assert second["reused"] is True and second["pid"] == first["pid"]
        saved = cli("read")
        assert saved["stages"] == names
        assert saved["stage_statuses"] == ["done", "active", "active", "pending"]
        assert json.loads(get("/state")) == {"state": saved, "error": None}
        updated = cli("status", "--parent", "Build", "--done", "State", "--done", "View")
        assert updated["stage_statuses"] == ["done", "done", "active", "pending"]
        assert json.loads(get("/state"))["state"] == updated
        cli("status", "--done", "Validate", "--active", "Deliver")
        finished = cli("finish")
        assert finished["stage_statuses"] == ["done"] * len(names)
        assert json.loads(get("/state"))["state"] == finished
        report = {
            "passed": True, "os": platform.system(), "python": platform.python_version(),
            "script": str(script), "state": str(state),
            "checks": ["packaged CLI", "Unicode and space paths", "detached start",
                       "verified server reuse", "packaged HTML in both languages",
                       "parallel stages", "substage labels and goals", "live HTTP updates",
                       "completion preserves lifecycle"],
        }
        (run / "runtime-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        # Stop only the new test server, after checking its task and state identity.
        try:
            recorded = json.loads(state.with_suffix(".runtime.json").read_text(encoding="utf-8"))
            if recorded["pid"] == first["pid"] and json.loads(get("/health")) == health:
                os.kill(first["pid"], signal.SIGTERM)
        except OSError:
            pass  # A server that already exited needs no cleanup.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", type=Path)
    args = parser.parse_args()
    run = ROOT / ".test-runs" / ("package-runtime-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    skill = args.skill_dir
    if skill is None:
        with zipfile.ZipFile(build()) as archive:
            archive.extractall(run / "package")
        skill = run / "package/skills/mainline"
    print(json.dumps(check_runtime(skill, run), ensure_ascii=False, indent=2))
