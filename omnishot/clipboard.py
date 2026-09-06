"""Read local clipboard images and media files without blocking the GUI."""
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit,unquote
from PySide6.QtGui import QImage
from . import backend

MEDIA={'.png','.jpg','.jpeg','.webp','.heic','.heif','.omnishot','.omnishot-video','.mp4','.gif','.webm','.mov','.mkv'}
IMAGE_TYPES=('image/png','image/webp','image/jpeg','image/bmp','image/tiff')


@dataclass
class Content:
    image: QImage | None = None
    files: tuple[Path,...] = ()
    annotations: bytes | None = None
    images: tuple[QImage,...] = ()


def local_files(data):
    if len(data)>1024*1024:raise ValueError('The clipboard file list is too large')
    paths=[]
    for line in data.decode('utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or line in ('copy','cut'):continue
        url=urlsplit(line)
        if url.scheme!='file' or url.netloc not in ('','localhost') or url.query or url.fragment:raise ValueError('Copy a local image or video file to the clipboard')
        path=Path(unquote(url.path))
        if not path.is_absolute() or '\x00' in str(path):raise ValueError('Invalid clipboard file path')
        if path.suffix.lower() not in MEDIA:continue
        if not path.is_file():raise ValueError(f'The copied file is no longer available: {path.name}')
        if path not in paths:paths.append(path)
        if len(paths)>100:raise ValueError('Open at most 100 clipboard files at once')
    if not paths:raise ValueError('There is no supported image or video file on the clipboard')
    return tuple(paths)


def read_content(annotations=False):
    try:types=set(backend.run(['wl-paste','--list-types'],timeout=5).decode().splitlines())
    except RuntimeError as exc:raise ValueError('Copy an image or a local media file first') from exc
    if annotations and 'application/x-omnishot-annotations+json' in types:
        return Content(annotations=backend.run(['wl-paste','--type','application/x-omnishot-annotations+json','--no-newline'],timeout=10))
    for mime in ('text/uri-list','x-special/gnome-copied-files'):
        if mime in types:return Content(files=local_files(backend.run(['wl-paste','--type',mime,'--no-newline'],timeout=10)))
    for mime in IMAGE_TYPES:
        if mime in types:
            data=backend.run(['wl-paste','--type',mime,'--no-newline'],timeout=15)
            if len(data)>512_000_000:raise ValueError('The clipboard image is too large')
            image=QImage.fromData(data)
            if image.isNull() or image.width()*image.height()>120_000_000:raise ValueError('Could not open the clipboard image')
            return Content(image=image)
    raise ValueError('Copy an image or a local media file first')


def read_for_paste():
    content=read_content(annotations=True)
    if content.files:
        from .images import load_image
        if any(path.suffix.lower() in {'.mp4','.mov','.mkv','.webm','.omnishot-video','.omnishot'} for path in content.files):raise ValueError('Paste an image into Annotate. Use Open from clipboard for video files and projects.')
        images=tuple(load_image(path) for path in content.files)
        if any(image.isNull() for image in images) or sum(image.width()*image.height() for image in images)>120_000_000:raise ValueError('Could not paste clipboard images (limit: 120 megapixels)')
        content.images=images;content.files=()
    return content
