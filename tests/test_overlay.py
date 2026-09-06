import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from omnishot.backend import Store
from omnishot.widgets import QuickOverlay


def test_overlay_swipes_restore_and_preview(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data");path=store.add(image=np.zeros((200,300,3),np.uint8))
    monkeypatch.setattr("omnishot.widgets.place_window",lambda *args:None)
    overlay=QuickOverlay(path,store);closed=[];overlay.dismissed.connect(closed.append);overlay.show();app.processEvents()
    def wheel(pixel,angle=QPoint()):
        event=QWheelEvent(QPointF(40,40),QPointF(40,40),pixel,angle,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.ScrollEnd,False);app.sendEvent(overlay,event);app.processEvents()
    wheel(QPoint(),QPoint(0,-120));assert overlay.isVisible() and not overlay.collapsed
    wheel(QPoint(0,-110));assert overlay.collapsed and not overlay.preview.isVisible() and overlay.restore_button.isVisible()
    QTest.mouseClick(overlay.restore_button,Qt.MouseButton.LeftButton);assert not overlay.collapsed and overlay.preview.isVisible()
    overlay.preview_large();assert overlay.quicklook.isVisible();overlay.quicklook.close();app.processEvents();assert overlay.quicklook is None
    wheel(QPoint(110,0));assert not overlay.isVisible() and closed==[str(path)]
