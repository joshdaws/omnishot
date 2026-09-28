"""`omnishot doctor`: check that this machine can run OmniShot, and say how to fix what can't.

Checks are read-only. The clean-mirror load test is the one exception, and it
only runs with --load-test because it loads a plugin into the running compositor.
"""
import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import __version__, compat

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
REPO = Path(__file__).resolve().parent.parent
# Everything install.sh builds into native/ that the app loads or runs.
NATIVE_FILES = ("clean-capture.so", "clean-mirror.so", "drag-status.so", "recording-guard.so",
                "clipboard-helper", "scroll-helper", "window-helper", "live-selector")
# Commands the app runs, with the Omarchy package that provides each.
RUNTIME_COMMANDS = {"grim": "grim", "slurp": "slurp", "wl-copy": "wl-clipboard", "ffmpeg": "ffmpeg", "ffprobe": "ffmpeg",
                    "tesseract": "tesseract", "gpu-screen-recorder": "gpu-screen-recorder", "parec": "libpulse",
                    "notify-send": "libnotify"}
BINDINGS_MARKER = "-- OmniShot managed bindings"
RULES_REQUIRE = 'require("hypr.omnishot")'
MARKS = {OK: "✓", WARN: "!", FAIL: "✗", SKIP: "-"}


@dataclass
class Result:
    id: str
    status: str
    summary: str
    fix: str = ""


class System:
    """The machine, as the checks see it. Tests substitute their own."""
    def __init__(self, env=None, home=None, native=REPO / "native"):
        self.env = os.environ if env is None else env
        self.home = Path(home or Path.home())
        self.config = Path(self.env.get("XDG_CONFIG_HOME") or self.home / ".config")
        self.native = Path(native)
        self._hyprland = None
    def run(self, args, timeout=10):
        """Stdout of a successful command, or None."""
        try:result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):return None
        return result.stdout.strip() if result.returncode == 0 else None
    def which(self, name):return shutil.which(name)
    def hyprland(self):
        """`hyprctl -j version` of the running compositor, or None."""
        if self._hyprland is None:
            try:self._hyprland = json.loads(self.run(["hyprctl", "-j", "version"]) or "null") or {}
            except ValueError:self._hyprland = {}
        return self._hyprland or None
    def header_version_file(self):return compat.header_version_file()
    def shell_widget(self):
        from .shell_panel import available
        return available()


def installer(system):return f"bash {system.native.parent / 'install.sh'}"


def check_session(system):
    if not system.env.get("WAYLAND_DISPLAY") or not system.env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return Result("session", FAIL, "Not running inside a Hyprland session", "Run this in a terminal inside your Omarchy desktop session.")
    info = system.hyprland()
    if not info:return Result("session", FAIL, "hyprctl cannot reach the running compositor", "Run this in a terminal inside your Omarchy desktop session.")
    return Result("session", OK, f"Hyprland {info.get('version', '?')} session")


def check_config(system):
    needed = ("hypr/hyprland.lua", "hypr/bindings.lua", "omarchy/shell.json")
    missing = [name for name in needed if not (system.config / name).is_file()]
    if missing:return Result("config", FAIL, f"Missing Omarchy configuration: {', '.join(missing)}",
                             "OmniShot needs Omarchy with Lua Hyprland configuration and the shell plugin API.")
    return Result("config", OK, "Omarchy Lua configuration and shell settings found")


def check_versions(system):
    info = system.hyprland() or {}
    omarchy, hyprland = system.run(["omarchy", "version"]) or "", info.get("version", "")
    if not omarchy and not hyprland:return Result("versions", WARN, "Could not read the Omarchy or Hyprland version")
    found = compat.untested(omarchy, hyprland)
    if found:return Result("versions", WARN, f"Untested: {' and '.join(found)} (tested with {compat.tested_summary()})",
                           "Untested versions may work. Report problems with the output of: omnishot doctor --json")
    return Result("versions", OK, f"Omarchy {omarchy} with Hyprland {hyprland} (tested)")


def check_headers(system):
    path = system.header_version_file()
    if not path:return Result("headers", FAIL, "Hyprland development headers not found", "Install them with: omarchy pkg add hyprland")
    info = system.hyprland()
    if not info or not info.get("abiHash"):return Result("headers", WARN, "Headers found, but the running compositor's ABI is unknown")
    if compat.header_abi_hash(path) != info["abiHash"]:
        return Result("headers", FAIL, "Installed Hyprland headers do not match the running compositor",
                      f"Hyprland was updated after this session started. Restart your desktop session, then rebuild OmniShot: {installer(system)}")
    return Result("headers", OK, "Installed Hyprland headers match the running compositor")


def check_native(system):
    # exists() follows clean-mirror.so's symlink into .clean-mirrors/.
    missing = [name for name in NATIVE_FILES if not (system.native / name).exists()]
    if missing:return Result("native", FAIL, f"Native helpers not built: {', '.join(missing)}", f"Rebuild OmniShot: {installer(system)}")
    return Result("native", OK, f"Native helpers built in {system.native}")


def check_build_abi(system):
    stamp = system.native / "clean-mirror.abi"
    if not (system.native / "clean-mirror.so").exists():return Result("build-abi", WARN, "clean-mirror.so is not built, so its ABI was not checked")
    if not stamp.is_file():return Result("build-abi", WARN, "No record of which Hyprland clean-mirror.so was built for",
                                         f"Rebuild OmniShot to record it: {installer(system)}")
    info = system.hyprland()
    if not info or not info.get("abiHash"):return Result("build-abi", WARN, "The running compositor's ABI is unknown")
    if stamp.read_text().strip() != info["abiHash"]:
        return Result("build-abi", FAIL, "clean-mirror.so was built for a different Hyprland than the one running",
                      f"If you updated Hyprland, restart your desktop session first. Then rebuild OmniShot: {installer(system)}")
    return Result("build-abi", OK, "clean-mirror.so was built for the running Hyprland")


