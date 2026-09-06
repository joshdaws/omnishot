import pytest
import numpy as np
from PySide6.QtWidgets import QApplication
from omnishot.camera_framing import CameraFraming,options_at
from omnishot.studio import compose_frame
from omnishot.video_project import validate_manifest


def test_recorded_camera_changes_follow_source_clock_and_pauses(monkeypatch):
    clock=[99.];monkeypatch.setattr('omnishot.camera_framing.time.monotonic',lambda:clock[0]);framing=CameraFraming()
    framing.set_fullscreen(True);clock[0]=100.5;framing.set_fullscreen(False);clock[0]=101;framing.set_fullscreen(True)
    clock[0]=102;framing.pause(True);clock[0]=103;framing.set_fullscreen(False);clock[0]=103.5;framing.set_fullscreen(True)
    clock[0]=104;framing.pause(False);clock[0]=105;framing.set_fullscreen(False)
    events=framing.snapshot(100)
    assert events==[dict(t=0,fullscreen=True),dict(t=.5,fullscreen=False),dict(t=1,fullscreen=True),dict(t=2,fullscreen=True),dict(t=3,fullscreen=False)]
    assert framing.snapshot(None)==[]
    assert not options_at(dict(camera_framing=events),{},.75)['camera_fullscreen']
    assert options_at(dict(camera_framing=events),{},2.8)['camera_fullscreen']
    assert options_at(dict(camera_framing=events),dict(camera_fullscreen=True),4)['camera_fullscreen']


def test_recorded_camera_composition_and_editor_override():
    app=QApplication.instance() or QApplication([])
    source=np.full((180,320,3),[30,140,60],np.uint8);camera=np.full((60,80,3),[220,30,30],np.uint8)
    metadata=dict(camera_framing=[dict(t=1,fullscreen=True),dict(t=2,fullscreen=False)])
    options=dict(camera=True,camera_shadow=False,padding=0,cursor=False,keys=False,clicks=False)
    def center(t,opts):return compose_frame(source,t,metadata,opts,camera).pixelColor(160,90).getRgb()[:3]
    assert center(.5,options)==(30,140,60) and center(1.5,options)==(220,30,30) and center(2.5,options)==(30,140,60)
    assert center(1.5,{**options,'camera_recorded_framing':False})==(30,140,60)
    assert center(.5,{**options,'camera_fullscreen':True})==(220,30,30)


def test_camera_fallback_cannot_cover_unexcluded_source():
    from types import SimpleNamespace
    from omnishot.camera import CameraPreview
    app=QApplication.instance() or QApplication([])
    preview=CameraPreview(SimpleNamespace(latest=None),allow_fullscreen=False)
    changed=[];preview.fullscreen_changed.connect(changed.append);size=preview.size()
    preview.toggle_fullscreen()
    assert not preview.fullscreen and preview.size()==size and not changed
    preview.timer.stop();preview.close()


@pytest.mark.parametrize('shape',['Rounded','Rectangle'])
def test_preview_uses_actual_camera_aspect_after_first_frame(shape):
    from types import SimpleNamespace
    from omnishot.camera import CameraPreview
    app=QApplication.instance() or QApplication([]);track=SimpleNamespace(latest=None)
    preview=CameraPreview(track,shape,size=320);assert preview.height()==240
    track.latest=np.zeros((90,160,3),np.uint8);preview.refresh_frame();assert preview.size().toTuple()==(320,180)
    preview.fullscreen=True;preview.normal_placement=(12,15,320,240);preview.setFixedSize(800,500);preview.refresh_frame()
    assert preview.size().toTuple()==(800,500) and preview.normal_placement==(12,15,320,180)
    preview.set_shape('Square');assert preview.normal_placement==(12,15,320,320)
    preview.timer.stop();preview.close()


