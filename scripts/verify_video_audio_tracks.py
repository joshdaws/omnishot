"""Native audio controls and isolated speaker-loopback measurements; no microphone."""
import hashlib,json,os,subprocess,sys,time,uuid
from pathlib import Path
import numpy as np
from PySide6.QtCore import QPoint,Qt
from PySide6.QtMultimedia import QMediaDevices,QMediaPlayer
from PySide6.QtWidgets import QApplication,QCheckBox,QFileDialog,QScrollArea
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('PULSE_SERVER',f'unix:/run/user/{os.getuid()}/pulse/native')
sink='omnishot_edit_'+uuid.uuid4().hex[:8]
module=backend.run(['pactl','load-module','module-null-sink','sink_name='+sink,'rate=48000','sink_properties=device.description='+sink]).decode().strip()
os.environ['PULSE_SINK']=sink
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.015)
    assert predicate()
def click(widget):
    parent=widget.parentWidget()
    while parent and not isinstance(parent,QScrollArea):parent=parent.parentWidget()
    if parent:parent.ensureWidgetVisible(widget);QTest.qWait(50)
    assert widget.isVisible() and widget.isEnabled(),widget
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==editor.windowTitle())
    local=widget.mapTo(editor,QPoint(10,widget.height()//2) if isinstance(widget,QCheckBox) else widget.rect().center())
    backend.move_cursor(client['at'][0]+local.x()-2,client['at'][1]+local.y());command('move 2 0');QTest.qWait(70);command('click 272');QTest.qWait(120)
def enter(widget,value):
    click(widget);backend.copy_text(str(value));command('key 30 4');command('key 47 4');command('key 28 0');QTest.qWait(130)
def choose(widget,index):
    click(widget);command('key 102 0')
    for _ in range(index):command('key 108 0')
    command('key 28 0');QTest.qWait(150)
def save_dialog(path):
    wait(lambda:any(isinstance(w,QFileDialog) and w.isVisible() for w in app.topLevelWidgets()))
    QTest.qWait(180);command('key 38 4');QTest.qWait(80);backend.copy_text(str(path));command('key 47 4');QTest.qWait(80);command('key 28 0')
def measure(name):
    editor.player.pause();editor.player.setPosition(1000)
    target=out/(name+'.f32');stream=target.open('wb');proc=subprocess.Popen(['parec','--device='+sink+'.monitor','--format=float32le','--rate=48000','--channels=2','--latency-msec=20','--process-time-msec=10'],stdout=stream)
    try:
        editor.player.play();start=time.monotonic()
        wait(lambda:time.monotonic()-start>.85,2)
        editor.player.pause()
    finally:proc.terminate();proc.wait(2);stream.close()
    data=np.frombuffer(target.read_bytes(),dtype='<f4').reshape(-1,2)
    active=data[np.max(np.abs(data),axis=1)>.0001]
    # Discard the start/end latency using the middle half of the observation.
    window=data[len(data)//3:len(data)*2//3]
    return window,dict(rms=float(np.sqrt(np.mean(window**2))),frames=len(data),active_frames=len(active))
source=out/'source.mp4'
backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x240:rate=15:duration=8','-f','lavfi','-i','aevalsrc=0.12*sin(440*2*PI*t)|0.06*sin(880*2*PI*t):s=48000:d=8','-f','lavfi','-i','aevalsrc=0.1*sin(1320*2*PI*t)|0.08*sin(1760*2*PI*t):s=48000:d=8','-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-threads','1','-c:a','aac',source])
source.with_suffix('.studio.json').write_text(json.dumps(dict(version=1,cursor=[],events=[],capture_options=dict(audio_sources=['system','microphone']))))
original=hashlib.sha256(source.read_bytes()).hexdigest()
store=backend.Store(out/'data');store.settings['output_dir']=str(out);editor=None
try:
    wait(lambda:any(sink in device.description() for device in QMediaDevices.audioOutputs()))
    device=next(d for d in QMediaDevices.audioOutputs() if sink in d.description())
    editor=VideoEditor(source,store);editor.player.pause();editor.audio.setDevice(device);editor.audio_preview.output.setDevice(device);editor.show()
    wait(lambda:editor.last_frame is not None and len(editor.player.audioTracks())==2)
    QTest.qWait(250);click(editor.tool_buttons['Audio'])
    assert editor.audio_mix.isChecked()
    wait(lambda:len(editor.audio_tracks_controls.rows)==2)
    system,mic=editor.audio_tracks_controls.rows
    assert system[1].text()=='System audio' and mic[1].text()=='Microphone'
    def tone(data,hz):
        t=np.arange(len(data))/48000
        return float(abs(np.sum(data[:,0]*np.exp(-2j*np.pi*hz*t)))*2/len(data))
    baseline,full=measure('full');assert full['rms']>.05,(full,editor.audio_notice.text())
    peaks=[tone(baseline,hz) for hz in (440,1320)];assert min(peaks)>.08,peaks
    enter(system[3],50);enter(mic[3],200)
    mixed_data,mixed=measure('independent');ratios=[tone(mixed_data,hz)/peaks[i] for i,hz in enumerate((440,1320))]
    assert .45<ratios[0]<.55 and 1.8<ratios[1]<2.2,ratios
    click(system[1]);isolated_data,isolated=measure('microphone-only')
    assert tone(isolated_data,440)<.001 and tone(isolated_data,1320)>.17
    click(mic[1]);disabled_data,disabled=measure('both-disabled');assert disabled['rms']<1e-6,disabled
    click(system[1]);click(mic[1]);enter(mic[3],100)
    click(editor.audio_mono);mono_data,mono=measure('mono');assert mono['rms']>.01,(mono,editor.audio_notice.text())
    difference=float(np.max(np.abs(mono_data[:,0]-mono_data[:,1])));assert difference<1e-5,difference
    click(editor.audio_muted);muted_data,muted=measure('muted');assert muted['rms']<1e-6,muted;click(editor.audio_muted)
    click(editor.tool_buttons['Trim']);choose(editor.speed,2);assert editor.player.playbackRate()==1.5
    editor.player.setPosition(3500);editor.player.play();start=time.monotonic();wait(lambda:time.monotonic()-start>.45,2)
    drift=abs(editor.player.position()-editor.audio_preview.mix.position());assert drift<230,drift;editor.player.pause()
    editor.cuts=[[1.2,2.4]];editor.player.setPosition(1500);editor.player.play()
    wait(lambda:editor.player.position()>=2400)
    QTest.qWait(150);cut_drift=abs(editor.player.position()-editor.audio_preview.mix.position());assert cut_drift<230,cut_drift
    editor.player.pause();assert editor.audio_preview.mix.process is None
    editor.cuts=[]
    click(editor.tool_buttons['Audio']);click(editor.audio_muted)
    click(editor.tool_buttons['Export']);choose(editor.format,1);assert not editor.audio_volume.isEnabled() and editor.audio_preview.output.isMuted()
    choose(editor.format,0);assert editor.audio_volume.isEnabled() and editor.audio_preview.output.isMuted()
    click(editor.tool_buttons['Audio']);assert editor.audio_muted.isChecked();click(editor.audio_muted)
    editor.grab().save(str(out/'audio-editor.png'))
    editor.start.setValue(.2);editor.end.setValue(1.6);editor.cuts=[[.7,.9]];editor.fps.setValue(15);editor.size.setCurrentText('400')
    from PySide6.QtCore import QTimer
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(lambda:save_dialog(out/'edited.mp4'));timer.start(180);click(editor.export_btn);wait(lambda:(out/'edited.mp4').exists() and editor.export_cancel is None)
    probe=json.loads(backend.run(['ffprobe','-v','error','-select_streams','a','-show_entries','stream=channels','-of','json',out/'edited.mp4']))['streams'];assert [t['channels'] for t in probe]==[1]
    timer.timeout.disconnect();timer.timeout.connect(lambda:save_dialog(out/'edited.omnishot-video'));timer.start(180);click(editor.project_btn);wait(lambda:(out/'edited.omnishot-video').exists() and editor.export_cancel is None)
    expected=editor.edit_options();editor.close();assert editor.audio_preview.mix.process is None
    editor=VideoEditor(out/'edited.omnishot-video',store);editor.player.pause();editor.audio.setDevice(device);editor.audio_preview.output.setDevice(device)
    wait(lambda:len(editor.audio_tracks_controls.rows)==2)
    assert editor.edit_options()==expected and editor.audio_mono.isChecked()
    editor.close()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    report=dict(native_audio_controls=True,isolated_loopback=True,physical_microphone_used=False,
        full=full,both_source_amplitudes=peaks,independent_gain_ratios=ratios,isolated_microphone=isolated,
        both_disabled=disabled,muted=muted,mono=mono,mono_channel_difference=difference,
        speed_seek_drift_ms=drift,cut_skip_drift_ms=cut_drift,gif_preserves_audio_edits=True,
        native_export_mono_tracks=probe,native_editable_save_reopen=True,source_unchanged=True,
        streaming_decoder_cleanup=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if editor:editor.close()
    command('mods 0');command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
    backend.run(['pactl','unload-module',module])
