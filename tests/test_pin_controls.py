import pytest
pytestmark = pytest.mark.usefixtures('no_compositor')
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent,QImage,QColor
from PySide6.QtWidgets import QApplication
from omnishot.backend import Store
from omnishot.widgets import Pin


def make_pin(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data')
    image=QImage(320,200,QImage.Format.Format_RGB32);image.fill(QColor('#2070b0'))
    pin=Pin(store.add(image=image),0,store);pin.show();app.processEvents();return app,pin


def test_trackpad_changes_opacity_and_empty_or_horizontal_events_do_nothing(tmp_path):
    app,pin=make_pin(tmp_path);original=pin.size()
    def wheel(pixels=QPoint(),angle=QPoint(),mods=Qt.KeyboardModifier.NoModifier):
        event=QWheelEvent(QPointF(100,100),QPointF(100,100),pixels,angle,Qt.MouseButton.NoButton,mods,Qt.ScrollPhase.ScrollUpdate,False)
        app.sendEvent(pin,event);app.processEvents()
    try:
        wheel(pixels=QPoint(0,-50));assert pin.opacity==.9 and pin.size()==original
        wheel();wheel(pixels=QPoint(60,0));wheel(angle=QPoint(120,0));assert pin.opacity==.9 and pin.size()==original
        wheel(angle=QPoint(0,-120));assert pin.size()!=original and pin.opacity==.9
        size=pin.size();wheel(angle=QPoint(-120,0),mods=Qt.KeyboardModifier.AltModifier);assert abs(pin.opacity-.82)<1e-9 and pin.size()==size
        pin.locked=True;size=pin.size();wheel(pixels=QPoint(0,-50));assert pin.size()==size and abs(pin.opacity-.82)<1e-9
    finally:pin.close()


def test_lock_exposes_only_unlock_and_controls_fit_small_pins(tmp_path):
    app,pin=make_pin(tmp_path)
    try:
        pin.controls.hovered=True;pin.controls.sync();assert pin.controls.drag.isVisible()
        pin.locked=True;pin.controls.sync();pin.controls.position_unlock();pin.update_input()
        mask=pin.windowHandle().mask();assert not mask.intersects(pin.rect())
        assert pin.controls.unlock.isVisible() and not pin.controls.lock.isVisible() and not pin.controls.close.isVisible() and not pin.controls.drag.isVisible()
        for w,h in ((50,30),(10,520),(520,10)):
            pin.setFixedSize(w,h);app.processEvents();assert pin.rect().contains(pin.controls.lock.geometry())
    finally:pin.close()
