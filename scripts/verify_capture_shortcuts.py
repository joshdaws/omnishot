"""Native configurable area-action shortcuts, settings and latest screenshot."""
import io,json,os,subprocess,sys,time,tempfile,shutil,shlex
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QPoint,QPointF
from PySide6.QtGui import QImage,QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QDialogButtonBox,QScrollArea
from PySide6.QtNetwork import QLocalServer
from PySide6.QtTest import QTest
from omnishot import backend,theme
from omnishot.app import Controller
import omnishot.app as application
from omnishot.shortcuts import ShortcutsDialog
from omnishot.widgets import place_window,Settings,JOBS
from omnishot.editor import Editor
from PIL import Image

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
socket_dir=Path(tempfile.mkdtemp(prefix='ob-',dir='/tmp'));os.environ['TMPDIR']=str(socket_dir)
os.environ['OMNISHOT_DATA_DIR']=str(out/'data');os.environ['XDG_CONFIG_HOME']=str(out/'config')
config=out/'config/hypr/bindings.lua';config.parent.mkdir(parents=True,exist_ok=True);config.write_text('-- Unrelated fixture shortcut\no.bind("CTRL + F6", "Fixture action", "true")\n')
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);manager=theme.ThemeManager(app)
state=Controller(app);state.store.settings.update(background_preset='None',overlay_timeout=0,output_dir=str(out/'saved'),after_capture='overlay',after_capture_extra=['copy','save'],freeze=sys.argv[3]=='combined',capture_shortcut_actions=sys.argv[3]!='combined');combined=sys.argv[3]=='combined';errors=[];application.error=lambda parent,message:errors.append(str(message))
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
QTimer.singleShot(29000,watchdog)
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
        import faulthandler
        with (out/'threads.log').open('w') as log:faulthandler.dump_traceback(file=log,all_threads=True)
        (out/'failure.json').write_text(json.dumps(dict(errors=errors,received=received,busy=state.busy,jobs=len(JOBS),selectors=len(state.selectors),clients=backend.hypr('clients'),layers=backend.hypr('layers'),bindings=backend.hypr('binds'),server=server.fullServerName()),indent=2))
    assert predicate(),errors
