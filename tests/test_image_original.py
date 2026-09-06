import json,zipfile
import pytest
from PySide6.QtCore import QPointF,QRect
from PySide6.QtGui import QTransform,QColorSpace
from omnishot.editor import Editor,Annotation
from test_crop import make_editor


def test_original_survives_project_and_preserves_later_annotations(tmp_path):
    app,e=make_editor(tmp_path)
    e.base.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3));original=e.base.copy();before=e.render(convert_srgb=False)
    e.crop(QRect(50,40,600,400));e.rotate();e.flip(True);e.resize_to(300)
    obj=Annotation(dict(kind='rect',x=30,y=40,w=80,h=60,width=3,color='#ff0000'),e);e.scene.addItem(obj);e.objects.append(obj);e.commit()
    inverse,valid=e.source_transform.inverted();assert valid
    expected=inverse.map(obj.mapToScene(QPointF(80,60)))
    cropped=e.render(convert_srgb=False);project=tmp_path/'original.omnishot';e.write_project(project);e.close()
    e=Editor(project,e.store)
    try:
        assert e.render(convert_srgb=False)==cropped
        e.set_tool('crop');session=e.crop_session;session.reset()
        assert e.base==original and e.base.colorSpace()==original.colorSpace()
        actual=e.objects[-1].mapToScene(QPointF(80,60));assert (actual-expected).manhattanLength()<1e-6
        assert len(e.objects)==2
        session.cancel();assert e.render(convert_srgb=False)==cropped
        e.set_tool('crop');e.crop_session.reset();e.crop_session.apply();restored=e.render(convert_srgb=False)
        assert e.base==original and e.source_transform.isIdentity()
        e.undo();assert e.render(convert_srgb=False)==cropped;e.redo();assert e.render(convert_srgb=False)==restored
        e.write_project(project);second=Editor(project,e.store);assert second.render(convert_srgb=False)==restored;second.close()
    finally:e.close()


def test_history_draft_and_legacy_project_originals(tmp_path):
    app,e=make_editor(tmp_path);original=e.base.copy();path=e.path;store=e.store
    e.crop(QRect(20,30,500,300));e.save_draft();e.close();e=Editor(path,store)
    try:
        assert e.base.size().width()==500;e.set_tool('crop');e.crop_session.reset();assert e.base==original;e.crop_session.cancel()
        modern=tmp_path/'modern.omnishot';e.write_project(modern)
        legacy=tmp_path/'legacy.omnishot'
        with zipfile.ZipFile(modern) as src,zipfile.ZipFile(legacy,'w') as dst:
            data=json.loads(src.read('project.json'));data['version']=1;data.pop('original_image');data.pop('source_transform');dst.writestr('project.json',json.dumps(data));dst.writestr('image.png',src.read('image.png'))
        old=Editor(legacy,store);baseline=old.base.copy();assert old.original_image is None
        old.crop(QRect(5,5,100,100));old.set_tool('crop');old.crop_session.reset();assert old.base==baseline;old.crop_session.cancel();old.close()
    finally:e.close()


def test_invalid_original_geometry_does_not_replace_open_image(tmp_path):
    app,e=make_editor(tmp_path);e.crop(QRect(20,20,400,300));valid=tmp_path/'valid.omnishot';e.write_project(valid);before=e.snapshot()
    try:
        for i,transform in enumerate(([0,0,0,0,0,0],[1,0,0,1,float('nan'),0],[1,0,0,1,0],['1',0,0,1,0,0])):
            path=tmp_path/f'invalid{i}.omnishot'
            with zipfile.ZipFile(valid) as src,zipfile.ZipFile(path,'w') as dst:
                for name in ('image.png','original.png'):dst.writestr(name,src.read(name))
                data=json.loads(src.read('project.json'));data['source_transform']=transform;dst.writestr('project.json',json.dumps(data))
            with pytest.raises(ValueError):e.load_project(path)
            assert e.snapshot()==before
    finally:e.close()
