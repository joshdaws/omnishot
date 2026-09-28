"""The repository root is the Omarchy plugin `omarchy plugin add` clones."""
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from omnishot.shell_panel import PLUGIN_ID

REPO = Path(__file__).resolve().parents[1]


def test_manifest_matches_the_shell_schema_and_ids():
    manifest = json.loads((REPO / 'manifest.json').read_text())
    assert manifest['schemaVersion'] == 1
    assert manifest['id'] == PLUGIN_ID
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', PLUGIN_ID) and not PLUGIN_ID.startswith('omarchy.')
    assert manifest['kinds'] == ['bar-widget']
    entry = manifest['entryPoints']['barWidget']
    assert not entry.startswith('/') and '..' not in entry and (REPO / entry).is_file()
    widget = (REPO / entry).read_text()
    assert f'moduleName: "{PLUGIN_ID}"' in widget and f'ipcTarget: "{PLUGIN_ID}"' in widget


def test_repository_tracks_no_symlinks():
    # `omarchy plugin validate` rejects any symlink in the plugin folder.
    tracked = subprocess.run(['git', '-C', str(REPO), 'ls-files', '-s'], capture_output=True, text=True, check=True).stdout
    assert not [line for line in tracked.splitlines() if line.startswith('120000')]


def test_widget_qml_parses():
    # Unit tests never load the widget; the shell drops it on a syntax error.
    lint = Path(sys.executable).with_name('pyside6-qmllint')
    if not lint.exists():
        pytest.skip('pyside6-qmllint is not installed')
    widget = REPO / json.loads((REPO / 'manifest.json').read_text())['entryPoints']['barWidget']
    result = subprocess.run([str(lint), str(widget)], capture_output=True, text=True)
    assert '[syntax]' not in result.stdout + result.stderr, result.stdout + result.stderr
