import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.studio import compose_frame,export_studio
from omnishot.motion_blur import shutter_times,blur_level


def pixels(image):
    return np.asarray(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3).copy()


def test_blur_is_time_local_increases_with_intensity_and_respects_cuts():
    app=QApplication.instance() or QApplication([])
    frame=np.full((180,320,3),255,np.uint8);meta=dict(cursor=[dict(t=0,x=.1,y=.5),dict(t=1,x=.9,y=.5)],events=[])
    opts=dict(fps=10,cursor=True,cursor_style='Dot',cursor_size=20,cursor_color='#000000',cursor_outline='#000000',padding=0)
    images=[pixels(compose_frame(frame,.5,meta,dict(opts,motion_blur=level))) for level in range(4)]
    starts=[np.where(image[:,:,0]<220)[1].min() for image in images]
    assert starts[0]>starts[1]>starts[2]>starts[3],starts
    repeat=pixels(compose_frame(frame,.5,meta,dict(opts,motion_blur=3)));assert np.array_equal(repeat,images[3])
    compose_frame(frame,.9,meta,dict(opts,motion_blur=3))
    assert np.array_equal(pixels(compose_frame(frame,.5,meta,dict(opts,motion_blur=3))),repeat)
    assert np.array_equal(pixels(compose_frame(frame,.5,meta,dict(opts,motion_blur=3,cuts=[(.2,.5)]))),images[0])
    assert np.array_equal(pixels(compose_frame(frame,.5,{},dict(opts,motion_blur=3))),frame)
    assert shutter_times(.6,dict(opts,motion_blur=3,speed=2))[0]==pytest.approx(.4)
    assert shutter_times(.6,dict(opts,motion_blur=3,speed=2,start=.55))[0]==.55


def test_zoom_blur_changes_edges_without_blurring_static_framing():
    app=QApplication.instance() or QApplication([])
    frame=np.zeros((180,320,3),np.uint8);frame[:,::12]=255
    zoom=dict(start=0,end=1,scale=2,x=.5,y=.5);opts=dict(cursor=False,zooms=[zoom],fps=15)
    sharp=pixels(compose_frame(frame,.15,{},opts));blurred=pixels(compose_frame(frame,.15,{},dict(opts,motion_blur=3)))
    assert np.mean(np.abs(sharp.astype(float)-blurred))>5
    sharp=pixels(compose_frame(frame,.5,{},opts));blurred=pixels(compose_frame(frame,.5,{},dict(opts,motion_blur=3)))
    assert np.array_equal(sharp,blurred)


def test_export_blur_matches_compositor_and_does_not_ghost_across_cuts(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/'source.mp4';dest=tmp_path/'export.mp4'
    backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=white:size=320x180:rate=10:duration=1','-c:v','libx264',source])
    meta=dict(cursor=[dict(t=0,x=.1,y=.5),dict(t=1,x=.9,y=.5)],events=[])
    opts=dict(fps=10,speed=1,width=320,padding=0,motion_blur=3,cursor_style='Dot',cursor_color='#000000',cursor_outline='#000000',cursor_size=20,cuts=[(.2,.5)])
    export_studio(source,dest,meta,opts)
    cap=cv2.VideoCapture(str(dest));cap.set(cv2.CAP_PROP_POS_FRAMES,2);ok,frame=cap.read();assert ok
    expected=pixels(compose_frame(np.full((180,320,3),255,np.uint8),.5,meta,opts))
    assert np.mean(np.abs(frame[:,:,::-1].astype(float)-expected))<1
    cap.release()


def test_legacy_blur_migration_level_persistence_and_manifest_validation(tmp_path):
    from omnishot.recording import VideoEditor
    from omnishot.video_project import validate_manifest
    app=QApplication.instance() or QApplication([]);source=tmp_path/'source.mp4'
    backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=white:size=160x90:rate=10:duration=1','-c:v','libx264',source]);store=backend.Store(tmp_path/'data')
    store.video_edit_path(source).parent.mkdir(exist_ok=True);store.atomic_json(store.video_edit_path(source),dict(options=dict(blur=True)))
    e=VideoEditor(source,store);e.player.pause();assert e.motion.value()==2 and e.motion_label.text()=='Medium'
    e.motion.setValue(3);e.close();e=VideoEditor(source,store);e.player.pause();assert e.motion.value()==3;e.motion.setValue(0);e.close()
    e=VideoEditor(source,store);e.player.pause();assert e.motion.value()==0 and not e.studio_options()['blur'];e.close();app.processEvents()
    assert blur_level(dict(blur=True))==2 and blur_level(dict(blur=False))==0
    manifest=dict(format='omnishot-video',version=1,source='source.mp4')
    for level in (-1,4,True,'Medium',float('nan')):
        with pytest.raises(ValueError,match='motion blur'):validate_manifest(dict(manifest,options=dict(motion_blur=level)))