@pytest.mark.parametrize('room',[True,False])
def test_resized_fallback_rechecks_space_outside_source(monkeypatch,room):
    from types import SimpleNamespace
    from omnishot.camera import CameraPreview
    app=QApplication.instance() or QApplication([])
    preview=CameraPreview(SimpleNamespace(latest=None),'Rectangle',rect=(0,0,800,600),allow_fullscreen=False)
    placements=[]
    monkeypatch.setattr('omnishot.camera.place_outside',lambda widget,rect:placements.append((widget.size().toTuple(),rect)) or room)
    monkeypatch.setattr(preview,'current_placement',lambda:(-200,0,preview.width(),preview.height()))
    preview.show();preview.track.latest=np.zeros((160,80,3),np.uint8);preview.refresh_frame()
    assert placements==[((200,400),(0,0,800,600))] and preview.isVisible()==room
    preview.timer.stop();preview.close()


@pytest.mark.parametrize('shape',['Circle','Square','Rounded','Rectangle'])
@pytest.mark.parametrize('feed',[(90,160),(160,80)])
def test_large_camera_fits_capture_and_preserves_requested_width(shape,feed):
    from types import SimpleNamespace
    from omnishot.camera import CameraPreview
    app=QApplication.instance() or QApplication([])
    preview=CameraPreview(SimpleNamespace(latest=np.zeros((*feed,3),np.uint8)),shape,size=1440,rect=(100,-80,1800,1125))
    preview.refresh_frame();w,h=preview.size().toTuple()
    ratio=1 if shape in ('Circle','Square') else feed[0]/feed[1]
    assert w<=1440 and w<=1760 and h<=1005 and abs(h/w-ratio)<.002
    # Expanding the feed shape near an edge moves the overlay wholly into view.
    x,y,w,h=preview.fitted_placement((1880,1030,20,20))
    assert 100<=x and -80<=y and x+w<=1900 and y+h<=1045
    preview.fullscreen=True;preview.normal_placement=(x,y,w,h);preview.setFixedSize(1800,1125)
    preview.set_shape('Rectangle');preview.refresh_frame()
    assert preview.size().toTuple()==(1800,1125) and preview.normal_placement[3]<=1005
    preview.set_shape('Circle');assert preview.normal_placement[2:]==(1005,1005)
    assert preview.preferred_width==1440
    preview.timer.stop();preview.close()


def test_shape_changes_survive_fullscreen_and_collapse_during_pause(monkeypatch):
    clock=[100.];monkeypatch.setattr('omnishot.camera_framing.time.monotonic',lambda:clock[0]);framing=CameraFraming()
    framing.set_shape('Square');clock[0]=101;framing.set_fullscreen(True)
    clock[0]=102;framing.pause(True);clock[0]=103;framing.set_shape('Rectangle');clock[0]=104;framing.set_fullscreen(False)
    clock[0]=105;framing.pause(False);clock[0]=106;framing.set_shape('Circle')
    events=framing.snapshot(100)
    assert events==[dict(t=0,fullscreen=False,shape='Square'),dict(t=1,fullscreen=True,shape='Square'),dict(t=2,fullscreen=False,shape='Rectangle'),dict(t=3,fullscreen=False,shape='Circle')]
    meta=dict(camera_framing=events);opts=dict(camera_shape='Rounded')
    assert options_at(meta,opts,2.5)['camera_shape']=='Rectangle'
    assert options_at(meta,{**opts,'camera_recorded_framing':False},2.5)['camera_shape']=='Rounded'


def test_placement_survives_pause_fullscreen_and_export_scaling(monkeypatch):
    from omnishot.video_position import camera_rect
    clock=[100.];monkeypatch.setattr('omnishot.camera_framing.time.monotonic',lambda:clock[0]);framing=CameraFraming()
    framing.set_placement((.6,.5,.22));clock[0]=101;framing.pause(True)
    clock[0]=102;framing.set_placement((.2,.3,.22));clock[0]=103;framing.set_fullscreen(True)
    clock[0]=104;framing.pause(False);clock[0]=105;framing.set_fullscreen(False)
    events=framing.snapshot(100)
    assert [(e['t'],e['placement'],e['fullscreen']) for e in events]==[(0,[.6,.5,.22],False),(1,[.2,.3,.22],True),(2,[.2,.3,.22],False)]
    opts=options_at(dict(camera_framing=events),{},2.5)
    for w,h in ((1000,600),(500,300)):
        rect=camera_rect(w,h,.75,opts)
        assert rect.getRect()==pytest.approx((.2*w,.3*h,.22*w,.22*w))
    assert 'camera_placement' not in options_at(dict(camera_framing=events),dict(camera_recorded_framing=False),2.5)


