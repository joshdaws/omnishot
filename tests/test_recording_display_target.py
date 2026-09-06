from PySide6.QtWidgets import QApplication
from omnishot import backend,recording

FIRST=dict(name='first',x=0,y=0,width=2880,height=1800,scale=1.6,focused=False)
SECOND=dict(name='second',x=1800,y=0,width=1920,height=1080,scale=1,focused=True)
OPTIONS=dict(mode='Fullscreen',delay=600,fps=10,quality='high',cursor=False,size='Native',scale_video=True,system=False,mic=False)


def test_fullscreen_keeps_display_chosen_before_countdown(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(backend,'capture_monitors',lambda:[dict(FIRST,focused=True),dict(SECOND,focused=False)])
    monkeypatch.setattr(backend,'hypr',lambda command:dict(x=1900,y=100))
    rec=recording.Recorder(backend.Store(tmp_path/'data'),None,OPTIONS)
    rec.timer.stop();rec.countdown.stop()
    try:
        monkeypatch.setattr(backend,'hypr',lambda command:[dict(FIRST,focused=True),dict(SECOND,focused=False)])
        command=recording.recorder_command(rec.path,None,rec.opts)
        assert command[command.index('-w')+1]=='second'
        assert command[command.index('-s')+1]=='1920x1080'
    finally:rec.shutdown();rec.close()


def test_explicit_output_survives_restart_and_monitor_layout_change(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(backend,'capture_monitors',lambda:[dict(FIRST,focused=True),dict(SECOND,focused=False)])
    rec=recording.Recorder(backend.Store(tmp_path/'data'),None,dict(OPTIONS,capture_output='second'))
    rec.timer.stop();rec.countdown.stop()
    try:
        monkeypatch.setattr(backend,'hypr',lambda command:[FIRST,dict(SECOND,x=-1080,transform=1)])
        command=recording.recorder_command(rec.path,None,rec.opts)
        assert command[command.index('-w')+1]=='second'
        assert command[command.index('-s')+1]=='1080x1920'
    finally:rec.shutdown();rec.close()


def test_disconnected_fullscreen_output_is_not_replaced(tmp_path,monkeypatch):
    import pytest
    from omnishot.recording_options import recording_monitors
    monkeypatch.setattr(backend,'hypr',lambda command:[dict(FIRST,focused=True)])
    with pytest.raises(RuntimeError,match='no longer connected'):
        recording.recorder_command(tmp_path/'out.mp4',None,dict(OPTIONS,capture_output='second'))
    with pytest.raises(RuntimeError,match='no longer connected'):recording_monitors([FIRST],'second')


def test_region_capture_does_not_inherit_fullscreen_target(tmp_path,monkeypatch):
    def unexpected(command):raise AssertionError('Region source should not query a fullscreen target')
    monkeypatch.setattr(backend,'hypr',unexpected)
    command=recording.recorder_command(tmp_path/'out.mp4',(-1800,740,320,180),dict(OPTIONS,capture_output='second'))
    assert command[command.index('-w')+1]=='region'
    assert command[command.index('-region')+1]=='320x180+-1800+740'
    assert command[command.index('-s')+1]=='320x180'


def test_pointer_display_handles_negative_rotated_bounds_and_focus_fallback():
    from omnishot.recording_options import recording_output
    monitors=[dict(FIRST,focused=True),dict(SECOND,x=-1080,transform=1,focused=False)]
    assert recording_output(monitors,dict(x=-100,y=1800))=='second'
    assert recording_output(monitors,dict(x=0,y=100))=='first'
    assert recording_output(monitors,dict(x=-1081,y=100))=='first'


def test_fullscreen_monitor_null_blockers_allow_capture(monkeypatch):
    monitors=[dict(FIRST,solitaryBlockedBy=None),dict(SECOND,solitaryBlockedBy=[])]
    monkeypatch.setattr(backend,'hypr',lambda command:monitors)
    assert backend.capture_monitors()==monitors
    assert not backend.session_locked(monitors+[{}])


def test_locked_output_is_detected_alongside_null_blockers(monkeypatch):
    import pytest
    monitors=[dict(FIRST,solitaryBlockedBy=None),dict(SECOND,solitaryBlockedBy=['LOCK'])]
    monkeypatch.setattr(backend,'hypr',lambda command:monitors)
    assert backend.session_locked(monitors)
    with pytest.raises(RuntimeError,match='Unlock'):backend.capture_monitors()


def test_window_placement_assigns_the_destination_monitor_without_following(monkeypatch):
    calls=[];client=dict(address='0x123',monitor=0,size=[400,60])
    monitors=[dict(FIRST,id=0),dict(SECOND,id=1)]
    monkeypatch.setattr(backend,'hypr',lambda name:[client] if name=='clients' else monitors)
    monkeypatch.setattr(backend,'run',lambda args,**kwargs:calls.append(args))
    backend.move_window('0x123',1900,900)
    assert len(calls)==2 and 'monitor="1",follow=false' in calls[0][-1]
    assert 'x = 1900, y = 900' in calls[1][-1]
    calls.clear();backend.move_window('0x123',100,200)
    assert len(calls)==1 and 'x = 100, y = 200' in calls[0][-1]


def test_window_placement_uses_center_with_negative_rotated_display(monkeypatch):
    calls=[];client=dict(address='0x123',monitor=0,size=[400,60])
    monitors=[dict(FIRST,id=0),dict(SECOND,id=1,x=-1080,transform=1)]
    monkeypatch.setattr(backend,'hypr',lambda name:[client] if name=='clients' else monitors)
    monkeypatch.setattr(backend,'run',lambda args,**kwargs:calls.append(args))
    backend.move_window('0x123',-1090,1500)
    assert len(calls)==2 and 'monitor="1",follow=false' in calls[0][-1]
    assert 'x = -1090, y = 1500' in calls[1][-1]
