"""Run the curl entry point through stdin with isolated desktop/package commands."""
import json
import os
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/bootstrap.sh'
PLUGIN_ID = 'io.github.joshdaws.omnishot'


@pytest.fixture
def bootstrap(tmp_path):
    if os.geteuid() == 0:
        pytest.skip('The installer intentionally rejects root')
    home = tmp_path / 'home with spaces'
    config = home / '.config'
    (config / 'hypr').mkdir(parents=True)
    (config / 'omarchy').mkdir()
    for name in ('hypr/hyprland.lua', 'hypr/bindings.lua', 'omarchy/shell.json'):
        (config / name).write_text('{}')
    commands = tmp_path / 'bin'
    commands.mkdir()
    log = tmp_path / 'commands.jsonl'
    # `omarchy plugin add` clones into the plugins folder; its setup.sh stub
    # records that it ran and exits with SETUP_EXIT.
    stub = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ['BOOTSTRAP_LOG'], 'a') as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == os.environ.get('FAIL_COMMAND'):
    sys.exit(23)
if name == 'omarchy' and sys.argv[1:3] == ['plugin', 'add']:
    plugin = pathlib.Path(os.environ['XDG_CONFIG_HOME']) / 'omarchy/plugins' / os.environ['PLUGIN_ID']
    (plugin / '.git').mkdir(parents=True)
    (plugin / 'scripts').mkdir()
    (plugin / 'scripts/setup.sh').write_text('printf "setup ran\\\\n"\\nexit ' + os.environ.get('SETUP_EXIT', '0') + '\\n')
'''
    for name in ('omarchy', 'omarchy-shell', 'hyprctl'):
        path = commands / name
        path.write_text(stub)
        path.chmod(0o755)
    env = {**os.environ, 'HOME': str(home), 'XDG_CONFIG_HOME': str(config),
           'PATH': str(commands) + os.pathsep + os.environ['PATH'],
           'WAYLAND_DISPLAY': 'test-wayland', 'HYPRLAND_INSTANCE_SIGNATURE': 'test-instance',
           'BOOTSTRAP_LOG': str(log), 'PLUGIN_ID': PLUGIN_ID}
    for key in ('OMNISHOT_INSTALL_DIR', 'OMNISHOT_REPOSITORY', 'XDG_DATA_HOME'):
        env.pop(key, None)

    def run(**changes):
        return subprocess.run(['bash'], input=SCRIPT.read_text(), text=True,
                              capture_output=True, env={**env, **changes}, timeout=10)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    return home, run, calls


def test_fresh_install_adds_plugin_then_runs_setup(bootstrap):
    home, run, calls = bootstrap
    result = run()
    assert result.returncode == 0, result.stderr
    assert 'setup ran' in result.stdout
    assert [c[0] for c in calls()] == ['hyprctl', 'omarchy']
    assert calls()[1] == ['omarchy', 'plugin', 'add', 'https://github.com/joshdaws/omnishot.git', '--enable', '--yes']
    assert (home / '.config/omarchy/plugins' / PLUGIN_ID / '.git').is_dir()


def test_existing_plugin_is_rebuilt_not_re_added(bootstrap):
    home, run, calls = bootstrap
    assert run().returncode == 0
    before = len(calls())
    result = run()
    assert result.returncode == 0, result.stderr
    assert 'already added' in result.stdout and 'setup ran' in result.stdout
    assert not any(c[:3] == ['omarchy', 'plugin', 'add'] for c in calls()[before:])


def test_manual_widget_copy_is_untouched(bootstrap):
    home, run, calls = bootstrap
    plugin = home / '.config/omarchy/plugins' / PLUGIN_ID
    plugin.mkdir(parents=True)
    (plugin / 'manifest.json').write_text('manual copy')
    result = run()
    assert result.returncode != 0
    assert 'manually installed' in result.stderr
    assert (plugin / 'manifest.json').read_text() == 'manual copy'
    assert [c[0] for c in calls()] == ['hyprctl']


def test_rejects_missing_desktop_before_changing_anything(bootstrap):
    home, run, calls = bootstrap
    result = run(WAYLAND_DISPLAY='')
    assert result.returncode != 0
    assert 'desktop session' in result.stderr
    assert calls() == []
    assert not (home / '.config/omarchy/plugins').exists()


@pytest.mark.parametrize('failure', ['add', 'setup'])
def test_failure_stops_install(bootstrap, failure):
    home, run, calls = bootstrap
    result = run(**({'FAIL_COMMAND': 'omarchy'} if failure == 'add' else {'SETUP_EXIT': '23'}))
    assert result.returncode == 23
    assert 'OmniShot installation failed' in result.stderr
    assert ('setup ran' in result.stdout) == (failure == 'setup')


def test_custom_repository(bootstrap):
    home, run, calls = bootstrap
    result = run(OMNISHOT_REPOSITORY='https://example.test/fork.git')
    assert result.returncode == 0, result.stderr
    assert calls()[1][3] == 'https://example.test/fork.git'
