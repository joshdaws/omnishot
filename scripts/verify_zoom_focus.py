"""Native zoom focus gestures, cancel, accept and persisted reopening."""
import json
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QCheckBox
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app)
store=backend.Store(out/"data");source=store.captures/"zoom-test.mp4"
backend.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=size=640x360:rate=30","-t","4","-c:v","libx264","-pix_fmt","yuv420p",source])
editor=VideoEditor(source,store);editor.show();errors=[]
try:
    QTest.qWait(900);assert editor.last_frame is not None
    editor.player.pause();editor.zooms=[dict(start=.5,end=3.5,scale=2,x=.5,y=.5,follow=False)];editor.sync_timeline()
    original=dict(editor.zooms[0])
    for save in (False,True):
        def gesture(save=save):
            dialog=app.activeModalWidget()
            try:
                focus=editor.timeline.focus_editor;assert focus and not focus.image.isNull()
                center=focus.focus_rect().center().toPoint()
                QTest.mousePress(focus,Qt.MouseButton.LeftButton,pos=center)
                QTest.mouseMove(focus,center+QPoint(30,15));QTest.mouseRelease(focus,Qt.MouseButton.LeftButton)
                corner=focus.corners()[2].toPoint()
                QTest.mousePress(focus,Qt.MouseButton.LeftButton,pos=corner)
                QTest.mouseMove(focus,corner-QPoint(25,14));QTest.mouseRelease(focus,Qt.MouseButton.LeftButton)
                assert focus.cx>.5 and focus.scale>2
                follow=dialog.findChild(QCheckBox);follow.setChecked(True);assert not focus.isEnabled();follow.setChecked(False)
                QTest.qWait(100);dialog.grab().save(str(out/("accepted.png" if save else "cancelled.png")))
                button=QDialogButtonBox.StandardButton.Ok if save else QDialogButtonBox.StandardButton.Cancel
                QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(button),Qt.MouseButton.LeftButton)
            except Exception as exc:
                errors.append(repr(exc))
                if dialog:dialog.reject()
        QTimer.singleShot(300,gesture)
        point=editor.timeline.clip_rect("zoom",0).center().toPoint()
        QTest.mouseClick(editor.timeline,Qt.MouseButton.LeftButton,pos=point)
        QTest.mouseDClick(editor.timeline,Qt.MouseButton.LeftButton,pos=point)
        assert not errors,errors
        if not save:assert editor.zooms[0]==original,"Cancel changed the saved zoom"
    result=dict(editor.zooms[0]);assert result["scale"]>2 and result["x"]>.5
    editor.close();QTest.qWait(100)
    reopened=VideoEditor(source,store);assert reopened.zooms[0]==result;reopened.close()
    report=dict(move_resize=True,follow_cursor_toggle=True,cancel_preserves_original=True,reopened=result)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    for window in app.topLevelWidgets():window.close()
