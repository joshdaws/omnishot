import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication
from omnishot.app import Controller
from omnishot.backend import Store


@pytest.mark.parametrize('action',['copy','save','annotate','pin'])
@pytest.mark.parametrize('combined',[True,False])
def test_area_shortcuts_respect_configured_actions_without_changing_explicit_actions(action,combined):
    from omnishot.backend import screenshot_actions
    settings=dict(after_capture='overlay',after_capture_extra=['copy','save'],capture_shortcut_actions=combined)
    assert screenshot_actions(settings,'area-'+action)==({'overlay','copy','save',action} if combined else {action})
    assert screenshot_actions(settings,action)=={action}
    assert screenshot_actions(settings)=={'overlay','copy','save'}


def test_last_screenshot_skips_newer_imports_clipboard_images_and_recordings(tmp_path,monkeypatch):
    from omnishot import app as application
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data')
    state=Controller.__new__(Controller);state.store=store;state.restore_capture_windows=lambda:None
    state.perform_capture_actions=lambda *args:None;opened=[];state.edit=opened.append
    monkeypatch.setattr(application,'error',lambda *args:pytest.fail(str(args)))
    state.dispatch(dict(command='last-screenshot'));assert not opened
    state.finished_capture(np.zeros((40,60,3),np.uint8),kind='scroll');screenshot=store.history()[0]['path']
    # Preserve an editable draft and a newer file timestamp without changing
    # capture chronology, just as reopening an old capture does.
    from omnishot.editor import Editor,Annotation
    editor=Editor(screenshot,store);obj=Annotation(dict(kind='rect',x=5,y=5,w=20,h=20),editor);editor.objects.append(obj);editor.scene.addItem(obj);editor.commit();editor.close()
    external=tmp_path/'import.png';Image.new('RGB',(60,40),'blue').save(external);store.import_file(external)
    store.add(image=np.ones((40,60,3),np.uint8))
    recording=store.add(image=np.zeros((40,60,3),np.uint8),kind='video');store.name_capture(recording)
    state.dispatch(dict(command='last-screenshot'));assert opened==[screenshot]
    restored=Editor(opened[0],store);assert len(restored.objects)==1;restored.close()
    state.dispatch(dict(command='last'));assert opened[-1]==str(recording)


def test_area_shortcuts_enter_the_real_selection_path(tmp_path,monkeypatch):
    from omnishot import backend
    state=Controller.__new__(Controller);state.store=Store(tmp_path/'data');captures=[]
    state.capture=lambda mode,args:captures.append((mode,args))
    for command in backend.AREA_SHORTCUTS:
        state.dispatch(dict(command=command));assert captures[-1]==('area',dict(command=command,action=command))
    state.dispatch(dict(command='area-save',action='copy'));assert captures[-1][1]['action']=='copy'


@pytest.mark.parametrize('command,keep',[('ocr-lines',True),('ocr-single-line',False)])
def test_explicit_ocr_actions_override_without_mutating_preferences_or_arguments(tmp_path,command,keep):
    from omnishot.app import parse_args
    state=Controller.__new__(Controller);state.store=Store(tmp_path/'data');state.store.settings['ocr_linebreaks']=not keep
    captures=[];files=[];state.capture=lambda mode,args:captures.append((mode,args));state.recognize_text=lambda path,lines:files.append((path,lines))
    args={**parse_args([command,'--geometry','10,20 300x200']), 'linebreaks':not keep};original=dict(args)
    state.dispatch(args)
    assert captures==[('ocr',{**original,'linebreaks':keep})] and args==original
    state.dispatch(parse_args([command,'generated.png']))
    assert files==[('generated.png',keep)] and state.store.settings['ocr_linebreaks']==(not keep)


def test_combined_actions_use_editable_automatic_background(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data")
    store.settings.update(background_preset="Ocean",after_capture="overlay",after_capture_extra=["copy","save","overlay"],output_dir=str(tmp_path/"exports"))
    controller=Controller.__new__(Controller);controller.store=store;controller.restore_capture_windows=lambda:None;overlays=[];controller.overlay=overlays.append;copies=[]
    monkeypatch.setattr("omnishot.backend.copy_image",lambda path,*args,**kwargs:copies.append(path))
    controller.finished_capture(np.full((120,200,3),255,np.uint8))
    assert len(overlays)==1 and len(copies)==1
    original=overlays[0];assert Image.open(original).size==(200,120)
    assert store.image_edit_path(original).exists()
    assert Image.open(copies[0]).size==(328,248)
    saved=list((tmp_path/"exports").glob("*.png"));assert len(saved)==1 and Image.open(saved[0]).size==(328,248)
    controller.finished_capture(np.full((120,200,3),255,np.uint8),action="copy")
    assert len(copies)==2 and len(overlays)==1 and len(list((tmp_path/"exports").glob("*.png")))==1


def test_recording_actions_copy_file_save_and_open_together(tmp_path,monkeypatch):
    store=Store(tmp_path/"data");store.settings.update(after_recording="edit",after_recording_extra=["copy","save","overlay","edit"],output_dir=str(tmp_path/"exports"))
    source=tmp_path/"source.mp4";source.write_bytes(b"recording contents");path=store.add(source=source,kind="video")
    controller=Controller.__new__(Controller);controller.store=store;controller.restore_capture_windows=lambda:None
    edits=[];overlays=[];copies=[];controller.edit=edits.append;controller.overlay=overlays.append
    monkeypatch.setattr("omnishot.backend.copy_file",lambda path,store,name:copies.append((path,name)))
    monkeypatch.setattr("omnishot.app.background",lambda func,done,failed:done(func()))
    controller.finished_recording(path)
    assert edits==[path] and overlays==[path]
    assert copies==[(path,store.display_name(path))]
    assert (tmp_path/"exports"/store.display_name(path)).read_bytes()==source.read_bytes()
    store.settings.update(after_recording="",after_recording_extra=[])
    controller.finished_recording(path)
    assert edits==[path] and len(copies)==1
