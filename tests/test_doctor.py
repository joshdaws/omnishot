"""`omnishot doctor` against a fake machine: no compositor, commands or files are touched."""
import json
from pathlib import Path

import pytest
from omnishot import compat, doctor

ABI = 'efb50993780079460b0cbed1363e2166a2de1d9f_aq_0.15_hu_0.14_hg_0.5_hc_0.1_hlg_0.6'
VERSION_H = '''#pragma once
#define GIT_COMMIT_HASH    "efb50993780079460b0cbed1363e2166a2de1d9f"
#define GIT_TAG            "v0.56.2"
#define AQUAMARINE_VERSION "0.15.0"
#define AQUAMARINE_VERSION_MAJOR 0
#define HYPRLANG_VERSION     "0.6.8"
#define HYPRUTILS_VERSION    "0.14.1"
#define HYPRCURSOR_VERSION   "0.1.13"
#define HYPRGRAPHICS_VERSION "0.5.1"
'''
PROBE = ['hyprctl', 'repl', 'return tostring(hl.plugin ~= nil and hl.plugin.omnishot ~= nil)']


class Machine(doctor.System):
    """A healthy install; tests break one thing at a time."""
    def __init__(self, tmp_path):
        home = tmp_path / 'home'
        super().__init__(env={'WAYLAND_DISPLAY': 'wayland-1', 'HYPRLAND_INSTANCE_SIGNATURE': 'x'}, home=home,
                         native=tmp_path / 'app/native')
        self.native.mkdir(parents=True)
        for name in doctor.NATIVE_FILES:(self.native / name).write_text('built')
        (self.native / 'clean-mirror.abi').write_text(ABI + '\n')
        hypr = self.config / 'hypr'
        hypr.mkdir(parents=True)
        (hypr / 'bindings.lua').write_text('-- mine\n\n' + doctor.BINDINGS_MARKER + '\n')
        (hypr / 'hyprland.lua').write_text('-- mine\n' + doctor.RULES_REQUIRE + '\n')
        (hypr / 'omnishot.lua').write_text('-- rules\n')
        (self.config / 'omarchy').mkdir()
        (self.config / 'omarchy/shell.json').write_text('{}')
        launcher = home / '.local/bin/omnishot'
        launcher.parent.mkdir(parents=True)
        launcher.write_text(f'#!/bin/sh\nexport LD_PRELOAD={self.native / "drag-status.so"}\n')
        self.headers = tmp_path / 'version.h'
        self.headers.write_text(VERSION_H)
        self.info = {'version': '0.56.2', 'abiHash': ABI}
        self.omarchy = '4.0.2-1'
        self.missing = set()
        self.widget = True
        self.registered = False
        self.accepts_plugin = True
        self.calls = []
    def run(self, args, timeout=10):
        self.calls.append(list(args))
        if args == ['omarchy', 'version']:return self.omarchy
        if args == PROBE:return 'true' if self.registered else 'false'
        if args[:3] == ['hyprctl', 'plugin', 'load']:
            self.registered = self.accepts_plugin;return 'ok'
        if args[:3] == ['hyprctl', 'plugin', 'unload']:
            self.registered = False;return 'ok'
        return None
    def which(self, name):return None if name in self.missing else f'/usr/bin/{name}'
    def hyprland(self):return self.info
    def header_version_file(self):return self.headers if self.headers.exists() else None
    def shell_widget(self):return self.widget


def results(machine, load=False):return {r.id: r for r in doctor.diagnose(machine, load=load)}


def test_healthy_machine_passes_every_check(tmp_path, capsys):
    machine = Machine(tmp_path)
    assert {r.status for r in results(machine).values()} == {doctor.OK}
    assert doctor.main([], system=machine) == 0
    assert 'Everything OmniShot needs looks good.' in capsys.readouterr().out


def test_header_hash_mirrors_hyprland_plugin_api(tmp_path):
    (tmp_path / 'version.h').write_text(VERSION_H)
    assert compat.header_abi_hash(tmp_path / 'version.h') == ABI


def test_outside_a_session_fails_first(tmp_path):
    machine = Machine(tmp_path);machine.env = {}
    session = results(machine)['session']
    assert session.status == doctor.FAIL and 'Omarchy desktop session' in session.fix
    machine.env = {'WAYLAND_DISPLAY': 'w', 'HYPRLAND_INSTANCE_SIGNATURE': 'x'};machine.info = None
    assert results(machine)['session'].status == doctor.FAIL


def test_untested_versions_warn_without_failing(tmp_path, capsys):
    machine = Machine(tmp_path);machine.omarchy = '4.0.3rc4-1';machine.info = {'version': '0.57.0', 'abiHash': ABI}
    versions = results(machine)['versions']
    assert versions.status == doctor.WARN and 'Omarchy 4.0.3rc4-1 and Hyprland 0.57.0' in versions.summary
    assert doctor.main([], system=machine) == 0


def test_upgraded_hyprland_asks_for_a_session_restart(tmp_path):
    machine = Machine(tmp_path);machine.headers.write_text(VERSION_H.replace('0.15.0', '0.16.0'))
    headers = results(machine)['headers']
    assert headers.status == doctor.FAIL and 'Restart your desktop session' in headers.fix
    machine.headers.unlink()
    assert 'omarchy pkg add hyprland' in results(machine)['headers'].fix


def test_stale_or_unrecorded_build_abi(tmp_path):
    machine = Machine(tmp_path);(machine.native / 'clean-mirror.abi').write_text('older-hyprland\n')
    stale = results(machine)['build-abi']
    assert stale.status == doctor.FAIL and 'install.sh' in stale.fix
    (machine.native / 'clean-mirror.abi').unlink()
    assert results(machine)['build-abi'].status == doctor.WARN


