"""Native capture → naming → discard/cancel/rename, with recording cleanup."""
import io,json,os,shutil,subprocess,sys,time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QTimer,QPoint
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QApplication,QWidget,QDialogButtonBox
from PySide6.QtTest import QTest
from omnishot import backend,theme
from omnishot.app import Controller
import omnishot.app as application
from omnishot.capture_name import CaptureNameDialog
from omnishot.editor import Editor
from omnishot.widgets import place_window,JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);manager=theme.ThemeManager(app)
state=Controller(app);state.store.settings.update(ask_capture_name=True,background_preset='Ocean',after_capture='overlay',after_capture_extra=['copy','save','pin','annotate'],after_recording='edit',after_recording_extra=['copy','save','overlay'],output_dir=str(out/'saved'),filename_format='Capture %i',overlay_timeout=0)
errors=[];application.error=lambda parent,message:errors.append(str(message))
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),errors
def client(widget):return next((c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle()),None)
def click(widget):
    top=widget.window();native=client(top);p=widget.mapTo(top,widget.rect().center());backend.move_cursor(native['at'][0]+p.x()-2,native['at'][1]+p.y());command('move 2 0');QTest.qWait(70);command('click 272');QTest.qWait(120)
def enter(dialog,text):
    click(dialog.name);app.clipboard().setText(text);QTest.qWait(100);command('key 30 4');QTest.qWait(80);command('key 47 4');QTest.qWait(150);assert dialog.name.text()==text
def modal(operation,handler):
    handled=[]
    def poll():
        dialog=app.activeModalWidget()
        if not isinstance(dialog,CaptureNameDialog):QTimer.singleShot(50,poll);return
        try:
            wait(lambda:client(dialog));QTest.qWait(150);handler(dialog);handled.append(True)
        except Exception as exc:errors.append(repr(exc));dialog.reject();handled.append(False)
    QTimer.singleShot(50,poll);operation();wait(lambda:handled and not state.busy and not JOBS);assert handled==[True] and not errors,errors
def capture(action=None):state.dispatch(dict(command='area',geometry='450,350 300x180',**({'action':action} if action else {})))
def saved():return list((out/'saved').glob('*'))
def empty_views():return not state.windows and not state.overlays and not state.pins
def close_views():
    for widget in list(state.windows):widget.close()
    state.close_pins();state.close_all_overlays();QTest.qWait(150)
class Source(QWidget):
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#36a8c4'))
source=Source();source.setWindowTitle('OmniShot Naming Source');source.resize(800,500);source.show();place_window(source,350,250);QTest.qWait(200)
try:
    backend.clipboard_write('text/plain',b'Clipboard before discard')
    def discard(dialog):
        assert dialog.path.exists() and state.store.image_edit_path(dialog.path).exists()
        assert not saved() and empty_views();dialog.grab().save(str(out/'discard-image.png'));click(dialog.discard_button)
    modal(capture,discard)
    assert not state.store.history() and not saved() and empty_views()
    assert not list(state.store.captures.iterdir()) and not list((state.store.root/'image-edits').glob('*'))
    assert backend.run(['wl-paste','--type','text/plain','--no-newline'])==b'Clipboard before discard'
    state.store.settings['background_preset']='None'
    def cancel(dialog):
        enter(dialog,'Unused name');command('key 1 0');QTest.qWait(150);assert not dialog.isVisible()
    modal(lambda:capture('save'),cancel)
    path=Path(state.store.history()[0]['path']);assert state.store.display_name(path).startswith('Capture 2')
    assert len(saved())==1 and saved()[0].name==state.store.display_name(path)
    assert not (out/'saved/Unused name.png').exists() and empty_views()
    def rename(dialog):
        enter(dialog,'../invalid');click(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok));assert dialog.isVisible() and dialog.message.isVisible()
        dialog.grab().save(str(out/'invalid-name.png'));enter(dialog,'Named screenshot');command('key 28 0');QTest.qWait(150);assert not dialog.isVisible()
    modal(capture,rename);QTest.qWait(180)
    path=Path(state.store.history()[0]['path']);assert state.store.display_name(path)=='Named screenshot.png'
    assert len(saved())==2 and len(state.pins)==1 and len(state.overlays)==1 and any(isinstance(w,Editor) for w in state.windows)
    exported=Image.open(out/'saved/Named screenshot.png').convert('RGB');copied=Image.open(io.BytesIO(backend.run(['wl-paste','--type','image/png']))).convert('RGB')
    assert exported.tobytes()==copied.tobytes() and exported.getpixel((100,100))==(54,168,196)
    close_views();assert empty_views()
    movie=out/'source.mp4';backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=64x64:r=5','-t','0.4','-c:v','libx264','-y',movie])
    gif=out/'source.gif';backend.run(['ffmpeg','-v','error','-i',movie,'-y',gif])
    original_files={movie:movie.read_bytes(),gif:gif.read_bytes()};tracks=state.store.root/'tracks';tracks.mkdir(exist_ok=True)
    for input_path in (movie,gif):
        history_before=len(state.store.history());owned=state.store.add(source=input_path,kind='gif' if input_path==gif else 'video')
        camera=tracks/(owned.stem+'-camera.mp4');shutil.copy2(movie,camera)
        state.store.atomic_json(owned.with_suffix('.studio.json'),dict(source_path=str(movie),camera_path=str(camera)))
        if input_path==gif:shutil.copy2(movie,owned.with_suffix('.mp4'))
        backend.clipboard_write('text/plain',b'Clipboard before video discard')
        def discard_recording(dialog):
            dialog.grab().save(str(out/('discard-'+input_path.suffix[1:]+'.png')));click(dialog.discard_button)
        modal(lambda:state.finished_recording(owned),discard_recording)
        assert len(state.store.history())==history_before and not owned.exists() and not camera.exists()
        assert not owned.with_suffix('.studio.json').exists() and (input_path!=gif or not owned.with_suffix('.mp4').exists())
        assert len(saved())==2 and empty_views() and backend.run(['wl-paste','--type','text/plain','--no-newline'])==b'Clipboard before video discard'
        assert all(p.read_bytes()==data for p,data in original_files.items())
    report=dict(native_image_capture=True,discard_before_all_actions=True,automatic_background_cleaned=True,cancel_keeps_automatic_name=True,invalid_name_stays_open=True,enter_accepts_name=True,rename_before_combined_actions=True,saved_and_clipboard_pixels_match=True,mp4_and_gif_discard=True,owned_camera_and_gif_companion_removed=True,external_sources_preserved=True,clipboard_preserved_on_discard=True,display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
