"""Native Space-drag navigation of a long image with selected objects and crop."""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QColor,QPainter
from PySide6.QtWidgets import QApplication,QLineEdit
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.theme import ThemeManager
from omnishot.editor import Editor,Annotation

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);theme=ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate()
def pointer(widget,point=None):
    top=widget.window();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==top.windowTitle())
    point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def click(widget):pointer(widget);command('click 272');QTest.qWait(100)
image=QImage(2400,6000,QImage.Format.Format_RGB888);p=QPainter(image)
for y in range(0,6000,100):
    for x in range(0,2400,100):p.fillRect(x,y,100,100,QColor(30+x//20,40+y//40,150))
p.end();source=out/'long.png';image.save(str(source));store=backend.Store(out/'data');store.settings['annotation_shadow']=False
e=Editor(source,store)
for props in [dict(kind='rect',x=1000,y=2900,w=500,h=400,color='#ff0000',width=4),dict(kind='spotlight',x=950,y=2850,w=700,h=600)]:
    obj=Annotation(props,e);e.scene.addItem(obj);e.objects.append(obj)
e.commit();e.show();QTest.qWait(250)
samples=[]
def prepare():e.zoom_to(200);e.view.centerOn(1200,3050);e.view.setFocus();QTest.qWait(100)
def pixels_match():
    e.scene.clearSelection();QTest.qWait(100)
    point=e.view.viewport().rect().center()+QPoint(60,40);scene=e.view.mapToScene(point)
    local=e.view.viewport().mapTo(e,point);client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==e.windowTitle())
    scale=backend.capture_monitors()[0]['scale'];frame=backend.grab()
    actual=frame[round((client['at'][1]+local.y())*scale),round((client['at'][0]+local.x())*scale),:3]
    expected=np.array(e.render(with_background=False).pixelColor(round(scene.x()),round(scene.y())).getRgb()[:3])
    assert np.abs(actual.astype(int)-expected).max()<=2,(actual,expected)
    samples.append(dict(scene=[scene.x(),scene.y()],actual=actual.tolist(),expected=expected.tolist()))
def pan(repress=False):
    view=e.view;before=[bar.value() for bar in (view.horizontalScrollBar(),view.verticalScrollBar())]
    props=[obj.data_dict() for obj in e.objects];selected=list(e.scene.selectedItems());undo=e.undo_index
    start=view.viewport().rect().center();pointer(view.viewport(),start)
    command('key-state 57 1');wait(lambda:view.pan.held);assert view.cursor().shape()==Qt.CursorShape.OpenHandCursor
    command('button 272 1');wait(lambda:view.pan.origin is not None);assert view.cursor().shape()==Qt.CursorShape.ClosedHandCursor
    pointer(view.viewport(),start+QPoint(-150,-120))
    if repress:
        command('key-state 57 0');wait(lambda:not view.pan.held)
        assert view.pan.origin is not None and view.cursor().shape()==Qt.CursorShape.ClosedHandCursor
        command('key-state 57 1');wait(lambda:view.pan.held)
    pointer(view.viewport(),start+QPoint(-190,-175));command('button 272 0');wait(lambda:view.pan.origin is None)
    assert view.cursor().shape()==Qt.CursorShape.OpenHandCursor
    command('key-state 57 0');wait(lambda:not view.pan.held)
    after=[bar.value() for bar in (view.horizontalScrollBar(),view.verticalScrollBar())]
    assert [a-b for a,b in zip(after,before)]==[190,175],(before,after)
    assert [obj.data_dict() for obj in e.objects]==props and e.scene.selectedItems()==selected and e.undo_index==undo
    return dict(before=before,after=after)
try:
    prepare();e.objects[0].setSelected(True);expected=e.render();records=[pan(True)]
    assert e.view.tool=='select' and e.view.cursor().shape()==Qt.CursorShape.ArrowCursor and e.render()==expected
    pixels_match()
    click(e.toolbar.widgetForAction(e.tools['arrow']));prepare();records.append(pan())
    assert e.view.tool=='arrow' and e.view.cursor().shape()==Qt.CursorShape.CrossCursor and e.render()==expected
    # Releasing Space restores ordinary drawing immediately.
    a=e.view.viewport().rect().center();pointer(e.view.viewport(),a);command('button 272 1');QTest.qWait(60)
    pointer(e.view.viewport(),a+QPoint(90,60));command('button 272 0');QTest.qWait(120)
    assert len(e.objects)==3 and e.objects[-1].props['kind']=='arrow';expected=e.render()
    click(e.toolbar.widgetForAction(e.tools['crop']));prepare();crop=e.crop_session;rect=crop.rect.getRect();records.append(pan())
    assert e.crop_session is crop and crop.rect.getRect()==rect and crop.drag is None and e.render()==expected
    click(crop.cancel_button);assert e.crop_session is None and e.render()==expected
    # Focus loss must release hand mode even if Space is released in another app.
    prepare();command('key-state 57 1');wait(lambda:e.view.pan.held)
    other=QLineEdit();other.setWindowTitle('Generated focus target');other.resize(260,60);other.show();QTest.qWait(130);click(other)
    wait(lambda:not e.view.pan.held and e.view.pan.origin is None)
    command('key-state 57 0');command('key 57 0');QTest.qWait(100);assert other.text()==' '
    other.close();QTest.qWait(100);prepare();assert e.view.cursor().shape()!=Qt.CursorShape.OpenHandCursor
    pixels_match();e.grab().save(str(out/'canvas-pan.png'))
    project=out/'panned.omnishot';e.write_project(project);e.close();reopened=Editor(project,store)
    assert reopened.render()==expected
    decoded=reopened.base.convertToFormat(QImage.Format.Format_RGB888)
    assert decoded.size()==image.size() and bytes(decoded.bits())==bytes(image.bits()),(decoded.size(),image.size())
    reopened.close()
    report=dict(native_space_drag=True,long_image=[2400,6000],zoom_percent=200,selected_objects_unchanged=True,no_pan_undo_entries=True,drawing_tool_restored=True,space_release_repress_during_drag=True,unfinished_crop_preserved=True,focus_loss_releases_hand=True,space_types_normally_in_other_field=True,composited_preview_matches_export=True,project_reopen_unchanged=True,display_scale=1.6,scrolls=records,pixel_samples=samples)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('key-state 57 0');command('button 272 0');command('mods 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
