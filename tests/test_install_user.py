"""Installer integration in an isolated home; no desktop services are changed."""
import json
from pathlib import Path
import runpy
import shutil
from types import SimpleNamespace

import pytest


@pytest.fixture
def install_home(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    source = tmp_path / 'checkout'
    for name in ('plugin', 'packaging'):
        shutil.copytree(repo / name, source / name)
    shutil.copy2(repo / 'manifest.json', source / 'manifest.json')
    home, config, data = (tmp_path / name for name in ('home', 'config', 'data'))
    home.mkdir()
    (config / 'hypr').mkdir(parents=True)
    (config / 'omarchy').mkdir()
    (config / 'hypr/hyprland.lua').write_text('-- existing window config\n')
    (config / 'hypr/bindings.lua').write_text('-- existing keybindings\n')
    (config / 'omarchy/shell.json').write_text(json.dumps({
        'idle': {'lock': 600},
        'bar': {'layout': {'left': [{'id': 'local.omnishot'}], 'right': [{'id': 'omarchy.clock'}]}}
    }))
    monkeypatch.setattr(Path, 'home', lambda: home)
    for key, value in dict(OMNISHOT_SOURCE=source, OMNISHOT_PYTHON=source / '.venv/bin/python',
                           XDG_CONFIG_HOME=config, XDG_DATA_HOME=data).items():
        monkeypatch.setenv(key, str(value))
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('subprocess.run', run)
    monkeypatch.setattr(shutil, 'which', lambda name: '/usr/bin/' + name)
    return SimpleNamespace(source=source, home=home, config=config, data=data, calls=calls,
                           install=lambda: runpy.run_path(str(repo / 'scripts/install_user.py')),
                           uninstall=lambda: runpy.run_path(str(repo / 'scripts/uninstall_user.py')))


PLUGIN_ID = 'io.github.joshdaws.omnishot'


def layout(env):
    return json.loads((env.config / 'omarchy/shell.json').read_text())['bar']['layout']


def test_reinstall_preserves_widget_placement_and_user_config(install_home):
    env = install_home
    env.install()
    first = {p: p.read_bytes() for p in env.config.rglob('*') if p.is_file()}
    env.install()
    assert all(p.read_bytes() == before for p, before in first.items())
    shell = json.loads((env.config / 'omarchy/shell.json').read_text())
    # The pre-plugin id is renamed in place, keeping the user's placement.
    assert shell['bar']['layout']['left'] == [{'id': PLUGIN_ID}]
    assert shell['bar']['layout']['right'] == [{'id': 'omarchy.clock'}]
    assert shell['idle']['lock'] == 600
    assert len(list((env.source / 'backups').iterdir())) == 2
    assert env.calls.count(['omarchy', 'restart', 'shell']) == 1


def test_installs_desktop_files_into_xdg_data_home(install_home):
    env = install_home
    env.install()
    desktop = env.data / 'applications/org.omarchy.OmniShot.desktop'
    assert desktop.is_file()
    assert (env.data / 'mime/packages/omnishot.xml').is_file()
    assert not (env.home / '.local/share').exists()
    launcher = (env.home / '.local/bin/omnishot').read_text()
    assert str(env.source / '.venv/bin/python') in launcher
    assert str(env.source / 'native/drag-status.so') in launcher
    assert ['update-desktop-database', str(env.data / 'applications')] in env.calls
    assert ['update-mime-database', str(env.data / 'mime')] in env.calls
    defaults = next(c for c in env.calls if c[0] == 'xdg-mime')
    assert defaults[3:] == ['application/x-omnishot', 'application/x-omnishot-video', 'x-scheme-handler/omnishot']


def test_bad_shell_config_does_not_partially_install(install_home):
    env = install_home
    (env.config / 'omarchy/shell.json').write_text('{broken')
    with pytest.raises(json.JSONDecodeError):
        env.install()
    assert not (env.home / '.local/bin/omnishot').exists()
    assert not env.data.exists()
    assert not (env.source / 'backups').exists()
    assert not env.calls


def test_manual_install_copies_widget_under_plugin_id(install_home):
    env = install_home
    env.install()
    plugin = env.config / 'omarchy/plugins' / PLUGIN_ID
    manifest = json.loads((plugin / 'manifest.json').read_text())
    assert manifest['id'] == PLUGIN_ID
    assert (plugin / manifest['entryPoints']['barWidget']).read_bytes() == (env.source / 'plugin/BarWidget.qml').read_bytes()


def test_migrates_legacy_widget_with_its_settings(install_home):
    env = install_home
    legacy = env.config / 'omarchy/plugins/local.omnishot'
    legacy.mkdir(parents=True)
    (legacy / 'BarWidget.qml').write_text('old widget')
    (legacy / 'manifest.json').write_text('{}')
    shell = env.config / 'omarchy/shell.json'
    shell.write_text(json.dumps({'bar': {'layout': {'left': [], 'right': [
        {'id': 'omarchy.clock'}, {'id': 'local.omnishot', 'custom': 1}]}}}))
    env.install()
    assert not legacy.exists()
    assert layout(env)['right'] == [{'id': 'omarchy.clock'}, {'id': PLUGIN_ID, 'custom': 1}]
    backup = next((env.source / 'backups').iterdir())
    assert (backup / 'local.omnishot-BarWidget.qml').read_text() == 'old widget'
    assert ['omarchy', 'restart', 'shell'] in env.calls


def test_migration_keeps_legacy_position_over_default_placement(install_home):
    # `omarchy plugin add --enable` places the new id before setup migrates.
    env = install_home
    shell = env.config / 'omarchy/shell.json'
    shell.write_text(json.dumps({'bar': {'layout': {'left': [], 'right': [
        {'id': 'local.omnishot', 'custom': 1}, {'id': 'omarchy.tray'}, {'id': PLUGIN_ID}]}}}))
    env.install()
    assert layout(env)['right'] == [{'id': PLUGIN_ID, 'custom': 1}, {'id': 'omarchy.tray'}]


def test_plugin_managed_checkout_is_never_written(install_home):
    env = install_home
    plugin = env.config / 'omarchy/plugins' / PLUGIN_ID
    (plugin / '.git').mkdir(parents=True)
    (plugin / 'manifest.json').write_text('from git')
    (env.config / 'omarchy/shell.json').write_text(json.dumps({'bar': {'layout': {'right': [{'id': 'local.omnishot'}]}}}))
    env.install()
    assert (plugin / 'manifest.json').read_text() == 'from git'
    assert not (plugin / 'plugin').exists()
    # `omarchy plugin add --enable` placed the widget; a stale legacy entry is dropped.
    assert layout(env)['right'] == [{'id': PLUGIN_ID}]
    (env.config / 'omarchy/shell.json').write_text(json.dumps({'bar': {'layout': {'right': []}}}))
    env.install()
    assert layout(env)['right'] == []


def test_uninstall_restores_configuration_and_keeps_captures(install_home):
    env = install_home
    tracked = {name: (env.config / name).read_text() for name in ('hypr/hyprland.lua', 'hypr/bindings.lua')}
    shell_before = json.loads((env.config / 'omarchy/shell.json').read_text())
    (env.config / 'mimeapps.list').write_text('[Default Applications]\nimage/png=viewer.desktop;\n')
    captures = env.data / 'omnishot/captures'
    captures.mkdir(parents=True)
    (captures / 'shot.png').write_bytes(b'capture')
    env.install()
    with (env.config / 'mimeapps.list').open('a') as f:
        f.write('application/x-omnishot=org.omarchy.OmniShot.desktop;\nimage/jpeg=org.omarchy.OmniShot.desktop;viewer.desktop;\n')
    managed = env.config / 'omarchy/plugins/other.plugin'
    (managed / '.git').mkdir(parents=True)
    env.uninstall()
    assert {name: (env.config / name).read_text() for name in tracked} == tracked
    shell_before['bar']['layout']['left'] = []
    assert json.loads((env.config / 'omarchy/shell.json').read_text()) == shell_before
    assert (env.config / 'mimeapps.list').read_text() == '[Default Applications]\nimage/png=viewer.desktop;\nimage/jpeg=viewer.desktop;\n'
    assert not (env.home / '.local/bin/omnishot').exists()
    assert not (env.data / 'applications/org.omarchy.OmniShot.desktop').exists()
    assert not (env.config / 'hypr/omnishot.lua').exists()
    assert not (env.config / 'omarchy/plugins' / PLUGIN_ID).exists()
    assert managed.exists()
    assert (captures / 'shot.png').read_bytes() == b'capture'
    backups = next((env.data / 'omnishot/config-backups').iterdir())
    assert (backups / 'config/hypr/bindings.lua').read_text() != tracked['hypr/bindings.lua']


def test_uninstall_leaves_plugin_checkout_and_foreign_launcher(install_home):
    env = install_home
    plugin = env.config / 'omarchy/plugins' / PLUGIN_ID
    (plugin / '.git').mkdir(parents=True)
    launcher = env.home / '.local/bin/omnishot'
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\necho something else\n')
    env.uninstall()
    assert plugin.exists()
    assert launcher.read_text() == '#!/bin/sh\necho something else\n'
