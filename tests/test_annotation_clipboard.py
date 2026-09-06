import base64,json
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage,QColor
from omnishot.annotation_clipboard import MIME,encode,decode
from omnishot.clipboard import Content
from omnishot.editor import Annotation,Editor,png_bytes
from test_crop import make_editor


def test_editable_round_trip_preserves_geometry_styles_layers_and_one_undo(tmp_path,monkeypatch):
    app,e=make_editor(tmp_path);offers=[]
    monkeypatch.setattr('omnishot.annotation_clipboard.publish',lambda data,png,store:offers.append((data,png)))
    image=QImage(20,15,QImage.Format.Format_RGBA8888);image.fill(QColor(80,30,10,64))
    props=[dict(kind='text',x=20,y=25,w=210,h=80,text='Editable é\nsecond line',font_size=22,bold=False,italic=True,color='#ff0033',transform=[1,.2,.1,1,0,0]),dict(kind='pencil',x=50,y=140,w=60,h=0,points=[[0,0],[30,0],[60,0]],smooth=False),dict(kind='image',x=100,y=200,w=20,h=15,image=base64.b64encode(png_bytes(image)).decode())]
    try:
        for p in props:
            obj=Annotation(p,e);e.scene.addItem(obj);e.objects.append(obj);obj.setSelected(True)
        e.commit();before=e.render();original=[obj.data_dict() for obj in e.objects[1:]];index=e.undo_index
        e.copy_selection();data,png=offers[-1]
        assert decode(data)==original
        assert QImage.fromData(png).convertToFormat(QImage.Format.Format_RGBA8888)==before.convertToFormat(QImage.Format.Format_RGBA8888)
        e.paste_content(Content(annotations=data))
        assert e.undo_index==index+1 and len(e.objects)==7
        for previous,obj in zip(original,e.objects[4:]):
            actual=obj.data_dict();assert actual['x']==previous['x']+20 and actual['y']==previous['y']+20
            for k,v in previous.items():
                if k not in ('x','y','z'):assert actual[k]==v
            assert obj.isSelected()
        assert not any(obj.isSelected() for obj in e.objects[:4])
        after=e.render();e.undo();assert e.render()==before;e.redo();assert e.render()==after
        project=tmp_path/'pasted.omnishot';e.write_project(project);other=Editor(project,e.store);assert other.render()==after;other.close()
    finally:app.clipboard().clear();e.close()


@pytest.mark.parametrize('bad',[[],{},dict(kind=[]),dict(kind='exec'),dict(kind='rect',w=float('nan')),dict(kind='text',font_size='20'),dict(kind='text',bold='yes'),dict(kind='image',image='!!!'),dict(kind='pencil',points=[[None,2]]),dict(kind='rect',transform=[0,0,0,0,0,0]),dict(kind='rect',w=20000,h=20000),dict(kind='rect',color=[]),dict(kind='rect',strength=0)])
def test_malformed_objects_leave_editor_and_undo_untouched(tmp_path,bad):
    app,e=make_editor(tmp_path);before=e.snapshot();index=e.undo_index
    try:
        with pytest.raises(ValueError,match='invalid clipboard'):
            e.paste_content(Content(annotations=json.dumps(dict(version=1,objects=[bad])).encode()))
        assert e.snapshot()==before and e.undo_index==index
    finally:e.close()


def test_multiple_images_are_atomic_and_stale_async_paste_is_discarded(tmp_path,monkeypatch):
    app,e=make_editor(tmp_path);before=e.render();index=e.undo_index;calls=[]
    image=QImage(20,15,QImage.Format.Format_RGBA8888);image.fill(QColor(80,30,10,64));path=tmp_path/'small.png';image.save(str(path))
    try:
        with pytest.raises(ValueError):e.paste_content(Content(files=(path,tmp_path/'missing.mp4')))
        assert e.render()==before and e.undo_index==index
        e.paste_content(Content(files=(path,path)));assert len(e.objects)==3 and e.undo_index==index+1
        e.undo();assert e.render()==before
        monkeypatch.setattr('omnishot.widgets.background',lambda work,done,failed:calls.append(done))
        e.paste_image();e.objects[0].setPos(QPointF(4,8));e.commit();state=e.snapshot();calls[-1](Content(image=image));assert e.snapshot()==state
        e.paste_image();e.close();calls[-1](Content(image=image));assert e.snapshot()==state
    finally:e.close()


def test_paste_onto_smaller_capture_keeps_group_visible(tmp_path):
    app,e=make_editor(tmp_path)
    try:
        content=Content(annotations=encode([dict(kind='rect',x=5000,y=8000,w=100,h=80),dict(kind='text',x=5150,y=8000,w=150,h=60,text='Far away')]))
        e.paste_content(content);a,b=e.objects[-2:]
        assert a.content_bounds().intersects(e.scene.sceneRect()) and b.x()-a.x()==150 and b.y()==a.y()
    finally:e.close()


@pytest.mark.parametrize('fail',[False,True])
def test_clipboard_owner_loads_payload_before_temporary_files_removed(tmp_path,monkeypatch,fail):
    from pathlib import Path
    from omnishot.annotation_clipboard import publish
    from omnishot.backend import Store
    store=Store(tmp_path/'data');paths=[]
    def run(args,**kwargs):
        assert args[1]=='annotations';image,objects=map(Path,args[2:]);paths.extend([image,objects])
        assert image.read_bytes()==b'png' and objects.read_bytes()==b'objects'
        if fail:raise RuntimeError('Clipboard unavailable')
    monkeypatch.setattr('omnishot.backend.run',run)
    if fail:
        with pytest.raises(RuntimeError):publish(b'objects',b'png',store)
    else:publish(b'objects',b'png',store)
    assert paths and not any(path.exists() for path in paths)
    assert not list(store.root.glob('.annotation-copy-*'))
