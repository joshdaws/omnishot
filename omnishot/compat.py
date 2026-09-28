"""Versions OmniShot is tested with, and the Hyprland plugin ABI hash.

This is the single source for supported versions: README.md (kept in sync by a
test), install.sh and `omnishot doctor` all use it. It imports nothing outside
the standard library so install.sh can run it before the app is installed.
"""
import json
from pathlib import Path
import re
import subprocess
import sys

TESTED_OMARCHY = ("4.0.2",)
TESTED_HYPRLAND = ("0.56.2",)


def tested_summary():
    return f"Omarchy {' / '.join(TESTED_OMARCHY)} and Hyprland {' / '.join(TESTED_HYPRLAND)}"


def untested(omarchy, hyprland):
    """Names of the given versions that are not in the tested lists."""
    found = []
    # `omarchy version` reports the package version, e.g. 4.0.3rc4-1.
    if omarchy and omarchy.rsplit("-", 1)[0] not in TESTED_OMARCHY:found.append(f"Omarchy {omarchy}")
    if hyprland and hyprland not in TESTED_HYPRLAND:found.append(f"Hyprland {hyprland}")
    return found


def header_abi_hash(version_h):
    """The ABI hash a plugin built against these headers expects.

    Mirrors __hyprland_api_get_client_hash() in Hyprland's PluginAPI.hpp, so it
    can be compared with the running compositor's `hyprctl -j version` abiHash.
    """
    defines = dict(re.findall(r'^#define\s+(\w+)\s+"([^"]*)"', Path(version_h).read_text(), re.M))
    def strip_patch(version):return version.rsplit(".", 1)[0] if "." in version else version
    parts = (("aq", "AQUAMARINE_VERSION"), ("hu", "HYPRUTILS_VERSION"), ("hg", "HYPRGRAPHICS_VERSION"),
             ("hc", "HYPRCURSOR_VERSION"), ("hlg", "HYPRLANG_VERSION"))
    return defines["GIT_COMMIT_HASH"] + "".join(f"_{tag}_{strip_patch(defines[name])}" for tag, name in parts)


def header_version_file():
    """The version.h a plugin build would compile against, or None.

    Found through the same -I paths build-clean.sh compiles with. hyprland.pc
    sets only a prefix, not includedir, so asking for includedir is not enough.
    """
    try:flags = subprocess.run(["pkg-config", "--cflags-only-I", "hyprland"], capture_output=True, text=True, timeout=10).stdout.split()
    except (OSError, subprocess.SubprocessError):return None
    for flag in flags:
        include = Path(flag.removeprefix("-I"))
        for path in (include / "hyprland/src/version.h", include / "version.h" if include.match("hyprland/src") else None):
            if path and path.is_file():return path
    return None


def _output(args):
    try:result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["header-abi"]:
        path = header_version_file()
        if not path:print("Hyprland headers not found", file=sys.stderr);return 1
        print(header_abi_hash(path));return 0
    if argv == ["warn"]:
        # Untested versions may work: say so, but never block the caller.
        try:hyprland = json.loads(_output(["hyprctl", "-j", "version"]) or "{}").get("version", "")
        except ValueError:hyprland = ""
        found = untested(_output(["omarchy", "version"]), hyprland)
        if found:print(f"Warning: OmniShot is tested with {tested_summary()}; this is {' and '.join(found)}. "
                       "It may still work; report problems with the output of: omnishot doctor --json", file=sys.stderr)
        return 0
    print("usage: python -m omnishot.compat header-abi|warn", file=sys.stderr);return 2


if __name__ == "__main__":sys.exit(main())
