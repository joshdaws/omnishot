"""Exercise native presentation dialogs with generated video and input tracks."""
import argparse,json,time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QPushButton,QDialogButtonBox,QTableView,QTabWidget,QLineEdit
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.video_styles import EffectsDialog,InputEventsDialog
from omnishot.backgrounds import BackgroundDialog

parser=argparse.ArgumentParser();parser.add_argument("source",type=Path);parser.add_argument("output",type=Path);args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");theme=ThemeManager(app)
store=backend.Store(out/"data");store.settings["output_dir"]=str(out);source=store.add(source=args.source,kind="video")
metadata={"cursor":[{"t":0,"x":.2,"y":.4},{"t":3,"x":.8,"y":.4}],"events":[{"kind":"click","t":.4,"x":.4,"y":.5},{"kind":"key","t":.5,"state":1,"label":"Ctrl+C"}]};source.with_suffix(".studio.json").write_text(json.dumps(metadata))
editor=VideoEditor(source,store);editor.show();errors=[]
def wait(milliseconds):QTest.qWait(milliseconds)
def click(label):
    page="Background" if label=="Background…" else "Cursor"
    QTest.mouseClick(editor.tool_buttons[page],Qt.MouseButton.LeftButton);app.processEvents()
    widget=next(b for b in editor.findChildren(QPushButton) if b.text()==label and b.isVisible())
    editor.inspector.currentWidget().ensureWidgetVisible(widget);app.processEvents()
    QTest.mouseClick(widget,Qt.MouseButton.LeftButton)
def accept(dialog):QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton)
def modal(expected,work):
    def run():
        dialog=app.activeModalWidget()
        try:assert isinstance(dialog,expected),type(dialog);work(dialog)
        except Exception as exc:
            errors.append(str(exc))
            if dialog:dialog.reject()
    QTimer.singleShot(250,run)
try:
    wait(900);editor.player.pause();assert editor.last_frame is not None
    def effects(dialog):
        dialog.fields["cursor_style"].setCurrentText("Dot");dialog.fields["click_size"].setValue(36);dialog.fields["key_position"].setCurrentText("Top Left");dialog.fields["camera_mirror"].setChecked(True)
        dialog.findChild(QTabWidget).setCurrentIndex(2);wait(100);dialog.grab().save(str(out/"effects.png"));accept(dialog)
    modal(EffectsDialog,effects);click("Effects…")
    assert editor.studio_options()["cursor_style"]=="Dot" and editor.studio_options()["click_size"]==36
    assert editor.effect_controls["Cursor"].fields["cursor_style"].currentText()=="Dot"
    assert editor.effect_controls["Clicks"].fields["click_size"].value()==36
    def background(dialog):
        dialog.presets.setCurrentText("Ocean");dialog.pad.setValue(36);dialog.radius.setValue(24);dialog.aspect.setCurrentText("1:1");wait(120);dialog.grab().save(str(out/"background.png"));accept(dialog)
    modal(BackgroundDialog,background);click("Background…")
    assert editor.studio_options()["background2"]=="#184496" and editor.padding.value()==36
    def inputs(dialog):
        table=dialog.findChild(QTableView);index=dialog.model.index(1,3);rect=table.visualRect(index);QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=rect.center());QTest.mouseDClick(table.viewport(),Qt.MouseButton.LeftButton,pos=rect.center());wait(100);field=next(w for w in table.findChildren(QLineEdit) if w.isVisible());QTest.keyClick(field,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);QTest.keyClicks(field,"Ctrl+Shift+S");QTest.keyClick(field,Qt.Key.Key_Return);wait(100)
        # The checkbox delegate aligns its indicator at the left edge.
        rect=table.visualRect(dialog.model.index(0,0));QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=rect.topLeft()+__import__("PySide6.QtCore",fromlist=["QPoint"]).QPoint(9,rect.height()//2));wait(100)
        dialog.grab().save(str(out/"events.png"));accept(dialog)
    modal(InputEventsDialog,inputs);click("Edit input events…")
    assert editor.styles["event_edits"]["0"]["hidden"]
    assert editor.styles["event_edits"]["1"]["label"]=="Ctrl+Shift+S",editor.styles
    editor.player.setPosition(1300);wait(150);editor.grab().save(str(out/"editor.png"));editor.close();wait(100)
    reopened=VideoEditor(source,store);reopened.player.pause();assert reopened.studio_options()["key_position"]=="Top Left" and reopened.styles["event_edits"]["1"]["label"]=="Ctrl+Shift+S";reopened.close()
    report={"effects_dialog":True,"shared_background_dialog":True,"input_event_checkbox_and_label":True,"reopened_styles_and_events":True};(out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    for window in app.topLevelWidgets():window.close()
if errors:raise RuntimeError(errors)