def test_missing_helpers_and_commands_name_the_fix(tmp_path):
    machine = Machine(tmp_path);(machine.native / 'live-selector').unlink();machine.missing = {'ffmpeg', 'ffprobe', 'wl-copy'}
    found = results(machine)
    assert found['native'].status == doctor.FAIL and 'live-selector' in found['native'].summary
    assert found['commands'].fix == 'Install them with: omarchy pkg add wl-clipboard ffmpeg'


def test_launcher_and_desktop_integration(tmp_path):
    machine = Machine(tmp_path)
    launcher = machine.home / '.local/bin/omnishot'
    launcher.write_text('#!/bin/sh\nexport LD_PRELOAD=/elsewhere/native/drag-status.so\n')
    assert results(machine)['launcher'].status == doctor.WARN
    launcher.unlink()
    assert results(machine)['launcher'].status == doctor.FAIL
    (machine.config / 'hypr/bindings.lua').write_text('-- mine\n');(machine.config / 'hypr/omnishot.lua').unlink()
    config = results(machine)['hyprland-config']
    assert config.status == doctor.WARN and 'keyboard shortcuts and window rules' in config.summary
    machine.widget = False
    assert results(machine)['shell'].status == doctor.WARN


def test_load_test_only_runs_when_asked(tmp_path):
    machine = Machine(tmp_path)
    results(machine)
    assert not [c for c in machine.calls if c[:2] == ['hyprctl', 'plugin']]


def test_load_test_loads_probes_and_unloads(tmp_path):
    machine = Machine(tmp_path)
    assert results(machine, load=True)['load-test'].status == doctor.OK
    plugin = [c[2] for c in machine.calls if c[:2] == ['hyprctl', 'plugin']]
    assert plugin == ['load', 'unload'] and not machine.registered


def test_load_test_reports_a_rejected_plugin_and_still_unloads(tmp_path):
    # `hyprctl plugin load` exits 0 even when the plugin cannot install its hooks.
    machine = Machine(tmp_path);machine.accepts_plugin = False
    result = results(machine, load=True)['load-test']
    assert result.status == doctor.FAIL and 'aarch64' in result.fix
    assert ['unload'] == [c[2] for c in machine.calls if c[:3] == ['hyprctl', 'plugin', 'unload']]


def test_load_test_leaves_an_already_loaded_plugin_alone(tmp_path):
    machine = Machine(tmp_path);machine.registered = True
    assert results(machine, load=True)['load-test'].status == doctor.OK
    assert not [c for c in machine.calls if c[:2] == ['hyprctl', 'plugin']] and machine.registered


def test_json_output_and_failure_exit_code(tmp_path, capsys):
    machine = Machine(tmp_path);machine.missing = {'grim'}
    assert doctor.main(['--json'], system=machine) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['hyprland'] == '0.56.2'
    assert {r['id']: r['status'] for r in report['results']}['commands'] == 'fail'


def test_app_routes_doctor_before_starting_qt(monkeypatch):
    from omnishot import app
    seen = []
    monkeypatch.setattr(doctor, 'main', lambda argv: seen.append(argv) or 7)
    monkeypatch.setattr(app, 'QApplication', lambda *a: pytest.fail('doctor must not start Qt'))
    assert app.main(['doctor', '--json']) == 7 and seen == [['--json']]


def test_untested_helper_strips_the_package_release():
    assert compat.untested('4.0.2-1', '0.56.2') == []
    assert compat.untested('4.0.3rc4-1', '') == ['Omarchy 4.0.3rc4-1']


def test_supported_versions_have_one_source():
    repo = Path(__file__).resolve().parents[1]
    readme = repo / 'README.md'
    stated = next(line for line in readme.read_text().splitlines() if line.startswith('Developed and tested on'))
    for version in (*compat.TESTED_OMARCHY, *compat.TESTED_HYPRLAND):
        assert version in stated, f'README.md does not list tested version {version}; update it to match omnishot/compat.py'
    assert '-m omnishot.compat warn' in (repo / 'install.sh').read_text()
    assert 'omnishot.compat header-abi' in (repo / 'native/build-clean.sh').read_text()


def test_compositor_checks_are_skipped_outside_a_session(tmp_path, capsys):
    machine = Machine(tmp_path);machine.env = {};machine.widget = False
    found = results(machine, load=True)
    assert {name for name, r in found.items() if r.status == doctor.SKIP} == {'headers', 'build-abi', 'shell', 'load-test'}
    assert not [c for c in machine.calls if c[:2] == ['hyprctl', 'plugin']]
    doctor.main([], system=machine)
    assert '1 problem, 0 warnings' in capsys.readouterr().out


def test_headers_are_found_through_the_compiler_include_paths(tmp_path, monkeypatch):
    # hyprland.pc sets only prefix=, so the -I flags are what a build sees.
    (tmp_path / 'hyprland/src').mkdir(parents=True)
    (tmp_path / 'hyprland/src/version.h').write_text(VERSION_H)
    flags = f'-I{tmp_path} -I{tmp_path}/hyprland/protocols -I{tmp_path}/hyprland -I{tmp_path}/hyprland/src -I/usr/include/pixman-1\n'
    monkeypatch.setattr(compat.subprocess, 'run', lambda *a, **k: type('R', (), {'stdout': flags})())
    assert compat.header_version_file() == tmp_path / 'hyprland/src/version.h'
    monkeypatch.setattr(compat.subprocess, 'run', lambda *a, **k: type('R', (), {'stdout': ''})())
    assert compat.header_version_file() is None
