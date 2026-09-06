import json
import numpy as np
import pytest
from PySide6.QtCore import QRectF,QPointF
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.editor import Editor,Annotation
from omnishot.rounded_corners import rounded_path


@pytest.mark.parametrize('rounding,power,fullscreen,expected',[(0,2,0,0),(30,2,0,48),(24,4,0,77),(24,4,1,77),(24,4,2,0)])
def test_window_uses_its_own_rounding_at_fractional_scale(monkeypatch,rounding,power,fullscreen,expected):
    def run(args,**kwargs):
        assert args[2]=='getprop'
        return json.dumps({args[-1]:rounding if args[-1]=='rounding' else power})
    monkeypatch.setattr(backend,'run',run)
    opts=backend.window_background(dict(address='0x123',size=[500,340],fullscreen=fullscreen),np.zeros((544,800,4),np.uint8))
    assert opts['radius']==expected and opts['radius_power']==power


def test_missing_window_property_falls_back_to_global(monkeypatch):
    def run(args,**kwargs):
        if args[2]=='getprop':return 'window not found'
        return '{"int":12}' if args[-1].endswith(':rounding') else '{"float":3}'
    monkeypatch.setattr(backend,'run',run)
    opts=backend.window_background(dict(address='0x123',size=[500,340]),np.zeros((544,800,4),np.uint8))
    assert opts['radius']==29 and opts['radius_power']==3


@pytest.mark.parametrize('power',[1,2,4,8])
def test_corner_contours_match_superellipse_in_every_corner(power):
    path=rounded_path(QRectF(10,20,500,300),60,power)
    for dx in range(3,59,5):
        for dy in range(3,59,5):
            distance=((60-dx)**power+(60-dy)**power)**(1/power)
            if abs(distance-60)<.3:continue
            for x,y in [(10+dx,20+dy),(510-dx,20+dy),(10+dx,320-dy),(510-dx,320-dy)]:
                assert path.contains(QPointF(x,y))==(distance<60)


def test_powered_background_clips_annotations_and_reopens(tmp_path):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/'data');store.settings['annotation_shadow']=False
    editor=Editor(store.add(image=np.full((240,360,3),255,np.uint8)),store)
    editor.background=dict(color='#00000000',color2='#00000000',padding=20,radius=60,radius_power=4,shadow=False,aspect='Auto',align='Center')
    annotation=Annotation(dict(kind='fill',x=0,y=0,w=130,h=130,color='#ff0000'),editor);editor.objects.append(annotation);editor.scene.addItem(annotation);editor.commit()
    image=editor.render();assert image.pixelColor(25,25).alpha()==0 and image.pixelColor(32,32).alpha()==255
    assert image.pixelColor(32,32).red()==255
    project=tmp_path/'window.omnishot';editor.write_project(project);other=Editor(project,store)
    assert other.background['radius_power']==4 and other.render()==image
    other.close();editor.close()
