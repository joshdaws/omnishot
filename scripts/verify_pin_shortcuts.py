"""Configured compositor keys → installed CLI → IPC → pinned image actions."""
import json,os,subprocess,sys,time,tempfile,shutil,shlex
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QWidget,QDialogButtonBox,QScrollArea
from PySide6.QtNetwork import QLocalServer
from PySide6.QtTest import QTest
from omnishot import backend,theme
from omnishot.app import Controller
import omnishot.app as application
from omnishot.shortcuts import ShortcutsDialog
from omnishot.widgets import place_window

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
socket_dir=Path(tempfile.mkdtemp(prefix='ob-',dir='/tmp'));os.environ['TMPDIR']=str(socket_dir)
os.environ['OMNISHOT_DATA_DIR']=str(out/'data');os.environ['XDG_CONFIG_HOME']=str(out/'config')
config=out/'config/hypr/bindings.lua';config.parent.mkdir(parents=True,exist_ok=True);config.write_text('-- Unrelated fixture shortcut\no.bind("CTRL + F6", "Fixture action", "true")\n')
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);manager=theme.ThemeManager(app)
state=Controller(app);state.store.settings.update(background_preset='None',overlay_timeout=0,output_dir=str(out/'saved'));errors=[];application.error=lambda parent,message:errors.append(str(message))
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
server=QLocalServer();server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
assert server.listen(f'omnishot-{os.getuid()}'),server.errorString()
assert Path(server.fullServerName()).parent==socket_dir,server.fullServerName()
sockets=[];received=[]
def checkpoint(stage):
    (out/'progress.json').write_text(json.dumps(dict(stage=stage,errors=errors,received=received),indent=2))
def watchdog():
    checkpoint('watchdog: '+str(app.activeModalWidget())+' popup: '+str(app.activePopupWidget()))
    popup=app.activePopupWidget();modal=app.activeModalWidget()
    if popup:popup.close()
    if modal:modal.reject()
QTimer.singleShot(24000,watchdog)
def connection():
    socket=server.nextPendingConnection();sockets.append(socket);socket.setProperty('buffer',b'')
    def read():
        data=socket.property('buffer')+bytes(socket.readAll());socket.setProperty('buffer',data)
        if b'\n' in data:
            args=json.loads(data.split(b'\n',1)[0]);received.append(args['command']);socket.disconnectFromServer();state.dispatch(args)
    socket.readyRead.connect(read)
server.newConnection.connect(connection)
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    if not predicate():
        (out/'failure.json').write_text(json.dumps(dict(errors=errors,received=received,bindings=backend.hypr('binds'),server=server.fullServerName()),indent=2))
    assert predicate(),errors
