"""Native capture → highlighter, text sizing, Ctrl bypass, undo and project save."""
import io,json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPointF,QTimer
from PySide6.QtGui import QColor,QFont,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QFileDialog,QLineEdit,QDialogButtonBox
from PySide6.QtTest import QTest
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.editor import Editor,png_bytes
from omnishot.widgets import JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot')
state=Controller(app);state.store.settings.update(include_cursor=False,annotation_shadow=False,background_preset='None')
errors=[];application.error=lambda parent,message:errors.append(str(message))
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=7):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate(),errors
def pointer(widget,point=None):
    window=widget.window();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle())
    point=widget.mapTo(window,point or widget.rect().center());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(65)
def click(widget):pointer(widget);command('click 272');QTest.qWait(100)
class TextPage(QWidget):
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('white'));p.setPen(QColor('black'))
        font=QFont('DejaVu Sans');font.setPixelSize(24);p.setFont(font);p.drawText(140,300,'Small text with automatic highlighting')
        font.setPixelSize(44);p.setFont(font);p.drawText(140,430,'Larger type in the same capture')
        p.fillRect(130,505,850,120,QColor('#202020'));p.setPen(QColor('white'));font.setPixelSize(30);p.setFont(font);p.drawText(140,580,'Light text on a dark background')
source=TextPage();source.setWindowTitle('Generated highlighter reference page');source.showFullScreen();QTest.qWait(300)
def stroke(bounds,bypass=False):
    left,top,right,bottom=bounds;center=(top+bottom)/2
    a=e.view.mapFromScene(QPointF(left-6,center-3));b=e.view.mapFromScene(QPointF(right+6,center+3))
    pointer(e.view.viewport(),a);command('mods '+('4' if bypass else '0'));command('button 272 1');QTest.qWait(70)
    for i in range(1,5):
        pointer(e.view.viewport(),a+(b-a)*i/4)
    command('button 272 0');QTest.qWait(130);command('mods 0');QTest.qWait(70)
    obj=e.objects[-1];assert obj.props['kind']=='highlight'
    return [obj.x(),obj.y(),obj.props['w'],obj.props['h']]
