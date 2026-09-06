"""Native settings navigation, direct Save and the Qt Save As dialog."""
import json
import os
from pathlib import Path
import sys
import numpy as np
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QPushButton,QDialogButtonBox,QFileDialog,QLineEdit
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.widgets import Settings,QuickOverlay

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
store=backend.Store(out/"data");settings=Settings(store);settings.show();errors=[]
try:
    QTest.qWait(300)
    for index,key in enumerate(settings.page_names):
        QTest.mouseClick(settings.sections.viewport(),Qt.MouseButton.LeftButton,pos=settings.sections.visualItemRect(settings.sections.item(index)).center());QTest.qWait(70)
        assert settings.pages.currentIndex()==index
        if key in ("general","quickaccess","recording"):settings.grab().save(str(out/f"settings-{key}.png"))
    settings.show_page("general");folder=settings.fields["output_dir"];folder.setFocus();QTest.keyClick(folder,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);QTest.keyClicks(folder,str(out/"saved"))
    QTest.mouseClick(settings.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
    store=backend.Store(out/"data");assert store.settings["output_dir"]==str(out/"saved")
    path=store.add(image=np.full((120,200,3),(24,115,210),np.uint8));store.rename(path,"Settings save test")
    overlay=QuickOverlay(path,store);overlay.show();QTest.qWait(350)
    button=next(b for b in overlay.findChildren(QPushButton) if b.text()=="Save")
    client=next(c for c in backend.hypr("clients") if c["pid"]==os.getpid() and c["title"]==overlay.windowTitle())
    point=button.mapTo(overlay,button.rect().center());backend.move_cursor(client["at"][0]+point.x(),client["at"][1]+point.y());QTest.qWait(100)
    backend.run([Path(__file__).resolve().parents[1]/"native/scroll-helper","click",272]);QTest.qWait(200)
    assert (out/"saved/Settings save test.png").is_file() and not overlay.isVisible()
    overlay=QuickOverlay(path,store);overlay.show();QTest.qWait(300)
    def save_as():
        dialog=app.activeModalWidget()
        try:
            assert isinstance(dialog,QFileDialog),type(dialog)
            name=dialog.findChild(QLineEdit,"fileNameEdit");assert name
            name.setFocus();QTest.keyClick(name,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);QTest.keyClicks(name,"Explicit export.png")
            dialog.grab().save(str(out/"save-as.png"))
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
        except Exception as exc:
            errors.append(repr(exc))
            if dialog:dialog.reject()
    QTimer.singleShot(250,save_as);overlay.save(True)
    assert not errors,errors
    assert (out/"saved/Explicit export.png").is_file()
    from omnishot.app import Controller
    from types import SimpleNamespace
    controller=Controller.__new__(Controller);controller.store=store;controller.overlays=[];controller.tray=SimpleNamespace(showMessage=lambda *args:None)
    for color in ((210,80,30),(20,180,100)):
        item=store.add(image=np.full((100,160,3),color,np.uint8));store.rename(item,"Batch")
        preview=QuickOverlay(item,store,len(controller.overlays));controller.overlays.append(preview);preview.show()
    QTest.qWait(200);batch=out/"batch";batch.mkdir(exist_ok=True)
    def batch_folder():
        dialog=app.activeModalWidget()
        try:
            assert isinstance(dialog,QFileDialog)
            dialog.setDirectory(str(batch));QTest.qWait(80)
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open),Qt.MouseButton.LeftButton)
        except Exception as exc:
            errors.append(repr(exc))
            if dialog:dialog.reject()
    QTimer.singleShot(250,batch_folder);controller.save_all_overlays()
    assert not errors,errors
    assert (batch/"Batch.png").is_file() and (batch/"Batch (2).png").is_file()
    assert all(not preview.isVisible() for preview in controller.overlays)
    reopened=Settings(backend.Store(out/"data"),"quickaccess")
    assert reopened.fields["output_dir"].text()==str(out/"saved");reopened.close()
    report=dict(settings_pages=len(settings.page_names),settings_persisted=True,direct_save_wayland_click=True,qt_save_as=True,batch_save_unique_names=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    for window in app.topLevelWidgets():window.close()
