"""Session undo/redo of complete video edits, grouped by input gesture."""
import copy
from PySide6.QtCore import QObject,QTimer,QEvent,Qt,QSignalBlocker
from PySide6.QtGui import QKeySequence,QShortcut
from PySide6.QtWidgets import QApplication,QWidget,QAbstractSpinBox,QLineEdit,QCheckBox,QSlider,QComboBox


def restore_options(e,opts):
    previous=e.restoring_options;e.restoring_options=True
    blockers=[QSignalBlocker(w) for w in e.findChildren(QWidget)]
    try:
        e.styles=copy.deepcopy(opts)
        e.zooms=copy.deepcopy(opts.get('zooms',e.zooms));e.cuts=copy.deepcopy(opts.get('cuts',e.cuts))
        from .video_splits import clean_splits
        e.splits=clean_splits(opts.get('splits',[]))
        for key,name in [('padding','padding'),('cursor_size','cursor_size'),('start','start'),('end','end'),('fps','fps'),('gif_quality','gif_quality'),('audio_volume','audio_volume')]:
            if key in opts:getattr(e,name).setValue(opts[key])
        if 'background' in opts:e.bg_color.setText(opts['background'])
        for key,name in [('zoom_animation','zoom_animation'),('aspect','aspect'),('camera_shape','camera_shape'),('camera_position','camera_position'),('format','format')]:
            if key in opts:getattr(e,name).setCurrentText(opts[key])
        for key,name in [('cursor','show_cursor'),('smoothing','smoothing'),('clicks','show_clicks'),('keys','show_keys'),('hardware','hardware'),('camera','camera_enabled'),('camera_fullscreen','camera_fullscreen'),('camera_recorded_framing','camera_recorded_framing'),('gif_optimize','gif_optimize'),('audio_muted','audio_muted'),('audio_mono','audio_mono')]:
            if key in opts:getattr(e,name).setChecked(bool(opts[key]))
        e.press_effect.setChecked(bool(opts.get('click_press',False)))
        from .motion_blur import blur_level,LEVELS
        e.motion.setValue(blur_level(opts));e.motion_label.setText(LEVELS[e.motion.value()]);e.motion.setAccessibleDescription(LEVELS[e.motion.value()])
        if 'camera_size' in opts:e.camera_size.setValue(round(opts['camera_size']*100))
        e.audio_mix.setChecked(isinstance(opts.get('audio_tracks'),list));tracks=copy.deepcopy(opts.get('audio_tracks') or []);e.audio_tracks_controls.saved=tracks
        for i,(_,enabled,gain,value) in enumerate(e.audio_tracks_controls.rows):
            row=tracks[i] if i<len(tracks) else {};enabled.setChecked(row.get('enabled',True));gain.setValue(row.get('volume',100));value.setValue(gain.value())
        e.volume.setValue(e.audio_volume.value())
        if 'speed' in opts:e.speed.setCurrentText(str(opts['speed']).removesuffix('.0'))
        if 'width' in opts:e.size.setCurrentText(str(opts['width']) if opts['width'] else 'Original')
        for panel in getattr(e,'effect_controls',{}).values():panel.set_options({**panel.defaults,**opts})
        e.previous_export_format=e.format.currentText();e.export_profiles[e.previous_export_format]=(e.fps.value(),e.size.currentText())
        e.gif_quality.setVisible(e.format.currentText()=='GIF');e.gif_optimize.setVisible(e.format.currentText()=='GIF')
        e.gif_quality_label.setVisible(e.format.currentText()=='GIF')
    finally:
        blockers.clear();e.restoring_options=previous
    e.player.setPlaybackRate(float(e.speed.currentText()))
    if hasattr(e,'audio_preview'):e.audio_preview.update()


