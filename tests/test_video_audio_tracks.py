import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import hashlib,json,time
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.recording import export_video,VideoEditor,recorder_command
from omnishot.studio import export_studio
from omnishot.video_audio_tracks import capture_audio_sources
from omnishot.video_project import write_project,read_project,validate_manifest
from test_video_audio import make_source,samples,tracks


def amplitude(data,hz):
    sample=data[4800:48000,0];t=np.arange(len(sample))/48000
    return abs(np.sum(sample*np.exp(-2j*np.pi*hz*t)))*2/len(sample)


@pytest.mark.parametrize('studio',[False,True])
def test_independent_mix_export(tmp_path,studio):
    app=QApplication.instance() or QApplication([])
    source=tmp_path/'source.mp4';make_source(source,2);digest=hashlib.sha256(source.read_bytes()).digest()
    opts=dict(start=0,end=1.8,speed=1,fps=15,width=160,format='MP4',padding=0,background='#202633',cursor=False,keys=False,clicks=False)
    def export(name,rows,**changes):
        path=tmp_path/(name+'.mp4');settings=dict(opts,audio_tracks=rows,**changes)
        if studio:export_studio(source,path,{},settings)
        else:export_video(source,path,settings)
        return path
    both=export('both',[dict(enabled=True,volume=100)]*2)
    mix=samples(both);assert len(tracks(both))==1
    edited=export('edited',[dict(enabled=True,volume=50),dict(enabled=True,volume=200)])
    quiet=samples(edited)
    ratios=[amplitude(quiet,hz)/amplitude(mix,hz) for hz in (440,1320)]
    assert .47<ratios[0]<.53 and 1.9<ratios[1]<2.1,ratios
    only=export('only',[dict(enabled=False),dict(enabled=True,volume=100)])
    isolated=samples(only);assert amplitude(isolated,440)<.0001 and amplitude(isolated,1320)>.08
    silent=export('silent',[dict(enabled=True)]*2,audio_muted=True);assert np.max(np.abs(samples(silent)))<1e-6
    none=export('none',[dict(enabled=False)]*2);assert tracks(none)==[]
    mono=export('mono',[dict(enabled=True)]*2,audio_mono=True);assert [t['channels'] for t in tracks(mono)]==[1]
    assert hashlib.sha256(source.read_bytes()).digest()==digest


def test_track_controls_and_project(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/'source.mp4';make_source(source)
    meta=dict(version=1,cursor=[],events=[],capture_options=dict(audio_sources=['system','microphone']))
    source.with_suffix('.studio.json').write_text(json.dumps(meta));store=backend.Store(tmp_path/'data');e=VideoEditor(source,store);e.player.pause()
    def wait(predicate):
        end=time.monotonic()+5
        while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.01)
        assert predicate()
    wait(lambda:len(e.audio_tracks_controls.rows)==2)
    assert e.audio_mix.isChecked()
    system,mic=e.audio_tracks_controls.rows
    assert system[1].text()=='System audio' and mic[1].text()=='Microphone'
    system[2].setValue(48);mic[1].setChecked(False);mic[3].setValue(172)
    options=e.edit_options();assert options['audio_tracks']==[dict(enabled=True,volume=48),dict(enabled=False,volume=172)]
    project=tmp_path/'mix.omnishot-video';write_project(project,source,meta,options);e.close()
    e=VideoEditor(project,store);e.player.pause();wait(lambda:len(e.audio_tracks_controls.rows)==2)
    assert e.edit_options()==options and read_project(project,store)[2]==options
    e.format.setCurrentText('GIF');assert not e.audio_tracks_controls.isEnabled()
    e.format.setCurrentText('MP4');assert e.audio_tracks_controls.isEnabled()
    e.close();assert e.audio_preview.mix.closed and e.audio_preview.mix.process is None
    app.processEvents()


def test_studio_retains_sources_and_rejects_invalid_edits(tmp_path):
    opts=dict(studio=True,separate_audio=False,system=True,mic=True,fps=30,size='Native',quality='high',cursor=True)
    assert capture_audio_sources(opts)==['system','microphone']
    cmd=recorder_command(tmp_path/'out.mp4',(0,0,640,360),opts);assert cmd.count('-a')==2
    opts['studio']=False;assert capture_audio_sources(opts)==['mixed']
    assert recorder_command(tmp_path/'out.mp4',(0,0,640,360),opts).count('-a')==1
    for invalid in ('x',[dict(volume=float('nan'))],[dict(volume=201)],[dict(enabled='false')],[dict(volume=True)]):
        with pytest.raises(ValueError):validate_manifest(dict(format='omnishot-video',version=1,source='source.mp4',options=dict(audio_tracks=invalid)))


@pytest.mark.parametrize('studio',[False,True])
def test_mix_preserves_late_audio_and_short_track_duration(tmp_path,studio):
    app=QApplication.instance() or QApplication([]);source=tmp_path/'offset.mp4'
    backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=160x120:rate=15:duration=2.4',
        '-itsoffset','0.6','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=0.7',
        '-map','0:v','-map','1:a','-c:v','libx264','-c:a','aac',source])
    opts=dict(start=.2,end=2.2,speed=1,fps=15,width=160,format='MP4',padding=0,background='#202633',cursor=False,audio_tracks=[dict(enabled=True,volume=100)])
    destination=tmp_path/'offset-edit.mp4'
    if studio:export_studio(source,destination,{},opts)
    else:export_video(source,destination,opts)
    data=samples(destination)
    assert np.max(np.abs(data[:12000]))<.001
    assert np.sqrt(np.mean(data[24000:36000]**2))>.03
    duration=float(json.loads(backend.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',destination]))['format']['duration'])
    assert 1.9<duration<2.1,duration
