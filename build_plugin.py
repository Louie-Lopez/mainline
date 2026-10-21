"""Package the single source skill as a portable plugin. No third-party modules."""

import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
SOURCES = {
    "SKILL.md": ROOT / "packaging/mainline-skill.md",
    "mainline.py": ROOT / "mainline.py",
    "card.html": ROOT / "card.html",
}


def build():
    compatibility = json.loads((ROOT / "packaging/plugin.json").read_text(encoding="utf-8"))
    portable = {key: compatibility[key] for key in
                ("name", "version", "description", "author", "homepage", "repository", "license")}
    portable["$schema"] = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    portable["extensions"] = {"com.openai": {
        "requires_local_executor": True,
        "interface": compatibility["interface"],
    }}
    compatibility["skills"] = "./skills/"
    files = {
        "plugin.json": (json.dumps(portable, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        ".codex-plugin/plugin.json": (json.dumps(compatibility, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }
    for name, source in SOURCES.items():
        files["skills/mainline/" + name] = source.read_bytes()
    files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    # Installers discover only the generated skill; development instructions use another filename.
    package = ROOT / "plugin"
    for name, data in files.items():
        destination = package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    output = ROOT / "dist" / ("mainline-" + portable["version"] + ".zip")
    output.parent.mkdir(exist_ok=True)
    # Stable member ordering and timestamps make rebuilding the same source reproducible.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(files)
        for name, source in SOURCES.items():
            assert archive.read("skills/mainline/" + name) == source.read_bytes()
    return output


if __name__ == "__main__":
    print(build())
