"""Versioned, validated clipboard representation of editable annotations."""
import base64
import json
import math
from PySide6.QtGui import QColor,QImage,QTransform

MIME='application/x-omnishot-annotations+json'
KINDS={'arrow','line','ellipse','rect','fill','pencil','text','counter','highlight','redact','blur','pixelate','spotlight','image'}
NUMBERS={'x','y','w','h','width','ax','ay','bx','by','font_size','strength','z','effect_seed'}
STRINGS={'color','text','font_family','style','text_style','counter_style','blur_mode','pixelate_mode'}
FLAGS={'bold','italic','underline','smooth','shadow'}


def number(value,limit=1_000_000):
    return type(value) in (int,float) and math.isfinite(value) and abs(value)<=limit


def decode(data):
    try:
        if len(data)>64_000_000:raise ValueError()
        document=json.loads(data)
        if not isinstance(document,dict) or document.get('version')!=1:raise ValueError()
        objects=document.get('objects')
        if not isinstance(objects,list) or not 1<=len(objects)<=1000:raise ValueError()
        pixels=0
        for p in objects:
            if not isinstance(p,dict) or not isinstance(p.get('kind'),str) or p['kind'] not in KINDS:raise ValueError()
            if set(p)-NUMBERS-STRINGS-FLAGS-{'kind','points','transform','image'}:raise ValueError()
            for key,value in p.items():
                if key in NUMBERS and not number(value,2**64 if key=='effect_seed' else 1_000_000):raise ValueError()
                if key in STRINGS and (not isinstance(value,str) or len(value)>100_000):raise ValueError()
                if key in FLAGS and type(value) is not bool:raise ValueError()
            if not QColor(p.get('color','#ff5b61')).isValid():raise ValueError()
            if any(p.get(key,1)<0 for key in ('w','h','width')) or any(p.get(key,1)<=0 for key in ('font_size','strength')):raise ValueError()
            if p.get('w',100)*p.get('h',40)>120_000_000:raise ValueError()
            if p.get('font_size',28)>1000 or p.get('width',4)>1000:raise ValueError()
            if 'transform' in p:
                matrix=p['transform']
                if not isinstance(matrix,list) or len(matrix)!=6 or not all(number(v) for v in matrix) or not QTransform(*matrix).isInvertible():raise ValueError()
            if 'points' in p:
                points=p['points']
                if not isinstance(points,list) or len(points)>100_000 or any(not isinstance(point,list) or len(point)!=2 or not all(number(v) for v in point) for point in points):raise ValueError()
            if p['kind']=='image':
                if not isinstance(p.get('image'),str):raise ValueError()
                image=QImage.fromData(base64.b64decode(p['image'],validate=True));pixels+=image.width()*image.height()
                if image.isNull() or pixels>120_000_000:raise ValueError()
        return objects
    except (ValueError,TypeError,OverflowError,RecursionError) as exc:
        raise ValueError('Could not paste editable annotations: invalid clipboard data') from exc


def encode(objects):
    data=json.dumps({'version':1,'objects':objects},allow_nan=False,separators=(',',':')).encode()
    decode(data)
    return data


def publish(data,png,store):
    """The native owner retains both representations independently of the GUI."""
    import tempfile
    from pathlib import Path
    from . import backend
    with tempfile.TemporaryDirectory(prefix='.annotation-copy-',dir=store.root) as directory:
        directory=Path(directory);image=directory/'image.png';objects=directory/'annotations.json'
        image.write_bytes(png);objects.write_bytes(data)
        backend.run([Path(__file__).resolve().parent.parent/'native/clipboard-helper','annotations',image,objects],timeout=10)
