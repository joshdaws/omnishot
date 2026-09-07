"""Optional Omarchy panel bridge; standalone UI remains available without it."""
import json
import subprocess


def call(*args):
    try:
        result = subprocess.run(['omarchy-shell', *args], capture_output=True, text=True, timeout=4)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def available():
    try:
        state = json.loads(call('local.omnishot', 'state'))
        return isinstance(state, dict) and state.get('panelApi') == 1
    except (ValueError, TypeError):
        return False


def show():
    # The shell routes this to the widget on the focused monitor.
    return available() and call('shell', 'summon', 'local.omnishot') == 'ok'
