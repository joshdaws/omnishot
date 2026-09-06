import pytest
from omnishot.clean_capture import CleanCapture

MONITORS=[dict(name='left',x=-1800,y=0,width=2880,height=1800,scale=1.6),
          dict(name='right',x=0,y=0,width=1920,height=1080,scale=1)]


def test_spanning_recording_keeps_clean_capture(monkeypatch,native_capture_files):
    capture=CleanCapture(MONITORS,(-100,100,300,200),True)
    calls=[]
    monkeypatch.setattr(capture.lease,'start',lambda:calls.append('start'))
    monkeypatch.setattr(capture.lease,'stop',lambda:calls.append('stop'))
    assert capture.start()
    env=capture.environment()
    assert env['OMNISHOT_CAPTURE_PARTS']=='300,200\nleft\t1700,100 100x200\t0,0\nright\t0,100 200x200\t100,0'
    assert env['OMNISHOT_CAPTURE_CURSOR']=='1'
    assert 'OMNISHOT_CAPTURE_OUTPUT' not in env
    assert capture.target[2]==(-100,100,300,200)
    capture.stop();assert calls==['start','stop'] and not capture.enabled


def test_spanning_geometry_retains_gaps_and_rotated_output(monkeypatch):
    displays=[MONITORS[0],dict(MONITORS[1],x=100,y=50,transform=1)]
    capture=CleanCapture(displays,(-100,0,400,150))
    capture.enabled=True
    assert capture.environment()['OMNISHOT_CAPTURE_PARTS']=='400,150\nleft\t1700,0 100x150\t0,0\nright\t0,0 200x100\t200,50'


def test_region_outside_every_display_is_rejected():
    with pytest.raises(ValueError,match='does not overlap'):
        CleanCapture(MONITORS,(5000,0,200,200))


def test_single_output_clears_inherited_composite_layout(monkeypatch):
    monkeypatch.setenv('OMNISHOT_CAPTURE_PARTS','stale layout')
    capture=CleanCapture(MONITORS,(-500,100,200,200));capture.enabled=True
    assert 'OMNISHOT_CAPTURE_PARTS' not in capture.environment()
    assert capture.environment()['OMNISHOT_CAPTURE_OUTPUT']=='left'


def test_center_in_display_gap_uses_output_for_encoder_sizing_only():
    displays=[dict(MONITORS[0],x=0),dict(MONITORS[1],x=2100,y=250)]
    capture=CleanCapture(displays,(1700,200,600,300));capture.enabled=True
    assert capture.encoder_rect==(2760,640,600,300)
    assert capture.controls_bounds==(2100,250,1920,1080)
    assert capture.target[2]==(1700,200,600,300)
    assert capture.environment()['OMNISHOT_CAPTURE_PARTS']=='600,300\nleft\t1700,200 100x300\t0,0\nright\t0,0 200x250\t400,50'
