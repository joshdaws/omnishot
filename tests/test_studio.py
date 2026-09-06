import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import json
import numpy as np
from PySide6.QtWidgets import QApplication
from omnishot.studio import compose_frame,smooth_cursor,smart_zooms,zoom_at,kept_segments,export_studio
from omnishot import backend


def test_zoom_easing_and_cuts():
    zooms=smart_zooms([{"kind":"click","t":2,"x":.3,"y":.4}])
    assert zoom_at(zooms,0)[0]==1
    assert zoom_at(zooms,2.4)[0]>1.7
    assert zoom_at(zooms,9)[0]==1
    assert kept_segments(0,10,[(2,4),(3,5),(8,12)])==[(0,2),(5,8)]


def test_cursor_smoothing_and_composition():
    app=QApplication.instance() or QApplication([])
    samples=[{"t":0,"x":.2,"y":.2},{"t":.05,"x":.8,"y":.8}]
    smoothed=smooth_cursor(samples);assert .2<smoothed[-1]["x"]<.8
    frame=np.full((240,320,3),240,np.uint8)
    meta={"cursor":samples,"events":[{"kind":"click","t":.05,"x":.8,"y":.8},{"kind":"key","t":.05,"state":1,"label":"Ctrl+C"}]}
    result=compose_frame(frame,.1,meta,{"padding":24,"width":320,"aspect":"1:1","background":"#25304f","cursor":True})
    assert result.width()==result.height()==368
    assert result.pixelColor(5,5).name()=="#25304f"


def test_studio_export_real_media(tmp_path):
    app=QApplication.instance() or QApplication([])
    src=tmp_path/"raw.mp4";dst=tmp_path/"edited.mp4"
    backend.run(["ffmpeg","-loglevel","error","-f","lavfi","-i","testsrc2=size=320x240:rate=15","-t","1.2","-c:v","libx264","-pix_fmt","yuv420p",src])
    meta={"cursor":[{"t":0,"x":.2,"y":.3},{"t":1.2,"x":.8,"y":.6}],"events":[{"kind":"click","t":.4,"x":.5,"y":.5}]}
    export_studio(src,dst,meta,{"start":0,"end":1.1,"speed":1,"fps":15,"width":320,"padding":20,"background":"#25304f","zooms":smart_zooms(meta["events"]),"cursor":True,"cuts":[(.6,.8)],"smoothing":.8})
    probe=json.loads(backend.run(["ffprobe","-v","error","-show_entries","stream=codec_name,width,height:format=duration","-of","json",dst]))
    assert probe["streams"][0]["width"]==360 and probe["streams"][0]["height"]==280
    assert .6<float(probe["format"]["duration"])<1.1
    backend.run(["ffmpeg","-v","error","-i",dst,"-f","null","-"])
