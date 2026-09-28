"""Choose between hardware and software decoding for Qt video previews."""
import os
from pathlib import Path

VARIABLE='QT_FFMPEG_DECODING_HW_DEVICE_TYPES'
# A value set before OmniShot started (for example while debugging) stays
# authoritative; only the value this module writes follows the setting.
EXPLICIT=os.environ.get(VARIABLE)


def hardware_decoding_supported():
    # Qt copies decoded surfaces into QImage for our annotation compositor.
    # iHD can crash in vaSyncSurface during rapid seeks, so Intel always
    # decodes in software.
    for device in Path('/sys/class/drm').glob('renderD*/device/vendor'):
        try:vendor=device.read_text().strip()
        except OSError:continue
        if vendor=='0x8086':return False
    return True


def configure_preview_decoder(settings):
    # Off by default: hardware decoders such as Apple AVD need large contiguous
    # buffers, and under memory pressure those allocations fail repeatedly.
    # Encoding runs in separate capture/export processes and ignores this.
    # Qt reads the variable when its media backend starts, so a change applies
    # after OmniShot restarts.
    if EXPLICIT is not None:return
    if settings.get('hardware_video_decoding',False) and hardware_decoding_supported():os.environ.pop(VARIABLE,None)
    else:os.environ[VARIABLE]=','
