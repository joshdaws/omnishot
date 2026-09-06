"""Native preview Trash action, real GIO restore, editable image/video recovery."""
import configparser,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from urllib.parse import quote,unquote
from PySide6.QtCore import QPointF,QTimer
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QMenu,QScrollArea
from PySide6.QtTest import QTest
from omnishot import backend,theme
from omnishot.app import Controller
import omnishot.app as application
from omnishot.api import parse_url
from omnishot.editor import Editor
from omnishot.recording import VideoEditor
from omnishot.widgets import JOBS,place_window

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['OMNISHOT_DATA_DIR']=str(out/'data');os.environ['XDG_DATA_HOME']=str(out/'xdg-data')
(out/'xdg-data').mkdir(exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);manager=theme.ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
state=Controller(app);state.store.settings.update(background_preset='None',overlay_timeout=0);errors=[];application.error=lambda parent,message:errors.append(str(message))
autosave='--autosave' in sys.argv;state.store.settings['output_dir']=str(out/'saved')
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),errors
def client(widget):return next((c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle()),None)
def pointer(widget,point=None):
    top=widget.window();c=client(top);point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(c['at'][0]+point.x()-2,c['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def click(widget):pointer(widget);command('click 272');QTest.qWait(120)
def open_editor(path,kind):
    state.dispatch(parse_url('omnishot://open-annotate?filepath='+quote(str(path))))
    wait(lambda:any(isinstance(w,kind) for w in state.windows) and not JOBS)
    editor=next(w for w in state.windows if isinstance(w,kind));wait(lambda:client(editor));place_window(editor,40,40);QTest.qWait(180);return editor
def trash_restore(path):
    if autosave:state.perform_capture_actions(path,{'save','overlay'},recording=Path(path).suffix=='.mp4')
    else:state.overlay(path)
    wait(lambda:bool(state.overlays));overlay=state.overlays[0];wait(lambda:client(overlay));QTest.qWait(200)
    assert overlay.trash_button.isVisible()==autosave
    saved=None
    if autosave:
        saved=Path(state.store.metadata(path)['autosaved_files'][0]['path']);assert saved.is_file();saved_digest=hashlib.sha256(saved.read_bytes()).hexdigest()
        overlay.grab().save(str(out/('autosaved-video-preview.png' if overlay.is_video else 'autosaved-image-preview.png')))
    def choose_trash():
        menu=app.activePopupWidget();assert isinstance(menu,QMenu)
        # Send real menu navigation, including separators' normal keyboard skip.
        items=[a for a in menu.actions() if not a.isSeparator() and a.isEnabled()]
        count=next(i for i,a in enumerate(items) if a.text()=='Move to Trash')+1
        for _ in range(count):command('key 108 0');QTest.qWait(25)
        assert menu.activeAction().text()=='Move to Trash';command('key 28 0')
    if autosave:click(overlay.trash_button)
    else:pointer(overlay);QTimer.singleShot(200,choose_trash);command('click 273')
    wait(lambda:not Path(path).exists() and not JOBS and not state.overlays)
    trash=out/'xdg-data/Trash';infos=list((trash/'info').glob('*.trashinfo'));assert len(infos)==(2 if autosave else 1),infos
    if saved:assert not saved.exists()
    restored=None;uris=[]
    for info_path in infos:
        info=configparser.ConfigParser(interpolation=None);info.read(info_path);original=Path(unquote(info['Trash Info']['Path']))
        if original.parent==state.store.root/'trash-staging':restored=original
        else:assert original==saved
        assert not original.exists();uris.append('trash:///'+quote(info_path.name[:-10]))
    assert restored
    env=dict(os.environ);env.pop('DBUS_SESSION_BUS_ADDRESS',None)
    result=subprocess.run(['dbus-run-session','--','gio','trash','--restore',*uris],env=env,text=True,capture_output=True,timeout=10)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert restored.is_dir() and not any(p.exists() for p in infos)
    if saved:assert saved.is_file() and hashlib.sha256(saved.read_bytes()).hexdigest()==saved_digest
    return restored
try:
    image=QImage(700,400,QImage.Format.Format_RGB32);image.fill(QColor('#edf2f7'));source=out/'Original screenshot.png';image.save(str(source));digest=hashlib.sha256(source.read_bytes()).hexdigest()
    editor=open_editor(source,Editor);path=editor.path
    click(editor.toolbar.widgetForAction(editor.tools['arrow']))
    start=editor.view.mapFromScene(QPointF(60,100));end=editor.view.mapFromScene(QPointF(450,250));pointer(editor.view.viewport(),start)
    command('button 272 1');QTest.qWait(70);command(f'move {end.x()-start.x()} {end.y()-start.y()}');QTest.qWait(100);command('button 272 0');QTest.qWait(150)
    assert len(editor.objects)==1;expected=editor.render().convertToFormat(QImage.Format.Format_RGBA8888);editor.close();wait(lambda:not state.windows)
    restored=trash_restore(path);project=next(restored.glob('*.omnishot'));editor=open_editor(project,Editor)
    assert len(editor.objects)==1 and editor.objects[0].props['kind']=='arrow'
    assert editor.render().convertToFormat(QImage.Format.Format_RGBA8888)==expected
    editor.grab().save(str(out/'restored-image.png'));editor.close();wait(lambda:not state.windows)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    video=out/'Imported recording.mp4';backend.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=15','-t','2','-c:v','libx264','-pix_fmt','yuv420p',video]);digest=hashlib.sha256(video.read_bytes()).hexdigest()
    editor=open_editor(video,VideoEditor);path=editor.path;wait(lambda:editor.player.duration()>0)
    # The Background tab exposes the padding spinbox; change it with native keys.
    click(editor.tool_buttons['Background'])
    for scroll in editor.findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(editor.padding):scroll.ensureWidgetVisible(editor.padding)
    assert editor.padding.isVisible()
    click(editor.padding);command('key 103 0');QTest.qWait(100);assert editor.padding.value()>0
    padding=editor.padding.value();editor.close();wait(lambda:not state.windows)
    assert not path.with_suffix('.studio.json').exists() and state.store.video_edit_path(path).exists()
    restored=trash_restore(path);project=next(restored.glob('*.omnishot-video'));editor=open_editor(project,VideoEditor);wait(lambda:editor.player.duration()>0)
    assert editor.padding.value()==padding and hashlib.sha256(editor.source_path.read_bytes()).hexdigest()==digest
    editor.grab().save(str(out/'restored-video.png'));editor.close();wait(lambda:not state.windows)
    assert hashlib.sha256(video.read_bytes()).hexdigest()==digest and not errors,errors
    assert not list((out/'xdg-data/Trash/info').glob('*.trashinfo'))
    report=dict(native_preview_trash=True,native_autosave_trash_button=autosave,autosaved_files_removed_and_restored=autosave,actual_qt_trash=True,gio_restore_original_location=True,native_image_annotation=True,recovered_annotation_pixels=True,plain_video_edits_recovered=True,video_source_unchanged=True,external_originals_kept=True,owned_trash_empty=True,display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');command('button 272 0');state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
