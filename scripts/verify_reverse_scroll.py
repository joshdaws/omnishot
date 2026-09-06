"""Native reverse scrolling with fixed leading/trailing chrome and edit handoff."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QPixmap
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QScrollArea,QLabel,QFrame
from PySide6.QtTest import QTest
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.widgets import place_window,JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
horizontal='--horizontal' in sys.argv;recover='--recover' in sys.argv
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
errors=[];panel=None
def wait(predicate,seconds=8):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),dict(errors=errors,status=panel.status.text() if panel else '',position=bar.value())
def point(x,y):backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(80)
def click(widget):
    top=widget.window();c=next(c for c in backend.hypr('clients') if c['title']==top.windowTitle());p=widget.mapTo(top,widget.rect().center());point(c['at'][0]+p.x(),c['at'][1]+p.y());command('click 272');QTest.qWait(100)
window=QWidget();window.setWindowTitle('Generated reverse scrolling source');window.setFixedSize(600 if horizontal else 700,600)
layout=(QHBoxLayout if horizontal else QVBoxLayout)(window);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
for index,color,size in [(0,'#50466e',45),(1,None,0),(2,'#8296aa',30)]:
    if color:
        widget=QWidget();widget.setStyleSheet('background:'+color)
        (widget.setFixedWidth if horizontal else widget.setFixedHeight)(size)
    else:
        widget=QScrollArea();area=widget;area.setFrameShape(QFrame.Shape.NoFrame);area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    layout.addWidget(widget)
source=QImage(3000 if horizontal else 700,600 if horizontal else 3000,QImage.Format.Format_RGB888);source.fill(QColor('white'));p=QPainter(source);p.setFont(QFont('sans-serif',16))
for pos in range(0,3000,60):
    if horizontal:
        for y in range(0,600,60):
            p.fillRect(pos+2,y+2,56,56,QColor.fromHsv((pos+y)%360,85,230));p.setPen(QColor('#243756'));p.drawText(pos+5,y+36,str(pos//60+1)+'/'+str(y//60+1))
    else:
        p.fillRect(0,pos,700,60,QColor('#edf1f5' if pos%120 else 'white'));p.setPen(QColor('#243756'));p.drawText(20,pos+38,f'Row {pos//60+1:02d} · unique marker {pos*73+42}')
p.end();label=QLabel();label.setPixmap(QPixmap.fromImage(source));area.setWidget(label)
bar=area.horizontalScrollBar() if horizontal else area.verticalScrollBar();bar.setSingleStep(20)
window.show();place_window(window,450,160);QTest.qWait(250);bar.setValue(540);QTest.qWait(150)
client=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());rect=(*client['at'],window.width(),window.height());scale=backend.capture_monitors()[0]['scale'];assert scale==1.6
state=Controller(app);application.error=lambda parent,message:errors.append(str(message));state.store.settings.update(scroll_interval=200,overlay_timeout=0,background_preset='None')
frames=[];positions=[]
def sample():
    wait(lambda:not panel.busy and time.monotonic()>=panel.visuals.ready_at)
    frame=backend.grab(rect);frames.append(frame.transpose(1,0,2).copy() if horizontal else frame);positions.append(bar.value())
def scroll(amount):
    point(rect[0]+rect[2]//2,rect[1]+rect[3]//2);before=bar.value();accepted=panel.stitcher.accepted
    backend.scroll_step(horizontal,amount);wait(lambda:bar.value()!=before)
    wait(lambda:panel.stitcher.accepted>accepted and panel.stitcher.position==round((bar.value()-540)*scale))
    sample()
try:
    state.scroll(rect,horizontal);wait(lambda:state.panel is not None);panel=state.panel;QTest.qWait(250)
    click(panel.start_btn);wait(lambda:panel.stitcher.accepted>=1);sample()
    if recover:
        saved=panel.stitcher.output.copy();accepted=panel.stitcher.accepted
        reference=panel.stitcher.previous.copy();Image.fromarray(reference).save(out/'before-jump.png')
        point(rect[0]+rect[2]//2,rect[1]+rect[3]//2);backend.scroll_step(horizontal,-8)
        QTest.qWait(250);jump=backend.grab(rect);jump=jump.transpose(1,0,2).copy() if horizontal else jump;Image.fromarray(jump).save(out/'after-jump.png')
        from omnishot.stitch import match_translation
        match=match_translation(reference,jump)
        (out/'jump-state.json').write_text(json.dumps(dict(match=vars(match),position=panel.stitcher.position,accepted=panel.stitcher.accepted,status=panel.status.text()),indent=2))
        wait(lambda:'Could not align' in panel.status.text() and not panel.busy)
        assert bar.value()==60 and panel.stitcher.accepted==accepted and np.array_equal(panel.stitcher.output,saved)
        scroll(6)
    else:scroll(-2)
    scroll(2);scroll(-2)
    unchanged=panel.stitcher.output.copy();QTest.qWait(500);wait(lambda:not panel.busy);assert np.array_equal(panel.stitcher.output,unchanged)
    while bar.value()>0:scroll(-2)
    frame=frames[-1];header=round(45*scale);footer=round(30*scale);body=len(frame)-header-footer
    expected=np.zeros((round(540*scale)+len(frame),frame.shape[1],3),np.uint8);expected[:header]=frame[:header];expected[-footer:]=frames[0][-footer:]
    covered=np.zeros(len(expected),bool);covered[:header]=True;covered[-footer:]=True
    for position,frame in zip(positions,frames):
        start=header+round(position*scale);expected[start:start+body]=frame[header:-footer];covered[start:start+body]=True
    assert covered.all()
    actual=panel.stitcher.output.transpose(1,0,2) if horizontal else panel.stitcher.output
    Image.fromarray(expected).save(out/'expected-verticalized.png');Image.fromarray(actual).save(out/'actual-verticalized.png')
    assert np.array_equal(actual,expected),(actual.shape,expected.shape,int(np.count_nonzero(actual!=expected)) if actual.shape==expected.shape else None)
    click(panel.done_btn);wait(lambda:len(state.overlays)==1 and not JOBS)
    assert not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
    QTest.qWait(200);click(state.overlays[0].preview);wait(lambda:any(isinstance(w,Editor) for w in state.windows));editor=next(w for w in state.windows if isinstance(w,Editor));QTest.qWait(150)
    original=hashlib.sha256(editor.path.read_bytes()).hexdigest();click(editor.toolbar.widgetForAction(editor.tools['arrow']))
    c=next(c for c in backend.hypr('clients') if c['title']==editor.windowTitle())
    for (x,y),pressed in [((150,200),True),((600,700),False)]:
        pt=editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(x,y)));point(c['at'][0]+pt.x(),c['at'][1]+pt.y());command('button 272 '+('1' if pressed else '0'));QTest.qWait(100)
    assert len(editor.objects)==1;project=out/'reverse-scroll.omnishot';editor.write_project(project);rendered=editor.render();reopened=Editor(project,state.store);assert reopened.render()==rendered;reopened.close();editor.grab().save(str(out/'editor.png'))
    assert hashlib.sha256(editor.path.read_bytes()).hexdigest()==original and not errors
    report=dict(horizontal=horizontal,scale=scale,scroll_positions=positions,native_alignment_failure_and_recovery=recover,native_reverse_and_direction_changes=True,pause_does_not_grow=True,all_pixels_match_recorded_viewports=True,fixed_leading_edge_once=True,fixed_trailing_edge_once=True,result_size=[panel.stitcher.output.shape[1],panel.stitcher.output.shape[0]],native_done_preview_annotation=True,editable_project_roundtrip=True,source_unchanged=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cleanup()
    for w in app.topLevelWidgets():w.close()
    command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
