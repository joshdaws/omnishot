"""The app keeps its fallback UI when the shell widget cannot open."""
import subprocess
from types import SimpleNamespace

import pytest
from omnishot import shell_panel


@pytest.mark.parametrize('output,expected', [
    ('{"panelApi":1}', True),
    ('{"recording":false}', False),
    ('{"panelApi":2}', False),
    ('[]', False),
    ('Target not found.', False),
    ('', False),
])
def test_detects_only_compatible_live_panel(monkeypatch, output, expected):
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=output))
    assert shell_panel.available() is expected


@pytest.mark.parametrize('failure', [FileNotFoundError(), subprocess.TimeoutExpired('omarchy-shell', 4)])
def test_missing_or_unresponsive_shell_keeps_fallback(monkeypatch, failure):
    def run(*args, **kwargs):
        raise failure
    monkeypatch.setattr(subprocess, 'run', run)
    assert not shell_panel.show()


@pytest.mark.parametrize('reply,expected', [('ok', True), ('unknown', False)])
def test_summons_through_focused_monitor_router(monkeypatch, reply, expected):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"panelApi":1}' if command[-1] == 'state' else reply)
    monkeypatch.setattr(subprocess, 'run', run)
    assert shell_panel.show() is expected
    assert calls[-1] == ['omarchy-shell', 'shell', 'summon', 'local.omnishot']


def test_failed_ipc_is_not_treated_as_success(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout='{"panelApi":1}'))
    assert not shell_panel.available()
