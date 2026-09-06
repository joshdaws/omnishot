"""Validate local recording imports before adding them to History."""
import json
from . import backend


def validate_video(path):
    try:
        data=json.loads(backend.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,codec_type','-of','json',path],timeout=30))
        streams=data.get('streams',[])
        if not streams or streams[0].get('codec_type')!='video':raise ValueError('There is no video track')
        width,height=streams[0].get('width',0),streams[0].get('height',0)
        if not 0<width*height<=120_000_000:raise ValueError('Unsupported video dimensions')
        # Header-only probing accepts truncated tracks. Decode the first frame,
        # without scanning an entire long recording before opening its editor.
        frames=backend.run(['ffmpeg','-v','error','-xerror','-i',path,'-map','0:v:0','-frames:v','1','-an','-f','framehash','-'],timeout=30)
        if not any(line.strip() and not line.startswith(b'#') for line in frames.splitlines()):raise ValueError('There are no decodable video frames')
    except Exception as exc:
        raise ValueError(f'Could not open recording {path.name}: {exc}') from exc
