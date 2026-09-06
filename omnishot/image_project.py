"""Read editable images before importing or changing an open editor."""
import json
import zipfile
from PySide6.QtGui import QImage,QTransform
from .image_original import parse_transform


def read_project(path):
    try:
        with zipfile.ZipFile(path) as archive:
            entries=archive.infolist();names=[entry.filename for entry in entries]
            if len(names)!=len(set(names)):raise ValueError('Duplicate project entries')
            if sum(entry.file_size for entry in entries)>512_000_000:raise ValueError('Project is too large')
            image=QImage.fromData(archive.read('image.png'));data=json.loads(archive.read('project.json'))
            if (image.isNull() or image.width()*image.height()>120_000_000 or not isinstance(data,dict)
                    or data.get('version') not in (1,2) or not isinstance(data.get('objects'),list)
                    or not all(isinstance(obj,dict) and isinstance(obj.get('kind'),str) for obj in data['objects'])
                    or data.get('background') is not None and not isinstance(data['background'],dict)):
                raise ValueError('Unsupported project')
            original=None;transform=QTransform()
            if 'original_image' in data or 'source_transform' in data:
                if data.get('original_image')!='original.png':raise ValueError('Invalid original image')
                original=QImage.fromData(archive.read('original.png'));transform=parse_transform(data.get('source_transform'))
                if original.isNull() or original.width()*original.height()>120_000_000:raise ValueError('Invalid original image')
        return image,data,original,transform
    except (zipfile.BadZipFile,KeyError,OSError,ValueError) as exc:
        raise ValueError(f'Could not open image project: {exc}') from exc