def client(widget):return next((c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle()),None)
def pointer(widget,point=None):
    top=widget.window();native=client(top);point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(native['at'][0]+point.x()-2,native['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def click(widget):
    for scroll in widget.window().findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(widget):scroll.ensureWidgetVisible(widget);QTest.qWait(80)
    pointer(widget);command('click 272');QTest.qWait(120)
class Source(QWidget):
    clicks=0
    def mousePressEvent(self,event):self.clicks+=1;super().mousePressEvent(event)
sink=Source();sink.setWindowTitle('OmniShot Shortcut Receiver');sink.resize(1500,850);sink.show();place_window(sink,20,20)
def focus_source():
    pointer(sink,QPoint(30,30));backend.focus_window(client(sink)['address']);QTest.qWait(100);assert backend.hypr('activewindow')['title']==sink.windowTitle()
try:
    dialog=ShortcutsDialog(state.store);dialog.show();wait(lambda:client(dialog));QTest.qWait(200);backend.focus_window(client(dialog)['address']);QTest.qWait(120)
    for action,code in [('toggle-pins',65),('close-pins',66)]:
        click(dialog.fields[action]);command(f'key {code} 4');QTest.qWait(180)
    dialog.grab().save(str(out/'shortcut-entry.png'))
    assert dialog.fields['toggle-pins'].keySequence().toString()=='Ctrl+F7' and dialog.fields['close-pins'].keySequence().toString()=='Ctrl+F8',({key:field.keySequence().toString() for key,field in dialog.fields.items()},client(dialog),str(app.focusWidget()))
    dialog.grab().save(str(out/'shortcuts.png'));click(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save));assert not dialog.isVisible()
    values=backend.Store(state.store.root).settings['shortcuts'];assert values['toggle-pins']=='Ctrl+F7' and values['close-pins']=='Ctrl+F8'
    assert 'Fixture action' in config.read_text()
    # The isolated compositor has no Omarchy wrapper. Its equivalent calls the
    # exact commands generated by the real shortcut editor and installed CLI.
    prefix='env TMPDIR='+shlex.quote(str(socket_dir))+' '
    suffix=' >>'+shlex.quote(str(out/'cli.log'))+' 2>&1'
    backend.run(['hyprctl','eval','o={bind=function(key,label,cmd) return hl.bind(key,hl.dsp.exec_cmd('+json.dumps(prefix)+'..cmd..'+json.dumps(suffix)+'),{description=label}) end}; dofile('+json.dumps(str(config))+')'])
    assert any(b.get('description')=='Fixture action' for b in backend.hypr('binds'))
    paths=[]
    state.store.settings.update(pin_shadow=True,pin_border=True)
    for color in ('#eb6b55','#54a5cf'):
        image=QImage(320,200,QImage.Format.Format_RGB32);image.fill(QColor(color));path=state.store.add(image=image);paths.append(path);state.pin(path)
    wait(lambda:len(state.pins)==2 and all(client(p) for p in state.pins));first,second=state.pins
    place_window(first,200,240);place_window(second,800,240);QTest.qWait(200)
    pointer(first);backend.scroll_step(False,-1);QTest.qWait(150)
    command('mods 8');QTest.qWait(80);backend.scroll_step(False,1);QTest.qWait(150);command('mods 0');QTest.qWait(80)
    assert first.opacity<1
    pointer(second);QTest.qWait(100);click(second.controls.lock);wait(lambda:second.locked and second.controls.unlock.isVisible());QTest.qWait(250)
    positions=[client(p)['at'] for p in state.pins];sizes=[p.size() for p in state.pins];opacity=first.opacity
    assert all(p.shadow_window.isVisible() for p in state.pins)
    focus_source();command('key 65 4');wait(lambda:all(not p.isVisible() for p in state.pins));QTest.qWait(200)
    assert not second.controls.unlock.isVisible() and all(not p.shadow_window.isVisible() for p in state.pins)
    before=sink.clicks
    for x in (300,900):pointer(sink,QPoint(x-20,340-20));command('click 272');QTest.qWait(100)
    assert sink.clicks==before+2
    command('key 65 4');wait(lambda:all(p.isVisible() for p in state.pins) and second.controls.unlock.isVisible());QTest.qWait(300)
    assert [client(p)['at'] for p in state.pins]==positions and [p.size() for p in state.pins]==sizes
    assert first.opacity==opacity and second.locked and all(p.shadow_window.isVisible() for p in state.pins)
    first.grab().save(str(out/'restored-pin.png'))
    # The restored locked pin continues to pass clicks to the source.
    before=sink.clicks;pointer(second);command('click 272');QTest.qWait(120);assert sink.clicks==before+1
    # Middle click closes the unlocked pin and leaves its history intact.
    pointer(first);command('click 274');wait(lambda:len(state.pins)==1);assert state.pins[0] is second and len(state.store.history())==2
    state.pin(paths[0]);wait(lambda:len(state.pins)==2);state.overlay(paths[0]);wait(lambda:len(state.overlays)==1);QTest.qWait(200)
    focus_source();command('key 65 4');wait(lambda:all(not p.isVisible() for p in state.pins))
    command('key 66 4');wait(lambda:not state.pins);QTest.qWait(200)
    assert len(state.overlays)==1 and state.overlays[0].isVisible() and len(state.store.history())==2
    assert not any(c['pid']==os.getpid() and c['title'].startswith(('OmniShot Pin','OmniShot Locked Pin')) for c in backend.hypr('clients'))
    assert received==['toggle-pins','toggle-pins','toggle-pins','close-pins'],received
    assert not errors,errors
    report=dict(configured_native_pin_shortcuts=True,installed_cli_ipc=True,unrelated_shortcut_preserved=True,hidden_pins_release_input=True,locked_unlock_button_hidden=True,positions_sizes_opacity_restored=True,shadows_restored=True,lock_and_clickthrough_restored=True,native_middle_click=True,close_all_includes_hidden_pins=True,unlock_windows_released=True,preview_and_history_preserved=True,display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');server.close();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
    shutil.rmtree(socket_dir)
