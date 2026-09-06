"""Verify GIF frame rate, maximum width, palette quality and optimization."""
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageSequence
from omnishot import backend
from omnishot.recording import export_video

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
y,x=np.mgrid[:180,:320];base=np.stack((x*255//319,y*255//179,(x+y)*255//498),axis=2).astype(np.uint8);frames=[]
for index in range(30):
    frame=base.copy();left=20+index*6;frame[65:100,left:left+35]=[230,30,50];frames.append(frame)
source=out/'source.mp4';backend.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size','320x180','-framerate','15','-i','pipe:0','-c:v','libx264','-crf','0','-pix_fmt','yuv444p',source],data=np.stack(frames).tobytes())
reports={}
for name,options in [('optimized',dict(gif_quality=100,gif_optimize=True,fps=10,width=800)),('full',dict(gif_quality=100,gif_optimize=False,fps=10,width=800)),('low-palette',dict(gif_quality=10,gif_optimize=True,fps=10,width=800)),('small',dict(gif_quality=10,gif_optimize=True,fps=5,width=160))]:
    target=out/(name+'.gif');export_video(source,target,dict(start=0,end=0,speed=1,format='GIF',padding=0,background='#202633',blur=False,**options))
    with Image.open(target) as image:
        duration=sum(frame.info.get('duration',0) for frame in ImageSequence.Iterator(image))/1000
        image.seek(0);colors=len(image.convert('RGB').getcolors(image.width*image.height))
        report=dict(size=list(image.size),frames=image.n_frames,seconds=duration,colors=colors,bytes=target.stat().st_size)
        assert abs(image.n_frames/duration-options['fps'])<.2,report
        assert image.width==min(320,options['width'])
        reports[name]=report
assert reports['optimized']['bytes']<reports['full']['bytes'],reports
assert reports['small']['colors']<reports['optimized']['colors'] and reports['small']['bytes']<reports['optimized']['bytes'],reports
(out/'report.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports))
