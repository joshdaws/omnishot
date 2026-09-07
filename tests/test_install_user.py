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
                           install=lambda: runpy.run_path(str(repo / 'scripts/install_user.py')))


def test_reinstall_preserves_widget_placement_and_user_config(install_home):
    env = install_home
    env.install()
    first = {p: p.read_bytes() for p in env.config.rglob('*') if p.is_file()}
    env.install()
    assert all(p.read_bytes() == before for p, before in first.items())
    shell = json.loads((env.config / 'omarchy/shell.json').read_text())
    assert shell['bar']['layout']['left'] == [{'id': 'local.omnishot'}]
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
