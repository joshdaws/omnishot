import pytest
from omnishot.clean_capture import capture_target, CleanCapture
from omnishot.recording import recorder_command


def test_fractional_negative_and_rotated_outputs():
    displays = [dict(name="left", x=-1800, y=0, width=2880, height=1800, scale=1.6, focused=True),
                dict(name="portrait", x=0, y=0, width=1920, height=1080, scale=1, transform=1)]
    assert capture_target(displays) == ("left", None, (-1800, 0, 1800, 1125))
    assert capture_target(displays, (-1700, 100, 800, 500))[1] == (100, 100, 800, 500)
    assert capture_target(displays, (0, 0, 1080, 1920))[0] == "portrait"
    assert capture_target(displays, (-100, 0, 200, 100)) is None
    with pytest.raises(ValueError): capture_target(displays, (0, 0, 1, 100))


def test_capture_environment_does_not_inherit_test_socket(monkeypatch):
    monkeypatch.setenv("OMNISHOT_CAPTURE_SOCKET", "/test/socket")
    monkeypatch.setenv("OMNISHOT_CAPTURE_REGION", "bad geometry")
    c = CleanCapture([dict(name="display", x=0, y=0, width=1920, height=1080, scale=1)], None, True)
    c.enabled = True
    env = c.environment()
    assert "OMNISHOT_CAPTURE_SOCKET" not in env and "OMNISHOT_CAPTURE_REGION" not in env
    assert env["OMNISHOT_CAPTURE_OUTPUT"] == "display" and env["OMNISHOT_CAPTURE_CURSOR"] == "1"


def test_clean_source_keeps_audio_and_pause_capable_recorder():
    opts = dict(fps=60, quality="high", cursor=True, studio=True, size="Native", system=True, mic=True,
                system_device="speakers.monitor", mic_device="microphone")
    cmd = recorder_command("out.mp4", (10, 20, 640, 360), opts, clean=True)
    assert cmd[0] == "gpu-screen-recorder"
    assert cmd[cmd.index("-cursor")+1] == "no"
    assert [cmd[i+1] for i,value in enumerate(cmd) if value=="-a"] == ["speakers.monitor","microphone"]
    assert cmd[cmd.index("-p")+1].endswith("/native/clean-capture.so")


def test_capture_releases_only_its_own_loaded_extension(monkeypatch,native_capture_files):
    from omnishot import backend
    monitor=dict(name='display',x=0,y=0,width=1920,height=1080,scale=1)
    calls=[];monkeypatch.setattr(backend,'run',lambda args,**kwargs:calls.append(args) or (b'false' if args[1]=='repl' else b'ok'))
    monkeypatch.setattr(backend,'hypr',lambda query:[])
    capture=CleanCapture([monitor],None);capture.start();capture.stop()
    assert [call[2] for call in calls if call[1]=='plugin']==['load','unload']
    assert calls[0][-1]==calls[-1][-1] and calls[0][-1].is_absolute() and not calls[0][-1].is_symlink()
    assert not capture.enabled
    calls.clear();monkeypatch.setattr(backend,'hypr',lambda query:[dict(name='omnishot-clean-mirror')])
    capture=CleanCapture([monitor],None);capture.start();capture.stop()
    assert not any(call[1]=='plugin' for call in calls)


def test_independent_mirror_consumers_and_failed_registration(monkeypatch,native_capture_files):
    from omnishot import backend
    from omnishot.clean_capture import MirrorLease,SelectionMirror,CursorMirror
    plugins=[];calls=[];registered={};fail=[False]
    monkeypatch.setattr(MirrorLease,'roles',{});monkeypatch.setattr(MirrorLease,'loaded_path',None)
    monkeypatch.setattr(backend,'hypr',lambda query:plugins)
    def run(args,**kwargs):
        calls.append(args)
        if args[1:3]==['plugin','load']:plugins.append({'name':'omnishot-clean-mirror'})
        elif args[1:3]==['plugin','unload']:plugins.clear()
        elif args[1]=='eval':
            if fail[0]:raise RuntimeError('registration failed')
            role=args[-1].split('omnishot.')[1].split('(')[0];registered[role]=not args[-1].endswith('(0)')
        elif args[1]=='repl':return b'true' if any(registered.values()) else b'false'
        return b'ok'
    monkeypatch.setattr(backend,'run',run)
    first=SelectionMirror();second=SelectionMirror();recording=MirrorLease('clean_capture');scrolling=CursorMirror()
    first.start();second.start();recording.start();scrolling.start();first.stop();assert registered['selection_capture']
    recording.stop();assert plugins and registered['selection_capture']
    second.stop();assert plugins and registered['cursor_capture']
    scrolling.stop();assert not plugins and not any(registered.values())
    fail[0]=True
    with pytest.raises(RuntimeError,match='registration'):SelectionMirror().start()
    assert not plugins and MirrorLease.loaded_path is None