def check_commands(system):
    missing = [name for name in RUNTIME_COMMANDS if not system.which(name)]
    if missing:
        packages = " ".join(dict.fromkeys(RUNTIME_COMMANDS[name] for name in missing))
        return Result("commands", FAIL, f"Missing commands: {', '.join(missing)}", f"Install them with: omarchy pkg add {packages}")
    return Result("commands", OK, "Required commands are installed")


def check_launcher(system):
    launcher = system.home / ".local/bin/omnishot"
    if not launcher.is_file():return Result("launcher", FAIL, f"{launcher} is missing", f"Reinstall OmniShot: {installer(system)}")
    # install_user.py preloads this installation's drag-status.so.
    if str(system.native / "drag-status.so") not in launcher.read_text(errors="replace"):
        return Result("launcher", WARN, f"{launcher} starts a different OmniShot installation than {system.native.parent}",
                      "Expected if you ran doctor from a development checkout. Otherwise rerun the installer in the installation you use.")
    return Result("launcher", OK, f"{launcher} starts this installation")


def check_hyprland_config(system):
    missing = []
    bindings, hypr, rules = (system.config / "hypr" / name for name in ("bindings.lua", "hyprland.lua", "omnishot.lua"))
    if not bindings.is_file() or BINDINGS_MARKER not in bindings.read_text(errors="replace"):missing.append("keyboard shortcuts")
    if not rules.is_file() or not hypr.is_file() or RULES_REQUIRE not in hypr.read_text(errors="replace"):missing.append("window rules")
    if missing:return Result("hyprland-config", WARN, f"OmniShot {' and '.join(missing)} are not installed", f"Reinstall OmniShot: {installer(system)}")
    return Result("hyprland-config", OK, "Keyboard shortcuts and window rules are installed")


def check_shell(system):
    if not system.shell_widget():
        return Result("shell", WARN, "The OmniShot bar widget is not responding; OmniShot falls back to its tray icon",
                      "Check that it is listed by `omarchy plugin list`, or rerun the installer.")
    return Result("shell", OK, "The OmniShot bar widget responds")


def load_test(system):
    """Load clean-mirror.so, confirm it registered, and unload it again."""
    path = (system.native / "clean-mirror.so").resolve()
    if not path.is_file():return Result("load-test", FAIL, "clean-mirror.so is not built", f"Rebuild OmniShot: {installer(system)}")
    if not system.hyprland():return Result("load-test", FAIL, "hyprctl cannot reach the running compositor")
    probe = ["hyprctl", "repl", "return tostring(hl.plugin ~= nil and hl.plugin.omnishot ~= nil)"]
    if system.run(probe) == "true":return Result("load-test", OK, "clean-mirror.so is already loaded and registered")
    # `hyprctl plugin load` can exit 0 even when the plugin fails to start, so
    # the probe, not the exit code, decides.
    system.run(["hyprctl", "plugin", "load", str(path)])
    registered = system.run(probe) == "true"
    system.run(["hyprctl", "plugin", "unload", str(path)])
    if registered:return Result("load-test", OK, "clean-mirror.so loads into the running compositor and registers")
    return Result("load-test", FAIL, "Hyprland did not accept clean-mirror.so",
                  "Check `hyprctl plugin load` output and the Hyprland log. Without it, OmniShot cannot hide its own "
                  "windows from recordings. On aarch64, Hyprland cannot install the function hooks it needs.")


CHECKS = (check_session, check_config, check_versions, check_headers, check_native, check_build_abi,
          check_commands, check_launcher, check_hyprland_config, check_shell)


# These compare against or talk to the running compositor and shell.
NEEDS_SESSION = {check_headers: ("headers", "Hyprland header check"), check_build_abi: ("build-abi", "Build ABI check"),
                 check_shell: ("shell", "Bar widget check"), load_test: ("load-test", "Load test")}


def diagnose(system, load=False):
    checks = CHECKS + ((load_test,) if load else ())
    results = [check_session(system)]
    in_session = results[0].status == OK
    for check in checks[1:]:
        if not in_session and check in NEEDS_SESSION:
            name, label = NEEDS_SESSION[check]
            results.append(Result(name, SKIP, f"{label} skipped: needs the running compositor"))
        else:results.append(check(system))
    return results


def report(results):
    lines = []
    for result in results:
        lines.append(f"{MARKS[result.status]} {result.summary}")
        if result.fix and result.status != OK:lines.append(f"  → {result.fix}")
    failed = sum(r.status == FAIL for r in results);warned = sum(r.status == WARN for r in results)
    lines.append("")
    lines.append(f"{failed} problem{'s' * (failed != 1)}, {warned} warning{'s' * (warned != 1)}" if failed or warned else "Everything OmniShot needs looks good.")
    return "\n".join(lines)


def main(argv=None, system=None):
    parser = argparse.ArgumentParser(prog="omnishot doctor", description="Check that this machine can run OmniShot.")
    parser.add_argument("--json", action="store_true", help="print machine-readable results, e.g. for a bug report")
    parser.add_argument("--load-test", action="store_true", help="also load clean-mirror.so into the running compositor to confirm it works")
    args = parser.parse_args(argv)
    system = system or System()
    results = diagnose(system, load=args.load_test)
    if args.json:
        print(json.dumps({"omnishot": __version__, "hyprland": (system.hyprland() or {}).get("version"),
                          "results": [asdict(r) for r in results]}, indent=2))
    else:print(report(results))
    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":sys.exit(main())
