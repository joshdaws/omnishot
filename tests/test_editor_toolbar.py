from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtTest import QTest
from omnishot.editor import Annotation
from test_crop import make_editor


def test_properties_follow_selection_and_view_zoom(tmp_path):
    app,e=make_editor(tmp_path);e.show();app.processEvents()
    try:
        e.set_tool('blur');assert e.hide_button.defaultAction()==e.tools['blur'] and e.blur_mode_action.isVisible()
        e.set_tool('pixelate');assert e.hide_button.defaultAction()==e.tools['pixelate'] and e.pixelate_mode_action.isVisible() and not e.blur_mode_action.isVisible()
        text=Annotation(dict(kind='text',text='Properties',text_style='Rounded',x=20,y=20,w=240,h=90),e);e.scene.addItem(text);e.objects.append(text)
        e.set_tool('select');text.setSelected(True);assert e.text_style_action.isVisible() and not e.width_action.isVisible()
        e.scene.clearSelection();assert not e.text_style_action.isVisible()
        e.zoom_to(200);assert e.view.transform().m11()==2 and e.zoom_button.text()=='200%'
        e.actual_size();assert e.zoom_button.text()=='100%'
        e.fit();assert e.zoom_button.text()==f'{round(e.view.transform().m11()*100,1):g}%'
        assert abs(e.drag_handle.mapTo(e,e.drag_handle.rect().center()).x()-e.rect().center().x())<=3
    finally:e.close()


def test_drag_handle_requires_held_movement(tmp_path,monkeypatch):
    app,e=make_editor(tmp_path);e.show();app.processEvents();calls=[]
    monkeypatch.setattr(e,'drag_image',lambda:calls.append(True))
    try:
        b=e.drag_handle;QTest.mouseClick(b,Qt.MouseButton.LeftButton);assert not calls
        start=b.rect().center();QTest.mousePress(b,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(b,start+QPoint(20,0));QTest.mouseRelease(b,Qt.MouseButton.LeftButton,pos=start+QPoint(20,0));assert calls==[True]
    finally:e.close()
