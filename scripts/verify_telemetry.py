"""Exercise opt-in cursor/click/shortcut recording against our own test window."""
import json
import sys
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication,QTextEdit
from PySide6.QtCore import QTimer
from omnishot import backend
from omnishot.widgets import place_window
from omnishot.studio import Telemetry

out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot")
window=QTextEdit();window.setWindowTitle("OmniShot Input Verification");window.setPlainText("OmniShot synthetic input test");window.resize(600,300);window.show()
def wait(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.processEvents();time.sleep(.02)
wait(.3);place_window(window,100,100);wait(.4)
client=next(c for c in backend.hypr("clients") if c["title"]==window.windowTitle())
x,y=client["at"];backend.move_cursor(x+120,y+100)
backend.run([str(Path(__file__).resolve().parents[1]/"native/scroll-helper"),"click","272"]);wait(.25)
assert backend.hypr("activewindow").get("title")==window.windowTitle(),"Test window must own keyboard focus"
trace=Telemetry((x,y,600,300),keys=True,clicks=True,commands_only=True)
try:
    trace.start();wait(.2)
    backend.run([str(Path(__file__).resolve().parents[1]/"native/scroll-helper"),"click","272"])
    backend.run([sys.argv[2]]);wait(.3)
    backend.move_cursor(x+350,y+180);wait(.15)
finally:metadata=trace.stop()
assert not metadata["telemetry_error"],metadata["telemetry_error"]
assert len(metadata["cursor"])>=3
assert any(e["kind"]=="click" for e in metadata["events"]),metadata
assert any(e.get("label")=="Ctrl+A" for e in metadata["events"]),metadata
removed=backend.run(["hyprctl","repl","return omnishot_capture == nil"]).decode().strip()
assert removed=="true",removed
report={"cursor_samples":len(metadata["cursor"]),"clicks":sum(e["kind"]=="click" for e in metadata["events"]),"shortcuts":[e["label"] for e in metadata["events"] if e["kind"]=="key"],"subscriptions_removed":True}
(out/"telemetry-report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));window.close()
