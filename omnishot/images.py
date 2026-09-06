"""Image codecs shared by capture previews, editing, and exports."""
import io
from pathlib import Path
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from PySide6.QtCore import QBuffer, QIODevice,Qt
from PySide6.QtGui import QImage,QImageReader,QColorSpace,QColor
from .storage import atomic_output

register_heif_opener(thumbnails=False)
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.heic *.heif *.bmp *.tif *.tiff)"


def validate_image(path):
    """Reject unreadable images before importing them into capture history."""
    try:
        with Image.open(path) as source:
            if source.width*source.height>120_000_000:
                raise ValueError("The image exceeds the 120 megapixel limit")
            source.load()
    except (OSError,ValueError,Image.DecompressionBombError) as exc:
        raise ValueError(f"Could not open image: {exc}") from exc


def image_color_space(image):
    space=image.colorSpace()
    return space if space.isValid() else QColorSpace(QColorSpace.NamedColorSpace.SRgb)


def convert_image(image,target=None):
    """Transform tagged pixels; assume sRGB only when no profile exists."""
    if image.isNull():return image
    target=target or QColorSpace(QColorSpace.NamedColorSpace.SRgb)
    source=QImage(image)
    if not source.colorSpace().isValid():source.setColorSpace(image_color_space(source))
    if source.colorSpace()==target:return source
    result=source.convertedToColorSpace(target,QImage.Format.Format_ARGB32_Premultiplied)
    if result.isNull():raise ValueError("Could not convert the image color profile")
    return result


def convert_color(color,target):
    source=QColorSpace(QColorSpace.NamedColorSpace.SRgb)
    return QColor(color) if target==source else source.transformationToColorSpace(target).map(QColor(color))


def load_image(path,thumbnail=None):
    reader=QImageReader(str(path));reader.setAutoTransform(True)
    if thumbnail and reader.size().isValid():reader.setScaledSize(reader.size().scaled(thumbnail,Qt.AspectRatioMode.KeepAspectRatio))
    image=reader.read()
    if not image.isNull():
        return image
    try:
        with Image.open(path) as source:
            profile=source.info.get("icc_profile")
            source = ImageOps.exif_transpose(source).convert("RGBA")
            if thumbnail:source.thumbnail((thumbnail.width(),thumbnail.height()),Image.Resampling.LANCZOS)
            data = source.tobytes()
            image=QImage(data, source.width, source.height, source.width * 4,
                         QImage.Format.Format_RGBA8888).copy()
            if profile:image.setColorSpace(QColorSpace.fromIccProfile(profile))
            return image
    except (OSError, ValueError):
        return QImage()


def save_image(image, path, quality=95,convert_srgb=False):
    """Export pixels; composite alpha onto white for formats without alpha."""
    if image.isNull():
        raise ValueError("Cannot save an empty image")
    if convert_srgb:image=convert_image(image)
    buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buf, "PNG"):
        raise OSError("Could not encode image")
    with Image.open(io.BytesIO(bytes(buf.data()))) as source,atomic_output(path) as temporary:
        suffix = Path(path).suffix.lower()
        profile={"icc_profile":source.info["icc_profile"]} if source.info.get("icc_profile") else {}
        if suffix in (".jpg", ".jpeg"):
            rgba = source.convert("RGBA")
            flattened = Image.new("RGB", source.size, "white")
            flattened.paste(rgba, mask=rgba.getchannel("A"))
            flattened.save(temporary, quality=quality, subsampling=0,**profile)
        elif suffix in (".heic", ".heif"):
            source.save(temporary, format="HEIF", quality=quality,**profile)
        elif suffix == ".webp":
            source.save(temporary, lossless=True,**profile)
        else:
            source.save(temporary,**profile)
