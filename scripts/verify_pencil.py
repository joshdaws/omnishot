"""Native pencil drawing in eight directions, live pixels and proportional resize."""
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
    click(e.toolbar.widgetForAction(e.tools['pencil']));records=[]
    directions=[(-130,-80),(-130,0),(-130,80),(0,-80),(0,80),(130,-80),(130,0),(130,80)]
    starts=[(200,180),(500,180),(800,180),(200,380),(500,380),(800,380),(200,570),(500,570)]
    for index,(origin,delta) in enumerate(zip(starts,directions)):
        a=QPointF(*origin);b=a+QPointF(*delta);scene_pointer(a);command('button 272 1');delay(.04)
        for step in (1,2):scene_pointer(a+(b-a)*step/2)
        draft=e.view.draft;assert draft is not None
        for point in draft.props['points']:assert draft.boundingRect().contains(QPointF(*point))
        live=e.render();mid=(a+b)/2;pixel=live.pixelColor(round(mid.x()),round(mid.y()));assert pixel.green()<170,pixel.getRgb()
        command('button 272 0');delay(.08);assert len(e.objects)==index+1
        obj=e.objects[-1];assert obj.props['w']>3 or obj.props['h']>3
        expected=e.render();command('key 44 4');delay(.06);assert len(e.objects)==index
        command('key 44 5');delay(.06);assert e.render()==expected and len(e.objects)==index+1
        records.append(dict(delta=delta,live_pixels=True,retained_after_release=True,undo_redo=True))
    loop=[QPointF(*point) for point in [(770,570),(700,625),(900,655),(900,550),(700,520),(770,570)]]
    scene_pointer(loop[0]);command('button 272 1');delay(.05)
    for point in loop[1:]:scene_pointer(point)
    command('button 272 0');delay(.08);assert len(e.objects)==9
    obj=e.objects[-1]
    assert (QPointF(*obj.props['points'][0])-QPointF(*obj.props['points'][-1])).manhattanLength()<2
    click(e.toolbar.widgetForAction(e.tools['select']))
    opposite={'lt':'rb','t':'b','rt':'lb','r':'l','rb':'lt','b':'t','lb':'rt','l':'r'}
    deltas={'lt':(-30,-20),'t':(0,-25),'rt':(30,-20),'r':(30,0),'rb':(30,20),'b':(0,25),'lb':(-30,20),'l':(-30,0)}
    for edge,delta in deltas.items():
        obj=e.objects[0];scene_click(obj.mapToScene(QPointF(obj.props['w']/2,obj.props['h']/2)));assert obj.isSelected()
        before=e.render();props=obj.data_dict();anchor=obj.mapToScene(obj.handles()[opposite[edge]]);start=obj.mapToScene(obj.handles()[edge])
        command('mods 1');drag(start,start+QPointF(*delta));command('mods 0');delay(.05)
        assert abs(obj.props['w']/obj.props['h']-props['w']/props['h'])<.001
        assert (obj.mapToScene(obj.handles()[opposite[edge]])-anchor).manhattanLength()<2
        assert obj.props['points']!=props['points']
        for (x,y),(px,py) in zip(obj.props['points'],props['points']):
            assert abs(x-px*obj.props['w']/props['w'])<.001 and abs(y-py*obj.props['h']/props['h'])<.001
        changed=e.render();assert changed!=before
        command('key 44 4');delay(.06);assert e.render()==before
        command('key 44 5');delay(.06);assert e.render()==changed
        if edge!='l':command('key 44 4');delay(.06);assert e.render()==before
    scene_click(QPointF(930,650));expected=e.render();e.grab().save(str(out/'pencil-editor.png'));project=out/'pencil.omnishot';e.write_project(project)
    other=Editor(project,store);assert other.render()==expected and len(other.objects)==9;assert other.objects[0].props['points']==e.objects[0].props['points'];other.close();assert e.base==original_source
    report=dict(native_pencil_directions=records,native_all_eight_resize_handles=True,native_closed_loop=True,resized_stroke_portable=True,shift_proportions=True,points_scale_with_selection=True,opposite_anchor=True,resize_undo_redo=True,portable_reopen=True,source_unchanged=True,display_scale=1.6,theme_applied=bool(theme.applied))
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    e.close();command('button 272 0');command('mods 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
