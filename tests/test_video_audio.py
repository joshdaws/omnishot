import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import hashlib
import json
import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.recording import VideoEditor, export_video
from omnishot.studio import export_studio
from omnishot.video_project import write_project, read_project


def make_source(path,duration=1.6):
    backend.run(["ffmpeg","-v","error","-y","-f","lavfi","-i",f"testsrc2=size=160x120:rate=15:duration={duration}",
        "-f","lavfi","-i",f"aevalsrc=0.12*sin(440*2*PI*t)|0.06*sin(880*2*PI*t):s=48000:d={duration}",
        "-f","lavfi","-i",f"aevalsrc=0.1*sin(1320*2*PI*t)|0.08*sin(1760*2*PI*t):s=48000:d={duration}",
        "-map","0:v","-map","1:a","-map","2:a","-c:v","libx264","-threads","1","-c:a","aac","-pix_fmt","yuv420p",path])


def samples(path,index=0,channels=2):
    raw=backend.run(["ffmpeg","-v","error","-i",path,"-map",f"0:a:{index}","-f","f32le","-ac",str(channels),"-ar","48000","-"])
    return np.frombuffer(raw,dtype="<f4").reshape(-1,channels)


def tracks(path):
    return json.loads(backend.run(["ffprobe","-v","error","-select_streams","a","-show_entries","stream=channels","-of","json",path]))["streams"]


@pytest.mark.parametrize("studio",[False,True])
def test_audio_edits_reach_every_exported_track(tmp_path,studio):
    app=QApplication.instance() or QApplication([])
    source=tmp_path/"source.mp4";make_source(source);original=hashlib.sha256(source.read_bytes()).digest()
    opts=dict(start=.1,end=1.4,speed=1.5,fps=15,width=160,format="MP4",padding=0,background="#202633",cursor=False,keys=False,clicks=False,cuts=[[.5,.7]])
    def export(path,changes):
        if studio:export_studio(source,path,{},dict(opts,**changes))
        else:export_video(source,path,dict(opts,**changes))
    reference=tmp_path/"reference.mp4";export(reference,{})
    half=tmp_path/"half.mp4";export(half,{"audio_volume":50})
    mono=tmp_path/"mono.mp4";export(mono,{"audio_mono":True,"audio_volume":50})
    silent=tmp_path/"silent.mp4";export(silent,{"audio_muted":True,"audio_volume":70})
    assert [t["channels"] for t in tracks(half)]==[2,2]
    assert [t["channels"] for t in tracks(mono)]==[1,1]
    for i in range(2):
        ref=samples(reference,i);quiet=samples(half,i)
        ratio=np.sqrt(np.mean(quiet**2)/np.mean(ref**2));assert .47<ratio<.53,ratio
        mono_ref=samples(reference,i,1);mono_quiet=samples(mono,i,1)
        ratio=np.sqrt(np.mean(mono_quiet**2)/np.mean(mono_ref**2));assert .46<ratio<.54,ratio
        assert np.max(np.abs(samples(silent,i)))<1e-6
    assert hashlib.sha256(source.read_bytes()).digest()==original


def test_audio_settings_project_preview_and_cleanup(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/"source.mp4";make_source(source)
    store=backend.Store(tmp_path/"data");e=VideoEditor(source,store);e.player.pause()
    def wait(predicate):
        deadline=time.monotonic()+6
        while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert predicate()
    wait(lambda:len(e.player.audioTracks())==2)
    e.audio_volume.setValue(43);e.audio_muted.setChecked(True);e.audio_mono.setChecked(True)
    wait(lambda:e.audio_preview.ready)
    assert e.volume.value()==43 and e.audio.isMuted() and e.audio_preview.output.isMuted()
    assert abs(e.audio_preview.output.volume()-.43)<.001
    e.format.setCurrentText("GIF");assert not e.audio_volume.isEnabled() and e.audio_muted.isChecked()
    e.format.setCurrentText("MP4");assert e.audio_volume.isEnabled() and e.audio.isMuted()
    e.audio_muted.setChecked(False);assert not e.audio_preview.output.isMuted() and e.audio.isMuted()
    assert [t["channels"] for t in tracks(e.audio_preview.path)]==[1,1]
    e.audio_track.setCurrentIndex(1);assert e.player.activeAudioTrack()==1
    project=tmp_path/"audio.omnishot-video";options=e.edit_options();write_project(project,source,{},options)
    directory=e.audio_preview.directory.name;e.close();assert not os.path.exists(directory)
    reopened=VideoEditor(project,store);reopened.player.pause()
    assert reopened.audio_volume.value()==43 and reopened.audio_mono.isChecked() and not reopened.audio_muted.isChecked()
    assert read_project(project,store)[2]==options
    wait(lambda:len(reopened.audio_tracks_controls.rows)==2)
    reopened.audio_mix.setChecked(True)
    assert reopened.audio_tracks_controls.values()==[dict(enabled=True,volume=100)]*2
    reopened.close();app.processEvents()
