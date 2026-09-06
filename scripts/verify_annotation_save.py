"""Native Alt-save, collision preservation, ordinary Save As and error recovery."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QFileDialog,QLineEdit,QDialogButtonBox
from PySide6.QtTest import QTest
from omnishot import backend
import omnishot.editor as editor_module
from omnishot.editor import Editor,Annotation
from omnishot.theme import ThemeManager

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);theme=ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate()
def pointer(widget):
    top=widget.window();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==top.windowTitle())
    point=widget.mapTo(top,widget.rect().center());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def click(widget):pointer(widget);command('click 272')
def pixels(image):
    decoded=image.convertToFormat(QImage.Format.Format_RGBA8888)
    return decoded.size(),bytes(decoded.bits())
source=out/'source.png';image=QImage(800,500,QImage.Format.Format_RGB888);image.fill(QColor('#ecf0f2'));assert image.save(str(source));original=source.read_bytes()
store=backend.Store(out/'data');folder=out/'exports';store.settings.update(output_dir=str(folder),format='png',annotation_shadow=False)
e=Editor(source,store);obj=Annotation(dict(kind='rect',x=90,y=80,w=320,h=240,color='#e03050',width=8),e);e.objects.append(obj);e.scene.addItem(obj);e.commit();e.show();QTest.qWait(250)
saved=[];errors=[];e.saved.connect(saved.append);editor_module.error=lambda parent,message:errors.append(str(message))
def direct():
    pointer(e.save_button);command('mods 8');QTest.qWait(80)
    command('click 272');QTest.qWait(150);command('mods 0');QTest.qWait(70)
    assert app.activeModalWidget() is None and e.isVisible()
def chooser(cancel,initial=None):
    done=[];failures=[]
    def interact():
        dialog=app.activeModalWidget()
        if not isinstance(dialog,QFileDialog):timer.start(40);return
        try:
            wait(lambda:any(c['pid']==os.getpid() and c['title']==dialog.windowTitle() for c in backend.hypr('clients')))
            if initial is not None:assert Path(dialog.directory().absolutePath())==initial,(dialog.directory().absolutePath(),initial)
            if cancel:command('key 1 0')
            else:
                field=dialog.findChild(QLineEdit,'fileNameEdit');pointer(field);command('click 272');command('key 30 4');backend.copy_text(str(out/'chosen-folder'/'chosen.png'));command('key 47 4');QTest.qWait(100)
                button=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save);pointer(button);command('click 272')
            done.append(True)
        except Exception as exc:failures.append(repr(exc));dialog.reject()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(interact);timer.start(40);click(e.save_button)
    wait(lambda:done or failures);wait(lambda:app.activeModalWidget() is None);assert not failures,failures
try:
    expected=pixels(e.render());direct();assert len(saved)==1 and pixels(QImage(saved[0]))==expected
    first=Path(saved[0]);before=first.read_bytes();direct();assert len(saved)==2 and Path(saved[1])!=first and first.read_bytes()==before
    assert pixels(QImage(saved[1]))==expected
    chooser(True);assert e.isVisible() and len(saved)==2
    # An ordinary filesystem failure must leave edits and both earlier files intact.
    bad=out/'not-a-directory';bad.write_text('existing file');store.settings['output_dir']=str(bad/'child');direct()
    assert errors and len(saved)==2 and pixels(e.render())==expected and bad.read_text()=='existing file'
    store.settings['output_dir']=str(folder);direct();assert len(saved)==3 and pixels(QImage(saved[-1]))==expected
    e.grab().save(str(out/'annotation-save.png'));project=out/'saved.omnishot';e.write_project(project)
    chosen_folder=out/'chosen-folder';chosen_folder.mkdir();chooser(False,folder);wait(lambda:not e.isVisible())
    assert len(saved)==4 and Path(saved[-1])==chosen_folder/'chosen.png' and pixels(QImage(saved[-1]))==expected
    assert source.read_bytes()==original and first.read_bytes()==before
    store=backend.Store(out/'data');assert store.settings['annotation_save_dir']==str(chosen_folder)
    e=Editor(project,store);e.saved.connect(saved.append);e.show();QTest.qWait(200)
    chooser(True,chosen_folder);assert e.isVisible() and store.settings['annotation_save_dir']==str(chosen_folder)
    direct();assert len(saved)==5 and Path(saved[-1]).parent==folder and pixels(QImage(saved[-1]))==expected
    assert backend.Store(out/'data').settings['annotation_save_dir']==str(chosen_folder)
    chosen_folder.rename(out/'moved-folder');chooser(True,folder);assert not chosen_folder.exists()
    assert e.isVisible() and len(saved)==5
    report=dict(remembered_folder_across_reopen=True,alt_uses_configured_capture_folder=True,cancel_preserves_remembered_folder=True,missing_folder_fallback=True,native_alt_click=True,dialog_bypassed=True,current_annotation_pixels=True,existing_exports_preserved=True,source_unchanged=True,keep_editing=True,normal_chooser_cancel=True,normal_chooser_save_and_close=True,filesystem_failure_retains_edits=True,retry_after_failure=True,display_scale=1.6,saved=[Path(p).name for p in saved])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
