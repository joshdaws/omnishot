import pytest
from omnishot.api import parse_url,url_geometry


def test_url_coordinates_actions_and_booleans():
    args=parse_url("omnishot://scrolling-capture?x=100&y=120&width=200&height=150&display=1&start=true&autoscroll=false")
    assert args["command"]=="scroll" and args["start"] and not args["autoscroll"]
    monitors=[{"x":-1920,"y":0,"width":2880,"height":1800,"scale":1.5}]
    assert url_geometry(args["url_coordinates"],monitors,{"x":0,"y":0})==(-1820,930,200,150)
    with pytest.raises(ValueError):url_geometry({"width":9999},monitors,{"x":0,"y":0})
    with pytest.raises(ValueError):parse_url("omnishot://capture-area?action=upload")
    assert parse_url("cleanshot://open-annotate?filepath=%2Ftmp%2Fmy%20image.png")["path"]=="/tmp/my image.png"


def test_desktop_file_uri_keeps_spaces(tmp_path):
    from omnishot.app import parse_args
    path=tmp_path/"my image.png";path.write_bytes(b"image")
    args=parse_args([path.as_uri()]);assert args["command"]=="open" and args["path"]==str(path)


def test_url_coordinates_respect_portrait_rotation_and_cursor_display():
    displays=[dict(x=-1920,y=0,width=1920,height=1080,scale=1),dict(x=0,y=0,width=1920,height=1080,scale=1,transform=1)]
    assert url_geometry(dict(x=20,y=30,width=400,height=600),displays,dict(x=500,y=1700))==(20,1290,400,600)
    with pytest.raises(ValueError):url_geometry(dict(x=1000,y=0,width=400,height=600),displays,dict(x=500,y=1700))


def test_disabling_url_commands_preserves_direct_cli_actions(monkeypatch):
    from types import SimpleNamespace
    from omnishot.app import Controller
    state=Controller.__new__(Controller);state.store=SimpleNamespace(settings={'url_api_enabled':False});calls=[];errors=[]
    state.capture=lambda command,args:calls.append(command)
    monkeypatch.setattr('omnishot.app.error',lambda parent,message:errors.append(str(message)))
    state.dispatch(parse_url('omnishot://capture-area?x=0&y=0&width=200&height=100'))
    assert not calls and errors and 'disabled' in errors[0]
    state.dispatch(dict(command='area'));assert calls==['area']


@pytest.mark.parametrize('start,auto',[(False,True),(True,False),(True,True),(False,False),(None,True)])
def test_scroll_start_and_auto_mode_are_independent(start,auto,monkeypatch):
    from types import SimpleNamespace
    from omnishot.app import Controller
    from omnishot import app as application
    panel=SimpleNamespace(auto=False,running=False)
    panel.start=lambda:setattr(panel,'running',True)
    panel.set_auto=lambda value:setattr(panel,'auto',value)
    state=Controller.__new__(Controller);state.busy=False;state.panel=None
    state.store=SimpleNamespace(settings=dict(freeze=False,include_cursor=False),capture_name_context=lambda:{},save_settings=lambda:None)
    state.hide_capture_windows=lambda:None;state.restore_capture_windows=lambda:None;state.scroll=lambda *a,**k:setattr(state,'panel',panel)
    jobs=[];monkeypatch.setattr(application.QTimer,'singleShot',lambda delay,work:jobs.append(work))
    monkeypatch.setattr(application,'background',lambda work,done,fail:done(work()))
    args=dict(geometry='20,30 400x250',autoscroll=auto)
    if start is not None:args['start']=start
    state.capture('scroll',args);jobs.pop(0)()
    assert panel.auto==auto and not panel.running
    for job in jobs:job()
    assert panel.running==bool(start)
