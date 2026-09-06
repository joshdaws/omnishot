"""Qt playback transitions that release the Python interpreter lock on Linux.

PySide 6.11.2's direct track setter (and QObject.setProperty) hold the GIL.
Qt retires audio renderers in a worker; their QObject destruction can call the
Python QAudioOutput wrapper's disconnectNotify while holding a QObject lock.
Creating/reconnecting a renderer on the main thread needs that same lock.
Playback state/output changes can also recreate renderers. CDLL calls release
the GIL while calling these public Qt methods on their original GUI thread.
"""
import ctypes
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import QLibraryInfo,QThread,QObject
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from shiboken6 import getCppPointer,isValid


@lru_cache(maxsize=None)
def _method(name,signature):
    # Load this PySide installation's Qt, never a different system Qt.
    library=ctypes.CDLL(str(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.LibrariesPath))/'libQt6Multimedia.so.6'))
    function=library[f'_ZN12QMediaPlayer{len(name)}{name}E{signature}']
    argument={'v':(), 'i':(ctypes.c_int,), 'P12QAudioOutput':(ctypes.c_void_p,), 'P7QObject':(ctypes.c_void_p,)}[signature]
    function.argtypes=(ctypes.c_void_p,*argument);function.restype=None
    return function


def _call(player,name,signature='v',*arguments):
    if not isinstance(player,QMediaPlayer) or not isValid(player):raise RuntimeError('Media player is closed')
    if QThread.currentThread()!=player.thread():raise RuntimeError('Change playback on the media player thread')
    _method(name,signature)(getCppPointer(player)[0],*arguments)


def set_audio_track(player,index):
    if not isinstance(player,QMediaPlayer) or not isValid(player):return False
    if QThread.currentThread()!=player.thread():raise RuntimeError('Change audio tracks on the media player thread')
    # The mono source is asynchronous: loaded() applies the latest selection.
    if index<0 or index>=len(player.audioTracks()):return False
    if player.activeAudioTrack()!=index:_call(player,'setActiveAudioTrack','i',index)
    return player.activeAudioTrack()==index


class MediaPlayer(QMediaPlayer):
    def play(self):_call(self,'play')
    def pause(self):_call(self,'pause')
    def stop(self):_call(self,'stop')
    def setActiveAudioTrack(self,index):set_audio_track(self,index)
    def setAudioOutput(self,output):
        if output is not None and (not isinstance(output,QAudioOutput) or not isValid(output)):raise TypeError('Expected a live audio output')
        _call(self,'setAudioOutput','P12QAudioOutput',getCppPointer(output)[0] if output is not None else None)
        self._audio_output=output
    def setVideoOutput(self,output):
        if output is not None and (not isinstance(output,QObject) or not isValid(output)):raise TypeError('Expected a live video output')
        _call(self,'setVideoOutput','P7QObject',getCppPointer(output)[0] if output is not None else None)
        self._video_output=output
