"""Install a plugin in an isolated Codex profile and test its cached runtime."""

import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import uuid
import zipfile

from build_plugin import ROOT, SOURCES, build
from test_package_runtime import check_runtime


def check(browser=False):
    archive = build()
    with zipfile.ZipFile(archive) as bundle:
        for name, source_file in SOURCES.items():
            assert bundle.read("skills/mainline/" + name) == source_file.read_bytes()
        manifest = json.loads(bundle.read("plugin.json"))
        assert manifest["extensions"]["com.openai"]["requires_local_executor"] is True
        assert len(manifest["extensions"]["com.openai"]["interface"]["shortDescription"]) <= 30
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Package verified. Install Codex CLI to run the installation check.")
    run = ROOT / ".test-runs" / ("plugin-" + uuid.uuid4().hex[:8])
    source, profile = run / "source", run / "codex-home"
    source.mkdir(parents=True)
    profile.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(source / "plugin")
    catalog = source / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / ".agents/plugins/marketplace.json", catalog)
    # CODEX_HOME configures only these child processes, never the user's profile.
    env = {**os.environ, "CODEX_HOME": str(profile)}
    for args in (["plugin", "marketplace", "add", str(source), "--json"],
                 ["plugin", "add", "mainline@mainline-tools", "--json"]):
        subprocess.run([codex, *args], cwd=source, env=env, check=True,
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    process = subprocess.Popen(
        [codex, "app-server"], cwd=source, env=env, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    received = queue.Queue()

    def receive():
        for line in process.stdout:
            received.put(json.loads(line))

    threading.Thread(target=receive, daemon=True).start()

    def send(value):
        process.stdin.write(json.dumps(value) + "\n")
        process.stdin.flush()

    def response(identity):
        while True:
            value = received.get(timeout=20)
            if value.get("id") == identity:
                assert "error" not in value, value
                return value["result"]

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "mainline-test", "version": "0.1.0"}}})
        response(1)
        send({"method": "initialized"})
        send({"id": 2, "method": "skills/list", "params": {
            "cwds": [str(source)], "forceReload": True}})
        data = response(2)
        found = [skill for entry in data["data"] for skill in entry["skills"]
                 if skill["name"] == "mainline:mainline"]
        assert len(found) == 1 and found[0]["enabled"], found
        installed = Path(found[0]["path"]).parent
        assert installed.resolve().is_relative_to((profile / "plugins/cache").resolve())
        assert not (profile / "skills/mainline").exists()
        assert not any(skill["name"] == "mainline"
                       for entry in data["data"] for skill in entry["skills"])
        for name, source_file in SOURCES.items():
            assert (installed / name).read_bytes() == source_file.read_bytes()
        runtime = check_runtime(installed, run)
        browsers = []
        if browser:
            browser_env = {**os.environ, "MAINLINE_SCRIPT": str(installed / "mainline.py"),
                           "MAINLINE_PYTHON": sys.executable}
            for suite in ("test_browser.cjs", "test_languages.cjs", "test_branches_browser.cjs"):
                result = subprocess.run(["node", str(ROOT / suite)], cwd=ROOT,
                                        env=browser_env, capture_output=True, text=True,
                                        encoding="utf-8", timeout=180)
                assert result.returncode == 0, result.stdout + result.stderr
                browsers.append({"suite": suite, "result": json.loads(result.stdout)})
        report = {"passed": True, "skill": found[0]["name"], "installed": str(installed),
                  "archive": str(archive), "fixture": str(run),
                  "runtime": runtime, "browser_suites": browsers}
        (run / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)
                                         + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true")
    check(browser=parser.parse_args().browser)
