"""Build the standalone branch experiment using the existing card renderer."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build():
    source = (ROOT / 'card.html').read_text(encoding='utf-8')
    # This experiment keeps the light appearance used in its original preview.
    source = re.sub(r'@media\(prefers-color-scheme:dark\)\{[^\n]+\}', '', source)
    source = source.replace('color-scheme:light dark', 'color-scheme:light')
    source = source.replace('content="light dark"', 'content="light"')
    source = source.replace('<title></title>', '<title>Mainline — branch demo</title>')
    source = source.replace('</style>', (ROOT / 'demo/branches.css').read_text(encoding='utf-8') + '\n</style>')
    source = source[:source.index('let refreshTimer=')]
    data = json.loads((ROOT / 'demo/branches-data.json').read_text(encoding='utf-8'))
    fixture = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    source += '\nconst branchSamples=' + fixture + ';\n'
    source += (ROOT / 'demo/branches.js').read_text(encoding='utf-8')
    source += '\n</script>\n</body>\n</html>\n'
    assert 'fetch(' not in source
    output = ROOT / 'docs/branches.html'
    output.write_bytes(source.encode('utf-8'))
    return output


if __name__ == '__main__':
    print(build())