@pytest.mark.parametrize('placement',[[0,0], [0,0,float('nan')], [True,0,.2], [0,0,0], [2,0,.2], 'invalid'])
def test_project_rejects_invalid_camera_placement(placement):
    with pytest.raises(ValueError,match='camera framing placement'):
        validate_manifest(dict(format='omnishot-video',version=1,source='source.mp4',metadata=dict(camera_framing=[dict(t=0,fullscreen=False,placement=placement)]),options={}))


def test_recorded_square_has_square_aperture_and_legacy_shapes_still_render():
    app=QApplication.instance() or QApplication([])
    source=np.full((180,320,3),[30,140,60],np.uint8);camera=np.full((60,80,3),[220,30,30],np.uint8)
    options=dict(camera=True,camera_shadow=False,camera_size=.5,camera_position='Center',padding=0,cursor=False,keys=False,clicks=False)
    meta=dict(camera_framing=[dict(t=1,fullscreen=False,shape='Square')])
    # Near the top-left of the same bounding square: circle excludes it, square includes it.
    def sample(t,opts):return compose_frame(source,t,meta,opts,camera).pixelColor(102,32).getRgb()[:3]
    assert sample(.5,options)==(30,140,60)
    assert sample(1.5,options)==(220,30,30)
    assert sample(1.5,{**options,'camera_recorded_framing':False})==(30,140,60)
    for shape in ('Circle','Square','Rounded','Rectangle'):
        image=compose_frame(source,0,{},dict(options,camera_shape=shape,camera_fullscreen=True),camera)
        assert image.pixelColor(0,0).getRgb()[:3]==(220,30,30)


@pytest.mark.parametrize('events',[[dict(t=-1,fullscreen=True)],[dict(t=2,fullscreen=True),dict(t=1,fullscreen=False)],[dict(t=1,fullscreen='yes')],[dict(t=float('nan'),fullscreen=True)],'invalid',[dict(t=1,fullscreen=False,shape='Triangle')]])
def test_project_rejects_invalid_camera_framing(events):
    with pytest.raises(ValueError,match='camera framing'):validate_manifest(dict(format='omnishot-video',version=1,source='source.mp4',metadata=dict(camera_framing=events),options={}))


@pytest.mark.parametrize('shape',['Circle','Square','Rounded','Rectangle'])
@pytest.mark.parametrize('fullscreen',[False,True])
def test_camera_flip_matches_composition_without_altering_track(shape,fullscreen):
    from types import SimpleNamespace
    from omnishot.camera import CameraPreview
    from omnishot.video_position import camera_rect
    app=QApplication.instance() or QApplication([])
    frame=np.full((120,160,3),[220,30,30],np.uint8);frame[:,80:]=[30,30,220];original=frame.copy()
    preview=CameraPreview(SimpleNamespace(latest=frame),shape,size=200,mirror=True)
    preview.fullscreen=fullscreen;preview.refresh_frame();image=preview.grab().toImage()
    assert image.pixelColor(image.width()//4,image.height()//2).blue()>200
    assert image.pixelColor(image.width()*3//4,image.height()//2).red()>200
    source=np.full((300,480,3),[30,140,60],np.uint8)
    opts=dict(camera=True,camera_shape=shape,camera_mirror=True,camera_fullscreen=fullscreen,camera_shadow=False,padding=0,cursor=False,keys=False,clicks=False)
    result=compose_frame(source,0,{},opts,frame);r=camera_rect(result.width(),result.height(),.75,opts)
    assert result.pixelColor(round(r.x()+r.width()/4),round(r.center().y())).blue()>200
    assert result.pixelColor(round(r.x()+r.width()*3/4),round(r.center().y())).red()>200
    assert np.array_equal(frame,original)
    preview.timer.stop();preview.close()
