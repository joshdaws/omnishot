"""Recording editor layout: tools and inspector beside the preview, tracks below."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaPlayer,QMediaMetaData
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QScrollArea, QStackedWidget, QButtonGroup, QToolButton,
    QSpinBox, QDoubleSpinBox,  QCheckBox, QLineEdit, QProgressBar,
    QSizePolicy, QSlider, QGridLayout)
from .widgets import button
from .timeline import Timeline,SCROLLBAR_STYLE
from .controls import Choice as QComboBox
from .editor_toolbar import icon as tool_icon

TOOL_STYLE='QToolButton { border:0; background:transparent; padding:6px; border-radius:8px; } QToolButton:hover { background:palette(light); } QToolButton:checked { background:palette(highlight); color:palette(highlighted-text); }'


def build_editor_ui(editor):
    e=editor;layout=QVBoxLayout(e);layout.setContentsMargins(12,10,12,10);layout.setSpacing(10)
    header=QHBoxLayout();title=QLabel(e.store.display_name(e.path))
    title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);title.setToolTip(title.text());header.addWidget(title,1)
    e.undo_button=button('↶',lambda:e.edit_history.undo());e.redo_button=button('↷',lambda:e.edit_history.redo())
    for control,label,keys in [(e.undo_button,'Undo','Ctrl+Z'),(e.redo_button,'Redo','Ctrl+Shift+Z')]:
        control.setText('');control.setIcon(tool_icon(label.lower()));control.setIconSize(QSize(20,20));control.setFixedWidth(36);control.setAccessibleName(label);control.setToolTip(label+' · '+keys);header.addWidget(control)
    e.project_btn=button("Save editable project…",e.save_project);header.addWidget(e.project_btn)
    e.export_btn=button("Export…",e.export,True);header.addWidget(e.export_btn);layout.addLayout(header)
    body=QHBoxLayout();body.setSpacing(0);layout.addLayout(body,1)
    rail=QWidget();rail.setFixedWidth(58);navigation=QVBoxLayout(rail);navigation.setContentsMargins(0,0,8,0);navigation.setSpacing(5);body.addWidget(rail)
    rail.setStyleSheet(TOOL_STYLE)
    e.inspector=QStackedWidget();e.inspector.setFixedWidth(284);body.addWidget(e.inspector)
    e.tool_group=QButtonGroup(e);e.tool_buttons={};e.tool_pages={}
    tools=[("Cursor","cursor-click"),("Keystrokes","keyboard"),
           ("Audio","volume"),("Camera","camera"),("Background","background"),
           ("Motion","motion"),("Trim","crop"),("Export","export")]
    for index,(name,icon) in enumerate(tools):
        tool=QToolButton();tool.setText(name);tool.setAccessibleName(name+" settings");tool.setToolTip(name)
        tool.setIcon(tool_icon(icon));tool.setIconSize(QSize(23,23))
        tool.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly);tool.setCheckable(True);tool.setFixedSize(48,38)
        e.tool_group.addButton(tool,index);e.tool_buttons[name]=tool;navigation.addWidget(tool)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(SCROLLBAR_STYLE)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page=QWidget();page_layout=QVBoxLayout(page);page_layout.setContentsMargins(14,6,14,12);page_layout.setSpacing(12)
        heading=QLabel(name);heading.setStyleSheet("font-size:16px;font-weight:600;");page_layout.addWidget(heading)
        e.tool_pages[name]=page_layout;scroll.setWidget(page);e.inspector.addWidget(scroll)
    navigation.addStretch();e.tool_group.idClicked.connect(e.inspector.setCurrentIndex);e.tool_buttons["Cursor"].setChecked(True)
    e.cut_tool=QToolButton();e.cut_tool.setCheckable(True);e.cut_tool.setFixedSize(48,38)
    e.cut_tool.setIcon(tool_icon('cut'));e.cut_tool.setIconSize(QSize(23,23))
    e.cut_tool.setAccessibleName('Cut tool');e.cut_tool.setToolTip('Cut tool · B · Ctrl+B splits at the playhead');navigation.addWidget(e.cut_tool)
    center=QVBoxLayout();center.setContentsMargins(14,0,0,0);body.addLayout(center,1)
    from .video_preview import PreviewLabel,toggle_fullscreen
    e.video=PreviewLabel();e.video.expanded.connect(lambda:toggle_fullscreen(e))
    QShortcut(QKeySequence("F11"),e,activated=lambda:toggle_fullscreen(e))
    e.video.setAlignment(Qt.AlignmentFlag.AlignCenter);e.video.setMinimumSize(320,220)
    e.video.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored);center.addWidget(e.video,1)
    transport=QHBoxLayout();e.time_label=QLabel("00:00 / 00:00");transport.addWidget(e.time_label);transport.addStretch()
    def transport_button(label,icon,slot):
        control=QToolButton();control.setIcon(tool_icon(icon));control.setIconSize(QSize(20,20));control.setToolTip(label);control.setAccessibleName(label)
        control.setStyleSheet(TOOL_STYLE)
        control.clicked.connect(slot);transport.addWidget(control);return control
    transport_button("Previous frame",'previous',lambda:step_frame(e,-1))
    e.play_button=transport_button("Play / Pause",'play',e.toggle)
    transport_button("Next frame",'next',lambda:step_frame(e,1));transport.addStretch()
    e.volume=QSlider(Qt.Orientation.Horizontal);e.volume.setRange(0,100);e.volume.setValue(100)
    e.volume.setToolTip("Recording volume · also applied to exports");e.volume.setAccessibleName("Recording volume")
    e.timeline_zoom=QSlider(Qt.Orientation.Horizontal);e.timeline_zoom.setRange(0,100);e.timeline_zoom.setFixedWidth(88)
    e.timeline_zoom.setAccessibleName("Timeline zoom");e.timeline_zoom.setToolTip("Timeline zoom · Home fits the entire recording")
    e.timeline_minus=QToolButton();e.timeline_minus.setText("−");e.timeline_plus=QToolButton();e.timeline_plus.setText("+")
    for control,label,delta in [(e.timeline_minus,"Zoom timeline out",-10),(e.timeline_plus,"Zoom timeline in",10)]:
        control.setFixedSize(24,24);control.setStyleSheet("padding:0;");control.setAccessibleName(label);control.setToolTip(label);control.clicked.connect(lambda checked=False,d=delta:e.timeline_zoom.setValue(e.timeline_zoom.value()+d))
    transport.addWidget(e.timeline_minus);transport.addWidget(e.timeline_zoom);transport.addWidget(e.timeline_plus);center.addLayout(transport)
    e.timeline=Timeline();layout.addWidget(e.timeline)
    e.cut_tool.toggled.connect(e.timeline.set_cut_mode);e.timeline.cut_mode_changed.connect(e.cut_tool.setChecked)
    e.cut_tool.clicked.connect(lambda:e.timeline.setFocus())
    def cut_shortcut(split=False):
        if getattr(e,'fullscreen_preview',None):return
        if split:e.timeline.split_at()
        else:e.timeline.set_cut_mode(True);e.timeline.setFocus()
    QShortcut(QKeySequence('B'),e,activated=cut_shortcut)
    QShortcut(QKeySequence('Ctrl+B'),e,activated=lambda:cut_shortcut(True))
    QShortcut(QKeySequence('Ctrl+Shift+B'),e,activated=lambda:e.timeline.split_zoom_at_playhead() if not getattr(e,'fullscreen_preview',None) else None)
    e.timeline_zoom.valueChanged.connect(e.timeline.set_zoom);e.timeline.zoom_changed.connect(e.timeline_zoom.setValue)
    e.timeline.set_source(e.source_path)
    e.player.durationChanged.connect(e.timeline.set_duration);e.player.positionChanged.connect(e.timeline.set_position)
    e.player.metaDataChanged.connect(lambda:e.timeline.set_frame_rate(e.player.metaData().value(QMediaMetaData.Key.VideoFrameRate)))
    e.player.playbackStateChanged.connect(lambda state:e.timeline.set_playing(state==QMediaPlayer.PlaybackState.PlayingState))
    def seek_started():e.resume_timeline=e.player.isPlaying();e.player.pause()
    def seek_finished():
        if getattr(e,"resume_timeline",False):e.player.play()
        e.resume_timeline=False
    e.timeline.seek_started.connect(seek_started);e.timeline.seek_finished.connect(seek_finished)
    e.timeline.seek.connect(e.player.setPosition);e.timeline.edited.connect(e.timeline_edited);e.timeline.editing_focus.connect(e.player.pause)
    e.player.positionChanged.connect(lambda _:update_transport(e));e.player.durationChanged.connect(lambda _:update_transport(e))
    e.player.playbackStateChanged.connect(lambda _:update_transport(e))
    QShortcut(QKeySequence("Space"),e,activated=e.toggle)
    QShortcut(QKeySequence("Ctrl+S"),e,activated=e.export)
    QShortcut(QKeySequence("Ctrl+Shift+S"),e,activated=e.save_project)
    def form(name):
        result=QFormLayout();result.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        result.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);result.setVerticalSpacing(10);e.tool_pages[name].addLayout(result);return result
    def integer(low,high,value=0,suffix=""):
        w=QSpinBox();w.setRange(low,high);w.setValue(value);w.setSuffix(suffix);return w
    def choice(items,current=None):
        w=QComboBox();w.addItems(items)
        if current is not None:w.setCurrentText(str(current))
        return w
    def check(text,value=False):
        w=QCheckBox(text);w.setChecked(value);return w
    cursor=form("Cursor");e.show_cursor=check("Show cursor",e.metadata.get("capture_options",{}).get("cursor",True));cursor.addRow(e.show_cursor)
    from .video_cursor import CursorSize,CursorMotion
    e.cursor_size=CursorSize();cursor.addRow(e.cursor_size)
    e.smoothing=CursorMotion();e.show_clicks=check("Ripple animation",e.metadata.get("capture_options",{}).get("clicks",True))
    e.press_effect=check('Press effect',False);e.press_effect.setToolTip('Briefly compress the cursor at each recorded click')
    e.show_clicks.setToolTip('Show a growing, fading highlight at each recorded click')
    keys=form("Keystrokes");e.show_keys=check("Show keystrokes",e.metadata.get("capture_options",{}).get("keys",True));keys.addRow(e.show_keys)
    camera=form("Camera");e.camera_enabled=check("Show camera",bool(e.metadata.get("camera_path")));camera.addRow(e.camera_enabled)
    e.camera_shape=choice(["Circle","Square","Rounded","Rectangle"],e.metadata.get("capture_options",{}).get("camera_shape","Circle"));camera.addRow("Shape",e.camera_shape)
    e.camera_size=integer(10,80,round(e.metadata.get('capture_options',{}).get('camera_size',.22)*100),"%");camera.addRow("Size",e.camera_size)
    from .video_position import PositionGrid
    e.camera_position=PositionGrid();camera.addRow("Position",e.camera_position)
    e.camera_fullscreen=check("Fullscreen camera");camera.addRow(e.camera_fullscreen)
    e.camera_recorded_framing=check('Use recorded camera framing',True);e.camera_recorded_framing.setToolTip('Replay camera placement, fullscreen and shape changes made during recording. Turn off to use one framing throughout.');camera.addRow(e.camera_recorded_framing);e.camera_recorded_framing.setVisible(bool(e.metadata.get('camera_framing')))
    bg=e.tool_pages["Background"];bg.addWidget(button("None",lambda:apply_background(e,None)))
    bg.addWidget(QLabel("Gradients"));presets=QGridLayout();presets.setHorizontalSpacing(6);presets.setVerticalSpacing(8);bg.addLayout(presets)
    from .backgrounds import PRESETS
    for i,(name,colors) in enumerate(list(PRESETS.items())[:18]):
        swatch=button("",lambda checked=False,n=name:apply_background(e,n));swatch.setFixedSize(43,38);swatch.setToolTip(name);swatch.setAccessibleName(name+" background")
        swatch.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {colors[0]},stop:1 {colors[1]});border-radius:9px;")
        presets.addWidget(swatch,i//5,i%5)
    bg.addWidget(button("Background…",e.edit_background));background_form=form("Background")
    e.padding=integer(0,500,0," px");background_form.addRow("Padding",e.padding)
    e.bg_color=QLineEdit("#202633");background_form.addRow("Color",e.bg_color)
    e.aspect=choice(["Original","16:9","1:1","9:16","4:3","3:2","4:5","5:4","21:9"]);background_form.addRow("Aspect ratio",e.aspect)
    motion=e.tool_pages["Motion"];row=QHBoxLayout();row.addWidget(QLabel('Motion Blur'));row.addStretch();e.motion_label=QLabel('None');row.addWidget(e.motion_label);motion.addLayout(row)
    e.motion=QSlider(Qt.Orientation.Horizontal);e.motion.setRange(0,3);e.motion.setPageStep(1);e.motion.setTickInterval(1);e.motion.setTickPosition(QSlider.TickPosition.TicksBelow);e.motion.setAccessibleName('Motion Blur intensity');motion.addWidget(e.motion)
    from .video_motion import AnimationChoice
    motion.addWidget(QLabel('Zoom animations'));e.zoom_animation=AnimationChoice();motion.addWidget(e.zoom_animation)
    def animation_changed(*_):
        from .motion_blur import LEVELS
        e.motion_label.setText(LEVELS[e.motion.value()]);e.motion.setAccessibleDescription(LEVELS[e.motion.value()])
        if not e.restoring_options:e.save_edits();e.refresh_preview()
    e.zoom_animation.currentTextChanged.connect(animation_changed)
    e.motion.valueChanged.connect(animation_changed)
    for label,slot in [("Smart zooms",e.auto_zoom),("Add zoom here",e.add_zoom),("Clear zooms",e.clear_zooms)]:motion.addWidget(button(label,slot))
    hint=QLabel("Click or drag in the zoom track to add a zoom. Select a segment to adjust its level and focus.");hint.setWordWrap(True);hint.setObjectName("muted");motion.addWidget(hint)
    trim=form("Trim");e.start=QDoubleSpinBox();e.end=QDoubleSpinBox()
    for control in (e.start,e.end):control.setRange(0,86400);control.setDecimals(2);control.setSuffix(" s")
    trim.addRow("From",e.start);trim.addRow("To (0 = end)",e.end)
    e.speed=choice(["0.5","1","1.5","2"],"1");trim.addRow("Speed",e.speed)
    for label,slot in [("Set trim start",lambda:e.start.setValue(e.player.position()/1000)),("Set trim end",lambda:e.end.setValue(e.player.position()/1000)),("Cut selected trim range",e.add_cut),("Clear cuts",e.clear_cuts)]:e.tool_pages["Trim"].addWidget(button(label,slot))
    audio=form("Audio")
    from .video_audio_tracks import TrackControls
    e.audio_mix=check("Mix audio tracks",bool(e.metadata.get("capture_options",{}).get("audio_sources")))
    audio.addRow(e.audio_mix);e.audio_tracks_controls=TrackControls(e);audio.addRow(e.audio_tracks_controls)
    e.audio_volume=integer(0,100,100,"%");audio.addRow("Volume",e.audio_volume)
    audio.addRow(e.volume)
    e.audio_muted=check("Mute audio");audio.addRow(e.audio_muted)
    e.audio_mono=check("Convert stereo to mono");audio.addRow(e.audio_mono)
    e.audio_track=choice([]);e.audio_track_label=QLabel("Preview track");audio.addRow(e.audio_track_label,e.audio_track)
    e.audio_track.setToolTip("Choose a track to listen to. Audio edits apply to every exported track.")
    e.audio_notice=QLabel();e.audio_notice.setWordWrap(True);e.tool_pages["Audio"].addWidget(e.audio_notice)
    hint=QLabel("Adjust each source, then export the mix. Original tracks stay in the editable project.");hint.setWordWrap(True);hint.setObjectName("muted");e.tool_pages["Audio"].addWidget(hint)
    e.volume.valueChanged.connect(e.audio_volume.setValue);e.audio_volume.valueChanged.connect(e.volume.setValue)
    def audio_changed(*_):
        if hasattr(e,"audio_preview"):e.audio_preview.update()
        if not e.restoring_options:e.save_edits()
    e.audio_mix.toggled.connect(audio_changed);e.audio_tracks_controls.changed.connect(audio_changed)
    e.audio_volume.valueChanged.connect(audio_changed);e.audio_muted.toggled.connect(audio_changed);e.audio_mono.toggled.connect(audio_changed)
    output=form("Export");e.size=choice(["Original","1920","1280","960","800","640","600","400"]);output.addRow("Width",e.size)
    is_gif=e.path.suffix.lower()==".gif"
    e.format=choice(["MP4","GIF"],"GIF" if is_gif else "MP4");output.addRow("Format",e.format);e.fps=integer(5,60,e.store.settings["gif_fps"] if is_gif else e.store.settings["fps"]);output.addRow("FPS",e.fps)
    gif_width=str(e.store.settings["gif_width"]) if e.store.settings["gif_width"] else "Original"
    if is_gif:e.size.setCurrentText(gif_width)
    e.gif_quality=integer(1,100,e.store.settings["gif_quality"],"%");output.addRow("GIF quality",e.gif_quality)
    e.gif_quality_label=output.labelForField(e.gif_quality)
    e.gif_optimize=check("Optimize GIFs",e.store.settings["gif_optimize"]);output.addRow(e.gif_optimize)
    e.hardware=check("Hardware export");output.addRow(e.hardware)
    for control,signal in ((e.fps,'valueChanged'),(e.speed,'currentTextChanged'),(e.start,'valueChanged')):
        getattr(control,signal).connect(lambda *_:e.refresh_preview() if not e.restoring_options else None)
    e.export_profiles={"MP4":(e.store.settings["fps"],"Original"),"GIF":(e.store.settings["gif_fps"],gif_width)};e.previous_export_format=e.format.currentText()
    def format_changed(value):
        if not getattr(e,"restoring_options",False):
            e.export_profiles[e.previous_export_format]=(e.fps.value(),e.size.currentText())
            fps,width=e.export_profiles[value];e.fps.setValue(fps);e.size.setCurrentText(width)
        e.previous_export_format=value
        if hasattr(e,"audio_preview"):e.audio_preview.update()
        e.gif_quality.setVisible(value=="GIF");output.labelForField(e.gif_quality).setVisible(value=="GIF");e.gif_optimize.setVisible(value=="GIF")
    e.format.currentTextChanged.connect(format_changed);format_changed(e.format.currentText())
    from .zoom_inspector import ZoomInspector
    e.zoom_inspector=ZoomInspector(e);e.inspector.addWidget(e.zoom_inspector)
    e.status=QLabel("Drag the trim handles or choose a tool to edit your recording.");e.status.setWordWrap(True);e.status.setObjectName("muted");layout.addWidget(e.status)
    progress_row=QHBoxLayout();e.progress=QProgressBar();e.progress.setRange(0,100);e.progress.hide();progress_row.addWidget(e.progress,1)
    e.export_progress.connect(e.progress.setValue);e.cancel_export=button("Cancel export",lambda:e.export_cancel.set() if e.export_cancel else None);e.cancel_export.hide();progress_row.addWidget(e.cancel_export);layout.addLayout(progress_row)


def populate_effects(e):
    from .video_styles import EffectsControls
    e.effect_controls={}
    for section,destination in [("Cursor","Cursor"),("Clicks","Cursor"),("Keystrokes","Keystrokes"),("Camera","Camera")]:
        opts=dict(e.styles);opts.setdefault('key_commands_only',e.metadata.get('capture_options',{}).get('commands_only',False))
        panel=EffectsControls(opts,e,section=section);e.effect_controls[section]=panel
        if section=="Clicks":
            e.tool_pages[destination].addWidget(QLabel("Clicks"));e.tool_pages[destination].addWidget(e.press_effect);e.tool_pages[destination].addWidget(e.show_clicks)
        e.tool_pages[destination].addWidget(panel)
        if section=='Cursor':
            panel.more_requested.connect(e.edit_effects)
            e.tool_pages[destination].addWidget(QLabel('Motion'));e.tool_pages[destination].addWidget(e.smoothing)
        if section=='Keystrokes' and e.metadata.get('capture_options',{}).get('commands_only'):
            note=QLabel('This recording contains only command shortcuts.');note.setWordWrap(True);note.setObjectName('muted');e.tool_pages[destination].addWidget(note)
        # Controls retain unrelated style values for the modal API. An inspector
        # only writes its own fields, so switching tools cannot restore old edits.
        keys={"Cursor":("cursor_",),"Clicks":("click_",),"Keystrokes":("key_",),"Camera":("camera_",)}[section]
        panel.changed.connect(lambda opts,prefixes=keys:change_effects(e,{k:v for k,v in opts.items() if k.startswith(prefixes) and k in panel_fields(prefixes)}))
    for page in ("Cursor","Keystrokes"):
        e.tool_pages[page].addWidget(button("Edit input events…",e.edit_input_events))
    e.tool_pages["Cursor"].addWidget(button("Effects…",e.edit_effects))
    for page in e.tool_pages.values():page.addStretch()


def panel_fields(prefixes):
    return {key for key in ("cursor_style","cursor_color","cursor_outline","click_style","click_color","click_size","click_duration","key_font","key_size","key_duration","key_color","key_background","key_position","key_style","key_commands_only","camera_radius","camera_mirror","camera_shadow","camera_shrink") if key.startswith(prefixes)}


def change_effects(e,options):
    e.styles.update(options);e.refresh_preview();e.save_edits()


def apply_background(e,name):
    from .backgrounds import PRESETS
    first,second=PRESETS[name] if name else ("#202633",None)
    e.styles.update(background2=second,background_image_data=None,radius=12 if name else 0,shadow=bool(name))
    e.bg_color.setText(first);e.padding.setValue(max(64,e.padding.value()) if name else 0)
    if not name:e.aspect.setCurrentText("Original")
    e.refresh_preview();e.save_edits()


def update_transport(e):
    def stamp(ms):
        seconds=max(0,ms//1000);return f"{seconds//60:02}:{seconds%60:02}"
    e.time_label.setText(f"{stamp(e.player.position())} / {stamp(e.player.duration())}")
    playing=e.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState
    e.play_button.setIcon(tool_icon('pause' if playing else 'play'))
    e.play_button.setAccessibleName("Pause" if playing else "Play");e.play_button.setToolTip("Pause" if playing else "Play")


def step_frame(e,direction):
    rate=e.player.metaData().value(QMediaMetaData.Key.VideoFrameRate)
    rate=float(rate) if rate and float(rate)>0 else 30
    e.player.pause();e.player.setPosition(max(0,min(e.player.duration(),e.player.position()+round(direction*1000/rate))))
