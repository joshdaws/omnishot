"""Native mixed-scale drag → frozen/live capture → preview → editable annotation."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.widgets import JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
config=Path(os.environ['XDG_RUNTIME_DIR'])/'hyprland.lua';assert config.parent.name.startswith('os-')
left='--left' in sys.argv;sx=-1920 if left else 1800
config.write_text(config.read_text()+f'\nhl.monitor({{output="HEADLESS-2",mode="1920x1080@60",position="{sx}x0",scale=1}})\n')
backend.run(['hyprctl','reload']);assert not backend.run(['hyprctl','configerrors']).strip();backend.run(['hyprctl','output','create','headless','HEADLESS-2'])
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
errors=[]
def wait(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate(),errors
def point(x,y):backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(80)
def click(widget):
    top=widget.window();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==top.windowTitle());p=widget.mapTo(top,widget.rect().center())
    point(client['at'][0]+p.x(),client['at'][1]+p.y());command('click 272');QTest.qWait(150)
wait(lambda:len(app.screens())==2)
class Pattern(QWidget):
    def paintEvent(self,event):p=QPainter(self);p.fillRect(self.rect(),QColor(self.color))
sources=[]
for name in ('HEADLESS-1','HEADLESS-2'):
    w=Pattern();w.color='#468ac0';w.setWindowTitle('Generated shared selection '+name);w.winId();w.windowHandle().setScreen(next(s for s in app.screens() if s.name()==name));w.showFullScreen();sources.append(w);QTest.qWait(150)
state=Controller(app);application.error=lambda parent,message:errors.append(str(message))
state.store.settings.update(background_preset='None',overlay_timeout=0,scale_screenshots=False)
rect=(-100 if left else 1700,150,200,200);reports=[]
try:
    for live in (False,True):
        state.store.settings.update(freeze=not live);state.store.settings.pop('previous_area',None)
        for w,color in zip(sources,('#468ac0','#54ac76')):w.color=color;w.update()
        QTest.qWait(150);backend.run(['hyprctl','dismissnotify','-1']);before=len(state.store.history());state.capture('select',{'action':'overlay'});wait(lambda:len(state.selectors)==2);QTest.qWait(250)
        x,y,w,h=rect;point(x,y);command('button 272 1');QTest.qWait(80);point(x+w-1,y+h-1);command('button 272 0');QTest.qWait(150)
        group=state.selectors[0].group
        assert all(group.region(s).getRect()==rect for s in state.selectors)
        command('key 106 4');QTest.qWait(100);assert all(s.width_box.value()==201 for s in state.selectors)
        command('key 105 4');QTest.qWait(100);assert all(group.region(s).getRect()==rect for s in state.selectors)
        for index,s in enumerate(state.selectors):s.grab().save(str(out/f'selection-{live}-{index}.png'))
        for w,color in zip(sources,('#c85670','#dbac32')):w.color=color;w.update()
        QTest.qWait(200);command('key 28 0')
        wait(lambda:len(state.store.history())==before+1 and len(state.overlays)==1 and not JOBS and not state.busy)
        path=Path(state.store.history()[0]['path']);original=hashlib.sha256(path.read_bytes()).hexdigest();image=Image.open(path).convert('RGB')
        colors=[(200,86,112),(219,172,50)] if live else [(70,138,192),(84,172,118)]
        if left:colors.reverse()
        assert image.size==(320,320) and state.store.metadata(path)['pixel_ratio']==1.6
        assert [image.getpixel((x,160)) for x in (50,270)]==colors
        assert state.store.settings['previous_area']==list(rect)
        assert not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
        QTest.qWait(250);preview=state.overlays[0];click(preview.preview);wait(lambda:any(isinstance(w,Editor) for w in state.windows));editor=next(w for w in state.windows if isinstance(w,Editor));QTest.qWait(200)
        click(editor.toolbar.widgetForAction(editor.tools['arrow']))
        client=next(c for c in backend.hypr('clients') if c['title']==editor.windowTitle())
        for (x,y),down in [((50,70),True),((270,220),False)]:
            p=editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(x,y)));point(client['at'][0]+p.x(),client['at'][1]+p.y());command('button 272 '+('1' if down else '0'));QTest.qWait(100)
        assert len(editor.objects)==1 and editor.objects[0].props['kind']=='arrow'
        project=out/f'annotated-{live}.omnishot';editor.write_project(project);render=editor.render();other=Editor(project,state.store);assert other.render()==render;other.close()
        editor.grab().save(str(out/f'editor-{live}.png'));render.save(str(out/f'annotated-{live}.png'));editor.close()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==original
        state.close_all_overlays();wait(lambda:not state.windows and not state.overlays and not JOBS)
        reports.append(dict(live=live,rect=rect,pixels=[320,320],colors=colors,native_drag=True,native_dimension_keys=True,native_preview_to_arrow=True,portable_project=True,source_unchanged=True))
    assert not errors
    report=dict(negative_position=left,mixed_scales=[1.6,1],cases=reports)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
