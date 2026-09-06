"""Native Wayland annotation gestures, expansion and editable project reopening."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.editor import Editor

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready"
def command(value):fixture.stdin.write(value+"\n");fixture.stdin.flush()
store=backend.Store(out/"data");store.settings.update(inverse_arrows=True,smooth_drawing=False,annotation_shadow=True,auto_expand_canvas=True)
path=store.add(image=np.full((140,240,3),255,np.uint8));editor=Editor(path,store);editor.show();QTest.qWait(350);editor.view.scale(.5,.5);editor.set_tool("arrow")
def draw(a,b,alt=False):
    client=next(c for c in backend.hypr("clients") if c["title"]==editor.windowTitle())
    start=editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(*a)));end=editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(*b)))
    backend.move_cursor(client["at"][0]+start.x(),client["at"][1]+start.y());QTest.qWait(80)
    command("mods 8" if alt else "mods 0");QTest.qWait(60);command("button 272 1");QTest.qWait(70)
    command(f"move {end.x()-start.x()} {end.y()-start.y()}");QTest.qWait(120);command("button 272 0");QTest.qWait(200);command("mods 0")
try:
    draw((40,40),(180,80));assert len(editor.objects)==1 and editor.objects[0].props["ax"]==1
    draw((100,100),(300,190),True);assert len(editor.objects)==2 and editor.objects[1].props["ax"]==0
    assert editor.base.width()>300 and editor.base.height()>190 and editor.objects[1].graphicsEffect()
    expected=editor.render();expected.save(str(out/"expanded.png"));editor.grab().save(str(out/"expanded-editor.png"))
    project=out/"expanded.omnishot";editor.write_project(project);editor.undo();assert len(editor.objects)==1 and editor.base.width()==240
    editor.redo();assert editor.render()==expected;editor.close()
    other=Editor(project,store);other.show();QTest.qWait(150);assert other.expand_canvas and other.render()==expected
    report=dict(display_scale=backend.capture_monitors()[0]["scale"],wayland_arrow_drawing=True,inverse_default=True,alt_override=True,annotation_shadows=True,expanded_pixels=[expected.width(),expected.height()],undo_redo=True,editable_project_reopened=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command("button 272 0");command("mods 0")
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
