"""Shared recording dimensions and output limits, in compositor logical pixels."""
from .clean_capture import capture_target,monitor_bounds

RESOLUTIONS = ['Native', '3840x2160', '2560x1440', '1920x1080', '1280x720', '960x540']


def recording_output(monitors,cursor):
    """Choose the screen under the Record pointer, independent of restored focus."""
    for monitor in monitors:
        x,y,w,h=monitor_bounds(monitor)
        if x<=cursor['x']<x+w and y<=cursor['y']<y+h:return monitor['name']
    return capture_target(monitors)[0]


def recording_monitors(monitors,output=None):
    if output is None:return monitors
    for monitor in monitors:
        if monitor['name']==output:return [dict(monitor,focused=True)]
    raise RuntimeError('The display selected for recording is no longer connected.')


def resolution_limit(size, scale_video, monitors, rect=None):
    limit = tuple(map(int, size.split('x'))) if size != 'Native' else None
    if scale_video:
        logical = tuple(rect[2:]) if rect else capture_target(monitors)[2][2:]
        limit = tuple(min(a, b) for a, b in zip(limit, logical)) if limit else logical
    return f'{limit[0]}x{limit[1]}' if limit else None
