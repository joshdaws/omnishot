"""Bounded native regressions for Python/Qt audio-renderer lock inversion."""
import os,subprocess,sys,textwrap,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from omnishot.media_player import MediaPlayer,set_audio_track
from omnishot.recording import VideoEditor
from omnishot.backend import Store
from test_video_audio import make_source


def test_renderer_disconnect_and_playback_transitions_release_interpreter(tmp_path):
    source=tmp_path/'source.mp4';make_source(source,3)
    # Bound the child process so a binding regression cannot hang the test runner.
    # Python disconnectNotify is invoked by the native audio renderer while its
    # QObject connection mutex is held. It must be able to acquire the GIL while
    # the GUI thread reconnects/stops. This probe hung at stop() with the original
    # PySide player even after fixing only setActiveAudioTrack.
    script=textwrap.dedent('''
        import sys,time,threading
        from PySide6.QtCore import QThread,QUrl
        from PySide6.QtWidgets import QApplication
        from PySide6.QtMultimedia import QAudioOutput
        from omnishot.media_player import MediaPlayer
        class Output(QAudioOutput):
            calls=0
            def disconnectNotify(self,signal):
                if QThread.currentThread()!=self.thread():
                    self.calls+=1;time.sleep(.002)
                super().disconnectNotify(signal)
        app=QApplication([])
        for cycle in range(12):
            player=MediaPlayer();output=Output();output.setMuted(True)
            player.setAudioOutput(output);player.setSource(QUrl.fromLocalFile(sys.argv[1]));player.play()
            end=time.monotonic()+4
            while len(player.audioTracks())!=2 and time.monotonic()<end:app.processEvents();time.sleep(.005)
            assert len(player.audioTracks())==2
            for track in (1,0,1,0):
                player.pause();player.setActiveAudioTrack(track);assert player.activeAudioTrack()==track
                player.play();app.processEvents();time.sleep(.005)
            player.stop();player.setAudioOutput(None);player.setSource(QUrl());app.processEvents()
            assert output.calls>0
        print('12 playback lifecycles passed')
    ''')
    result=subprocess.run([sys.executable,'-c',script,str(source)],env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=25)
    assert result.returncode==0,result.stderr[-3000:]
    assert '12 playback lifecycles passed' in result.stdout


def test_mono_load_applies_latest_track_and_close_releases_sources(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/'source.mp4';make_source(source)
    e=VideoEditor(source,Store(tmp_path/'data'));e.audio_muted.setChecked(True);e.player.pause()
    def wait(predicate):
        deadline=time.monotonic()+5
        while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
        assert predicate()
    try:
        wait(lambda:len(e.player.audioTracks())==2);e.audio_mono.setChecked(True)
        e.audio_track.setCurrentIndex(1)
        wait(lambda:len(e.audio_preview.player.audioTracks())==2 and e.audio_preview.player.activeAudioTrack()==1)
        assert e.player.activeAudioTrack()==1
        e.audio_track.setCurrentIndex(0);assert e.player.activeAudioTrack()==0 and e.audio_preview.player.activeAudioTrack()==0
        assert not set_audio_track(e.player,3) and e.player.activeAudioTrack()==0
    finally:e.close()
    assert e.player.source().isEmpty() and e.audio_preview.player.source().isEmpty()


def test_unloaded_player_has_no_selectable_track():
    app=QApplication.instance() or QApplication([]);player=MediaPlayer()
    assert not set_audio_track(player,0) and not set_audio_track(player,-1)
    assert not set_audio_track(None,0)
