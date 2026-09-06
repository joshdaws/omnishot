"""Capture wallpaper preferences, independent of the actual desktop theme."""
import base64,io
from pathlib import Path
from PIL import Image,ImageOps
from .storage import atomic_output


def image_data(path):
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB');buffer=io.BytesIO();image.save(buffer,format='PNG',**({'icc_profile':source.info['icc_profile']} if source.info.get('icc_profile') else {}))
        return base64.b64encode(buffer.getvalue()).decode()


def desktop_path():
    for path in (Path.home()/'.local/state/omarchy/current/background',Path.home()/'.config/omarchy/current/background'):
        if path.is_file():return path.resolve()
    return None


def capture_wallpaper(store):
    if store.settings['wallpaper_source']=='custom':return store.settings.get('wallpaper_data')
    cached=store.root/'wallpaper-desktop.png'
    if not store.settings['wallpaper_follow_changes'] and cached.is_file():return base64.b64encode(cached.read_bytes()).decode()
    path=desktop_path()
    if path is None:return None
    data=image_data(path)
    try:
        with atomic_output(cached) as temp:temp.write_bytes(base64.b64decode(data))
    except OSError:pass
    return data