def client(widget):return next((c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle()),None)
def pointer(widget,point=None):
    top=widget.window();native=client(top);point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(native['at'][0]+point.x()-2,native['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def click(widget):
    for scroll in widget.window().findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(widget):scroll.ensureWidgetVisible(widget);QTest.qWait(80)
    pointer(widget);command('click 272');QTest.qWait(120)
class Source(QWidget):
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#e35a44'))
sink=Source();sink.setWindowTitle('OmniShot Shortcut Receiver');sink.resize(800,500);sink.show();place_window(sink,350,250)
def focus_source():
    pointer(sink,QPoint(30,30));backend.focus_window(client(sink)['address']);QTest.qWait(100);assert backend.hypr('activewindow')['title']==sink.windowTitle()
def selecting():
    if combined:return bool(state.selectors)
    return any(row.get('namespace')=='selection' for monitor in backend.hypr('layers').values() for rows in monitor['levels'].values() for row in rows)
def select():
    wait(selecting);backend.move_cursor(448,350);command('move 2 0');QTest.qWait(70)
    command('button 272 1');QTest.qWait(70);command('move 300 180');QTest.qWait(100);command('button 272 0')
def close_results():
    for window in list(state.windows):window.close()
    state.close_pins();state.close_all_overlays();QTest.qWait(150)
try:
    assignments=[('area-copy',65),('area-save',66),('area-pin',67),('area-annotate',68),('last-screenshot',87)]
    dialog=ShortcutsDialog(state.store);dialog.show();wait(lambda:client(dialog));QTest.qWait(200);backend.focus_window(client(dialog)['address']);QTest.qWait(120)
    for action,code in assignments:
        click(dialog.fields[action]);command(f'key {code} 4');QTest.qWait(150)
    dialog.grab().save(str(out/'shortcuts.png'));click(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save));assert not dialog.isVisible()
    values=backend.Store(state.store.root).settings['shortcuts']
    assert all(values[action]=='Ctrl+F'+str(number) for (action,code),number in zip(assignments,range(7,12)))
    prefix='env TMPDIR='+shlex.quote(str(socket_dir))+' ';suffix=' >>'+shlex.quote(str(out/'cli.log'))+' 2>&1'
    generated='o={bind=function(key,label,cmd) return hl.bind(key,hl.dsp.exec_cmd('+json.dumps(prefix)+'..cmd..'+json.dumps(suffix)+'),{description=label}) end}; dofile('+json.dumps(str(config))+')'
    # Capture loads/unloads its compositor plugin, which reloads configuration.
    # Persist the exact generated commands in this isolated compositor's config.
    runtime=Path(os.environ['XDG_RUNTIME_DIR']).resolve();native_config=runtime/'hyprland.lua'
    assert runtime.parent==Path('/tmp') and runtime.name.startswith('os-') and native_config.is_file()
    native_config.write_text(native_config.read_text()+'\n'+generated+'\n');backend.run(['hyprctl','reload']);QTest.qWait(150)
    assert any(b.get('description')=='Fixture action' for b in backend.hypr('binds'))
    settings=Settings(state.store,'shortcuts');settings.show();wait(lambda:client(settings));QTest.qWait(150)
    field=settings.fields['capture_shortcut_actions'];pointer(field,QPoint(8,field.height()//2));command('click 272');QTest.qWait(100);assert field.isChecked()==combined
    settings.grab().save(str(out/'settings.png'));click(settings.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save))
    assert backend.Store(state.store.root).settings['capture_shortcut_actions']==combined
    checks=[]
    for action,code in assignments[:4]:
        checkpoint(action)
        close_results();backend.run(['wl-copy','--clear']);before=len(state.store.history());saved_before=len(list((out/'saved').glob('*')))
        focus_source();command(f'key {code} 4');select();wait(lambda:len(state.store.history())==before+1 and not state.busy and not JOBS)
        QTest.qWait(180);path=Path(state.store.history()[0]['path']);image=Image.open(path).convert('RGB')
        assert abs(image.width-480)<=2 and abs(image.height-288)<=2 and image.getpixel((100,100))==(227,90,68),image.size
        expected=({'copy','save','overlay'} if combined else set())|{action.removeprefix('area-')}
        assert bool(state.overlays)==('overlay' in expected) and bool(state.pins)==('pin' in expected)
        assert bool([w for w in state.windows if isinstance(w,Editor)])==('annotate' in expected)
        assert len(list((out/'saved').glob('*')))==saved_before+('save' in expected)
        if 'save' in expected:
            exported=Path(state.store.metadata(path)['autosaved_files'][0]['path']);assert Image.open(exported).convert('RGB').tobytes()==image.tobytes()
        clipboard=subprocess.run(['wl-paste','--list-types'],capture_output=True,text=True,timeout=3)
        if 'copy' in expected:
            assert 'image/png' in clipboard.stdout
            copied=Image.open(io.BytesIO(backend.run(['wl-paste','--type','image/png']))).convert('RGB');assert copied.tobytes()==image.tobytes()
        else:assert 'image/png' not in clipboard.stdout
        checks.append(dict(command=action,actions=sorted(expected),pixels=list(image.size)))
    # Annotate through real input, then use the last-screenshot key after newer
    # imported images, clipboard content and a recording enter History.
    editor=next(w for w in state.windows if isinstance(w,Editor));latest=editor.path;place_window(editor,30,40);QTest.qWait(150)
    click(editor.toolbar.widgetForAction(editor.tools['arrow']))
    a=editor.view.mapFromScene(QPointF(40,60));b=editor.view.mapFromScene(QPointF(300,160));pointer(editor.view.viewport(),a)
    command('button 272 1');QTest.qWait(60);command(f'move {b.x()-a.x()} {b.y()-a.y()}');QTest.qWait(100);command('button 272 0');QTest.qWait(150)
    assert len(editor.objects)==1;close_results()
    external=out/'external.png';Image.new('RGB',(90,60),'blue').save(external);state.store.import_file(external)
    clipboard_image=QImage(90,60,QImage.Format.Format_RGB32);clipboard_image.fill(QColor('green'));state.store.add(image=clipboard_image)
    recording=out/'recording.mp4';backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=64x64:r=5','-t','0.4','-c:v','libx264','-y',str(recording)])
    owned=state.store.add(source=recording,kind='video');state.store.name_capture(owned)
    focus_source();command('key 87 4');wait(lambda:any(isinstance(w,Editor) for w in state.windows));reopened=next(w for w in state.windows if isinstance(w,Editor))
    assert reopened.path==latest and len(reopened.objects)==1;QTest.qWait(180)
    assert reopened.zoom_button.width()>=reopened.zoom_button.fontMetrics().horizontalAdvance(reopened.zoom_button.text())+40
    reopened.grab().save(str(out/'last-screenshot.png'));close_results()
    # Explicit CLI action remains exclusive regardless of the shortcut setting.
    cli_env=dict(os.environ);cli_env['TMPDIR']=str(socket_dir)
    before=len(state.store.history());saved_before=len(list((out/'saved').glob('*')))
    focus_source();subprocess.run([str(Path.home()/'.local/bin/omnishot'),'area','--geometry','450,350 300x180','--action','copy'],env=cli_env,check=True,capture_output=True,timeout=3)
    wait(lambda:len(state.store.history())==before+1 and not state.busy and not JOBS)
    assert not state.overlays and not state.pins and not state.windows and len(list((out/'saved').glob('*')))==saved_before
    # Cancel via the real selector and ensure none of the named/default actions run.
    before=len(state.store.history());focus_source();command('key 66 4');wait(selecting)
    if combined:wait(lambda:backend.hypr('activewindow').get('title')==state.selectors[0].windowTitle())
    QTest.qWait(100);command('key 1 0');wait(lambda:not state.busy and not selecting())
    assert len(state.store.history())==before and not state.overlays and not state.pins and not state.windows
    assert received==[action for action,code in assignments]+['area','area-save'],received
    assert not errors,errors
    report=dict(combined_actions=combined,freeze=combined,native_shortcuts=checks,installed_cli_ipc=True,preference_saved=True,unrelated_binding_preserved=True,latest_screenshot_skips_imports_clipboard_and_recording=True,editable_annotation_restored=True,explicit_action_exclusive=True,escape_cancels_without_actions=True,display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');command('button 272 0');server.close();state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3);shutil.rmtree(socket_dir)
