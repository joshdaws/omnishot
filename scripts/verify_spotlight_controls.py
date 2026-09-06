"""Native Spotlight shape/radius/dimming edits, one-drag undo and portable pixels."""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QStyle,QStyleOptionSlider
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.editor import Editor
from omnishot.theme import ThemeManager

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);theme=ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=5):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate()
def pointer(widget,point=None):
    assert widget.isVisible(),widget
    top=widget.window();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==top.windowTitle())
    point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def click(widget):pointer(widget);command('click 272');QTest.qWait(100)
def canvas(x,y):return e.view.mapFromScene(QPointF(x,y))
def choose(index):
    field=e.spotlight.shape;before=field.currentIndex();click(field)
    for _ in range(abs(index-before)):command('key '+('108' if index>before else '103')+' 0');QTest.qWait(50)
    command('key 28 0');QTest.qWait(100);assert field.currentIndex()==index
def spot():return e.objects[-1]
image=QImage(800,500,QImage.Format.Format_RGB888);image.fill(QColor('#d0e0f0'));source=out/'source.png';assert image.save(str(source));original=source.read_bytes()
store=backend.Store(out/'data');store.settings['annotation_shadow']=False;e=Editor(source,store);e.show();QTest.qWait(250)
try:
    click(e.toolbar.widgetForAction(e.tools['spotlight']));pointer(e.view.viewport(),canvas(60,60));command('button 272 1');QTest.qWait(60)
    pointer(e.view.viewport(),canvas(340,260));command('button 272 0');QTest.qWait(120)
    assert len(e.objects)==1;spot().setSelected(True);QTest.qWait(100)
    assert e.spotlight.isVisible() and e.spotlight.radius.value()==8 and e.spotlight.opacity.value()==155
    choose(2);assert spot().props['spotlight_shape']=='Ellipse' and not e.spotlight.radius.isEnabled()
    assert e.render().pixelColor(200,160)==QColor('#d0e0f0') and e.render().pixelColor(90,80).red()<208
    slider=e.spotlight.opacity;option=QStyleOptionSlider();slider.initStyleOption(option)
    handle=slider.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,slider).center()
    before=e.render();index=e.undo_index;pointer(slider,handle);command('button 272 1');QTest.qWait(70)
    pointer(slider,handle+QPoint(-12,0));pointer(slider,handle+QPoint(-25,0));command('button 272 0');QTest.qWait(100)
    alpha=spot().props['spotlight_alpha'];assert 0<alpha<155 and e.undo_index==index+1,(alpha,e.undo_index,index)
    after=e.render();assert after.pixelColor(680,330).red()>before.pixelColor(680,330).red()
    e.view.setFocus();command('key 44 4');QTest.qWait(100);assert e.render()==before
    command('key 44 5');QTest.qWait(100);assert e.render()==after
    spot().setSelected(True);QTest.qWait(80);assert e.spotlight.opacity.value()==alpha and e.spotlight.shape.currentText()=='Ellipse'
    choose(1);assert e.render().pixelColor(90,80)==QColor('#d0e0f0') and not e.spotlight.radius.isEnabled()
    choose(0);assert e.spotlight.radius.isEnabled();click(e.spotlight.radius);command('key 30 4');backend.copy_text('70');command('key 47 4');command('key 28 0');QTest.qWait(100)
    assert spot().props['spotlight_radius']==70 and e.render().pixelColor(90,65).red()<208
    # Home/End reach the documented slider endpoints through native input.
    click(slider);command('key 102 0');QTest.qWait(100);assert spot().props['spotlight_alpha']==0 and e.render().pixelColor(680,330)==QColor('#d0e0f0')
    command('key 107 0');QTest.qWait(100);assert spot().props['spotlight_alpha']==255 and e.render().pixelColor(680,330)==QColor('black')
    command('key 105 0');QTest.qWait(100);assert spot().props['spotlight_alpha']==254
    samples=[];frame=backend.grab();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==e.windowTitle());scale=backend.capture_monitors()[0]['scale'];rendered=e.render()
    for x,y in ((200,160),(680,330),(90,65)):
        point=e.view.viewport().mapTo(e,canvas(x,y));actual=frame[round((client['at'][1]+point.y())*scale),round((client['at'][0]+point.x())*scale),:3];expected=np.array(rendered.pixelColor(x,y).getRgb()[:3])
        assert abs(actual.astype(int)-expected).max()<=2,(actual,expected);samples.append(dict(at=[x,y],actual=actual.tolist(),expected=expected.tolist()))
    e.grab().save(str(out/'spotlight-controls.png'));project=out/'spotlight.omnishot';e.write_project(project);e.close();other=Editor(project,store);assert other.render()==rendered
    other.objects[-1].setSelected(True);assert other.spotlight.radius.value()==70 and other.spotlight.opacity.value()==254;other.close();assert source.read_bytes()==original
    report=dict(native_draw=True,native_shape_switching=True,rounded_radius=True,opacity_slider=True,one_drag_one_undo=True,undo_redo_restores_pixels=True,selection_restores_controls=True,opacity_endpoints_and_keyboard=True,displayed_pixels_match_export=True,project_reopen=True,source_unchanged=True,display_scale=scale,pixel_samples=samples)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('button 272 0');command('mods 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
