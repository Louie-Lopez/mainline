"""Build the public demo with the real card renderer and fictional project data."""

from pathlib import Path
from build_branches import build as build_branches

ROOT = Path(__file__).resolve().parent


def build():
    card = (ROOT / "card.html").read_text(encoding="utf-8")
    style = card.split("<style>", 1)[1].split("</style>", 1)[0]
    view = card.split("<main>", 1)[1].split("</main>", 1)[0]
    # The static demo keeps rendering and interaction, without the local server poller.
    renderer = card.split("<script>", 1)[1].split("let refreshTimer=", 1)[0]
    driver = (ROOT / "demo/demo.js").read_text(encoding="utf-8")
    shell = (ROOT / "demo/shell.html").read_text(encoding="utf-8")
    for marker, value in (("STYLE", style), ("VIEW", view), ("SCRIPT", renderer + driver)):
        shell = shell.replace("{{" + marker + "}}", value)
    assert "{{" not in shell and "fetch(" not in shell
    output = ROOT / "docs/index.html"
    output.write_bytes(shell.encode("utf-8"))
    (ROOT / "docs/.nojekyll").write_bytes(b"")
    return output


if __name__ == "__main__":
    print(build())
    print(build_branches())
