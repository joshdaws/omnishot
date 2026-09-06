"""Apply recording audio preferences without recompressing the video stream."""
import json
from . import backend
from .storage import atomic_output


def make_mono(path):
    streams=json.loads(backend.run(['ffprobe','-v','error','-select_streams','a','-show_entries','stream=channels','-of','json',path],timeout=15)).get('streams',[])
    if not any(stream.get('channels',0)>1 for stream in streams):return
    with atomic_output(path) as output:
        backend.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',path,'-map','0:v:0','-map','0:a?','-c:v','copy','-c:a','aac','-ac','1','-movflags','+faststart',output],timeout=86400)
