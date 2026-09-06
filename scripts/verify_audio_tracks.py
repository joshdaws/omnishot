"""Record two isolated synthetic audio sources and preserve both through export."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import wave
import numpy as np
from PySide6.QtWidgets import QApplication,QLabel
from omnishot import backend,recording
from omnishot.widgets import place_window
from omnishot.studio import export_studio
from omnishot.clean_capture import NATIVE

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
mono='--mono' in sys.argv
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False)
modules=[];players=[];names=[];rec=None;errors=[];recording.error=lambda parent,message:errors.append(str(message))
loaded=any(p.get('name')=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
def wait(predicate,seconds):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),errors

def inspect(path):
    streams=json.loads(backend.run(['ffprobe','-v','error','-select_streams','a','-show_entries','stream=index,channels','-of','json',path]))['streams'];assert len(streams)==2,streams
    if mono:assert all(stream['channels']==1 for stream in streams),streams
    results=[]
    for index,frequency in enumerate((440,1320)):
        raw=backend.run(['ffmpeg','-v','error','-i',path,'-map',f'0:a:{index}','-f','f32le','-ac','1','-ar','8000','-']);audio=np.frombuffer(raw,dtype='<f4');rms=float(np.sqrt(np.mean(audio**2)));peak=float(np.argmax(np.abs(np.fft.rfft(audio)))*8000/len(audio))
        assert rms>.02 and abs(peak-frequency)<4,(rms,peak,frequency)
        results.append(dict(track=index,dominant_hz=peak,rms=rms))
    return results
try:
    for frequency in (440,1320):
        name='omnishot_tracks_'+uuid.uuid4().hex[:8];names.append(name)
        modules.append(backend.run(['pactl','load-module','module-null-sink','sink_name='+name,'rate=48000']).decode().strip())
        samples=(np.sin(np.arange(48000*12)*2*np.pi*frequency/48000)*14000).astype('<i2');tone=out/f'tone-{frequency}.wav'
        with wave.open(str(tone),'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(samples.tobytes())
        players.append(subprocess.Popen(['paplay','--device='+name,str(tone)]))
    window=QLabel('OmniShot generated audio-track test\nTwo isolated tones; no physical microphone.');window.setWindowTitle('OmniShot Generated Audio Tracks');window.resize(600,400);window.show();place_window(window,100,100)
    started=time.monotonic();wait(lambda:time.monotonic()-started>.6,2)
    client=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());rect=(*client['at'],*client['size'])
    opts=dict(mode='Area',format='MP4',fps=15,quality='high',size='Native',system=True,mic=True,cursor=False,delay=0,system_device=names[0]+'.monitor',mic_device=names[1]+'.monitor',separate_audio=True,mono=mono,dnd=False)
    store=backend.Store(out/'data');rec=recording.Recorder(store,rect,opts);results=[];rec.completed.connect(results.append);rec.show();wait(lambda:rec.ready or bool(errors),10);assert not errors
    started=time.monotonic();wait(lambda:time.monotonic()-started>2.4,4);rec.stop();wait(lambda:bool(results) or bool(errors),20);assert not errors
    source=Path(results[0]);original=inspect(source)
    options=dict(start=.2,end=2,speed=1.5,fps=15,width=240,format='MP4',padding=0,background='#202633',blur=False)
    plain=out/'plain-export.mp4';recording.export_video(source,plain,options);plain_audio=inspect(plain)
    studio=out/'studio-export.mp4';export_studio(source,studio,{'cursor':[],'events':[]},{**options,'cursor':False,'keys':False,'clicks':False,'camera':False,'cuts':[[.8,1.1]]});studio_audio=inspect(studio)
    report=dict(native_separate_audio_tracks=original,plain_export=plain_audio,studio_export_with_cut=studio_audio,physical_microphone_used=False,mono_audio=mono)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if rec:rec.shutdown();rec.stopping=True;rec.close()
    for player in players:
        if player.poll() is None:player.terminate();player.wait(timeout=3)
    for module in modules:backend.run(['pactl','unload-module',module])
    for widget in app.topLevelWidgets():widget.close()
    if not loaded:subprocess.run(['hyprctl','plugin','unload',str((NATIVE/'clean-mirror.so').resolve())],capture_output=True,timeout=5)
