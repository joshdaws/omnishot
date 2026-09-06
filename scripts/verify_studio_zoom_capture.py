"""Generate a native Studio capture with clicks hidden and automatic zooms."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtWidgets import QApplication,QLabel
from omnishot import backend,recording
from omnishot.widgets import place_window,JOBS
from omnishot.clean_capture import NATIVE

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
original_command=recording.recorder_command
def isolated_command(*args,**kwargs):
    cmd=original_command(*args,**kwargs);cmd[cmd.index('-w')+1]='screen'
    if '-region' in cmd:
        index=cmd.index('-region');del cmd[index:index+2]
    return cmd
recording.recorder_command=isolated_command
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
errors=[];rec=None;recording.error=lambda parent,message:errors.append(str(message))
loaded=any(p.get('name')=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),errors
def delay(seconds):
    start=time.monotonic();wait(lambda:time.monotonic()-start>=seconds,seconds+1)
try:
    window=QLabel('Automatic zoom capture fixture');window.setWindowTitle('OmniShot Zoom Capture Fixture');window.setStyleSheet('background:#20385b;color:white;font-size:24px');window.resize(600,400);window.show();place_window(window,100,100);delay(.6)
    client=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());rect=(*client['at'],*client['size'])
    opts=dict(mode='Area',format='MP4',fps=15,quality='high',size='Native',system=False,mic=False,cursor=False,delay=0,studio=True,keys=False,clicks=False,camera=False,dnd=False)
    store=backend.Store(out/'data');rec=recording.Recorder(store,rect,opts);results=[];rec.completed.connect(results.append);rec.show();wait(lambda:rec.ready or bool(errors),10);assert not errors
    assert rec.telemetry.clicks and not rec.telemetry.keys
    delay(.7);backend.move_cursor(rect[0]+rect[2]//3-2,rect[1]+rect[3]//2);command('move 2 0');delay(.1);command('click 272');delay(1.7)
    rec.stop();wait(lambda:bool(results) or bool(errors),20);assert not errors
    rendered=Path(results[0]);metadata=json.loads(rendered.with_suffix('.studio.json').read_text());zooms=metadata['initial_zooms']
    assert zooms and any(event['kind']=='click' for event in metadata['events'])
    assert not any(event['kind']=='key' for event in metadata['events'])
    duration=float(json.loads(backend.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',metadata['source_path']]))['format']['duration'])
    assert all(0<=z['start']<z['end']<=duration for z in zooms)
    assert not metadata['capture_options']['clicks']
    assert backend.run(['hyprctl','repl','return omnishot_capture==nil']).decode().strip()=='true'
    e=recording.VideoEditor(rendered,store);e.player.pause();assert e.zooms==zooms and not e.show_clicks.isChecked() and not e.show_cursor.isChecked() and not e.show_keys.isChecked()
    e.close();wait(lambda:not JOBS)
    report=dict(native_studio_capture=True,automatic_zooms=zooms,source_duration=duration,hidden_click_effect_preserved=True,no_keystrokes_observed=True,subscriptions_removed_after_stop=True,editor_seeded=True,physical_microphone_used=False)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if rec:rec.shutdown();rec.stopping=True;rec.close()
    fixture.stdin.close();fixture.wait(timeout=3)
    for widget in app.topLevelWidgets():widget.close()
    if not loaded:subprocess.run(['hyprctl','plugin','unload',str((NATIVE/'clean-mirror.so').resolve())],capture_output=True,timeout=5)
