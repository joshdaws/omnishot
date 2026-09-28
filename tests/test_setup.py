"""setup.sh / uninstall.sh against a real git plugin checkout with stubbed desktop commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN_ID = 'io.github.joshdaws.omnishot'
# Stands in for install.sh: records where it ran and leaves ignored build outputs.
INSTALL = '''printf 'install ran in %s\\n' "$PWD" >>"$SETUP_LOG.install"
mkdir -p native .venv backups/stamp
printf built >native/helper.so
printf venv >.venv/marker
exit "${INSTALL_EXIT:-0}"
'''


@pytest.fixture
def plugin(tmp_path):
    if os.geteuid() == 0:
        pytest.skip('The scripts intentionally reject root')
    if not shutil.which('git') or not shutil.which('rsync'):
        pytest.skip('git and rsync are required')
    home = tmp_path / 'home'
    config, data = home / '.config', home / '.local/share'
    (config / 'hypr').mkdir(parents=True)
    (config / 'omarchy').mkdir()
    (config / 'hypr/hyprland.lua').write_text('-- mine\n')
    (config / 'hypr/bindings.lua').write_text('-- mine\n')
    (config / 'omarchy/shell.json').write_text('{"bar": {"layout": {"right": [{"id": "%s"}]}}}' % PLUGIN_ID)
    source = config / 'omarchy/plugins' / PLUGIN_ID
    (source / 'scripts').mkdir(parents=True)
    for name in ('setup.sh', 'uninstall.sh', 'runtime.sh', 'uninstall_user.py'):
        shutil.copy2(REPO / 'scripts' / name, source / 'scripts' / name)
    for name in ('manifest.json', '.gitignore'):
        shutil.copy2(REPO / name, source / name)
    (source / 'install.sh').write_text(INSTALL)
    (source / 'removed-later.txt').write_text('old')
    git = ['git', '-C', str(source), '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run(['git', 'init', '-q', str(source)], check=True)
    subprocess.run([*git, 'add', '-A'], check=True)
    subprocess.run([*git, 'commit', '-qm', 'one'], check=True)
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    log = tmp_path / 'commands.jsonl'
    stub = '''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ['SETUP_LOG'], 'a') as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == 'pgrep':
    sys.exit(0 if os.environ.get('APP_RUNNING') else 1)
if name == 'omarchy' and sys.argv[1:3] == ['plugin', 'remove']:
    shutil.rmtree(pathlib.Path(os.environ['XDG_CONFIG_HOME']) / 'omarchy/plugins' / sys.argv[3])
'''
    for name in ('omarchy', 'hyprctl', 'pgrep', 'setsid'):
        (bin_dir / name).write_text(stub)
        (bin_dir / name).chmod(0o755)
    env = {**os.environ, 'HOME': str(home), 'XDG_CONFIG_HOME': str(config), 'XDG_DATA_HOME': str(data),
           'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'], 'SETUP_LOG': str(log),
           'WAYLAND_DISPLAY': 'test', 'HYPRLAND_INSTANCE_SIGNATURE': 'test'}
    env.pop('OMNISHOT_INSTALL_DIR', None)

    def run(script, **changes):
        return subprocess.run(['bash', str(source / 'scripts' / script)], capture_output=True, text=True,
                              env={**env, **changes}, timeout=30, stdin=subprocess.DEVNULL)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def commit(message):
        subprocess.run([*git, 'add', '-A'], check=True)
        subprocess.run([*git, 'commit', '-qm', message], check=True)
        return subprocess.run([*git, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()

    head = subprocess.run([*git, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    runtime = data / 'omnishot-app'
    return type('Plugin', (), dict(source=source, runtime=runtime, config=config, data=data, head=head,
                                    run=staticmethod(run), calls=staticmethod(calls), commit=staticmethod(commit),
                                    install_log=Path(str(log) + '.install')))


def test_builds_a_copy_outside_the_plugin_checkout(plugin):
    result = plugin.run('setup.sh')
    assert result.returncode == 0, result.stderr
    assert plugin.install_log.read_text().strip() == f'install ran in {plugin.runtime}'
    assert (plugin.runtime / 'removed-later.txt').read_text() == 'old'
    assert not (plugin.runtime / '.git').exists()
    assert (plugin.runtime / '.omnishot-source').read_text().strip() == plugin.head
    # Build outputs stay out of the plugin folder the validator checks.
    assert not (plugin.source / 'native').exists() and not (plugin.source / '.venv').exists()
    assert any(c[:3] == ['omarchy', 'pkg', 'add'] for c in plugin.calls())


def test_update_mirrors_source_but_keeps_build_outputs(plugin):
    assert plugin.run('setup.sh').returncode == 0
    (plugin.source / 'removed-later.txt').unlink()
    (plugin.source / 'added.txt').write_text('new')
    head = plugin.commit('two')
    result = plugin.run('setup.sh')
    assert result.returncode == 0, result.stderr
    assert not (plugin.runtime / 'removed-later.txt').exists()
    assert (plugin.runtime / 'added.txt').read_text() == 'new'
    assert (plugin.runtime / 'native/helper.so').exists() and (plugin.runtime / '.venv/marker').exists()
    assert (plugin.runtime / 'backups/stamp').is_dir()
    assert (plugin.runtime / '.omnishot-source').read_text().strip() == head


def test_update_restarts_the_shell_only_when_the_widget_changed(plugin):
    restart = ['omarchy', 'restart', 'shell']
    assert plugin.run('setup.sh').returncode == 0
    assert restart not in plugin.calls()
    (plugin.source / 'added.txt').write_text('new')
    plugin.commit('app only')
    assert plugin.run('setup.sh').returncode == 0
    assert restart not in plugin.calls()
    (plugin.source / 'plugin').mkdir()
    (plugin.source / 'plugin/BarWidget.qml').write_text('Item {}')
    plugin.commit('widget')
    assert plugin.run('setup.sh').returncode == 0
    assert plugin.calls().count(restart) == 1


def test_failed_build_is_left_unstamped(plugin):
    result = plugin.run('setup.sh', INSTALL_EXIT='3')
    assert result.returncode != 0
    assert not (plugin.runtime / '.omnishot-source').exists()


def test_moves_a_pre_plugin_checkout_aside(plugin):
    (plugin.runtime / '.git').mkdir(parents=True)
    (plugin.runtime / 'backups').mkdir()
    (plugin.runtime / 'backups/old.lua').write_text('backup')
    result = plugin.run('setup.sh')
    assert result.returncode == 0, result.stderr
    moved = [p for p in plugin.data.iterdir() if p.name.startswith('omnishot-app.pre-plugin-')]
    assert len(moved) == 1 and (moved[0] / 'backups/old.lua').read_text() == 'backup'
    assert not (plugin.runtime / '.git').exists()


def test_refuses_an_unknown_folder_before_installing_packages(plugin):
    plugin.runtime.mkdir(parents=True)
    (plugin.runtime / 'mine.txt').write_text('keep')
    result = plugin.run('setup.sh')
    assert result.returncode != 0 and 'not created by OmniShot setup' in result.stderr
    assert (plugin.runtime / 'mine.txt').read_text() == 'keep'
    assert not any(c[0] == 'omarchy' for c in plugin.calls())


def test_refuses_while_the_app_will_not_quit(plugin):
    plugin.runtime.mkdir(parents=True)
    result = plugin.run('setup.sh', APP_RUNNING='1', OMNISHOT_SKIP_PACKAGES='1', OMNISHOT_QUIT_WAIT='0')
    assert result.returncode != 0 and 'still running' in result.stderr
    assert not plugin.install_log.exists()


def test_requires_a_plugin_checkout(plugin):
    shutil.rmtree(plugin.source / '.git')
    result = plugin.run('setup.sh')
    assert result.returncode != 0 and 'bash install.sh' in result.stderr


def test_uninstall_removes_app_files_and_plugin(plugin):
    assert plugin.run('setup.sh').returncode == 0
    captures = plugin.data / 'omnishot/captures'
    captures.mkdir(parents=True)
    (captures / 'shot.png').write_bytes(b'keep')
    result = plugin.run('uninstall.sh', OMNISHOT_ASSUME_YES='1')
    assert result.returncode == 0, result.stderr
    assert not plugin.runtime.exists()
    assert not plugin.source.exists()
    assert ['omarchy', 'plugin', 'remove', PLUGIN_ID, '--yes'] in plugin.calls()
    assert (captures / 'shot.png').read_bytes() == b'keep'
    assert json.loads((plugin.config / 'omarchy/shell.json').read_text())['bar']['layout']['right'] == []


def test_uninstall_needs_confirmation_and_keeps_development_checkouts(plugin):
    result = plugin.run('uninstall.sh')
    assert result.returncode != 0 and 'confirmation' in result.stderr
    (plugin.runtime / '.git').mkdir(parents=True)
    (plugin.runtime / '.omnishot-source').write_text('x')
    assert plugin.run('uninstall.sh', OMNISHOT_ASSUME_YES='1').returncode == 0
    assert (plugin.runtime / '.git').exists()
