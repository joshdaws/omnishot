from PySide6.QtCore import QRect,QEvent
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from omnishot.app import Controller
from omnishot.backend import Store
from omnishot.editor import Editor,Annotation


def pixels(image):return image.convertToFormat(QImage.Format.Format_RGBA8888)


def controller(tmp_path):
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    state=Controller.__new__(Controller);state.app=app;state.store=Store(tmp_path/'data');state.windows=[];state.overlays=[];state.pins=[]
    image=QImage(800,500,QImage.Format.Format_RGB32);image.fill(QColor('#e3ebf6'));path=state.store.add(image=image);state.edit(path)
    return app,state,path,state.windows[0]


def finish(app,state):
    for window in list(state.windows)+list(state.overlays)+list(state.pins):window.close()
    app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()


def test_pins_keep_editable_identity_refresh_crop_undo_and_do_not_reopen_hidden(tmp_path):
    app,state,path,e=controller(tmp_path)
    try:
        obj=Annotation(dict(kind='rect',x=100,y=80,w=150,h=100,color='#df3048'),e);e.objects.append(obj);e.scene.addItem(obj);e.commit();e.pin();pin=state.pins[0]
        assert pin.path==path and pixels(pin.image)==pixels(e.render())
        state.overlay(path);overlay=state.overlays[0]
        pin.setFixedSize(400,250);pin.opacity=.45;pin.locked=True;pin.hide()
        e.crop(QRect(100,50,500,250));assert e.save_draft()
        assert pixels(pin.image)==pixels(e.render()) and (pin.width(),pin.height())==(250,125)
        assert overlay.info.text().startswith('500 × 250') and overlay.content_path==pin.content_path
        assert pin.opacity==.45 and pin.locked and not pin.isVisible()
        e.undo();assert e.draft_timer.isActive();e.save_draft();assert pixels(pin.image)==pixels(e.render()) and (pin.width(),pin.height())==(400,250)
        e.redo();assert e.draft_timer.isActive();e.save_draft();assert pixels(pin.image)==pixels(e.render()) and (pin.width(),pin.height())==(250,125)
        state.edit(path);assert state.windows==[e] and len(e.objects)==1
    finally:finish(app,state)


def test_repeated_crop_undo_keeps_fractional_pin_magnification(tmp_path):
    app,state,path,e=controller(tmp_path)
    try:
        e.pin();pin=state.pins[0];pin.setFixedSize(573,358);scale=pin.display_scale
        e.crop(QRect(0,0,500,300));e.save_draft()
        for _ in range(5):
            e.undo();e.save_draft();assert pin.width()==573 and pin.display_scale==scale
            e.redo();e.save_draft();assert pin.width()==358 and pin.display_scale==scale
    finally:finish(app,state)


def test_external_project_pin_imports_once_and_preserves_editable_content(tmp_path):
    import time
    app,state,path,e=controller(tmp_path)
    try:
        obj=Annotation(dict(kind='text',text='Still editable',x=20,y=20,w=300,h=80),e);e.objects.append(obj);e.scene.addItem(obj);e.commit()
        project=tmp_path/'Shared project.omnishot';e.write_project(project);original=project.read_bytes();expected=pixels(e.render())
        state.pin(project);end=time.monotonic()+5
        while not state.pins and time.monotonic()<end:app.processEvents();time.sleep(.01)
        assert len(state.pins)==1;pin=state.pins[0]
        assert pin.path.parent==state.store.captures and pin.path.suffix=='.omnishot' and pixels(pin.image)==expected
        state.edit(pin.path);other=state.windows[-1];assert other is not e and other.objects[0].props['text']=='Still editable'
        assert project.read_bytes()==original
    finally:finish(app,state)


def test_pin_titles_stay_unique_after_a_pin_closes(tmp_path):
    app,state,path,e=controller(tmp_path)
    try:
        e.pin();e.pin();state.pins[0].close();app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        e.pin();assert len({pin.windowTitle() for pin in state.pins})==len(state.pins)==2
    finally:finish(app,state)


def test_failed_preview_preserves_old_pin_and_does_not_publish_stale_new_pin(tmp_path,monkeypatch):
    app,state,path,e=controller(tmp_path);errors=[]
    try:
        e.pin();before=QImage(state.pins[0].image);e.rotate()
        with monkeypatch.context() as patch:
            def fail(*args,**kwargs):raise OSError('Generated disk error')
            patch.setattr('omnishot.editor.export_image',fail);patch.setattr('omnishot.editor.error',lambda parent,exc:errors.append(str(exc)))
            e.pin();assert errors==['Generated disk error'] and len(state.pins)==1 and state.pins[0].image==before
        e.save_draft();assert pixels(state.pins[0].image)==pixels(e.render()) and state.pins[0].image!=before
    finally:finish(app,state)
