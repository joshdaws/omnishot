"""Optional Omarchy panel bridge; standalone UI remains available without it."""
import json
import subprocess

# Must match manifest.json and the widget's ipcTarget.
PLUGIN_ID = 'io.github.joshdaws.omnishot'


def call(*args):
    try:
        result = subprocess.run(['omarchy-shell', *args], capture_output=True, text=True, timeout=4)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def available():
    try:
        state = json.loads(call(PLUGIN_ID, 'state'))
        return isinstance(state, dict) and state.get('panelApi') == 1
    except (ValueError, TypeError):
        return False


def show():
    # The shell routes this to the widget on the focused monitor.
    return available() and call('shell', 'summon', PLUGIN_ID) == 'ok'
