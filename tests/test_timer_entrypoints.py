from types import SimpleNamespace
import pytest
from omnishot.app import Controller
from omnishot import app as application


@pytest.mark.parametrize('freeze,geometry',[(False,None),(True,None),(False,'10,20 300x200'),(True,'10,20 300x200')])
def test_timer_selects_before_delay_and_never_grabs_before_countdown(freeze,geometry,monkeypatch):
    state=Controller.__new__(Controller);state.busy=False;state.panel=None
    state.store=SimpleNamespace(settings=dict(delay=5,freeze=freeze,include_cursor=False),capture_name_context=lambda:{},save_settings=lambda:None)
    state.hide_capture_windows=lambda:None;state.restore_capture_windows=lambda:None
    jobs=[];timed=[];selected=[];frozen=[]
    monkeypatch.setattr(application.QTimer,'singleShot',lambda delay,work:jobs.append((delay,work)))
    monkeypatch.setattr(application,'background',lambda work,done,fail:done(work()))
    monkeypatch.setattr(application.backend,'grab',lambda *args,**kwargs:pytest.fail('Captured before countdown'))
    def select(*args,**kwargs):selected.append(True);return (10,20,300,200),5
    monkeypatch.setattr(application.backend,'select_region',select)
    state.frozen_selection=lambda *args,**kwargs:frozen.append((args,kwargs))
    state.timed_capture=lambda *args:timed.append(args)
    state.capture('timer',dict(delay=7,geometry=geometry,action='copy'))
    assert jobs[0][0]==180;assert not selected and not timed
    jobs[0][1]()
    if freeze and not geometry:
        assert frozen[0][1]==dict(capture_kind='Self timer',timer_delay=7)
        assert not selected and not timed
    else:
        assert timed[0][0]==(10,20,300,200) and timed[0][1]=='copy' and timed[0][-1]==7
        assert bool(selected)==(geometry is None)
        assert timed[0][3]==(geometry is None) and timed[0][5]==(geometry is None)
        assert state.store.settings['previous_area']==[10,20,300,200]


def test_live_selection_uses_the_active_omarchy_palette(monkeypatch):
    from omnishot import backend,theme
    monkeypatch.setattr(theme,'_current',dict(background='#123456',accent='#abcdef'))
    calls=[]
    monkeypatch.setattr(backend,'run',lambda args,**kwargs:calls.append(args) or b'10,20 300x200|0\n')
    assert backend.select_region(with_modifiers=True)==((10,20,300,200),0)
    assert calls[0][2]=='#12345655' and calls[0][4]=='#abcdefff'
