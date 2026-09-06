"""Exercise the recording inspector through native Wayland pointer/key input."""
import json
from pathlib import Path
import subprocess
import sys
from PySide6.QtCore import QPoint,QObject,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton,QScrollArea,QCheckBox
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready"
def command(value):fixture.stdin.write(value+"\n");fixture.stdin.flush()
source=out/"source.mp4";backend.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=size=640x360:rate=15:duration=3","-c:v","libx264","-threads","1","-pix_fmt","yuv420p",source])
store=backend.Store(out/"data");path=store.add(source=source,kind="video")
path.with_suffix(".studio.json").write_text(json.dumps({"cursor":[{"t":0,"x":.4,"y":.4}],"events":[{"kind":"click","t":.5,"x":.4,"y":.4}]}))
editor=VideoEditor(path,store);editor.show();QTest.qWait(500);editor.player.pause()
events=[]
class InputLog(QObject):
    def eventFilter(self,target,event):
        if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease,QEvent.Type.MouseButtonDblClick):
            events.append((type(target).__name__,target.objectName(),str(event.type()),str(event.position())))
        return False
input_log=InputLog();app.installEventFilter(input_log)
def click(widget):
    parent=widget.parentWidget()
    while parent and not isinstance(parent,QScrollArea):parent=parent.parentWidget()
    if parent:parent.ensureWidgetVisible(widget);QTest.qWait(70)
    assert widget.isVisible(),widget
    client=next(c for c in backend.hypr("clients") if c["title"]==editor.windowTitle())
    local=widget.mapTo(editor,QPoint(8,widget.height()//2) if isinstance(widget,QCheckBox) else widget.rect().center())
    backend.move_cursor(client["at"][0]+local.x()-2,client["at"][1]+local.y());command("move 2 0");QTest.qWait(100)
    command("click 272");QTest.qWait(150)
def tool(name):
    click(editor.tool_buttons[name])
    if editor.inspector.currentIndex()!=list(editor.tool_buttons).index(name):
        editor.grab().save(str(out/"navigation-failure.png"))
        raise AssertionError((name,editor.inspector.currentIndex(),str(app.activePopupWidget()),events[-14:]))
try:
    assert editor.last_frame is not None
    for name in editor.tool_buttons:
        tool(name);editor.grab().save(str(out/(name.lower()+".png")))
    tool("Background")
    ocean=next(w for w in editor.findChildren(QPushButton) if w.accessibleName()=="Ocean background");click(ocean)
    assert editor.padding.value()==64 and editor.styles["background2"]=="#184496"
    tool("Cursor");field=editor.effect_controls["Cursor"].fields["cursor_style"];click(field.buttons["Dot"])
    assert editor.styles["cursor_style"]=="Dot",editor.styles
    tool("Camera");click(editor.effect_controls["Camera"].fields["camera_mirror"])
    assert editor.styles["camera_mirror"] and editor.styles["cursor_style"]=="Dot"
    tool("Motion");click(editor.motion);assert editor.motion.value()>0
    click(next(w for w in editor.findChildren(QPushButton) if w.text()=="Smart zooms"));assert editor.zooms
    editor.resize(900,650);QTest.qWait(250)
    assert editor.width()==900 and editor.height()==650,(editor.size().width(),editor.size().height())
    assert editor.video.width()>=320 and editor.timeline.isVisible() and editor.export_btn.isVisible()
    for name in editor.tool_buttons:
        tool(name);scroll=editor.inspector.currentWidget()
        assert scroll.widget().width()<=scroll.viewport().width(),(name,scroll.widget().width(),scroll.viewport().width())
    tool("Background");editor.grab().save(str(out/"compact.png"))
    editor.resize(1180,780);QTest.qWait(150);editor.grab().save(str(out/"background-edited.png"))
    expected=editor.edit_options();editor.close();QTest.qWait(80)
    reopened=VideoEditor(path,store);reopened.player.pause()
    assert reopened.edit_options()==expected,(reopened.edit_options(),expected)
    assert reopened.effect_controls["Cursor"].fields["cursor_style"].currentText()=="Dot"
    assert reopened.effect_controls["Camera"].fields["camera_mirror"].isChecked()
    reopened.close()
    report=dict(native_wayland_tool_navigation=True,inline_gradient=True,inline_cursor_shape=True,inline_camera_style=True,cross_tool_edits_preserved=True,smart_zooms=True,compact_layout=[900,650],editable_reopening=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command("button 272 0");command("mods 0")
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
