"""Full-screen playback of the editor's current composition and source clock."""
from PySide6.QtCore import Qt, QEvent, QRectF, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QFrame, QVBoxLayout,
    QHBoxLayout, QSlider, QToolButton)
from .editor_toolbar import icon as tool_icon


class PreviewLabel(QLabel):
    expanded=Signal()

    def __init__(self):
        super().__init__();self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.expand=QToolButton(self);self.expand.setIcon(tool_icon('expand'))
        self.expand.setAccessibleName("Full-screen preview");self.expand.setToolTip("Full-screen preview (F11)")
        self.expand.setFixedSize(30,30);self.expand.clicked.connect(self.expanded)

    def resizeEvent(self,event):
        super().resizeEvent(event);self.expand.move(max(0,self.width()-38),8)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.expanded.emit();event.accept()
        else:super().mouseDoubleClickEvent(event)


def toggle_fullscreen(editor):
    preview=getattr(editor,"fullscreen_preview",None)
    if preview is not None:preview.close();return
    preview=FullscreenPreview(editor);editor.fullscreen_preview=preview
    preview.winId();preview.windowHandle().setScreen(editor.screen())
    preview.showFullScreen();preview.setFocus();editor.refresh_preview()


class FullscreenPreview(QWidget):
    def __init__(self,editor):
        super().__init__(editor,Qt.WindowType.Window)
        self.editor=editor;self.image=QImage();self.closing=False;self.scrubbing=False
        self.setWindowTitle("OmniShot — Full-screen Preview")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setMouseTracking(True)
        self.setStyleSheet("QFrame#playbackControls {background:palette(window);border:1px solid palette(mid);border-radius:12px;} QLabel {color:palette(window-text);} QToolButton {color:palette(window-text);background:palette(button);border:1px solid palette(mid);border-radius:6px;padding:6px;} QToolButton:hover {background:palette(light);} QSlider::groove:horizontal {height:5px;background:palette(mid);} QSlider::handle:horizontal {background:palette(highlight);width:14px;margin:-5px 0;border-radius:7px;}")
        self.controls=QFrame(self);self.controls.setObjectName("playbackControls")
        layout=QVBoxLayout(self.controls);layout.setContentsMargins(16,12,16,12)
        self.seek=QSlider(Qt.Orientation.Horizontal);self.seek.setAccessibleName("Playback position")
        self.seek.setRange(0,editor.player.duration());self.seek.setValue(editor.player.position())
        self.seek.setSingleStep(1000);self.seek.setPageStep(5000);layout.addWidget(self.seek)
        transport=QHBoxLayout();layout.addLayout(transport)
        self.time=QLabel();transport.addWidget(self.time);transport.addStretch()
        def button(label,icon,slot):
            control=QToolButton();control.setAccessibleName(label);control.setToolTip(label)
            control.setIcon(tool_icon(icon));control.clicked.connect(slot);transport.addWidget(control);return control
        from .video_ui import step_frame
        self.previous=button("Previous frame",'previous',lambda:step_frame(editor,-1))
        self.play=button("Play / Pause",'play',editor.toggle)
        self.next=button("Next frame",'next',lambda:step_frame(editor,1));transport.addStretch()
        self.mute=button("Mute recording audio",'volume',editor.audio_muted.toggle)
        self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(editor.audio_volume.value());self.volume.setFixedWidth(100)
        self.volume.setAccessibleName("Recording volume");self.volume.setToolTip("Recording volume · also applied to exports")
        transport.addWidget(self.volume)
        self.exit=QToolButton();self.exit.setText("Exit full screen");self.exit.setAccessibleName("Exit full screen");self.exit.setToolTip("Return to editor (Escape)")
        self.exit.clicked.connect(self.close);transport.addWidget(self.exit)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(2200);self.timer.timeout.connect(self.hide_controls)
        self.click_timer=QTimer(self);self.click_timer.setSingleShot(True);self.click_timer.setInterval(QApplication.doubleClickInterval());self.click_timer.timeout.connect(editor.toggle)
        self.seek.sliderPressed.connect(self.start_scrub);self.seek.sliderReleased.connect(self.end_scrub)
        self.seek.valueChanged.connect(self.seek_changed);self.volume.valueChanged.connect(editor.audio_volume.setValue)
        self.connections=[]
        for signal,slot in [(editor.player.positionChanged,self.position_changed),(editor.player.durationChanged,self.duration_changed),(editor.player.playbackStateChanged,self.playback_changed),(editor.audio_volume.valueChanged,self.volume.setValue),(editor.audio_muted.toggled,self.audio_changed),(editor.format.currentTextChanged,self.audio_changed),(editor.player.tracksChanged,self.audio_changed)]:
            signal.connect(slot);self.connections.append((signal,slot))
        QApplication.instance().installEventFilter(self)
        self.position_changed(editor.player.position());self.playback_changed(editor.player.playbackState());self.audio_changed()
        self.set_image(getattr(editor,"preview_image",QImage()))

    def set_image(self,image):self.image=QImage(image);self.update()

    def image_rect(self):
        if self.image.isNull():return QRectF()
        area=QRectF(self.rect());size=self.image.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((area.width()-size.width())/2,(area.height()-size.height())/2,size.width(),size.height())

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor("#000000"));painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.image.isNull():painter.drawImage(self.image_rect(),self.image)

    def resizeEvent(self,event):
        super().resizeEvent(event);width=max(320,min(900,self.width()-48));height=self.controls.sizeHint().height()
        self.controls.setGeometry((self.width()-width)//2,max(0,self.height()-height-24),width,height)

    def show_controls(self):
        self.controls.show();self.unsetCursor()
        if self.editor.player.isPlaying():self.timer.start()

    def hide_controls(self):
        focus=QApplication.focusWidget()
        if not self.editor.player.isPlaying() or self.scrubbing or self.controls.underMouse() or (focus is not None and self.controls.isAncestorOf(focus)):self.timer.start();return
        self.controls.hide();self.setCursor(Qt.CursorShape.BlankCursor)

    def position_changed(self,position):
        if not self.scrubbing:
            self.seek.blockSignals(True);self.seek.setValue(position);self.seek.blockSignals(False)
        def stamp(ms):
            seconds=max(0,ms//1000);return f"{seconds//60:02}:{seconds%60:02}"
        self.time.setText(f"{stamp(position)} / {stamp(self.editor.player.duration())}")

    def duration_changed(self,duration):self.seek.setMaximum(duration);self.position_changed(self.editor.player.position())

    def playback_changed(self,state):
        playing=state==QMediaPlayer.PlaybackState.PlayingState
        self.play.setIcon(tool_icon('pause' if playing else 'play'))
        self.play.setAccessibleName("Pause" if playing else "Play");self.play.setToolTip("Pause (Space)" if playing else "Play (Space)")
        self.show_controls()
        if not playing:self.timer.stop()

    def audio_changed(self,*_):
        e=self.editor;muted=e.audio_muted.isChecked();available=bool(e.player.audioTracks()) and e.format.currentText()!="GIF"
        self.mute.setEnabled(available);self.volume.setEnabled(available)
        self.mute.setIcon(tool_icon('mute' if muted else 'volume'))
        self.mute.setAccessibleName("Unmute recording audio" if muted else "Mute recording audio")
        self.mute.setToolTip(self.mute.accessibleName()+" (M)")

    def start_scrub(self):
        self.scrubbing=True;self.resume=self.editor.player.isPlaying();self.editor.player.pause();self.timer.stop()

    def seek_changed(self,position):
        self.editor.player.setPosition(position);self.show_controls()

    def end_scrub(self):
        self.scrubbing=False
        if self.resume:self.editor.player.play()
        self.setFocus();self.show_controls()

    def eventFilter(self,target,event):
        if self.closing or not isinstance(target,QWidget) or target.window() is not self:return False
        if event.type()==QEvent.Type.MouseMove:self.show_controls()
        keys=(Qt.Key.Key_Escape,Qt.Key.Key_F11,Qt.Key.Key_Space,Qt.Key.Key_M)
        if target is self:keys+= (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Home,Qt.Key.Key_End)
        if event.type() in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress) and event.key() in keys:
            if event.type()==QEvent.Type.ShortcutOverride:event.accept();return True
            if event.isAutoRepeat() and event.key() in (Qt.Key.Key_Escape,Qt.Key.Key_F11,Qt.Key.Key_Space,Qt.Key.Key_M):return True
            self.handle_key(event);return True
        return False

    def handle_key(self,event):
        key=event.key();e=self.editor
        if key in (Qt.Key.Key_Escape,Qt.Key.Key_F11):self.close();return
        if key==Qt.Key.Key_Space:e.toggle()
        elif key==Qt.Key.Key_M:
            if self.mute.isEnabled():e.audio_muted.toggle()
        elif key in (Qt.Key.Key_Left,Qt.Key.Key_Right):
            if event.modifiers()&Qt.KeyboardModifier.ShiftModifier:
                e.player.pause();e.player.setPosition(max(0,min(e.player.duration(),e.player.position()+(1000 if key==Qt.Key.Key_Right else -1000))))
            else:
                from .video_ui import step_frame
                step_frame(e,1 if key==Qt.Key.Key_Right else -1)
        elif key in (Qt.Key.Key_Home,Qt.Key.Key_End):
            e.player.pause();e.player.setPosition(round(e.start.value()*1000) if key==Qt.Key.Key_Home else round((e.end.value() or e.player.duration()/1000)*1000))
        self.show_controls()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.setFocus();self.click_timer.start()

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.click_timer.stop();self.close()

    def closeEvent(self,event):
        self.closing=True;self.timer.stop();self.click_timer.stop();self.unsetCursor()
        QApplication.instance().removeEventFilter(self)
        for signal,slot in self.connections:signal.disconnect(slot)
        self.connections.clear();self.editor.fullscreen_preview=None
        if not getattr(self.editor,"closing_editor",False):self.editor.activateWindow();self.editor.video.setFocus()
        super().closeEvent(event)