class EditHistory(QObject):
    def __init__(self,e):
        super().__init__(e);self.editor=e;self.applying=False;self.closed=False;self.text_edit=None;self.past=[];self.future=[];self.current=self.snapshot()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.flush)
        self.undo_shortcut=QShortcut(QKeySequence('Ctrl+Z'),e,activated=self.undo)
        self.redo_shortcut=QShortcut(QKeySequence('Ctrl+Shift+Z'),e,activated=self.redo)
        self.redo_alt=QShortcut(QKeySequence('Ctrl+Y'),e,activated=self.redo)
        QApplication.instance().installEventFilter(self)
        for widget in e.findChildren(QWidget):
            if isinstance(widget,QAbstractSpinBox):widget.valueChanged.connect(self.queue)
            elif isinstance(widget,QLineEdit):widget.editingFinished.connect(self.queue)
            elif isinstance(widget,QCheckBox):widget.toggled.connect(self.queue)
            elif isinstance(widget,QSlider):widget.valueChanged.connect(self.queue)
            elif isinstance(widget,QComboBox):widget.currentTextChanged.connect(self.queue)
        self.update_actions()

    def snapshot(self):
        options=self.editor.edit_options()
        if options.get('audio_tracks')==[] and self.editor.audio_tracks_controls.signature is None:
            from .video_audio_tracks import default_track_edits
            options['audio_tracks']=default_track_edits(self.editor.metadata.get('capture_options',{}).get('audio_sources',[]))
        return copy.deepcopy(dict(options=options,profiles=self.editor.export_profiles))
    def belongs(self,target):return isinstance(target,QWidget) and (target==self.editor or self.editor.isAncestorOf(target))
    def eventFilter(self,target,event):
        if self.belongs(target) and not self.applying:
            if event.type()==QEvent.Type.MouseButtonPress:
                # Commit the previous command before a new input can change it.
                if not self.editor.timeline.drag and not self.editor.zoom_inspector.focus.drag and not QApplication.activeModalWidget():self.text_edit=None;self.flush(True)
            elif event.type()==QEvent.Type.KeyPress:
                if isinstance(target,QLineEdit) and event.key() not in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Tab,Qt.Key.Key_Escape):self.text_edit=target
                else:self.text_edit=None;self.flush()
            elif event.type()==QEvent.Type.FocusOut:self.text_edit=None;self.queue()
            elif event.type() in (QEvent.Type.MouseButtonRelease,QEvent.Type.KeyRelease):self.queue()
        return False
    def gesture(self):
        e=self.editor
        return bool(self.text_edit or e.timeline.drag or e.zoom_inspector.focus.drag or QApplication.mouseButtons()!=Qt.MouseButton.NoButton or QApplication.activeModalWidget())
    def queue(self,*_):
        if not self.closed and not self.applying and not self.editor.restoring_options:self.timer.start(0)
    def flush(self,force=False):
        if self.applying or self.editor.restoring_options:return
        if self.gesture() and not force:self.timer.start(40);return
        self.timer.stop();state=self.snapshot()
        if state==self.current:return
        self.past.append(self.current);self.past=self.past[-100:];self.current=state;self.future.clear();self.update_actions()
        self.applying=True
        try:self.editor.save_edits()
        finally:self.applying=False
    def update_actions(self):
        self.editor.undo_button.setEnabled(bool(self.past));self.editor.redo_button.setEnabled(bool(self.future))
    def restore(self,state):
        e=self.editor;self.applying=True;e.player.pause()
        try:
            restore_options(e,state['options']);e.export_profiles=copy.deepcopy(state['profiles']);e.timeline.select(None);e.sync_timeline();e.zoom_inspector.sync()
            e.save_edits();e.refresh_preview();self.current=self.snapshot();self.update_actions()
        finally:self.applying=False
    def undo(self):
        if getattr(self.editor,'fullscreen_preview',None) or QApplication.activeModalWidget():return
        if self.editor.timeline.drag:self.editor.timeline.finish_drag(cancel=True)
        self.flush(True)
        if not self.past:return
        self.future.append(self.current);self.restore(self.past.pop())
    def redo(self):
        if getattr(self.editor,'fullscreen_preview',None) or QApplication.activeModalWidget():return
        self.flush(True)
        if not self.future:return
        self.past.append(self.current);self.restore(self.future.pop())
    def close(self):self.closed=True;self.timer.stop();QApplication.instance().removeEventFilter(self)
