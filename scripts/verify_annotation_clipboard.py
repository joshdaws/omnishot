"""Native Wayland keyboard object clipboard and copied-media opening."""
import base64,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QTimer
from PySide6.QtGui import QImage,QColor,QColorSpace
from PySide6.QtWidgets import QApplication,QPushButton,QMessageBox
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.editor import Editor,Annotation,png_bytes
from omnishot.annotation_clipboard import MIME,decode
from omnishot.recording import VideoEditor
from omnishot.widgets import JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=10):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),[(w.windowTitle(),w.isVisible()) for w in app.topLevelWidgets()]
def mapped(window):return any(c['pid']==os.getpid() and c['title']==window.windowTitle() for c in backend.hypr('clients'))
def click(widget,window):
    wait(lambda:mapped(window));client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle());point=widget.mapTo(window,widget.rect().center())
    backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(80);command('click 272');QTest.qWait(100)
def read(mime):
    path=out/'clipboard-read';stream=path.open('wb');process=subprocess.Popen(['wl-paste','--type',mime,'--no-newline'],stdout=stream,stderr=subprocess.PIPE)
    wait(lambda:process.poll() is not None);stream.close();assert process.returncode==0,process.stderr.read();return path.read_bytes()
def open_clipboard():
    state.show_menu();menu=next(w for w in state.windows if w.windowTitle()=='OmniShot — Capture');click(next(b for b in menu.findChildren(QPushButton) if b.text()=='From clipboard'),menu)
state=Controller(app);state.store.settings.update(overlay_timeout=0,background_preset='None',convert_srgb=False)
base=QImage(800,500,QImage.Format.Format_RGB32);base.fill(QColor('#edf3fa'));path=state.store.add(image=base)
source=Editor(path,state.store);source.setWindowTitle('OmniShot — Source');source.show();source.fit()
props=[dict(kind='arrow',x=60,y=70,w=180,h=90,width=6,color='#ff3050',style='double'),dict(kind='text',x=290,y=75,w=280,h=80,text='Editable clipboard',font_size=24,bold=True,transform=[1,.1,0,1,0,0]),dict(kind='pencil',x=150,y=280,w=60,h=40,points=[[0,0],[30,40],[60,10]],color='#209080')]
try:
    for p in props:
        obj=Annotation(p,source);source.scene.addItem(obj);source.objects.append(obj)
    source.commit();click(source.view.viewport(),source)
    for obj in source.objects:obj.setSelected(True)
    command('key 46 4');QTest.qWait(160)
    data=read(MIME);assert len(decode(data))==3
    fallback=QImage.fromData(read('image/png'));assert fallback.convertToFormat(QImage.Format.Format_RGBA8888)==source.render().convertToFormat(QImage.Format.Format_RGBA8888)
    source.close()
    dest=Editor(path,state.store);dest.setWindowTitle('OmniShot — Pasted');dest.rebuild([]);dest.commit();dest.show();dest.fit();click(dest.view.viewport(),dest)
    index=dest.undo_index;command('key 47 4');wait(lambda:len(dest.objects)==3)
    assert dest.undo_index==index+1 and all(o.isSelected() for o in dest.objects)
    for before,after in zip(props,dest.objects):assert after.x()==before['x']+20 and after.y()==before['y']+20
    command('key 106 0');QTest.qWait(100);assert dest.objects[0].x()==81
    command('key 44 4');QTest.qWait(100);assert dest.objects[0].x()==80
    command('key 44 4');QTest.qWait(100);assert not dest.objects
    command('key 44 5');QTest.qWait(100);assert len(dest.objects)==3
    expected=dest.render();project=out/'Pasted.omnishot';dest.write_project(project);dest.grab().save(str(out/'editable-clipboard.png'));dest.close()
    reopened=Editor(project,state.store);assert reopened.render()==expected;reopened.close()
    # The capture menu accepts an externally owned PNG without dropping alpha/ICC.
    alpha=QImage(120,80,QImage.Format.Format_RGBA8888);alpha.fill(QColor(100,50,20,64));alpha.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3))
    backend.clipboard_write('image/png',png_bytes(alpha));open_clipboard();wait(lambda:any(isinstance(w,Editor) for w in state.windows))
    image_editor=next(w for w in state.windows if isinstance(w,Editor));assert image_editor.base.convertToFormat(QImage.Format.Format_RGBA8888)==alpha and image_editor.base.colorSpace()==alpha.colorSpace();image_editor.close()
    video=out/'Clipboard movie é & spaces.mp4';backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:r=10','-t','0.5','-c:v','libx264','-threads','1','-y',video]);digest=hashlib.sha256(video.read_bytes()).hexdigest()
    backend.copy_file(video,state.store);open_clipboard();wait(lambda:any(isinstance(w,VideoEditor) for w in state.windows))
    player=next(w for w in state.windows if isinstance(w,VideoEditor));wait(lambda:player.player.duration()>0)
    assert player.path.suffix=='.mp4' and hashlib.sha256(video.read_bytes()).hexdigest()==digest
    player.grab().save(str(out/'clipboard-video.png'));player.close();wait(lambda:not JOBS)
    before_history=state.store.history();broken=out/'broken.mp4';broken.write_bytes(b'not a recording');backend.copy_file(broken,state.store)
    error_seen=[False];timer=QTimer();timer.setInterval(75)
    def dismiss_error():
        dialog=app.activeModalWidget()
        if isinstance(dialog,QMessageBox) and mapped(dialog):
            timer.stop();assert 'Could not open recording' in dialog.text();error_seen[0]=True;click(dialog.button(QMessageBox.StandardButton.Ok),dialog)
    timer.timeout.connect(dismiss_error);timer.start();open_clipboard();wait(lambda:error_seen[0] and not JOBS)
    assert state.store.history()==before_history and broken.read_bytes()==b'not a recording'

    report=dict(display_scale=backend.capture_monitors()[0]['scale'],native_ctrl_c_v=True,editable_text_arrows_pencil=True,source_editor_close_preserves_clipboard=True,png_fallback_full_capture=True,native_nudge_undo_redo=True,project_reopen_exact=True,capture_menu_opens_rgba_p3_clipboard=True,capture_menu_opens_copied_mp4=True,video_preview_loaded=True,external_video_unchanged=True,invalid_video_shows_error_without_history_entry=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    command('mods 0');fixture.stdin.close();fixture.wait(timeout=3)
