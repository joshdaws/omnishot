"""Verify failed editor saves keep native windows and edits available."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.editor import Editor,Annotation
from omnishot.recording import VideoEditor

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready"
def command(value):fixture.stdin.write(value+"\n");fixture.stdin.flush()
errors=[];acknowledged=[]
def cancel_failure(name):
    def run():
        modal=app.activeModalWidget()
        try:
            assert isinstance(modal,QMessageBox),modal
            modal.grab().save(str(out/(name+"-save-failure.png")))
            control=modal.button(QMessageBox.StandardButton.Cancel)
            client=next(c for c in backend.hypr("clients") if c["title"]==modal.windowTitle())
            pos=control.mapTo(modal,control.rect().center());backend.move_cursor(client["at"][0]+pos.x()-2,client["at"][1]+pos.y())
            command("move 2 0");QTest.qWait(80);command("click 272");QTest.qWait(100)
            assert not modal.isVisible();acknowledged.append(name)
        except Exception as exc:
            errors.append(str(exc))
            if modal:modal.reject()
    QTimer.singleShot(180,run)
def fail(*args,**kwargs):raise OSError("Synthetic disk-full error in the capture history folder")
store=backend.Store(out/"data");path=store.add(image=np.full((240,480,3),255,np.uint8))
image_editor=Editor(path,store);image_editor.show();QTest.qWait(250);assert image_editor.save_draft();old=image_editor.draft_path.read_bytes()
item=Annotation(dict(kind="text",text="Keep my edits",x=40,y=70,w=340,h=65,color="#205cc4",font_size=34),image_editor)
image_editor.scene.addItem(item);image_editor.objects.append(item);image_editor.commit();expected=image_editor.render();write=image_editor.write_project;atomic=store.atomic_json
try:
    image_editor.write_project=fail;cancel_failure("annotation");assert not image_editor.close()
    assert image_editor.isVisible() and image_editor.render()==expected and image_editor.draft_path.read_bytes()==old
    write(out/"recovered-annotations.omnishot");image_editor.write_project=write;assert image_editor.close()
    reopened=Editor(path,store);assert reopened.render()==expected;reopened.close()
    source=store.captures/"recording.mp4";backend.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=s=320x180:r=15:d=1","-c:v","libx264","-threads","1",source])
    video=VideoEditor(source,store);video.show();QTest.qWait(300);video.player.pause();video.padding.setValue(42);video.styles["cursor_style"]="Dot"
    store.atomic_json=fail;cancel_failure("video");assert not video.close()
    assert video.isVisible() and video.padding.value()==42 and video.styles["cursor_style"]=="Dot"
    store.atomic_json=atomic;assert video.close()
    reopened_video=VideoEditor(source,store);reopened_video.player.pause();assert reopened_video.padding.value()==42 and reopened_video.styles["cursor_style"]=="Dot";reopened_video.close()
    assert acknowledged==["annotation","video"] and not errors,(acknowledged,errors)
    report=dict(native_cancel_buttons=True,annotation_window_kept=True,previous_draft_preserved=True,alternate_project_saved=True,annotation_retry_reopened=True,video_window_kept=True,video_retry_reopened=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    image_editor.write_project=write;store.atomic_json=atomic
    command("button 272 0");command("mods 0")
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
