"""Avoid Intel VAAPI surface-transfer crashes in the CPU-composed preview."""
import os
from pathlib import Path


def configure_preview_decoder():
    # Qt copies decoded surfaces into QImage for our annotation compositor.
    # iHD can crash in vaSyncSurface during rapid seeks. Encoding is performed
    # by separate capture/export processes and does not use this Qt setting.
    # Keep an explicitly configured backend choice authoritative.
    if 'QT_FFMPEG_DECODING_HW_DEVICE_TYPES' in os.environ:return
    for device in Path('/sys/class/drm').glob('renderD*/device/vendor'):
        try:vendor=device.read_text().strip()
        except OSError:continue
        if vendor=='0x8086':
            os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES']=','
            return
