"""Exercise Studio exports using generated media; never opens a mic or camera."""
import argparse
import json
import threading
import time
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.studio import export_studio

parser=argparse.ArgumentParser();parser.add_argument("output",type=Path);args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot")
source=out/"source.mp4";camera=out/"camera.mp4"
backend.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=size=640x360:rate=30","-f","lavfi","-i","aevalsrc=0.3*sin(2*PI*if(lt(t\\,1)\\,440\\,if(lt(t\\,2)\\,880\\,1320))*t):s=48000","-t","3","-c:v","libx264","-c:a","aac",source])
backend.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc=size=320x240:rate=30","-t","3","-c:v","libx264","-pix_fmt","yuv420p",camera])
metadata={"source_path":str(source),"camera_path":str(camera),"camera_offset":0,"cursor":[{"t":0,"x":.2,"y":.3},{"t":3,"x":.8,"y":.6}],"events":[{"kind":"click","t":.5,"x":.4,"y":.5},{"kind":"key","t":2.4,"state":1,"label":"Ctrl+C"}]}
source.with_suffix(".studio.json").write_text(json.dumps(metadata))
opts={"start":.2,"end":2.8,"speed":1.5,"fps":30,"width":640,"padding":24,"background":"#25304f","background2":"#624583","cuts":[[1,2]],"cursor":True,"clicks":True,"keys":True,"camera":True,"camera_shape":"Circle","smoothing":.75,"zooms":[{"start":.2,"end":.9,"scale":1.8,"x":.4,"y":.5}]}
report={}
for hardware in (False,True):
    dest=out/("hardware.mp4" if hardware else "software.mp4");progress=[]
    export_studio(source,dest,metadata,{**opts,"hardware":hardware},progress.append)
    probe=json.loads(backend.run(["ffprobe","-v","error","-show_entries","stream=codec_name,width,height:format=duration","-of","json",dest]))
    assert abs(float(probe["format"]["duration"])-1.0667)<.11,probe
    assert any(s["codec_name"]=="aac" for s in probe["streams"]),probe
    assert progress[-1]==100
    raw=backend.run(["ffmpeg","-v","error","-i",dest,"-vn","-f","f32le","-ar","8000","-ac","1","-"]);samples=np.frombuffer(raw,dtype="<f4")
    frequencies=[]
    for fraction in (.25,.75):
        center=int(len(samples)*fraction);chunk=samples[center-800:center+800]
        frequencies.append(round(np.argmax(abs(np.fft.rfft(chunk)))*8000/len(chunk)))
    assert abs(frequencies[0]-440)<10 and abs(frequencies[1]-1320)<10,frequencies
    report["hardware" if hardware else "software"]={"probe":probe,"audio_frequencies":frequencies}
cancel=threading.Event();cancel.set();preserved=out/"cancel.mp4";preserved.write_bytes(b"existing output")
try:export_studio(source,preserved,metadata,opts,cancel=cancel)
except InterruptedError:pass
else:raise AssertionError("Cancellation did not abort")
assert preserved.read_bytes()==b"existing output" and not preserved.with_name("cancel.partial.mp4").exists()
report["cancel_preserved_existing_file"]=True
editor=VideoEditor(source,backend.Store(out/"data"));editor.zooms=opts["zooms"];editor.cuts=opts["cuts"];editor.padding.setValue(24);editor.sync_timeline();editor.show()
end=time.monotonic()+1.5
while time.monotonic()<end:app.processEvents();time.sleep(.02)
editor.player.pause();editor.grab().save(str(out/"editor.png"));editor.close()
(out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
