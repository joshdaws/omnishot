"""Native arrow styles, arrowhead selection/drag, endpoint resize and reopening."""
import json,math,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor,QImage,QPainterPath,QPainterPathStroker
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.editor import Editor
from omnishot.theme import ThemeManager

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def delay(seconds=.12):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.processEvents();time.sleep(.01)
source=QImage(1000,700,QImage.Format.Format_RGB888);source.fill(QColor('white'));source.save(str(out/'source.png'))
store=backend.Store(out/'data');store.settings.update(annotation_shadow=False,auto_expand_canvas=False)
e=Editor(store.add(source=out/'source.png'),store);original_source=e.base.copy();e.show();delay(.3)
def pointer(widget,point=None):
    point=widget.mapTo(e,point or widget.rect().center());native=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==e.windowTitle())
    backend.move_cursor(native['at'][0]+point.x()-2,native['at'][1]+point.y());command('move 2 0');delay(.07)
def click(widget):pointer(widget);command('click 272');delay()
def scene_pointer(point):pointer(e.view.viewport(),e.view.mapFromScene(point))
def scene_click(point):scene_pointer(point);command('click 272');delay()
def drag(a,b):
    scene_pointer(a);command('button 272 1');delay(.07)
    for i in range(1,5):scene_pointer(a+(b-a)*i/4)
    command('button 272 0');delay()
def wing(obj,head='b'):
    a,b=obj.handles()['a'],obj.handles()['b'];shaft=QPainterPath(a)
    if obj.props['style']=='curved':control=(a+b)/2+QPointF(0,-max(40,obj.props['h']*.45));shaft.quadTo(control,b);direction=b-control
    else:shaft.lineTo(b);direction=b-a
    stroke=QPainterPathStroker();stroke.setWidth(max(14,obj.props['width']+8));shaft=stroke.createStroke(shaft)
    tip=b if head=='b' else a;angle=math.atan2(direction.y(),direction.x())+(math.pi if head=='a' else 0)
    for sign in (-1,1):
        spread=.43 if obj.props.get('arrow_taper') and obj.props['style']=='standard' else .5
        point=tip-QPointF(math.cos(angle+sign*spread)*60,math.sin(angle+sign*spread)*60)
        if not shaft.contains(point):return obj.mapToScene(point)
    raise AssertionError('No outer arrowhead test point')
try:
    click(e.toolbar.widgetForAction(e.tools['arrow']));click(e.width);backend.copy_text('16');command('key 30 4');command('key 47 4');command('key 28 0');delay();assert e.width.value()==16
    styles=['standard','open','double','curved']
    for i,style in enumerate(styles):
        click(e.arrow_style);command('key 102 0')
        for _ in range(i):command('key 108 0')
        command('key 28 0');delay();assert e.arrow_style.currentText()==style
        start=QPointF(150,100+i*145);end=QPointF(520,140+i*145)
        if i%2:start,end=end,start
        drag(start,end);assert len(e.objects)==i+1 and e.objects[-1].props['style']==style
    click(e.toolbar.widgetForAction(e.tools['select']));records=[]
    for i,style in enumerate(styles):
        scene_click(QPointF(900,650));obj=e.objects[i];point=wing(obj)
        pixel=e.render().pixelColor(round(point.x()),round(point.y()));assert pixel.red()>pixel.green()*1.3 and pixel.red()>pixel.blue()*1.3
        scene_click(point);assert obj.isSelected(),style
        if style=='double':
            scene_click(QPointF(900,650));scene_click(wing(obj,'a'));assert obj.isSelected()
        original=e.render();position=obj.pos();drag(point,point+QPointF(30,-15));assert (obj.pos()-position).manhattanLength()>35
        moved=e.render();assert moved!=original;command('key 44 4');delay();assert e.render()==original;command('key 44 5');delay();assert e.render()==moved
        obj=e.objects[i];scene_click(wing(obj));assert obj.isSelected();a=obj.mapToScene(obj.handles()['a']);b=obj.mapToScene(obj.handles()['b'])
        drag(b,b+QPointF(32,18));assert (obj.mapToScene(obj.handles()['a'])-a).manhattanLength()<2 and (obj.mapToScene(obj.handles()['b'])-b).manhattanLength()>40
        resized=e.render();assert resized!=moved;command('key 44 4');delay();assert e.render()==moved;command('key 44 5');delay();assert e.render()==resized
        records.append(dict(style=style,visible_head_selected=True,head_drag=True,endpoint_resize=True,undo_redo_pixels=True))
    scene_click(QPointF(900,650));expected=e.render();e.grab().save(str(out/'arrow-heads-editor.png'));expected.save(str(out/'arrows.png'));project=out/'arrows.omnishot';e.write_project(project)
    other=Editor(project,store);assert other.render()==expected and [o.props['style'] for o in other.objects]==styles;other.close();assert e.base==original_source
    report=dict(native_style_selection=True,native_drawing=True,double_both_heads=True,portable_reopen=True,source_unchanged=True,display_scale=1.6,styles=records)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    e.close();command('button 272 0');command('mods 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
