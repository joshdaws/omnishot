"""Native filename dialog, token drag, outer Cancel and capture naming."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit,QPushButton,QCheckBox,QDialogButtonBox
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.capture_name import CaptureNameDialog
from omnishot.widgets import Settings

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready"
def command(value):fixture.stdin.write(value+"\n");fixture.stdin.flush()
store=backend.Store(out/"data");store.settings["output_dir"]=str(out/"saved");errors=[]
try:
    QTest.qWait(250)
    def edit_format():
        dialog=app.activeModalWidget()
        try:
            line=dialog.findChild(QLineEdit,"filenameFormat");assert line
            line.setFocus();QTest.keyClick(line,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);QTest.keyClicks(line,"Demo ")
            token=next(b for b in dialog.findChildren(QPushButton) if b.text()=="%i");QTest.mouseClick(token,Qt.MouseButton.LeftButton);line.insert(" ")
            token=next(b for b in dialog.findChildren(QPushButton) if b.text()=="%y")
            client=next(c for c in backend.hypr("clients") if c["title"]==dialog.windowTitle())
            a=token.mapTo(dialog,token.rect().center());b=line.mapTo(dialog,line.rect().center())
            x,y=client["at"][0]+a.x(),client["at"][1]+a.y();backend.move_cursor(x,y);QTest.qWait(80);command("button 272 1");QTest.qWait(60)
            QTimer.singleShot(100,lambda:command("move 20 0"));QTimer.singleShot(300,lambda:command(f"move {b.x()-a.x()-20} {b.y()-a.y()}"));QTimer.singleShot(600,lambda:command("button 272 0"));QTest.qWait(900)
            assert line.text()=="Demo %i %y",line.text()
            utc=next(c for c in dialog.findChildren(QCheckBox) if c.text()=="Use UTC time zone");utc.setChecked(True)
            dialog.grab().save(str(out/"filename-format.png"))
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton)
        except Exception as exc:
            errors.append(repr(exc))
            if dialog:dialog.reject()
    original=store.settings["filename_format"]
    for save in (False,True):
        settings=Settings(store,"advanced");settings.show();QTest.qWait(250);settings.fields["filename_scale_suffix"].setChecked(False);QTimer.singleShot(250,edit_format);settings.customize_filename();assert not errors,errors
        assert settings.filename_options["filename_format"]=="Demo %i %y" and store.settings["filename_format"]==original
        if save:settings.save()
        else:settings.reject();assert store.settings["filename_scale_suffix"]
    restored=backend.Store(out/"data");assert restored.settings["filename_format"]=="Demo %i %y" and restored.settings["filename_utc"]
    assert restored.settings["filename_scale_suffix"] is False
    settings=Settings(restored,"advanced");settings.show();QTest.qWait(150);settings.fields["filename_scale_suffix"].setChecked(True);settings.save()
    controller=Controller.__new__(Controller);controller.store=restored;controller.restore_capture_windows=lambda:None;controller.overlay=lambda p:None
    controller.finished_capture(np.full((80,120,3),180,np.uint8),pixel_ratio=1.6)
    assert restored.history()[0]["name"].startswith("Demo 1 ")
    assert restored.history()[0]["name"].endswith("@1.6x.png")
    path=Path(restored.history()[0]["path"]);restored.set_pixel_ratio(path,1);assert "@1.6x" not in restored.display_name(path)
    restored.settings["ask_capture_name"]=True
    def name_capture():
        dialog=app.activeModalWidget()
        try:
            assert isinstance(dialog,CaptureNameDialog)
            line=dialog.findChild(QLineEdit);line.setFocus();QTest.keyClick(line,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);QTest.keyClicks(line,"Named capture")
            dialog.accept()
        except Exception as exc:
            errors.append(repr(exc))
            if dialog:dialog.reject()
    QTimer.singleShot(250,name_capture);controller.finished_capture(np.full((80,120,3),200,np.uint8),action="save");assert not errors,errors
    assert (out/"saved/Named capture.png").exists() and backend.Store(out/"data").settings["filename_counter"]==2
    report=dict(native_token_click_and_wayland_drag=True,outer_cancel_preserves_settings=True,format_and_utc_persisted=True,capture_sequence_persisted=True,ask_name_before_save=True,fractional_scale_filename=True,scale_suffix_setting_and_cancel=True,one_x_removes_generated_suffix=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command("button 272 0");command("mods 0")
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
