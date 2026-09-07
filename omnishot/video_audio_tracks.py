"""Source-specific audio controls and a shared preview/export mixing graph."""
from . import ui_scale as ui
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QCheckBox,QSlider,QSpinBox


def capture_audio_sources(options):
    sources=(["system"] if options.get("system") else [])+(["microphone"] if options.get("mic") else [])
    return sources if options.get("studio") or options.get("separate_audio") or len(sources)<2 else ["mixed"]


def default_track_edits(sources):
    return [dict(enabled=True,volume=100) for _ in sources]


def mix_graph(options,input_index=0,after=()):
    """Preserve each source's timeline and gain; never normalize a quiet source up."""
    rows=options['audio_tracks'];filters=[];labels=[]
    for i,row in enumerate(rows):
        if not row.get('enabled',True):continue
        gain=max(0,min(200,float(row.get('volume',100))))/100
        label=f'os_track_{i}';labels.append(f'[{label}]')
        filters.append(f'[{input_index}:a:{i}]aresample=48000:async=1:first_pts=0,volume={gain:g}[{label}]')
    if not labels:return None
    from .video_audio import audio_filters
    chain=[f'amix=inputs={len(labels)}:duration=longest:normalize=0',*after,*audio_filters(options)]
    filters.append(''.join(labels)+','.join(chain)+'[os_audio]')
    return ';'.join(filters)


def export_audio_args(options,input_index,after=()):
    if isinstance(options.get('audio_tracks'),list):
        graph=mix_graph(options,input_index,[*after,"apad"])
        args=['-filter_complex',graph,'-map','[os_audio]','-shortest'] if graph else ['-an']
    else:
        from .video_audio import audio_filters
        filters=[*after,*audio_filters(options)]
        args=['-map',f'{input_index}:a?']+(['-af',','.join(filters)] if filters else [])
    if options.get('audio_mono'):args+=['-ac','1']
    return args


class TrackControls(QWidget):
    changed=Signal()
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.saved=[];self.rows=[];self.signature=None
        self.layout=QVBoxLayout(self);ui.set(self.layout,"setContentsMargins",0,0,0,0);ui.set(self.layout,"setSpacing",14)

    def set_tracks(self,titles):
        if not titles and self.signature is None:return
        if tuple(titles)==self.signature:return
        saved=self.values();self.signature=tuple(titles)
        for row in self.rows:row[0].deleteLater()
        self.rows=[]
        sources=self.editor.metadata.get('capture_options',{}).get('audio_sources',[])
        names={'system':'System audio','microphone':'Microphone','mixed':'Recorded audio'}
        for index,title in enumerate(titles):
            label=names.get(sources[index]) if index<len(sources) else None
            label=label or title or f'Audio track {index+1}'
            opts=saved[index] if index<len(saved) else {}
            widget=QWidget();box=QVBoxLayout(widget);ui.set(box,"setContentsMargins",0,0,0,0);ui.set(box,"setSpacing",6)
            enabled=QCheckBox(label);enabled.setChecked(bool(opts.get('enabled',True)));box.addWidget(enabled)
            controls=QHBoxLayout();gain=QSlider(Qt.Orientation.Horizontal);gain.setRange(0,200);gain.setValue(round(opts.get('volume',100)))
            gain.setAccessibleName(label+' volume');gain.setToolTip('Double the source volume at 200%')
            value=QSpinBox();value.setRange(0,200);value.setSuffix('%');value.setValue(gain.value());ui.set(value,"setFixedWidth",80);value.setAccessibleName(label+' volume percent')
            controls.addWidget(gain,1);controls.addWidget(value);box.addLayout(controls)
            gain.valueChanged.connect(value.setValue);value.valueChanged.connect(gain.setValue)
            gain.valueChanged.connect(self.changed);enabled.toggled.connect(self.changed)
            self.rows.append((widget,enabled,gain,value))
            if index<len(sources) and sources[index]=="microphone":self.layout.insertWidget(0,widget)
            else:self.layout.addWidget(widget)

    def values(self):
        if self.signature is None:return self.saved
        return [dict(enabled=enabled.isChecked(),volume=gain.value()) for _,enabled,gain,_ in self.rows]
