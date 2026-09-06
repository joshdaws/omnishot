import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import json
from pathlib import Path
import threading
import time
import zipfile
import base64
import shutil
import pytest
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.video_project import write_project,read_project
from omnishot.recording import VideoEditor
from omnishot.studio import export_studio


def test_portable_video_project_reopens_and_exports_without_originals(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);source=tmp_path/"source.mp4";camera=tmp_path/"camera.mp4";project=tmp_path/"demo.omnishot-video"
    for path,pattern in [(source,"testsrc2=size=320x240:rate=15"),(camera,"color=c=blue:size=160x120:rate=15")]:
        backend.run(["ffmpeg","-v","error","-f","lavfi","-i",pattern,"-t","0.8","-c:v","libx264","-pix_fmt","yuv420p",path])
    metadata={"cursor":[{"t":0,"x":.2,"y":.3},{"t":.8,"x":.8,"y":.5}],"events":[{"kind":"key","state":1,"t":.2,"label":"Ctrl+C"}],"camera_path":str(camera)}
    opts={"start":.1,"end":.7,"speed":1,"fps":15,"width":0,"padding":8,"background":"#abcdef","camera":True,"camera_shape":"Rounded","zooms":[{"start":.1,"end":.6,"scale":1.4,"x":.4,"y":.5}],"cuts":[]}
    from omnishot.editor import png_bytes
    image=QImage(40,40,QImage.Format.Format_RGB32);image.fill(QColor("#aa77dd"))
    opts.update(background_image_data=base64.b64encode(png_bytes(image)).decode(),cursor_style="Dot",key_position="Top Left",camera_mirror=True,event_edits={"0":{"label":"Ctrl+V","t":.3}})
    write_project(project,source,metadata,opts);source.unlink();camera.unlink()
    store=backend.Store(tmp_path/"data");store.settings["output_dir"]=str(tmp_path/"exports");imported=store.import_file(project);raw,meta,options=read_project(imported,store)
    assert raw.is_file() and Path(meta["camera_path"]).is_file() and options==opts
    editor=VideoEditor(imported,store);editor.player.pause();assert editor.padding.value()==8 and editor.camera_shape.currentText()=="Rounded" and editor.zooms==opts["zooms"]
    second=tmp_path/"second.omnishot-video";monkeypatch.setattr("omnishot.recording.QFileDialog.getSaveFileName",lambda *args:(str(second),""));editor.zooms[0]["scale"]=1.7;editor.save_project()
    deadline=time.monotonic()+5
    while editor.export_cancel and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert editor.export_cancel is None and second.exists();editor.close();app.processEvents()
    raw2,meta2,opts2=read_project(second,store);assert opts2["zooms"][0]["scale"]==1.7 and opts2["background_image_data"]==opts["background_image_data"] and opts2["event_edits"]==opts["event_edits"]
    export_studio(raw2,tmp_path/"result.mp4",meta2,opts2);backend.run(["ffmpeg","-v","error","-i",tmp_path/"result.mp4","-f","null","-"])
    folder=raw.parent;recovered=tmp_path/"trash"
    def move(path):shutil.move(path,recovered);return str(recovered)
    monkeypatch.setattr('omnishot.backend.move_to_trash',move);store.trash(imported);assert not folder.exists() and project.exists()
    recovered_source,recovered_meta,recovered_opts=read_project(next(recovered.glob("*.omnishot-video")),store)
    assert recovered_source.exists() and Path(recovered_meta["camera_path"]).exists() and recovered_opts["zooms"][0]["scale"]==1.7 and recovered_opts["event_edits"]==opts["event_edits"]


def test_project_rejects_paths_and_cancellation_preserves_destination(tmp_path):
    source=tmp_path/"raw.mp4";source.write_bytes(b"media");dest=tmp_path/"keep.omnishot-video";dest.write_bytes(b"original")
    cancel=threading.Event();cancel.set()
    with pytest.raises(InterruptedError):write_project(dest,source,{"cursor":[],"events":[]},{},cancel=cancel)
    assert dest.read_bytes()==b"original" and not list(tmp_path.glob("*.partial"))
    malicious=tmp_path/"bad.omnishot-video"
    with zipfile.ZipFile(malicious,"w") as archive:
        archive.writestr("manifest.json",json.dumps({"format":"omnishot-video","version":1,"source":"../outside.mp4","metadata":{},"options":{}}));archive.writestr("../outside.mp4",b"data")
    with pytest.raises(ValueError):read_project(malicious,backend.Store(tmp_path/"data"))
    assert not (tmp_path/"outside.mp4").exists()


@pytest.mark.parametrize('extension',['mp4','gif','webm','mov','mkv'])
def test_trash_keeps_plain_video_edits_without_studio_metadata(tmp_path,monkeypatch,extension):
    source=tmp_path/f'Imported recording.{extension}';source.write_bytes(b'original media')
    store=backend.Store(tmp_path/'data');path=store.add(source=source,kind='video')
    options=dict(start=.2,end=2,speed=1.5,padding=16,cuts=[[.8,1.1]],splits=[.5],audio_tracks=[dict(enabled=True,volume=75)])
    store.video_edit_path(path).parent.mkdir(parents=True,exist_ok=True)
    store.atomic_json(store.video_edit_path(path),dict(options=options))
    restored=tmp_path/'restored'
    def move(bundle):shutil.move(bundle,restored);return str(restored)
    monkeypatch.setattr('omnishot.backend.move_to_trash',move)
    store.trash(path)
    assert not path.exists() and not store.video_edit_path(path).exists() and source.read_bytes()==b'original media'
    raw,metadata,edits=read_project(next(restored.glob('*.omnishot-video')),store)
    assert raw.read_bytes()==b'original media' and edits==options
    assert next(restored.glob('*.'+extension)).read_bytes()==b'original media'
