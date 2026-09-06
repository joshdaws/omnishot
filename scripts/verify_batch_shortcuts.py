"""Configured compositor keys → installed CLI → IPC → preview batch actions."""
import json,os,subprocess,sys,time,tempfile,shutil,shlex
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QWidget,QDialogButtonBox,QFileDialog,QLineEdit,QMenu,QScrollArea
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
sink=QWidget();sink.setWindowTitle('OmniShot Batch Shortcut Source');sink.resize(300,200);sink.show();place_window(sink,20,20)
def focus_source():
    backend.focus_window(client(sink)['address']);pointer(sink);QTest.qWait(100);assert backend.hypr('activewindow')['title']==sink.windowTitle()
def overlays(paths):
    for path in paths:state.overlay(path)
    wait(lambda:len(state.overlays)==len(paths));QTest.qWait(200)
try:
    dialog=ShortcutsDialog(state.store);dialog.show();wait(lambda:client(dialog));QTest.qWait(200);backend.focus_window(client(dialog)['address']);QTest.qWait(120)
    for action,code in [('save-all',65),('close-all',66)]:
        click(dialog.fields[action]);command(f'key {code} 4');QTest.qWait(180)
    assert dialog.fields['save-all'].keySequence().toString()=='Ctrl+F7' and dialog.fields['close-all'].keySequence().toString()=='Ctrl+F8'
    dialog.grab().save(str(out/'shortcuts.png'));click(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save));assert not dialog.isVisible()
    values=backend.Store(state.store.root).settings['shortcuts'];assert values['save-all']=='Ctrl+F7' and values['close-all']=='Ctrl+F8'
    assert 'Fixture action' in config.read_text()
    # The isolated compositor has no Omarchy wrapper. Its equivalent calls the
    # exact commands generated by the real shortcut editor and installed CLI.
    prefix='env TMPDIR='+shlex.quote(str(socket_dir))+' '
    suffix=' >>'+shlex.quote(str(out/'cli.log'))+' 2>&1'
    backend.run(['hyprctl','eval','o={bind=function(key,label,cmd) return hl.bind(key,hl.dsp.exec_cmd('+json.dumps(prefix)+'..cmd..'+json.dumps(suffix)+'),{description=label}) end}; dofile('+json.dumps(str(config))+')'])
    assert any(b.get('description')=='Fixture action' for b in backend.hypr('binds'))
    paths=[]
    for color in ('#eb6b55','#54a5cf'):
        image=QImage(320,200,QImage.Format.Format_RGB32);image.fill(QColor(color));path=state.store.add(image=image);state.store.rename(path,'Batch');paths.append(path)
    overlays(paths);state.overlays[0].set_collapsed(True);focus_source();command('key 66 4');wait(lambda:not state.overlays)
    checkpoint('global close passed')
    assert received==['close-all'] and len(state.store.history())==2
    state.dispatch({'command':'restore'});wait(lambda:len(state.overlays)==1);assert state.overlays[0].path==paths[-1]
    state.close_all_overlays();wait(lambda:not state.overlays)
    # The new menu entry is also a real Wayland keyboard-selected action.
    overlays(paths)
    def menu_close():
        menu=app.activePopupWidget()
        try:
            assert isinstance(menu,QMenu)
            items=[a for a in menu.actions() if a.isEnabled() and not a.isSeparator()]
            for _ in range(next(i for i,a in enumerate(items) if a.text()=='Close all previews')+1):command('key 108 0');QTest.qWait(25)
            assert menu.activeAction().text()=='Close all previews';command('key 28 0')
        except Exception as exc:
            errors.append(repr(exc))
            if isinstance(menu,QMenu):menu.close()
    pointer(state.overlays[0]);QTimer.singleShot(200,menu_close);command('click 273');wait(lambda:not state.overlays)
    checkpoint('menu close passed')
    overlays([paths[0],paths[1],paths[0]])
    batch=out/'batch';batch.mkdir();seen=[]
    def folder(cancel=False):
        checkpoint('picker callback '+str(cancel))
        try:
            picker=app.activeModalWidget();assert isinstance(picker,QFileDialog)
            if cancel:
                assert all(not o.timer.isActive() for o in state.overlays)
                QTest.qWait(1200);assert len(state.overlays)==3
                click(picker.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel))
            else:
                field=picker.findChild(QLineEdit,'fileNameEdit');click(field);app.clipboard().setText(str(batch));QTest.qWait(100);command('key 30 4');QTest.qWait(80);command('key 47 4');QTest.qWait(180)
                assert field.text()==str(batch),(field.text(),app.focusWidget())
                if app.activePopupWidget():command('key 1 0');QTest.qWait(100)
                click(picker.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open))
                if picker.isVisible():
                    assert Path(picker.directory().absolutePath())==batch,(picker.directory().absolutePath(),field.text())
                    click(picker.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open))
            seen.append('cancel' if cancel else 'save')
        except Exception as exc:
            errors.append(repr(exc));picker=app.activeModalWidget()
            if picker:picker.reject()
    state.store.settings['overlay_timeout']=1
    for overlay in state.overlays:overlay.timer.start(1000)
    focus_source();QTimer.singleShot(650,lambda:folder(True));command('key 65 4');wait(lambda:seen==['cancel'])
    checkpoint('cancel passed')
    assert len(state.overlays)==3 and not list(batch.iterdir())
    assert all(o.timer.isActive() for o in state.overlays)
    state.store.settings['overlay_timeout']=0
    for overlay in state.overlays:overlay.timer.stop()
    focus_source();QTimer.singleShot(650,folder);command('key 65 4');wait(lambda:not state.overlays)
    assert seen==['cancel','save'] and received==['close-all','save-all','save-all'],(seen,received)
    files=sorted(batch.glob('*.png'));assert [p.name for p in files]==['Batch (2).png','Batch.png']
    assert {QImage(str(p)).pixelColor(100,100).name() for p in files}=={'#eb6b55','#54a5cf'} and len(state.store.history())==2
    state.dispatch({'command':'save-all'});assert app.activeModalWidget() is None
    assert not errors,errors
    report=dict(configured_native_keys=True,installed_cli_ipc=True,unrelated_shortcut_preserved=True,close_all_and_restore=True,collapsed_preview_closed=True,native_close_all_menu=True,save_all_cancel_keeps_previews=True,auto_close_paused_during_picker=True,auto_close_resumes_after_cancel=True,duplicate_previews_save_once=True,unique_names_and_pixels=True,history_preserved=True,no_previews_no_picker=True,display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');server.close();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
    shutil.rmtree(socket_dir)
