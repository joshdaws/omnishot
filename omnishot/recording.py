from __future__ import annotations
from . import ui_scale as ui
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid
from PySide6.QtCore import Qt,QTimer,Signal,QUrl,QProcess
from PySide6.QtWidgets import (QWidget,QDialog,QFormLayout,QVBoxLayout,QHBoxLayout,
    QCheckBox,QSpinBox,QDoubleSpinBox,QLabel,QDialogButtonBox,QFileDialog,
    QSlider,QLineEdit,QProgressBar,QMessageBox)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QVideoSink
from PySide6.QtGui import QPixmap
import numpy as np
from PySide6.QtMultimediaWidgets import QVideoWidget
from .media_player import MediaPlayer
from .controls import Choice as QComboBox
from . import backend
from .clean_capture import CleanCapture,NATIVE
from .widgets import button,background,place_window,place_outside
from .editor import error


class AudioMeter(QProgressBar):
    def __init__(self,parent=None):
        super().__init__(parent);self.setRange(0,100);self.setTextVisible(False);ui.set(self,"setMaximumHeight",8)
        self.reader=QProcess(self);self.reader.readyReadStandardOutput.connect(self.level)
    def start(self,device):
        self.stop();args=["--raw","--format=float32le","--rate=8000","--channels=1","--latency-msec=80"]
        if device!="default_input":args.extend(["--device",device])
        self.reader.start("parec",args)
    def stop(self):
        if self.reader.state()!=QProcess.ProcessState.NotRunning:self.reader.kill();self.reader.waitForFinished(1000)
        self.setValue(0)
    def level(self):
        data=bytes(self.reader.readAllStandardOutput());data=data[:len(data)//4*4]
        if data:
            values=np.frombuffer(data,dtype="<f4");peak=float(np.max(np.abs(values)));self.setValue(min(100,round(peak**.5*100)))


class RecordSetup(QDialog):
    def __init__(self,store):
        super().__init__();self.store=store;self.setWindowTitle("OmniShot — Record Screen");form=QFormLayout(self);self.form=form
        self.mode=QComboBox();self.mode.addItems(["Area","Window","Fullscreen"]);form.addRow("Capture",self.mode)
        self.format=QComboBox();self.format.addItems(["MP4","GIF"]);form.addRow("Format",self.format)
        self.fps=QComboBox();self.fps.addItems(["5","10","15","24","30","60"]);self.fps.setCurrentText(str(store.settings["fps"]));form.addRow("Frames per second",self.fps)
        self.quality=QComboBox()
        for value,label in [("medium","Medium"),("high","High"),("very_high","Very high"),("ultra","Ultra")]:self.quality.addItem(label,value)
        self.quality.setCurrentIndex(max(0,self.quality.findData(store.settings["quality"])));form.addRow("Quality",self.quality)
        from .recording_options import RESOLUTIONS
        self.size=QComboBox()
        for size in RESOLUTIONS:self.size.addItem("Original" if size=="Native" else size,size)
        self.size.setCurrentIndex(max(0,self.size.findData(store.settings["record_max_resolution"])));form.addRow("Maximum resolution",self.size)
        self.scale_video=QCheckBox("Scale videos to 1×");self.scale_video.setChecked(store.settings["record_scale_video"]);form.addRow(self.scale_video)
        from .gif_options import WIDTHS
        self.gif_width=QComboBox()
        for width in WIDTHS:self.gif_width.addItem(f"{width} × auto" if width else "Original",width)
        self.gif_width.setCurrentIndex(max(0,self.gif_width.findData(store.settings["gif_width"])));form.addRow("GIF resolution",self.gif_width)
        self.gif_quality=QSlider(Qt.Orientation.Horizontal);self.gif_quality.setRange(1,100);self.gif_quality.setValue(store.settings["gif_quality"]);self.gif_quality.setAccessibleName("GIF quality");form.addRow("GIF quality",self.gif_quality)
        self.gif_optimize=QCheckBox("Optimize GIFs");self.gif_optimize.setChecked(store.settings["gif_optimize"]);form.addRow(self.gif_optimize)
        self.system=QCheckBox("Record computer audio");self.system.setChecked(store.settings["record_system_audio"]);form.addRow(self.system)
        self.mic=QCheckBox("Record microphone");self.mic.setChecked(store.settings["record_microphone"]);form.addRow(self.mic)
        self.mono=QCheckBox("Record audio in mono");self.mono.setChecked(store.settings.get("record_audio_mono",False));form.addRow(self.mono)
        self.audio_tracks=QComboBox();self.audio_tracks.addItem("Single track","single");self.audio_tracks.addItem("Separate tracks","separate");self.audio_tracks.setCurrentIndex(max(0,self.audio_tracks.findData(store.settings.get("record_audio_tracks","single"))));form.addRow("Saved audio tracks",self.audio_tracks)
        self.audio_tracks.setToolTip("Studio always keeps microphone and system sources separately for editing. Choose how audio is saved in the initial video.")
        self.system_device=QComboBox();self.mic_device=QComboBox()
        try:
            for line in backend.run(["gpu-screen-recorder","--list-audio-devices"]).decode().splitlines():
                device,_,label=line.partition("|")
                if device=="default_output" or device.endswith(".monitor"):self.system_device.addItem(label or device,device)
                else:self.mic_device.addItem(label or device,device)
        except Exception:
            self.system_device.addItem("Default output","default_output");self.mic_device.addItem("Default input","default_input")
        if not self.system_device.count():self.system_device.addItem("Default output","default_output")
        if not self.mic_device.count():self.mic_device.addItem("Default microphone","default_input")
        self.system_device.setCurrentIndex(max(0,self.system_device.findData(store.settings.get("record_system_device","default_output"))))
        self.mic_device.setCurrentIndex(max(0,self.mic_device.findData(store.settings.get("record_microphone_device","default_input"))))
        form.addRow("Computer audio source",self.system_device);form.addRow("Microphone source",self.mic_device)
        self.meter=AudioMeter(self);form.addRow("Microphone level",self.meter)
        def meter():
            audible=self.format.currentText()!="GIF"
            self.system_device.setEnabled(audible and self.system.isChecked());self.mic_device.setEnabled(audible and self.mic.isChecked())
            if audible and self.mic.isChecked():self.meter.start(self.mic_device.currentData() or "default_input")
            else:self.meter.stop()
        self.update_meter=meter
        self.mic.toggled.connect(meter);self.system.toggled.connect(meter);self.mic_device.currentIndexChanged.connect(meter);meter()
        self.cursor=QCheckBox("Show cursor");self.cursor.setChecked(store.settings["record_cursor"]);form.addRow(self.cursor)
        self.studio=QCheckBox("Studio recording — edit cursor, clicks and zooms afterwards");form.addRow(self.studio)
        self.clicks=QCheckBox("Capture mouse clicks");self.keys=QCheckBox("Capture keystrokes");self.clicks.setChecked(store.settings["record_clicks"]);self.keys.setChecked(store.settings["record_keys"]);form.addRow(self.clicks);form.addRow(self.keys)
        self.commands=QCheckBox("Show command shortcuts only");self.commands.setChecked(store.settings["record_commands_only"]);form.addRow(self.commands)
        def sync_studio():
            needed=self.clicks.isChecked() or self.keys.isChecked() or (hasattr(self,"camera") and self.camera.isChecked())
            if needed:self.studio.setChecked(True)
            self.studio.setEnabled(not needed)
        self.clicks.toggled.connect(sync_studio);self.keys.toggled.connect(sync_studio);sync_studio()
        self.dnd=QCheckBox("Do not disturb while recording");self.dnd.setChecked(store.settings["record_dnd"]);form.addRow(self.dnd)
        self.camera=QCheckBox("Record camera");form.addRow(self.camera)
        self.camera_device=QComboBox()
        try:
            for line in backend.run(["omarchy","capture","webcam","list"]).decode().splitlines():
                device,_,name=line.partition("  ");self.camera_device.addItem(name or device,device)
        except Exception:pass
        form.addRow("Camera",self.camera_device)
        self.camera_shape=QComboBox();self.camera_shape.addItems(["Circle","Square","Rounded","Rectangle"])
        self.camera_size=QSpinBox();self.camera_size.setRange(10,80);self.camera_size.setSuffix('%');self.camera_size.setValue(store.settings.get('record_camera_size',22));self.camera_size.setAccessibleName('Camera size');self.camera_size.setToolTip('Camera width as a percentage of the capture area; bounded to fit small areas.')
        self.camera_mirror=QCheckBox('Flip camera');self.camera_mirror.setChecked(store.settings.get('record_camera_mirror',False))
        camera_style=QWidget();camera_style_layout=QHBoxLayout(camera_style);ui.set(camera_style_layout,"setContentsMargins",0,0,0,0);camera_style_layout.addWidget(self.camera_shape);camera_style_layout.addWidget(self.camera_size);camera_style_layout.addWidget(self.camera_mirror);form.addRow('Camera shape / size',camera_style)
        self.camera.toggled.connect(sync_studio)
        self.delay=QSpinBox();self.delay.setRange(0,30);self.delay.setValue(store.settings["record_countdown"]);form.addRow("Countdown",self.delay)
        help=QLabel("Alt+Print opens recording · Stop and Pause are available from\nthe OmniShot tray menu. Recording controls stay out of the saved video.");help.setWordWrap(True);form.addRow(help)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Record");buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)
        self.fps_profiles={"MP4":store.settings["fps"],"GIF":store.settings["gif_fps"]};self.previous_format="MP4"
        self.format.currentTextChanged.connect(self.format_changed);self.format_changed("MP4")
    def format_changed(self,value):
        self.fps_profiles[self.previous_format]=int(self.fps.currentText());self.previous_format=value;self.fps.setCurrentText(str(self.fps_profiles[value]))
        gif=value=="GIF"
        for widget,visible in [(self.size,not gif),(self.scale_video,not gif),(self.quality,not gif),(self.gif_width,gif),(self.gif_quality,gif),(self.gif_optimize,gif)]:
            widget.setVisible(visible)
            label=self.form.labelForField(widget)
            if label:label.setVisible(visible)
        for widget in (self.system,self.mic,self.mono,self.audio_tracks):widget.setEnabled(not gif)
        self.update_meter();self.adjustSize()
    def options(self):
        opts={"mode":self.mode.currentText(),"format":self.format.currentText(),"fps":int(self.fps.currentText()),"quality":self.quality.currentData(),"size":self.size.currentData(),"scale_video":self.scale_video.isChecked(),"system":self.system.isChecked(),"mic":self.mic.isChecked(),"cursor":self.cursor.isChecked(),"delay":self.delay.value()}
        opts.update(dim_screen=self.store.settings["record_dim_screen"],show_controls=self.store.settings["record_show_controls"],show_time=self.store.settings["record_show_time"],remember_selection=self.store.settings["record_remember_selection"])
        opts.update(studio=self.studio.isChecked() or self.clicks.isChecked() or self.keys.isChecked() or self.camera.isChecked(),clicks=self.clicks.isChecked(),keys=self.keys.isChecked(),commands_only=self.commands.isChecked(),dnd=self.dnd.isChecked())
        opts.update(camera=self.camera.isChecked(),camera_device=self.camera_device.currentData(),camera_shape=self.camera_shape.currentText(),camera_size=self.camera_size.value()/100,camera_mirror=self.camera_mirror.isChecked())
        self.store.settings.update(record_camera_size=self.camera_size.value(),record_camera_mirror=self.camera_mirror.isChecked())
        opts.update(system_device=self.system_device.currentData(),mic_device=self.mic_device.currentData(),separate_audio=self.audio_tracks.currentData()=="separate",mono=self.mono.isChecked())
        self.store.settings.update(record_system_device=opts["system_device"],record_microphone_device=opts["mic_device"],record_audio_tracks="separate" if opts["separate_audio"] else "single",record_audio_mono=opts["mono"])
        opts.update(gif_width=self.gif_width.currentData(),gif_quality=self.gif_quality.value(),gif_optimize=self.gif_optimize.isChecked())
        self.store.settings.update(record_countdown=opts["delay"],record_dnd=opts["dnd"],record_clicks=opts["clicks"],record_keys=opts["keys"],record_commands_only=opts["commands_only"])
        self.store.settings.update(record_max_resolution=self.size.currentData(),record_scale_video=self.scale_video.isChecked())
        if opts["format"]=="GIF":opts.update(size="Native",scale_video=False,system=False,mic=False)
        self.fps_profiles[opts["format"]]=opts["fps"]
        self.store.settings.update(fps=self.fps_profiles["MP4"],gif_fps=self.fps_profiles["GIF"],gif_width=opts["gif_width"],gif_quality=opts["gif_quality"],gif_optimize=opts["gif_optimize"],quality=opts["quality"],record_system_audio=self.system.isChecked(),record_microphone=self.mic.isChecked(),record_cursor=opts["cursor"]);self.store.save_settings();return opts
    def done(self,result):self.meter.stop();super().done(result)


def recorder_command(path,rect,opts,clean=False):
    from .recording_options import resolution_limit,recording_monitors
    monitors=recording_monitors(backend.hypr("monitors"),opts.get('capture_output')) if rect is None else []
    if rect:
        x,y,w,h=rect;target=["-w","region","-region",f"{w}x{h}+{x}+{y}"]
    else:
        monitor=next((m for m in monitors if m["focused"]),monitors[0]);target=["-w",monitor["name"]]
    cmd=["gpu-screen-recorder",*target,"-k","h264","-f",str(opts["fps"]),"-fm","cfr","-q",opts["quality"],"-cursor","yes" if opts["cursor"] and not opts.get("studio") else "no","-fallback-cpu-encoding","yes","-write-first-frame-ts","yes","-o",str(path)]
    # Commit recoverable MP4 fragments every second. Hybrid fragmentation
    # converts to an ordinary MP4 on clean Stop; a killed encoder retains the
    # committed fragments instead of losing a short, buffered recording.
    cmd.extend(["-ffmpeg-opts","movflags=+hybrid_fragmented;frag_duration=1000000;flush_packets=1"])
    if clean:cmd.extend(["-p",str(NATIVE/"clean-capture.so")])
    limit=resolution_limit(opts["size"],opts.get("scale_video",False),monitors,rect)
    if limit:cmd.extend(["-s",limit])
    devices=[]
    if opts["system"]:devices.append(opts.get("system_device") or "default_output")
    if opts["mic"]:devices.append(opts.get("mic_device") or "default_input")
    if devices:
        for source in devices if opts.get("separate_audio") or opts.get("studio") else ["|".join(devices)]:cmd.extend(["-a",source])
        cmd.extend(["-ac","aac"])
    return cmd


class Recorder(QWidget):
    completed=Signal(str)
    recovered=Signal(str,str)
    restart_requested=Signal()
    def __init__(self,store,rect,opts):
        opts=dict(opts)
        if rect is None and opts.get('mode')=='Fullscreen' and not opts.get('capture_output'):
            from .recording_options import recording_output
            opts['capture_output']=recording_output(backend.capture_monitors(),backend.hypr('cursorpos'))
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("OmniShot Recording Controls");self.store=store;self.rect_capture=rect;self.opts=dict(opts);
        from .video_audio_tracks import capture_audio_sources
        self.opts["audio_sources"]=capture_audio_sources(opts)
        self.process=None;self.paused=False;self.stopping=False;self.ready=False
        self.path=store.captures/(time.strftime("%Y-%m-%d_%H-%M-%S")+"_"+uuid.uuid4().hex[:8]+".mp4");self.finalizing=False;self.discarding=False;self.waiting_for_encoder=False;self.exit_error=None
        self.journal=None;self.checkpoint=None;self.checkpoint_error=None
        self.name_context=store.capture_name_context()
        self.log_path=self.path.with_suffix(".log");self.log=None;self.started=0;self.elapsed=0;self.pause_at=0;self.pause_total=0;self.remaining=opts["delay"];self.telemetry=None;self.old_dnd=None;self.last_lock_check=0;self.camera_track=None;self.camera_preview=None
        self.status_path=Path(os.environ.get("XDG_RUNTIME_DIR",str(store.root)))/"omnishot-status.json";self.last_status=None;self.clean_capture=None;self.dim_guides=[]
        layout=QHBoxLayout(self);self.time_label=QLabel("Get ready…");ui.set(self.time_label,"setMinimumWidth",110);layout.addWidget(self.time_label)
        self.pause_btn=button("Pause",self.pause);self.pause_btn.setEnabled(False);layout.addWidget(self.pause_btn)
        self.stop_btn=button("Stop",self.stop,True);layout.addWidget(self.stop_btn);layout.addWidget(button("Restart",self.restart_requested.emit));layout.addWidget(button("Hide",self.hide));layout.addWidget(button("Cancel",self.cancel))
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(200);self.countdown=QTimer(self);self.countdown.timeout.connect(self.count)
        if self.remaining:self.time_label.setText(f"Starting in {self.remaining}");self.countdown.start(1000)
        else:QTimer.singleShot(300,self.start)
    def count(self):
        self.remaining-=1;self.time_label.setText(f"Starting in {self.remaining}")
        if self.remaining<=0:self.countdown.stop();self.start()
    def start(self):
        if self.process or self.stopping:return
        try:
            from .recording_journal import RecordingJournal
            from .recording_process import launch_encoder
            monitors=backend.capture_monitors()
            if self.rect_capture is None:
                from .recording_options import recording_monitors
                monitors=recording_monitors(monitors,self.opts.get('capture_output'))
            self.journal=RecordingJournal(self.store,self.path,self.opts)
            self.clean_capture=CleanCapture(monitors,self.rect_capture,self.opts["cursor"] and not self.opts.get("studio"))
            clean=self.clean_capture.start()
            if clean and self.opts.get("dim_screen",False):self.show_dim()
            if self.opts.get("camera"):
                if not self.opts.get("camera_device"):raise RuntimeError("Select an available camera first")
                from .camera import CameraTrack,CameraPreview
                tracks=self.store.root/"tracks";tracks.mkdir(exist_ok=True)
                self.camera_track=CameraTrack(self.opts["camera_device"],tracks/(self.path.stem+"-camera.mp4"),lease_fd=self.journal.lock.fileno());self.camera_track.start()
                from .clean_capture import capture_target
                self.camera_preview=CameraPreview(self.camera_track,self.opts.get("camera_shape","Circle"),rect=self.rect_capture or capture_target(monitors)[2],allow_fullscreen=bool(clean),mirror=self.opts.get('camera_mirror',False))
                self.camera_preview.fullscreen_changed.connect(self.camera_track.framing.set_fullscreen)
                self.camera_preview.shape_changed.connect(self.camera_track.framing.set_shape)
                self.camera_preview.placement_changed.connect(self.camera_track.framing.set_placement)
                if clean:
                    self.camera_preview.show();self.position_camera()
                    # Recorder controls remain above a moved or fullscreen camera.
                    self.camera_preview.windowHandle().activeChanged.connect(self.raise_controls)
                    self.camera_preview.fullscreen_changed.connect(self.raise_controls)
                    self.camera_preview.placement_changed.connect(self.raise_controls)
                    QTimer.singleShot(200,self.raise_controls)
                elif self.rect_capture:
                    self.camera_preview.show()
                    if not place_outside(self.camera_preview,self.rect_capture):self.camera_preview.hide()
            if self.opts.get("dnd"):
                self.old_dnd=backend.run(["omarchy-shell","notifications","isDnd"]).decode().strip()
                self.journal.update(old_dnd=self.old_dnd)
                backend.run(["omarchy-shell","notifications","setDnd","on"])
            if self.opts.get("studio"):
                from .studio import Telemetry
                from .clean_capture import capture_target
                rect=self.rect_capture or capture_target(monitors)[2]
                self.telemetry=Telemetry(rect,keys=self.opts.get("keys",False),clicks=True,commands_only=self.opts.get("commands_only",True));self.telemetry.start()
            self.log=open(self.log_path,"wb");self.process=launch_encoder(recorder_command(self.path,self.clean_capture.encoder_rect,self.opts,clean),stdout=self.log,stderr=self.log,env=self.clean_capture.environment(),lease_fd=self.journal.lock.fileno())
            if self.telemetry or self.camera_track:
                from .recording_checkpoint import StudioCheckpoint
                try:self.checkpoint=StudioCheckpoint(self.path,self.opts,self.telemetry,self.camera_track)
                except OSError as exc:self.checkpoint_error=str(exc)
            self.started=time.monotonic();self.time_label.setText("Starting recording…")
            if not self.opts.get("show_controls",True):self.hide()
            elif clean:self.show();self.position_controls()
            elif self.rect_capture is None or not place_outside(self,self.rect_capture):self.hide()
        except Exception as exc:
            if self.process:
                self.exit_error=str(exc);self.stop();return
            self.timer.stop();self.publish_status(False);self.restore_dnd()
            if self.camera_preview:self.camera_preview.close();self.camera_preview.timer.stop()
            self.hide_dim();self.stop_telemetry();self.release_capture()
            if self.log:self.log.close();self.log=None
            if self.journal:self.journal.close()
            error(self,exc);self.close()
    def tick(self):
        if self.process and not self.stopping:
            if self.process.poll() is not None:
                try:details=self.log_path.read_text()[-1800:].strip()
                except OSError:details=""
                self.exit_error=f"The recording ended unexpectedly (encoder status {self.process.returncode})."
                if details:self.exit_error+="\n"+details
                self.stop();return
            if time.monotonic()-self.last_lock_check>1:
                self.last_lock_check=time.monotonic()
                if backend.session_locked(backend.hypr("monitors")):self.stop();return
            if not self.ready:
                try:
                    self.started=float(Path(str(self.path)+".ts").read_text().strip().splitlines()[-1].split()[0])/1_000_000
                    self.ready=True;self.pause_btn.setEnabled(True)
                except (OSError,ValueError,IndexError):
                    self.publish_status(True);return
            if not self.paused:self.elapsed=time.monotonic()-self.started-self.pause_total
            self.time_label.setText(("Paused  " if self.paused else "●  ")+f"{int(self.elapsed)//60:02d}:{int(self.elapsed)%60:02d}")
            if self.camera_track and self.camera_track.error:self.time_label.setText("Camera unavailable · "+self.time_label.text())
            if self.checkpoint_error or (self.checkpoint and self.checkpoint.error):
                self.time_label.setText("Recovery backup unavailable · "+self.time_label.text())
                self.time_label.setToolTip(self.checkpoint_error or self.checkpoint.error)
            self.publish_status(True)
    def publish_status(self,active):
        status=(active,self.paused,int(self.elapsed),int(time.time()))
        if status==self.last_status:return
        self.last_status=status
        try:self.store.atomic_json(self.status_path,{"recording":active,"paused":self.paused,"seconds":int(self.elapsed),"updated":time.time(),"pid":os.getpid(),"show_time":self.opts.get("show_time",True)})
        except OSError:pass
    def pause(self):
        if not self.process or self.process.poll() is not None or self.stopping or not self.ready:return
        self.process.send_signal(signal.SIGUSR2);self.paused=not self.paused;self.pause_btn.setText("Resume" if self.paused else "Pause")
        if self.paused:self.pause_at=time.monotonic()
        else:self.pause_total+=time.monotonic()-self.pause_at
        if self.telemetry:self.telemetry.pause(self.paused)
        if self.camera_track:self.camera_track.paused=self.paused;self.camera_track.framing.pause(self.paused)
    def stop(self):
        if self.discarding:return
        if self.stopping and not self.waiting_for_encoder:return
        self.waiting_for_encoder=False;self.stopping=True;self.countdown.stop();self.timer.stop();self.hide_dim()
        if self.camera_preview:self.camera_preview.hide();self.camera_preview.timer.stop()
        if not self.process:self.close();return
        self.finalizing=True;self.time_label.setText("Saving recording…");self.stop_btn.setEnabled(False);self.pause_btn.setEnabled(False);self.hide()
        if self.process.poll() is None:
            try:self.process.send_signal(signal.SIGINT)
            except ProcessLookupError:pass
        def finish():
            try:code=self.process.wait(timeout=25)
            except subprocess.TimeoutExpired:raise RuntimeError("Recorder has not finished saving yet. The source recording has been preserved.")
            if self.log:self.log.close();self.log=None
            self.stop_telemetry();self.restore_dnd();self.release_capture()
            if not self.path.exists() or self.path.stat().st_size<100:raise RuntimeError(self.log_path.read_text()[-2000:])
            captured_duration=float(json.loads(backend.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",self.path]))["format"]["duration"])
            if self.opts.get("mono"):
                from .recording_audio import make_mono
                make_mono(self.path)
            path=self.path
            metadata_path=self.path.with_suffix(".studio.json")
            if self.opts.get("studio") or self.opts["format"]=="GIF":
                tracks=self.store.root/"tracks";tracks.mkdir(exist_ok=True)
                raw=tracks/(self.path.stem+"-source.mp4");self.path.replace(raw)
                metadata=json.loads(metadata_path.read_text()) if metadata_path.exists() else {"version":1,"cursor":[],"events":[],"capture_options":self.opts}
                metadata["source_path"]=str(raw.resolve())
                if self.opts.get("studio"):
                    from .studio import smart_zooms
                    metadata["initial_zooms"]=smart_zooms(metadata.get("events",[]),limit=captured_duration)
                self.store.atomic_json(metadata_path,metadata)
                opts={"start":0,"end":0,"speed":1,"fps":self.opts["fps"],"width":0,"format":"MP4","padding":0,"background":"#202633","blur":False,"cursor":self.opts["cursor"],"clicks":self.opts.get("clicks",False),"keys":self.opts.get("keys",False),"camera":self.opts.get("camera",False),"camera_shape":self.opts.get("camera_shape","Circle"),"camera_size":self.opts.get('camera_size',.22),"camera_mirror":self.opts.get('camera_mirror',False)}
                from .video_audio_tracks import default_track_edits
                if not self.opts.get("separate_audio"):opts["audio_tracks"]=default_track_edits(self.opts.get("audio_sources",[]))
                if self.opts.get("studio"):
                    from .studio import export_studio
                    opts["zooms"]=metadata.get("initial_zooms",[])
                    export_studio(raw,self.path,metadata,opts)
            if self.opts["format"]=="GIF":
                path=self.path.with_suffix(".gif");opts={"start":0,"end":0,"speed":1,"fps":self.opts["fps"],"width":self.opts.get("gif_width",self.store.settings["gif_width"]),"gif_quality":self.opts.get("gif_quality",self.store.settings["gif_quality"]),"gif_optimize":self.opts.get("gif_optimize",self.store.settings["gif_optimize"]),"format":"GIF","padding":0,"background":"#202633","blur":0}
                export_video(self.path if self.opts.get("studio") else raw,path,opts)
                self.path.unlink(missing_ok=True)
            record={"kind":"gif" if path.suffix==".gif" else "video","created":time.time(),"options":self.opts}
            if self.exit_error:record["recovery_error"]=self.exit_error
            self.store.atomic_json(path.with_suffix(".json"),record)
            return str(path)
        def work():
            try:return finish(),self.exit_error
            except Exception as exc:
                if self.process.poll() is None:raise
                if self.log:self.log.close();self.log=None
                self.stop_telemetry();self.restore_dnd();self.release_capture()
                from .recording_recovery import recover
                path=recover(self.store,self.path,self.opts,str(exc))
                if path:return path,str(exc)
                raise
        def done(result):
            self.finalizing=False;self.publish_status(False);path,message=result
            if self.journal:self.journal.complete()
            if message:self.recovered.emit(path,message)
            else:self.completed.emit(path)
            self.close()
        def failed(message):
            self.finalizing=False
            if self.process.poll() is None:
                self.waiting_for_encoder=True;self.time_label.setText("Still finishing recording…");self.stop_btn.setText("Keep waiting");self.stop_btn.setEnabled(True);self.show()
                error(self,message);return
            self.publish_status(False);error(None,f"{message}\n\nThe source files were kept in {self.store.root}.");self.close()
            if self.journal:self.journal.close()
        background(work,done,failed)
    def cancel(self):
        if self.finalizing or self.discarding:return
        if self.journal:self.journal.discard()
        self.discarding=True;self.waiting_for_encoder=False;self.stopping=True;self.timer.stop();self.countdown.stop();self.stop_btn.setEnabled(False);self.hide_dim();self.hide()
        if self.camera_preview:self.camera_preview.hide();self.camera_preview.timer.stop()
        def failed(message):
            self.discarding=False;self.stop_btn.setEnabled(True);self.show();error(self,message)
        if self.process and self.process.poll() is None:
            from .recording_process import stop_discarded_process
            background(lambda:stop_discarded_process(self.process),lambda _:self.discard(),failed)
        else:self.discard()
    def discard(self):
        self.publish_status(False);self.stop_telemetry(discard=True);self.restore_dnd();self.release_capture()
        if self.log:self.log.close();self.log=None
        self.path.unlink(missing_ok=True);self.log_path.unlink(missing_ok=True);self.close()
        self.store.remove(self.path)
        if self.journal:self.journal.complete()
    def shutdown(self):
        self.hide_dim();self.publish_status(False)
        if self.camera_preview:self.camera_preview.close()
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:pass
        self.stop_telemetry();self.restore_dnd()
        if not self.process or self.process.poll() is not None:self.release_capture()
        if self.journal:self.journal.close()

    def show_dim(self):
        from PySide6.QtCore import QRect
        from PySide6.QtWidgets import QApplication
        from .scroll_ui import ScrollGuide
        capture=QRect(*(self.rect_capture or self.clean_capture.target[2]))
        for index,screen in enumerate(QApplication.screens()):
            if capture.contains(screen.geometry()):continue
            guide=ScrollGuide(screen,capture,index);guide.setWindowTitle(f"OmniShot Recording Dim {index}")
            self.dim_guides.append(guide);guide.show()

    def hide_dim(self):
        for guide in self.dim_guides:guide.close();guide.deleteLater()
        self.dim_guides=[]

    def release_capture(self):
        if self.clean_capture and self.clean_capture.enabled:
            try:self.clean_capture.stop()
            except Exception:pass

    def restore_dnd(self):
        if self.old_dnd is not None:
            try:
                backend.run(["omarchy-shell","notifications","setDnd",self.old_dnd])
                if self.journal:self.journal.update(old_dnd=None)
            except Exception:pass
            self.old_dnd=None

    def stop_telemetry(self,discard=False):
        checkpoint=self.checkpoint;self.checkpoint=None
        if checkpoint:checkpoint.stop()
        trace=self.telemetry;self.telemetry=None
        camera=self.camera_track;self.camera_track=None
        if not trace and not camera:return
        origin=None;ts=Path(str(self.path)+".ts")
        try:origin=float(ts.read_text().strip().splitlines()[-1].split()[0])/1_000_000
        except (OSError,ValueError,IndexError):pass
        metadata=trace.stop(origin) if trace else {"version":1,"cursor":[],"events":[]};metadata["capture_options"]=self.opts;metadata["source_path"]=str(self.path.resolve())
        if camera:
            path=camera.stop()
            if path:metadata.update(camera_path=str(path),camera_offset=(camera.first_time or origin or 0)-(origin or camera.first_time or 0),camera_framing=camera.framing.snapshot(origin or camera.first_time))
            if camera.error:metadata["camera_error"]=camera.error
        if discard:
            if checkpoint:checkpoint.discard()
            if camera:
                path=Path(camera.path).resolve()
                if path.parent==(self.store.root/"tracks").resolve():path.unlink(missing_ok=True);path.with_suffix(".camera-log").unlink(missing_ok=True)
        else:
            self.store.atomic_json(self.path.with_suffix(".studio.json"),metadata)
            if checkpoint:checkpoint.path.unlink(missing_ok=True)
    def closeEvent(self,event):
        if self.finalizing or (self.process and self.process.poll() is None):self.hide();event.ignore()
        else:self.hide_dim();super().closeEvent(event)

    def position_controls(self):
        if self.clean_capture and self.clean_capture.enabled:
            x,y,w,h=self.clean_capture.controls_bounds
            place_window(self,x+(w-self.width())//2,y+h-self.height()-24)
        elif self.rect_capture:place_outside(self,self.rect_capture)

    def position_camera(self):
        x,y,w,h=self.camera_preview.capture_rect;preview=self.camera_preview
        preview.preferred_width=max(1,round(w*self.opts.get('camera_size',.22)));size,height=preview.overlay_size()
        preview.setFixedSize(size,height);px=round(x+w-size-min(24,(w-size)/2));py=round(y+h-height-min(100,(h-height)/2))
        place_window(preview,px,py);preview.remember_placement(px,py,size);preview.placement_after=time.monotonic()+.25;preview.placement_timer.start()

    def raise_controls(self,*_):
        if not self.isVisible() or not self.camera_preview or not self.camera_preview.isVisible():return
        try:
            native=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==self.windowTitle())
            backend.raise_window(native['address'])
        except (OSError,RuntimeError,StopIteration):pass

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.windowHandle().startSystemMove()

    def showEvent(self,event):
        super().showEvent(event);self.position_controls()


def export_video(source,destination,opts,cancel=None):
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y"]
    if opts["start"]>0:cmd.extend(["-ss",str(opts["start"])])
    cmd.extend(["-i",str(source)])
    if opts["end"]>opts["start"]:cmd.extend(["-t",str(opts["end"]-opts["start"])])
    filters=[]
    if opts.get("speed",1)!=1:filters.append(f"setpts=PTS/{opts['speed']}")
    if opts.get("width"):
        width=f"'min(iw,{int(opts['width'])})'" if opts["format"]=="GIF" else str(int(opts["width"]))
        filters.append(f"scale={width}:-2:flags=lanczos")
    filters.append(f"fps={opts['fps']}")
    if opts.get("blur"):filters.append("tmix=frames=3:weights='1 2 1'")
    if opts.get("padding"):
        pad=opts["padding"];color=opts["background"].replace("#","0x");filters.append(f"pad=iw+{2*pad}:ih+{2*pad}:{pad}:{pad}:color={color}")
    if opts["format"]=="GIF":
        from .gif_options import palette_chain
        chain=palette_chain(filters,opts)
        cmd.extend(["-filter_complex",chain,"-an","-loop","0","-gifflags","+offsetting+transdiff" if opts.get("gif_optimize",True) else "0"])
    else:
        cmd.extend(["-map","0:v:0","-vf",",".join(filters),"-c:v","libx264","-preset","fast","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart"])
        from .video_audio_tracks import export_audio_args
        af=[]
        if opts.get("speed",1)!=1:af.insert(0,f"atempo={opts['speed']}")
        cmd.extend(export_audio_args(opts,0,af))
    cmd.append(str(destination))
    import tempfile
    with tempfile.TemporaryFile() as log:
        process=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=log)
        try:
            while process.poll() is None:
                if cancel and cancel.is_set():raise InterruptedError("Export cancelled")
                try:process.wait(timeout=.2)
                except subprocess.TimeoutExpired:pass
            if process.returncode:log.seek(0);raise RuntimeError(log.read().decode(errors="replace")[-2000:])
        except Exception:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            raise


class VideoEditor(QWidget):
    export_progress=Signal(int)
    def __init__(self,path,store,prepared=None):
        super().__init__();self.path=Path(path);self.store=store;self.setWindowTitle("OmniShot — Video Editor");ui.set(self,"resize",1180,780);ui.set(self,"setMinimumSize",900,600)
        self.restoring_options=True;self.metadata={};self.zooms=[];self.cuts=[];self.splits=[];self.styles={};self.last_frame=None;self.last_camera=None;self.camera_reader=None;self.export_cancel=None;self.close_after_export=False
        from .recording_checkpoint import restore_checkpoint
        try:restore_checkpoint(store,self.path)
        except OSError:pass
        metadata_path=self.path.with_suffix(".studio.json")
        if metadata_path.exists():
            try:self.metadata=json.loads(metadata_path.read_text())
            except (OSError,ValueError):pass
        self.source_path=self.path
        if self.metadata.get("source_path") or (self.path.suffix.lower()==".gif" and self.metadata):
            raw=Path(self.metadata.get("source_path",str(self.path.with_suffix(".mp4"))))
            if raw.is_file():self.source_path=raw
            else:self.metadata={}
        project_options={}
        if self.path.suffix.lower()==".omnishot-video":
            from .video_project import read_project
            self.source_path,self.metadata,project_options=prepared or read_project(self.path,self.store)
        import copy
        self.zooms=copy.deepcopy(self.metadata.get("initial_zooms",[]))
        self.styles["camera_mirror"]=bool(self.metadata.get("capture_options",{}).get("camera_mirror",False))
        if self.metadata.get("camera_path"):
            import cv2
            self.camera_reader=cv2.VideoCapture(self.metadata["camera_path"])
        from .video_decoder import configure_preview_decoder
        configure_preview_decoder()
        self.player=MediaPlayer(self);self.audio=QAudioOutput(self);self.sink=QVideoSink(self)
        self.audio.setMuted(True);self.player.setAudioOutput(self.audio);self.player.setVideoOutput(self.sink)
        from .video_ui import build_editor_ui
        build_editor_ui(self)
        self.player.setSource(QUrl.fromLocalFile(str(self.source_path.resolve())))
        self.sink.videoFrameChanged.connect(self.frame_changed)
        self.player.errorOccurred.connect(lambda _,msg:self.status.setText(msg))
        self.player.play()
        self.speed.currentTextChanged.connect(lambda value:self.player.setPlaybackRate(float(value)))
        for control in (self.show_cursor,self.smoothing,self.show_clicks,self.press_effect,self.show_keys):control.toggled.connect(self.refresh_preview)
        self.cursor_size.valueChanged.connect(self.refresh_preview);self.padding.valueChanged.connect(self.refresh_preview);self.aspect.currentTextChanged.connect(self.refresh_preview);self.bg_color.editingFinished.connect(self.refresh_preview)
        self.camera_enabled.toggled.connect(self.refresh_preview);self.camera_fullscreen.toggled.connect(self.refresh_preview);self.camera_recorded_framing.toggled.connect(self.refresh_preview);self.camera_shape.currentTextChanged.connect(self.refresh_preview);self.camera_position.currentTextChanged.connect(self.refresh_preview);self.camera_size.valueChanged.connect(self.refresh_preview)
        edits=self.store.root/"video-edits";edits.mkdir(exist_ok=True)
        self.edit_path=self.store.video_edit_path(self.path)
        if self.edit_path.exists() or project_options:
            try:
                edit=json.loads(self.edit_path.read_text()) if self.edit_path.exists() else {"options":project_options,"zooms":project_options.get("zooms",[]),"cuts":project_options.get("cuts",[])};self.zooms=edit.get("zooms",[]);self.cuts=edit.get("cuts",[])
                opts=edit.get("options",{})
                from .video_history import restore_options
                restore_options(self,opts)
            except (ValueError,OSError):pass
        self.sync_timeline()
        self.start.valueChanged.connect(self.sync_timeline);self.end.valueChanged.connect(self.sync_timeline)
        self.player.positionChanged.connect(self.preview_position)
        from .video_ui import populate_effects
        populate_effects(self);self.restoring_options=False
        from .video_audio import AudioPreview
        self.audio_preview=AudioPreview(self)
        from .video_history import EditHistory
        self.edit_history=EditHistory(self)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"video"):QTimer.singleShot(0,self.refresh_preview)
    def sync_timeline(self,*args):
        self.timeline.start=self.start.value();self.timeline.end=self.end.value();self.timeline.zooms=self.zooms;self.timeline.cuts=self.cuts;self.timeline.splits=self.splits;self.timeline.update()
        if self.timeline.selected:
            kind,i=self.timeline.selected
            if (kind=="zoom" and i>=len(self.zooms)) or (kind=="cut" and i>=len(self.cuts)) or (kind=='clip' and i>=len(self.timeline.clips())):self.timeline.select(None)
    def timeline_edited(self):
        self.start.blockSignals(True);self.end.blockSignals(True)
        self.start.setValue(self.timeline.start);self.end.setValue(self.timeline.end)
        self.start.blockSignals(False);self.end.blockSignals(False)
        self.save_edits();self.refresh_preview()
    def preview_position(self,milliseconds):
        if self.player.playbackState()!=QMediaPlayer.PlaybackState.PlayingState:return
        t=milliseconds/1000;end=self.end.value() or self.player.duration()/1000
        if t<self.start.value():self.player.setPosition(round(self.start.value()*1000));return
        if end and t>=end:self.player.pause();return
        for a,b in sorted(self.cuts):
            if a<=t<b:self.player.setPosition(round(min(b,end)*1000));return
    def frame_changed(self,frame):
        # Queued sink frames can arrive after Stop has released decoder surfaces.
        # Do not map their hardware buffers while the editor is closing.
        if getattr(self,"closing_editor",False) or not frame.isValid():return
        from PySide6.QtGui import QImage
        image=frame.toImage().convertToFormat(QImage.Format.Format_RGB888)
        if image.isNull():return
        self.last_frame=np.asarray(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3).copy()
        self.timeline.set_source_image(image);self.refresh_preview()
    def studio_options(self):
        return {**self.styles,"zoom_animation":self.zoom_animation.currentText(),"audio_tracks":self.audio_tracks_controls.values() if self.audio_mix.isChecked() else None,"audio_volume":self.audio_volume.value(),"audio_muted":self.audio_muted.isChecked(),"audio_mono":self.audio_mono.isChecked(),"width":0 if self.size.currentText()=="Original" else int(self.size.currentText()),"padding":self.padding.value(),"background":self.bg_color.text(),"aspect":self.aspect.currentText(),"cursor":self.show_cursor.isChecked(),"cursor_size":self.cursor_size.value(),"smoothing":.75 if self.smoothing.isChecked() else 0,"clicks":self.show_clicks.isChecked(),"click_press":self.press_effect.isChecked(),"keys":self.show_keys.isChecked(),"zooms":self.zooms,"cuts":self.cuts,"hardware":self.hardware.isChecked(),"blur":bool(self.motion.value()),"motion_blur":self.motion.value(),"camera":self.camera_enabled.isChecked(),"camera_shape":self.camera_shape.currentText(),"camera_size":self.camera_size.value()/100,"camera_position":self.camera_position.currentText(),"camera_fullscreen":self.camera_fullscreen.isChecked(),"camera_recorded_framing":self.camera_recorded_framing.isChecked()}
    def edit_effects(self):
        from .video_styles import EffectsDialog
        original=dict(self.styles);options=dict(self.styles);options.setdefault('key_commands_only',self.metadata.get('capture_options',{}).get('commands_only',False));dialog=EffectsDialog(options,self)
        def preview(opts):self.styles=opts;self.refresh_preview()
        dialog.changed.connect(preview)
        if dialog.exec():self.styles=dialog.options();self.save_edits()
        else:self.styles=original
        for panel in self.effect_controls.values():panel.set_options({**panel.defaults,**self.styles})
        self.refresh_preview();dialog.deleteLater()
    def edit_input_events(self):
        from .video_styles import InputEventsDialog
        self.player.pause();dialog=InputEventsDialog(self)
        if dialog.exec():self.styles["event_edits"]=dialog.model.edits;self.save_edits();self.refresh_preview()
        dialog.deleteLater()
    def edit_background(self):
        if self.last_frame is None:return
        from .video_styles import VideoBackground
        from .backgrounds import BackgroundDialog
        self.player.pause();adapter=VideoBackground(self);dialog=BackgroundDialog(adapter);dialog.exec();dialog.deleteLater();adapter.deleteLater()
    def refresh_preview(self,*args):
        if self.last_frame is None:return
        from .studio import compose_frame,smooth_cursor,edited_events
        opts=self.studio_options();opts.update(start=self.start.value(),fps=self.fps.value(),speed=float(self.speed.currentText()));meta=dict(self.metadata)
        if opts["smoothing"]:
            if not hasattr(self,"smoothed_cursor"):self.smoothed_cursor=smooth_cursor(meta.get("cursor",[]),opts["smoothing"])
            meta["cursor"]=self.smoothed_cursor
        event_key=json.dumps(opts.get("event_edits",{}),sort_keys=True)
        if getattr(self,"event_key",None)!=event_key:self.event_key=event_key;self.preview_events=edited_events(self.metadata,opts)
        meta["events"]=self.preview_events;opts.pop("event_edits",None)
        camera=None
        if self.camera_reader and self.camera_reader.isOpened() and opts["camera"]:
            import cv2
            self.camera_reader.set(cv2.CAP_PROP_POS_MSEC,max(0,self.player.position()-self.metadata.get("camera_offset",0)*1000));ok,frame=self.camera_reader.read()
            if ok:camera=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        self.last_camera=camera;image=compose_frame(self.last_frame,self.player.position()/1000,meta,opts,camera);self.preview_image=image
        if getattr(self,"fullscreen_preview",None):self.fullscreen_preview.set_image(image)
        self.video.setPixmap(QPixmap.fromImage(image).scaled(self.video.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def edit_options(self):
        opts=self.studio_options();opts.update(start=self.start.value(),end=self.end.value(),speed=float(self.speed.currentText()),fps=self.fps.value(),format=self.format.currentText(),gif_quality=self.gif_quality.value(),gif_optimize=self.gif_optimize.isChecked())
        opts['splits']=self.splits
        return opts
    def save_edits(self):
        self.sync_timeline();opts=self.edit_options()
        if hasattr(self,"edit_history"):self.edit_history.queue()
        try:self.store.atomic_json(self.edit_path,{"version":1,"zooms":self.zooms,"cuts":self.cuts,"options":opts})
        except OSError as exc:
            self.edit_error=str(exc);self.status.setText(f"Could not preserve edits: {exc}");return False
        return True
    def auto_zoom(self):
        from .studio import smart_zooms,edited_events
        self.zooms=smart_zooms(edited_events(self.metadata,self.studio_options()),limit=self.timeline.duration);self.save_edits();self.refresh_preview();self.status.setText(f"{len(self.zooms)} smart zooms from captured clicks")
    def add_zoom(self):
        self.player.pause();self.timeline.add_zoom_at(self.player.position()/1000)
    def clear_zooms(self):self.zooms=[];self.save_edits();self.refresh_preview()
    def add_cut(self):
        if self.end.value()<=self.start.value():error(self,"Choose a trim start and end for the cut first");return
        self.cuts.append([self.start.value(),self.end.value()]);self.start.setValue(0);self.end.setValue(0);self.save_edits();self.status.setText(f"{len(self.cuts)} cut regions will be removed")
    def clear_cuts(self):self.cuts=[];self.save_edits();self.status.setText("Cuts cleared")
    def toggle(self):
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
        else:
            end=self.end.value() or self.player.duration()/1000
            if self.player.position()/1000>=end-.05:self.player.setPosition(round(self.start.value()*1000))
            self.player.play()
    def save_project(self):
        from .video_project import write_project,EXTENSION
        dest=Path(self.store.settings["output_dir"])
        try:dest.mkdir(parents=True,exist_ok=True)
        except OSError as exc:error(self,exc);return
        path,_=QFileDialog.getSaveFileName(self,"Save editable video project",str(dest/(Path(self.store.display_name(self.path)).stem+EXTENSION)),f"OmniShot video project (*{EXTENSION})")
        if not path:return
        if not path.lower().endswith(EXTENSION):path+=EXTENSION
        self.save_edits();options=self.edit_options()
        self.start_job(path,lambda cancel:write_project(path,self.source_path,self.metadata,options,self.export_progress.emit,cancel))
    def start_job(self,path,work):
        import threading
        self.export_cancel=threading.Event();cancel=self.export_cancel
        self.export_btn.setEnabled(False);self.project_btn.setEnabled(False);self.status.setText("Saving…");self.progress.setValue(0);self.progress.show();self.cancel_export.show()
        def finish():
            self.export_btn.setEnabled(True);self.project_btn.setEnabled(True);self.progress.hide();self.cancel_export.hide();self.export_cancel=None
            if self.close_after_export:self.close()
        def done(_):self.status.setText(f"Saved {Path(path).name}");finish()
        def fail(msg):
            self.status.setText("Save cancelled" if cancel.is_set() else "Save failed")
            if not cancel.is_set():error(self,msg)
            finish()
        background(lambda:work(cancel),done,fail)
    def export(self):
        import re
        if not re.fullmatch(r"#[0-9a-fA-F]{6}",self.bg_color.text()):error(self,"Enter a background color as #RRGGBB");return
        if self.end.value() and self.end.value()<=self.start.value():error(self,"Trim end must be after the start");return
        ext="gif" if self.format.currentText()=="GIF" else "mp4";dest=Path(self.store.settings["output_dir"])
        try:dest.mkdir(parents=True,exist_ok=True)
        except OSError as exc:error(self,exc);return
        path,_=QFileDialog.getSaveFileName(self,"Export video",str(dest/(Path(self.store.display_name(self.path)).stem+"-edited."+ext)),f"Video (*.{ext})")
        if not path:return
        if Path(path).resolve() in (self.path.resolve(),self.source_path.resolve()):error(self,"Choose a new filename to preserve the recording");return
        opts={"start":self.start.value(),"end":self.end.value(),"speed":float(self.speed.currentText()),"fps":self.fps.value(),"width":0 if self.size.currentText()=="Original" else int(self.size.currentText()),"format":self.format.currentText(),"padding":self.padding.value(),"background":self.bg_color.text(),"blur":bool(self.motion.value()),"motion_blur":self.motion.value()}
        opts.update(self.studio_options());self.save_edits()
        def work(cancel):
            from .studio import export_studio
            if opts["format"]=="GIF":
                intermediate=Path(path).with_name(".omnishot-"+uuid.uuid4().hex+".mp4")
                try:
                    export_studio(self.source_path,intermediate,self.metadata,opts,lambda n:self.export_progress.emit(int(n*.9)),cancel)
                    temporary=Path(path).with_name(Path(path).stem+".partial.gif")
                    try:
                        export_video(intermediate,temporary,{**opts,"start":0,"end":0,"speed":1,"width":0,"padding":0,"blur":False},cancel);temporary.replace(path)
                    finally:temporary.unlink(missing_ok=True)
                finally:intermediate.unlink(missing_ok=True)
            else:export_studio(self.source_path,path,self.metadata,opts,self.export_progress.emit,cancel)
        self.start_job(path,work)
    def closeEvent(self,event):
        self.closing_editor=True
        if getattr(self,"fullscreen_preview",None):self.fullscreen_preview.close()
        if self.export_cancel:
            self.close_after_export=True;self.export_cancel.set();event.ignore();return
        self.player.pause()
        while not self.save_edits():
            reply=QMessageBox.warning(self,"Could not preserve edits",self.edit_error+"\n\nKeep this window open to save an editable project elsewhere, or retry after freeing space.",QMessageBox.StandardButton.Retry|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if reply==QMessageBox.StandardButton.Discard:break
            if reply!=QMessageBox.StandardButton.Retry:self.close_after_export=False;self.closing_editor=False;event.ignore();return
        if not getattr(self,"media_closed",False):
            self.timeline.shutdown()
            self.media_closed=True;self.sink.videoFrameChanged.disconnect(self.frame_changed)
            self.player.stop();self.player.setVideoOutput(None)
        self.edit_history.close();self.audio_preview.close();self.player.setSource(QUrl())
        if self.camera_reader:self.camera_reader.release()
        super().closeEvent(event)
