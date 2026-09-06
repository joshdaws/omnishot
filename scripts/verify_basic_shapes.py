"""Native basic shape tools, proportional handles, line constraint and reopening."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor,QImage
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
    for i in range(1,3):scene_pointer(a+(b-a)*i/2)
    command('button 272 0');delay()
try:
    kinds=['rect','ellipse','fill','line'];positions=[(100,100),(520,100),(100,400),(520,400)]
    for kind,(x,y) in zip(kinds,positions):
        click(e.toolbar.widgetForAction(e.tools[kind]));command('mods '+('1' if kind in ('rect','line') else '0'))
        drag(QPointF(x,y),QPointF(x+220,y+120));command('mods 0');delay(.05)
        obj=e.objects[-1];assert obj.props['kind']==kind
        if kind in ('rect','line'):assert abs(obj.props['w']-obj.props['h'])<2
    click(e.toolbar.widgetForAction(e.tools['select']));records=[]
    opposite={'lt':'rb','t':'b','rt':'lb','r':'l','rb':'lt','b':'t','lb':'rt','l':'r'}
    deltas={'lt':(-35,-25),'t':(0,-30),'rt':(35,-25),'r':(35,0),'rb':(35,25),'b':(0,30),'lb':(-35,25),'l':(-35,0)}
    for i,kind in enumerate(kinds[:3]):
        for edge,delta in deltas.items():
            obj=e.objects[i];scene_click(obj.mapToScene(QPointF(obj.props['w']/2,obj.props['h']/2)));assert obj.isSelected()
            before=e.render();ratio=obj.props['w']/obj.props['h'];anchor=obj.mapToScene(obj.handles()[opposite[edge]]);start=obj.mapToScene(obj.handles()[edge]);old_size=(obj.props['w'],obj.props['h'])
            command('mods 1');drag(start,start+QPointF(*delta));command('mods 0');delay(.04)
            assert abs(obj.props['w']/obj.props['h']-ratio)<.001,(kind,edge)
            assert (obj.mapToScene(obj.handles()[opposite[edge]])-anchor).manhattanLength()<2,(kind,edge,anchor,obj.pos())
            assert abs(obj.props['w']-old_size[0])+abs(obj.props['h']-old_size[1])>20
            changed=e.render();assert changed!=before;command('key 44 4');delay(.07);assert e.render()==before
            command('key 44 5');delay(.07);assert e.render()==changed;command('key 44 4');delay(.07);assert e.render()==before
        records.append(dict(kind=kind,all_eight_handles=True,shift_ratio=True,opposite_anchor=True,undo_redo_pixels=True))
    line=e.objects[3];a=line.mapToScene(line.handles()['a']);b=line.mapToScene(line.handles()['b']);scene_click((a+b)/2);assert line.isSelected()
    command('mods 1');drag(b,b+QPointF(25,25));command('mods 0');delay(.05)
    assert (line.mapToScene(line.handles()['a'])-a).manhattanLength()<2 and abs(line.props['w']-line.props['h'])<2
    scene_click(QPointF(900,650));expected=e.render();e.grab().save(str(out/'basic-shapes-editor.png'));expected.save(str(out/'basic-shapes.png'));project=out/'shapes.omnishot';e.write_project(project)
    other=Editor(project,store);assert other.render()==expected and [o.props['kind'] for o in other.objects]==kinds;other.close();assert e.base==original_source
    report=dict(native_drawing=True,shift_square_and_line_angle=True,native_line_endpoint_resize=True,portable_reopen=True,source_unchanged=True,display_scale=1.6,shapes=records)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    e.close();command('button 272 0');command('mods 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