try:
    state.capture('area',dict(geometry='100,180 1000x480',action='annotate'))
    wait(lambda:any(isinstance(w,Editor) for w in state.windows) and not state.busy and not JOBS)
    e=next(w for w in state.windows if isinstance(w,Editor));QTest.qWait(200)
    assert (e.base.width(),e.base.height())==(1600,768)
    original=e.base.copy();pixels=np.array(Image.open(io.BytesIO(png_bytes(original))).convert('RGB'))
    bounds=[]
    # Measure the actual generated glyph pixels, independently of the snapping
    # algorithm. Each band contains one known line and no other content.
    for y0,y1,light in [(130,210,False),(310,420,False),(575,665,True)]:
        band=pixels[y0:y1,60:1300]
        mask=np.all(band>230,axis=2) if light else np.all(band<30,axis=2)
        ys,xs=np.where(mask);assert len(ys)>100
        bounds.append([int(xs.min()+60),int(ys.min()+y0),int(xs.max()+61),int(ys.max()+y0+1)])
    click(e.toolbar.widgetForAction(e.tools['highlight']));assert 'Ctrl' in e.tools['highlight'].toolTip()
    records=[]
    for index,bound in enumerate(bounds):
        depth=len(e.undo_states);snapped=stroke(bound)
        assert len(e.undo_states)==depth+1
        assert snapped[1]<=bound[1] and snapped[1]+snapped[3]>=bound[3],(bound,snapped)
        assert snapped[3]<(bound[3]-bound[1])+12,(bound,snapped)
        saved=e.render();command('key 44 4');QTest.qWait(100);assert len(e.objects)==index
        manual=stroke(bound,True);assert manual[3]<=10 and manual[3]<snapped[3]/2,(manual,snapped)
        assert e.render()!=saved
        command('key 44 4');QTest.qWait(100);assert len(e.objects)==index
        repeated=stroke(bound);assert repeated==snapped and e.render()==saved,(repeated,snapped)
        records.append(dict(text_bounds=bound,snapped=snapped,ctrl_bypass=manual))
    assert records[1]['snapped'][3]>records[0]['snapped'][3]*1.5
    # Edit actual highlighter opacity through the shared native color picker.
    click(e.toolbar.widgetForAction(e.tools['select']));first=e.objects[0]
    pointer(e.view.viewport(),e.view.mapFromScene(first.sceneBoundingRect().center()));command('click 272');QTest.qWait(100);assert first.isSelected()
    before_opacity=e.render();undo=e.undo_index;click(e.color_btn);pop=e.color_popup;assert pop.isVisible() and pop.channels[3].value()==39
    def picker_click(widget):
        point=widget.mapTo(e,widget.rect().center());client=next(c for c in backend.hypr('clients') if c['title']==e.windowTitle())
        backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(65);command('click 272');QTest.qWait(100)
    def opacity(value):
        picker_click(pop.channels[3]);backend.copy_text(str(value));command('key 30 4');command('key 47 4');command('key 28 0');QTest.qWait(130)
    opacity(0);assert first.props['highlight_alpha']==0 and e.render()!=before_opacity;zero=e.render()
    opacity(100);assert first.props['highlight_alpha']==255 and e.render()!=zero
    opacity(50);assert first.props['highlight_alpha']==128 and e.undo_index==undo
    pop.grab().save(str(out/'highlighter-opacity-picker.png'));command('key 1 0');QTest.qWait(150);assert e.undo_index==undo+1
    edited=e.render();command('key 44 4');QTest.qWait(100);assert e.render()==before_opacity
    command('key 44 5');QTest.qWait(100);assert e.render()==edited
    expected=e.render();command('key 44 4');QTest.qWait(100);assert e.render()!=expected
    command('key 44 5');QTest.qWait(100);assert e.render()==expected
    assert e.base==original
    e.scene.clearSelection();QTest.qWait(100);e.grab().save(str(out/'highlighter-editor.png'))
    project=out/'highlighted.omnishot';failures=[]
    def save_dialog():
        if not isinstance(app.activeModalWidget(),QFileDialog):timer.start(50);return
        try:
            dialog=app.activeModalWidget();QTest.qWait(150);field=dialog.findChild(QLineEdit,'fileNameEdit')
            click(field);backend.copy_text(str(project));command('key 30 4');command('key 47 4');QTest.qWait(120)
            if app.activePopupWidget():command('key 1 0');QTest.qWait(70)
            pointer(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save));command('click 272')
        except Exception as exc:failures.append(repr(exc));app.activeModalWidget().reject()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(save_dialog);timer.start(150)
    command('key 31 5');wait(lambda:project.exists());assert not failures,failures
    e.close();wait(lambda:not state.windows and not JOBS)
    reopened=Editor(project,state.store);assert reopened.render()==expected and reopened.base==original and len(reopened.objects)==3
    for obj,record in zip(reopened.objects,records):assert [obj.x(),obj.y(),obj.props['w'],obj.props['h']]==record['snapped']
    expected.save(str(out/'highlighted.png'));reopened.close()
    report=dict(native_capture_to_annotation=True,capture_pixels=[1600,768],small_and_large_text_auto_height=True,light_text_on_dark_auto_height=True,ctrl_bypasses_snapping=True,modifier_release_restores_snapping=True,one_undo_per_stroke=True,native_undo_redo=True,native_project_save=True,editable_reopening=True,source_pixels_unchanged=True,display_scale=1.6,strokes=records)
    report.update(native_opacity_endpoints=True,one_undo_per_opacity_session=True,opacity_undo_redo=True,opacity_project_reopen=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('button 272 0');command('mods 0');state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3);backend.run(['wl-copy','--clear'])
