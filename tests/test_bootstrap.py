"""Run the curl entry point through stdin with isolated desktop/package commands."""
import json
import os
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/bootstrap.sh'


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
    stub = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ['BOOTSTRAP_LOG'], 'a') as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == os.environ.get('FAIL_COMMAND'):
    sys.exit(23)
if name == 'git':
    destination = pathlib.Path(sys.argv[-1])
    destination.mkdir()
    (destination / 'install.sh').write_text('printf "install ran\\\\n"\\nexit ' + os.environ.get('INSTALL_EXIT', '0') + '\\n')
'''
    for name in ('omarchy', 'omarchy-shell', 'hyprctl', 'git'):
        path = commands / name
        path.write_text(stub)
        path.chmod(0o755)
    env = {**os.environ, 'HOME': str(home), 'XDG_CONFIG_HOME': str(config),
           'PATH': str(commands) + os.pathsep + os.environ['PATH'],
           'WAYLAND_DISPLAY': 'test-wayland', 'HYPRLAND_INSTANCE_SIGNATURE': 'test-instance',
           'BOOTSTRAP_LOG': str(log)}
    env.pop('OMNISHOT_INSTALL_DIR', None)

    def run(**changes):
        return subprocess.run(['bash'], input=SCRIPT.read_text(), text=True,
                              capture_output=True, env={**env, **changes}, timeout=10)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    return home, run, calls


def test_fresh_install_from_pipe(bootstrap):
    home, run, calls = bootstrap
    result = run()
    assert result.returncode == 0, result.stderr
    assert 'install ran' in result.stdout
    assert 'OmniShot installed in' in result.stdout
    assert (home / 'projects/omnishot/install.sh').is_file()
    commands = calls()
    assert [c[0] for c in commands] == ['hyprctl', 'omarchy', 'git']
    assert commands[1][1:3] == ['pkg', 'add']
    assert 'tesseract-data-osd' in commands[1]
    assert commands[2] == ['git', 'clone', '--branch', 'main', '--single-branch', '--',
                           'https://github.com/joshdaws/omnishot.git', str(home / 'projects/omnishot')]


def test_existing_checkout_is_untouched(bootstrap):
    home, run, calls = bootstrap
    checkout = home / 'projects/omnishot'
    checkout.mkdir(parents=True)
    (checkout / 'work.txt').write_text('local work')
    result = run()
    assert result.returncode != 0
    assert 'Destination already exists' in result.stderr
    assert (checkout / 'work.txt').read_text() == 'local work'
    assert [c[0] for c in calls()] == ['hyprctl']


def test_rejects_missing_desktop_before_installing_packages(bootstrap):
    home, run, calls = bootstrap
    result = run(WAYLAND_DISPLAY='')
    assert result.returncode != 0
    assert 'desktop session' in result.stderr
    assert calls() == []
    assert not (home / 'projects').exists()


@pytest.mark.parametrize('failure', ['packages', 'clone', 'build'])
def test_failure_stops_install_and_never_reports_success(bootstrap, failure):
    home, run, calls = bootstrap
    changes = {'INSTALL_EXIT': '23'} if failure == 'build' else {'FAIL_COMMAND': 'omarchy' if failure == 'packages' else 'git'}
    result = run(**changes)
    assert result.returncode == 23
    assert 'OmniShot installation failed' in result.stderr
    assert 'OmniShot installed in' not in result.stdout
    if failure == 'packages':
        assert not any(c[0] == 'git' for c in calls())
    if failure != 'build':
        assert not (home / 'projects/omnishot').exists()
