"""Persistent audio edits and a synchronized, local mono preview."""
from pathlib import Path
import tempfile
from .media_player import MediaPlayer,set_audio_track

from PySide6.QtCore import QObject, QProcess, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaMetaData


def audio_filters(options):
    """Use the same linear gain for playback and every exported audio stream."""
    volume=max(0.,min(1.,float(options.get("audio_volume",100))/100))
    if options.get("audio_muted"):volume=0.
    return [f"volume={volume:g}"] if volume!=1 else []


class AudioPreview(QObject):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;self.closed=False
        self.directory=None;self.process=None;self.ready=False;self.failed=False
        from .video_audio_mix import AudioMix
        self.mix=AudioMix(editor)
        self.player=MediaPlayer(self);self.output=QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        editor.player.tracksChanged.connect(self.tracks_changed)
        editor.player.positionChanged.connect(self.position_changed)
        editor.player.playbackStateChanged.connect(self.state_changed)
        editor.player.playbackRateChanged.connect(self.player.setPlaybackRate)
        editor.player.playbackRateChanged.connect(self.mix.changed)
        self.player.mediaStatusChanged.connect(self.loaded)
        self.player.errorOccurred.connect(self.preview_error)
        editor.audio_track.currentIndexChanged.connect(self.track_changed)
        self.tracks_changed();self.update()

    def tracks_changed(self):
        if self.closed:return
        e=self.editor;tracks=e.player.audioTracks();index=max(0,e.audio_track.currentIndex())
        e.audio_track.blockSignals(True);e.audio_track.clear()
        for i,track in enumerate(tracks):
            title=track.stringValue(QMediaMetaData.Key.Title)
            e.audio_track.addItem(title or f"Track {i+1}")
        e.audio_track.setCurrentIndex(min(index,len(tracks)-1));e.audio_track.blockSignals(False)
        e.audio_track.setVisible(len(tracks)>1);e.audio_track_label.setVisible(len(tracks)>1)
        e.audio_tracks_controls.set_tracks([t.stringValue(QMediaMetaData.Key.Title) for t in tracks])
        self.update()

    def track_changed(self,index):
        if self.closed or index<0:return
        set_audio_track(self.editor.player,index);set_audio_track(self.player,index)
        self.position_changed(self.editor.player.position(),force=True)

    def update(self):
        if self.closed:return
        e=self.editor;gif=e.format.currentText()=="GIF";available=bool(e.player.audioTracks())
        mix=e.audio_mix.isChecked()
        e.audio_tracks_controls.setVisible(mix);e.audio_tracks_controls.setEnabled(available and not gif)
        e.audio_track.setVisible(not mix and len(e.player.audioTracks())>1);e.audio_track_label.setVisible(not mix and len(e.player.audioTracks())>1)
        e.audio_mix.setEnabled(available and not gif)
        e.audio_mix.setVisible(not mix or not bool(e.metadata.get("capture_options",{}).get("audio_sources")))
        muted=e.audio_muted.isChecked() or gif
        mono=e.audio_mono.isChecked() and available and not gif and not mix
        if not mono:self.failed=False
        for widget in (e.audio_volume,e.audio_muted,e.audio_mono,e.audio_track,e.volume):widget.setEnabled(available and not gif)
        notice="GIFs have no audio. Your audio edits are retained for MP4." if gif else ("" if available else "This recording has no audio.")
        if mono and self.process:notice="Preparing mono preview…"
        if not self.failed:e.audio_notice.setText(notice)
        e.audio.setVolume(e.audio_volume.value()/100);self.output.setVolume(e.audio_volume.value()/100)
        e.audio.setMuted(muted or mono or mix);self.output.setMuted(muted or not mono)
        if mono and not self.ready and self.process is None and not self.failed:self.prepare()
        if mono and self.ready:
            if self.player.playbackState()!=e.player.playbackState():self.state_changed(e.player.playbackState())
        else:self.player.pause()
        self.mix.update()

    def prepare(self):
        e=self.editor
        if self.directory is None:self.directory=tempfile.TemporaryDirectory(prefix="omnishot-audio-")
        self.path=Path(self.directory.name)/"mono.m4a"
        self.process=QProcess(self);self.process.setProgram("ffmpeg")
        self.process.setArguments(["-hide_banner","-loglevel","error","-y","-i",str(e.source_path),"-map","0:a","-vn","-c:a","aac","-b:a","192k","-ac","1","-movflags","+faststart",str(self.path)])
        self.process.finished.connect(self.prepared);self.process.errorOccurred.connect(self.process_error)
        e.audio_notice.setText("Preparing mono preview…");self.process.start()

    def process_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:self.prepared(-1,QProcess.ExitStatus.CrashExit)

    def prepared(self,code,status):
        process=self.process
        if process is None:return
        self.process=None;message=bytes(process.readAllStandardError()).decode(errors="replace")[-500:];process.deleteLater()
        if self.closed:return
        if code or status!=QProcess.ExitStatus.NormalExit:
            self.failed=True;self.editor.audio_notice.setText("Could not prepare mono preview: "+(message or "FFmpeg could not start"));return
        self.ready=True;self.player.setSource(QUrl.fromLocalFile(str(self.path)))
        self.update()

    def loaded(self,status):
        if self.closed:return
        if status==QMediaPlayer.MediaStatus.LoadedMedia:
            set_audio_track(self.player,max(0,self.editor.audio_track.currentIndex()))
            self.state_changed(self.editor.player.playbackState())

    def preview_error(self,_,message):
        if not self.closed:self.editor.audio_notice.setText("Mono preview unavailable: "+message)

    def position_changed(self,position,force=False):
        self.mix.position_changed()
        if self.closed or not self.ready:return
        position=self.editor.player.position()
        # Source time is shared by both players, including trim/cut seeks. Correct
        # occasional clock drift without repeatedly flushing the audio decoder.
        if force or abs(self.player.position()-position)>150:self.player.setPosition(position)

    def state_changed(self,state):
        self.mix.update()
        if self.closed or not self.ready:return
        e=self.editor
        if e.audio_mix.isChecked() or not e.audio_mono.isChecked() or e.format.currentText()=="GIF":self.player.pause();return
        self.position_changed(e.player.position(),force=True);self.player.setPlaybackRate(e.player.playbackRate())
        if state==QMediaPlayer.PlaybackState.PlayingState:self.player.play()
        else:self.player.pause()

    def close(self):
        self.closed=True;self.mix.close();self.player.stop();self.player.setSource(QUrl())
        if self.process:
            self.process.kill();self.process.waitForFinished(1000)
            if self.process:self.process.deleteLater();self.process=None
        if self.directory:self.directory.cleanup();self.directory=None
