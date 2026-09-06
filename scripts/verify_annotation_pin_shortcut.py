"""Native Annotate Pin shortcut: settings, live editor, text, crop and scope."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QScrollArea,QToolButton,QLineEdit
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.widgets import Settings
import omnishot.widgets as widgets

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False)
state=Controller(app);state.store.settings.update(output_dir=str(out/'exports'),background_preset='None',annotation_shadow=False)
errors=[];widgets.error=lambda parent,message:errors.append(str(message))
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),errors
def client(widget):return next((c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle()),None)
def pointer(widget,point=None):
    top=widget.window();native=client(top);point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(native['at'][0]+point.x()-2,native['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def click(widget):
    for scroll in widget.window().findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(widget):scroll.ensureWidgetVisible(widget);QTest.qWait(60)
    pointer(widget);command('click 272');QTest.qWait(100)
def focus_editor():backend.focus_window(client(e)['address']);e.view.setFocus();QTest.qWait(90)
def pixels(image):return image.convertToFormat(QImage.Format.Format_RGBA8888)
def settings():
    state.dispatch(dict(command='settings',tab='annotate'));dialog=next(w for w in state.windows if isinstance(w,Settings));wait(lambda:client(dialog));QTest.qWait(150);backend.focus_window(client(dialog)['address']);QTest.qWait(100);return dialog
def keyfield(dialog,code,mods):click(dialog.fields['annotation_pin_shortcut']);command(f'key {code} {mods}');QTest.qWait(120)
def finish(dialog,save=True):click(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save if save else QDialogButtonBox.StandardButton.Cancel));QTest.qWait(100)
image=QImage(800,500,QImage.Format.Format_RGB888);image.fill(QColor('#e0e8f0'));path=state.store.add(image=image);original=path.read_bytes();state.edit(path);e=next(w for w in state.windows if isinstance(w,Editor));wait(lambda:client(e));QTest.qWait(200)
try:
    click(e.toolbar.widgetForAction(e.tools['arrow']));a=e.view.mapFromScene(QPointF(80,90));b=e.view.mapFromScene(QPointF(450,210));pointer(e.view.viewport(),a);command('button 272 1');QTest.qWait(70);pointer(e.view.viewport(),b);command('button 272 0');QTest.qWait(120);assert len(e.objects)==1
    dialog=settings();keyfield(dialog,25,12);assert dialog.fields['annotation_pin_shortcut'].keySequence().toString()=='Ctrl+Alt+P';dialog.grab().save(str(out/'annotation-pin-settings.png'));finish(dialog)
    assert backend.Store(state.store.root).settings['annotation_pin_shortcut']=='Ctrl+Alt+P' and e.pin_shortcut.key().toString()=='Ctrl+Alt+P'
    focus_editor();command('key 25 12');wait(lambda:len(state.pins)==1);pin=state.pins[0];assert pin.path==path and pixels(pin.image)==pixels(e.render()) and e.isVisible()
    state.close_pins();wait(lambda:not state.pins)
    # Saving a conflicting key must leave both the settings and open editor alone.
    dialog=settings();keyfield(dialog,25,4);finish(dialog);assert dialog.isVisible() and errors and 'already used' in errors.pop()
    assert state.store.settings['annotation_pin_shortcut']=='Ctrl+Alt+P' and e.pin_shortcut.key().toString()=='Ctrl+Alt+P';finish(dialog,False)
    dialog=settings();keyfield(dialog,24,12);finish(dialog,False);assert e.pin_shortcut.key().toString()=='Ctrl+Alt+P'
    # A modified Pin shortcut finishes the current inline text and exports it.
    focus_editor();click(e.toolbar.widgetForAction(e.tools['text']));pointer(e.view.viewport(),e.view.mapFromScene(QPointF(120,280)));command('click 272');QTest.qWait(100);assert e.inline is not None
    backend.copy_text('Current editable text');command('key 47 4');QTest.qWait(100);command('key 25 12');wait(lambda:len(state.pins)==1 and e.inline is None)
    assert e.objects[-1].props['text']=='Current editable text' and pixels(state.pins[0].image)==pixels(e.render());state.close_pins();wait(lambda:not state.pins)
    focus_editor();click(e.toolbar.widgetForAction(e.tools['crop']));assert e.crop_session is not None;command('key 25 12');QTest.qWait(120);assert not state.pins and e.crop_session is not None and 'crop' in e.statusBar().currentMessage()
    command('key 1 0');QTest.qWait(100);assert e.crop_session is None
    other=QLineEdit();other.setWindowTitle('Generated shortcut scope target');other.show();wait(lambda:client(other));click(other);command('key 25 12');QTest.qWait(150);assert not state.pins;other.close()
    dialog=settings();field=dialog.fields['annotation_pin_shortcut'];assert field.keySequence().toString()=='Ctrl+Alt+P'
    clear=next(button for button in field.findChildren(QToolButton) if button.isVisible());click(clear);assert field.keySequence().isEmpty();finish(dialog)
    assert e.pin_shortcut.key().isEmpty() and backend.Store(state.store.root).settings['annotation_pin_shortcut']==''
    focus_editor();command('key 25 12');QTest.qWait(150);assert not state.pins
    expected=pixels(e.render());e.close();wait(lambda:not any(isinstance(w,Editor) for w in state.windows));state.edit(path);e=next(w for w in state.windows if isinstance(w,Editor));assert e.pin_shortcut.key().isEmpty() and pixels(e.render())==expected
    assert path.read_bytes()==original and not errors
    report=dict(native_settings_assignment=True,persisted_and_live_editor_updated=True,native_pin_current_annotations=True,editable_capture_identity=True,conflict_rejected_without_mutation=True,cancel_preserves_key=True,inline_text_committed_by_shortcut=True,unfinished_crop_guard=True,annotation_window_scope=True,native_clear_disables=True,reopen_retains_disabled_setting=True,original_capture_unchanged=True,display_scale=1.6)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');command('button 272 0');state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
