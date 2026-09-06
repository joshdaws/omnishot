from omnishot.overlay_keys import available_actions


def test_hover_keys_preserve_user_bindings_in_other_submaps():
    bindings=[dict(modmask=4,key="c",submap="editor",enabled=False),
              dict(modmask=0,key="space",submap=""),dict(modmask=64,key="S")]
    actions=available_actions(bindings)
    assert "CTRL + C" not in actions and "SPACE" not in actions
    assert actions["CTRL + S"]=="save" and actions["CTRL + E"]=="annotate"
    assert bindings[0]["enabled"] is False and len(bindings)==3


def test_reload_rearms_only_a_visible_eligible_lease_and_never_replaces_another(monkeypatch):
    from PySide6.QtWidgets import QApplication,QWidget
    from omnishot.overlay_keys import OverlayKeys
    from omnishot.capture_countdown import CountdownKeys
    app=QApplication.instance() or QApplication([]);window=QWidget();window.show();keys=CountdownKeys(window);starts=[]
    monkeypatch.setattr(keys,'start',lambda:starts.append(True))
    monkeypatch.setattr('omnishot.overlay_keys.backend.run',lambda *args,**kwargs:b'inactive')
    keys.active=True;keys.poll();assert starts==[True] and not keys.active
    window.hide();keys.active=True;keys.poll();assert starts==[True]
    window.show();window.dragging=True;keys.active=True;keys.poll();assert starts==[True]
    window.dragging=False
    monkeypatch.setattr('omnishot.overlay_keys.backend.run',lambda *args,**kwargs:b'replaced')
    keys.active=True;keys.poll();assert starts==[True] and not keys.active
    keys.stop();window.close()


def test_reload_keeps_hover_requirement_and_rechecks_user_bindings(monkeypatch):
    from PySide6.QtWidgets import QApplication,QWidget
    from omnishot.overlay_keys import OverlayKeys
    from omnishot.capture_countdown import CountdownKeys
    app=QApplication.instance() or QApplication([]);window=QWidget();window.show();hover=OverlayKeys(window)
    monkeypatch.setattr(window,'underMouse',lambda:False);assert not hover.should_rearm()
    monkeypatch.setattr(window,'underMouse',lambda:True);assert hover.should_rearm()
    window.collapsed=True;assert not hover.should_rearm();window.collapsed=False
    keys=CountdownKeys(window);calls=[]
    monkeypatch.setattr(QApplication,'platformName',lambda:'wayland')
    monkeypatch.setattr('omnishot.overlay_keys.backend.run',lambda args,**kwargs:calls.append(args) or (b'inactive' if args[1]=='repl' else b'ok'))
    monkeypatch.setattr('omnishot.overlay_keys.backend.hypr',lambda query:[dict(modmask=0,key='ESCAPE',submap='other')])
    keys.active=True;keys.poll();assert not keys.active
    assert not any('hl.bind(' in args[-1] for args in calls)
    window.close()
