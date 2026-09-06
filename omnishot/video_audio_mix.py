"""Bounded streaming audio preview, synchronized to the editor's source clock."""
import os,subprocess,tempfile,time
from PySide6.QtCore import QObject,QTimer
from PySide6.QtMultimedia import QAudioFormat,QAudioSink,QMediaPlayer
from .video_audio_tracks import mix_graph


class AudioMix(QObject):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;self.process=None;self.sink=None;self.io=None;self.log=None
        self.closed=False;self.signature=None;self.pending=b'';self.origin=0;self.rate=1;self.started=0;self.ready=False;self.eof=False
        self.timer=QTimer(self);self.timer.setInterval(10);self.timer.timeout.connect(self.pump)
        self.restart_timer=QTimer(self);self.restart_timer.setSingleShot(True);self.restart_timer.setInterval(45);self.restart_timer.timeout.connect(self.start)
        editor.audio.deviceChanged.connect(self.changed)

    def options(self):
        e=self.editor
        return dict(audio_tracks=e.audio_tracks_controls.values(),audio_mono=e.audio_mono.isChecked(),audio_volume=100)

    def active(self):
        e=self.editor
        return not self.closed and e.audio_mix.isChecked() and e.format.currentText()!='GIF' and e.player.isPlaying() and not e.audio_muted.isChecked() and any(row['enabled'] and row['volume'] for row in e.audio_tracks_controls.values())

    def update(self):
        if not self.active():self.stop();return
        e=self.editor;signature=(repr(self.options()),e.player.playbackRate(),bytes(e.audio.device().id()))
        if signature!=self.signature:self.signature=signature;self.changed()
        elif not self.process and not self.eof and not self.restart_timer.isActive():self.restart_timer.start()
        if self.sink:self.sink.setVolume(e.audio_volume.value()/100)

    def changed(self,*_):
        self.stop()
        if self.active():self.restart_timer.start()

    def position(self):
        if not self.sink:return self.origin
        return self.origin+self.sink.processedUSecs()/1000*self.rate

    def position_changed(self,*_):
        if self.closed:return
        # Decoder startup is handled before the first write; subsequent source
        # jumps (including excluded clips) flush queued samples immediately.
        if self.ready:
            drift=self.editor.player.position()-self.position()
            if drift < -180 or (not self.eof and drift>180):self.changed()

    def start(self):
        if not self.active():return
        self.stop();e=self.editor;self.origin=e.player.position();self.rate=e.player.playbackRate();self.started=time.monotonic();self.eof=False
        opts=self.options();after=[f'atempo={self.rate:g}'] if self.rate!=1 else []
        graph=mix_graph(opts,0,after)
        if not graph:return
        fmt=QAudioFormat();fmt.setSampleRate(48000);fmt.setChannelCount(2);fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        self.sink=QAudioSink(e.audio.device(),fmt,self);self.sink.setBufferSize(48000*8//10);self.sink.setVolume(e.audio_volume.value()/100)
        self.io=self.sink.start()
        if self.io is None:e.audio_notice.setText('Audio output is unavailable.');self.stop();return
        # The pipe and 100 ms sink buffer bound memory for recordings of any
        # duration. We only read when the sink has room, so FFmpeg backpressures.
        if opts['audio_mono']:graph=graph.replace('[os_audio]',',aformat=channel_layouts=mono,pan=stereo|c0=c0|c1=c0[os_audio]')
        self.log=tempfile.TemporaryFile()
        try:
            self.process=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-ss',str(self.origin/1000),'-i',str(e.source_path),'-filter_complex',graph,'-map','[os_audio]','-vn','-ar','48000','-ac','2','-f','f32le','pipe:1'],stdout=subprocess.PIPE,stderr=self.log,bufsize=0)
            os.set_blocking(self.process.stdout.fileno(),False);self.timer.start()
        except OSError as exc:e.audio_notice.setText('Audio preview unavailable: '+str(exc));self.stop()

    def pump(self):
        if not self.process or not self.io:return
        try:
            free=max(0,min(38400,self.sink.bytesFree()))//8*8
            if free and not self.pending:
                try:data=os.read(self.process.stdout.fileno(),free)
                except BlockingIOError:return
                if not data:
                    if self.process.poll() is not None:
                        code=self.process.returncode
                        if code:
                            self.log.seek(0);self.editor.audio_notice.setText('Audio preview unavailable: '+self.log.read(500).decode(errors='replace'))
                        self.eof=True;self.timer.stop()
                    return
                self.pending=data
            if not self.ready and self.pending:
                # Skip samples decoded while the video clock continued during
                # startup. Never drag the video back to wait for an audio decode.
                lag=max(0,self.editor.player.position()-self.origin)
                drop=min(len(self.pending),int(lag/self.rate*48)*8)
                self.pending=self.pending[drop:];self.origin+=drop/384*self.rate
                if not self.pending:return
                self.ready=True
            if self.pending and free:
                written=self.io.write(self.pending[:free])
                if written>0:self.pending=self.pending[written:]
        except (OSError,RuntimeError) as exc:
            self.editor.audio_notice.setText('Audio preview unavailable: '+str(exc));self.stop()

    def stop(self):
        self.timer.stop();self.restart_timer.stop();self.ready=False;self.pending=b'';self.eof=False
        if self.sink:self.sink.reset();self.sink.deleteLater();self.sink=None;self.io=None
        if self.process:
            process=self.process;self.process=None
            if process.poll() is None:process.kill()
            process.wait(timeout=2);process.stdout.close()
        if self.log:self.log.close();self.log=None

    def close(self):
        self.closed=True;self.stop()
