"""Actual headed Chromium → native auto-scroll capture → annotation/project."""
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.widgets import JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
horizontal='--horizontal' in sys.argv
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
base=['npx','--yes','agent-browser','--session','omnishot-browser-scroll-'+str(os.getpid())]
def browser(*args):return subprocess.check_output(base+list(args),text=True,timeout=20).strip()
def page_info():return json.loads(json.loads(browser('eval','JSON.stringify({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,y:scrollY,x:scrollX,total:document.documentElement.scrollHeight,totalWidth:document.documentElement.scrollWidth})')))
state=None;fixture=None;app=None;panel=None;errors=[]
try:
    print(browser('--headed','--executable-path','/usr/bin/chromium','--args','--ozone-platform=wayland,--start-fullscreen','open',Path(__file__).with_name('fixtures').joinpath('browser-scroll-horizontal.html' if horizontal else 'browser-scroll.html').resolve().as_uri()),flush=True)
    snapshot=browser('snapshot','-i');(out/'browser-snapshot.txt').write_text(snapshot)
    info=page_info();assert (info['width'],info['height'])==(1800,1125) and abs(info['dpr']-1.6)<.001,info
    app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False)
    fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
    def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
    def point(x,y):backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(80)
    def wait(predicate,seconds=12):
        end=time.monotonic()+seconds
        while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
        assert predicate(),dict(errors=errors,status=panel.status.text() if panel else None,accepted=panel.stitcher.accepted if panel else None)
    def click(widget):
        top=widget.window();c=next(c for c in backend.hypr('clients') if c['title']==top.windowTitle());p=widget.mapTo(top,widget.rect().center());point(c['at'][0]+p.x(),c['at'][1]+p.y());command('click 272');QTest.qWait(100)
    # Chromium briefly overlays a fullscreen-exit notice when it first opens.
    # Begin with the ordinary page, after that browser-owned notice has cleared.
    point(1500,900) if horizontal else point(1500,100);backend.run(['hyprctl','dismissnotify','-1']);QTest.qWait(6000)
    rect=(0,0,1800,600) if horizontal else (0,0,1000,1125);baseline=backend.grab(rect);Image.fromarray(baseline).save(out/'baseline.png')
    state=Controller(app);application.error=lambda parent,message:errors.append(str(message));state.store.settings.update(overlay_timeout=0,background_preset='None')
    if '--fast' in sys.argv:state.store.settings['scroll_interval']=150
    state.scroll(rect,horizontal);wait(lambda:state.panel is not None);panel=state.panel;QTest.qWait(200)
    push=panel.stitcher.push
    def observed(frame):
        previous=panel.stitcher.previous
        result=push(frame)
        if 'Could not align' in result[1] and not (out/'rejected-current.png').exists():
            Image.fromarray(previous).save(out/'rejected-previous.png');Image.fromarray(frame).save(out/'rejected-current.png')
        return result
    panel.stitcher.push=observed
    click(panel.start_btn);wait(lambda:panel.stitcher.accepted>=1)
    assert np.array_equal(panel.stitcher.output,baseline)
    click(panel.auto_btn);wait(lambda:panel.reached_end or (not panel.auto and panel.stitcher.accepted>1),45)
    wait(lambda:not panel.busy);tail=backend.grab(rect);final=page_info()
    (out/'capture-state.json').write_text(json.dumps(dict(page=final,status=panel.status.text(),frames=panel.stitcher.accepted,position=panel.stitcher.position,reached_end=panel.reached_end),indent=2))
    Image.fromarray(panel.stitcher.output).save(out/'stitched.png');Image.fromarray(tail).save(out/'tail.png')
    assert panel.reached_end and (final['x']==final['totalWidth']-final['width'] if horizontal else final['y']==final['total']-final['height']),final
    result=panel.stitcher.output;expected_length=round(final['totalWidth' if horizontal else 'total']*1.6)
    if horizontal:
        result=result.transpose(1,0,2);baseline=baseline.transpose(1,0,2);tail=tail.transpose(1,0,2)
    assert result.shape==(expected_length,960 if horizontal else 1600,3),(result.shape,expected_length)
    assert np.array_equal(result[:len(baseline)-72],baseline[:-72])
    assert np.array_equal(result[-len(tail)+112:],tail[112:])
    text=backend.run(['tesseract',out/'stitched.png','stdout','--psm','6']).decode();(out/'text.txt').write_text(text)
    rows=[int(n) for n in re.findall(r'(?:Column|Row)\s*(\d{2})',text)];assert rows==list(range(1,31 if horizontal else 61)),rows
    click(panel.done_btn);wait(lambda:len(state.overlays)==1 and not JOBS);QTest.qWait(200);click(state.overlays[0].preview)
    wait(lambda:any(isinstance(w,Editor) for w in state.windows));editor=next(w for w in state.windows if isinstance(w,Editor));QTest.qWait(180)
    digest=hashlib.sha256(editor.path.read_bytes()).hexdigest();click(editor.toolbar.widgetForAction(editor.tools['arrow']))
    c=next(c for c in backend.hypr('clients') if c['title']==editor.windowTitle())
    for (x,y),pressed in ([((500,200),True),((3500,700),False)] if horizontal else [((200,500),True),((1100,3500),False)]):
        p=editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(x,y)));point(c['at'][0]+p.x(),c['at'][1]+p.y());command('button 272 '+('1' if pressed else '0'));QTest.qWait(100)
    assert len(editor.objects)==1;project=out/'browser-scroll.omnishot';editor.write_project(project);render=editor.render();reopened=Editor(project,state.store);assert reopened.render()==render;reopened.close();editor.grab().save(str(out/'editor.png'))
    assert hashlib.sha256(editor.path.read_bytes()).hexdigest()==digest and not errors
    assert not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
    report=dict(headed_chromium_wayland=True,horizontal=horizontal,scale=1.6,interval=state.store.settings['scroll_interval'],step=state.store.settings['scroll_step'],native_start_auto_done=True,frames=panel.stitcher.accepted,all_rows=rows,result_size=[panel.stitcher.output.shape[1],panel.stitcher.output.shape[0]],fixed_header_footer_edges_exact=True,reached_browser_bottom=True,native_preview_annotation=True,editable_project_reopens=True,source_unchanged=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
finally:
    if state:state.cleanup()
    if app:
        for w in app.topLevelWidgets():w.close()
    if fixture:fixture.stdin.close();fixture.wait(timeout=3)
    print(browser('close'),flush=True)
