"""Recording presentation controls with reversible, live preview."""
import copy
from PySide6.QtCore import Signal,Qt,QSize,QAbstractTableModel,QModelIndex,QSignalBlocker
from PySide6.QtGui import QColor,QFont,QPixmap,QIcon
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QWidget,QTabWidget,QToolButton,
    QSpinBox,QDoubleSpinBox,QFontComboBox,QPushButton,QColorDialog,
    QDialogButtonBox,QCheckBox,QTableView,QHeaderView,QLabel)
from .controls import Choice as QComboBox
from .video_position import PositionGrid
from .video_keys import KeySize,KeyMode
from .video_cursor import CursorStyle


class EffectsControls(QWidget):
    changed=Signal(dict)
    more_requested=Signal()
    def __init__(self,options,parent=None,section=None):
        super().__init__(parent)
        self.original=copy.deepcopy(options);self.fields={};layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        tabs=QTabWidget() if section is None else None
        if tabs:layout.addWidget(tabs)
        pages={}
        for name in ("Cursor","Clicks","Keystrokes","Camera"):
            page=QWidget();pages[name]=QFormLayout(page)
            pages[name].setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            pages[name].setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            if section is not None:pages[name].setContentsMargins(0,0,0,0)
            if tabs:tabs.addTab(page,name)
            elif name==section:layout.addWidget(page)
            else:page.setParent(self);page.hide()
        def choice(page,key,label,choices,default):
            field=QComboBox();field.addItems(choices);field.setCurrentText(options.get(key,default));self.fields[key]=field;pages[page].addRow(label,field);field.currentTextChanged.connect(self.emit_changed)
        def number(page,key,label,low,high,default,decimal=False):
            field=QDoubleSpinBox() if decimal else QSpinBox();field.setRange(low,high);field.setValue(options.get(key,default));self.fields[key]=field;pages[page].addRow(label,field);field.valueChanged.connect(self.emit_changed)
        def color(page,key,label,default):
            field=QPushButton();field.setProperty("color",options.get(key,default));self.fields[key]=field;self.update_color(field);pages[page].addRow(label,field)
            def select():
                value=QColorDialog.getColor(QColor(field.property("color")),self,label,QColorDialog.ColorDialogOption.ShowAlphaChannel)
                if value.isValid():field.setProperty("color",value.name(QColor.NameFormat.HexArgb));self.update_color(field);self.emit_changed()
            field.clicked.connect(select)
        field=CursorStyle(options.get('cursor_style','Arrow'),compact=section=='Cursor');self.fields['cursor_style']=field
        header=QHBoxLayout();header.addWidget(QLabel('Style'));header.addStretch()
        if section=='Cursor':
            from .editor_toolbar import ToolIcon
            self.cursor_more=QToolButton();self.cursor_more.setIcon(QIcon(ToolIcon('more')));self.cursor_more.setIconSize(QSize(20,20));self.cursor_more.setStyleSheet('padding:0;');self.cursor_more.setAccessibleName('More cursor options');self.cursor_more.setToolTip('More cursor options');self.cursor_more.setFixedSize(28,24)
            self.cursor_more.clicked.connect(self.more_requested);header.addWidget(self.cursor_more)
        pages['Cursor'].addRow(header);pages['Cursor'].addRow(field);field.currentTextChanged.connect(self.emit_changed)
        color("Cursor","cursor_color","Fill","#161821");color("Cursor","cursor_outline","Outline","#ffffff")
        if section=='Cursor':
            for key in ('cursor_color','cursor_outline'):pages['Cursor'].setRowVisible(self.fields[key],False)
        self.sync_cursor_colors()
        choice("Clicks","click_style","Style",["ring","filled"],"ring");color("Clicks","click_color","Color","#ff6565")
        number("Clicks","click_size","Radius",6,100,24);number("Clicks","click_duration","Duration (seconds)",.1,3,.5,True)
        field=KeySize(options.get('key_size',20));self.fields['key_size']=field;pages['Keystrokes'].addRow('Size',field);field.valueChanged.connect(self.emit_changed)
        choice('Keystrokes','key_style','Style',['Dark','Light','Custom'],'Custom' if 'key_color' in options or 'key_background' in options else 'Dark')
        field=PositionGrid(options.get('key_position','Bottom Center'));self.fields['key_position']=field;pages['Keystrokes'].addRow('Position',field);field.currentTextChanged.connect(self.emit_changed)
        field=KeyMode(options.get('key_commands_only',False));self.fields['key_commands_only']=field;pages['Keystrokes'].addRow('Options',field);field.toggled.connect(self.emit_changed)
        advanced=QWidget();advanced_form=QFormLayout(advanced);advanced_form.setContentsMargins(0,0,0,0);advanced_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        more=QPushButton('More options');more.setCheckable(True);more.toggled.connect(advanced.setVisible);pages['Keystrokes'].addRow(more);pages['Keystrokes'].addRow(advanced);advanced.hide();pages['Keystrokes']=advanced_form
        field=QFontComboBox();field.setMinimumContentsLength(10);field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        field.setCurrentFont(QFont(options.get("key_font","sans-serif")));self.fields["key_font"]=field;pages["Keystrokes"].addRow("Font",field);field.currentFontChanged.connect(self.emit_changed)
        number("Keystrokes","key_duration","Duration (seconds)",.2,5,1.3,True)
        color("Keystrokes","key_color","Text","#ffffff");color("Keystrokes","key_background","Background","#d7141720")
        def custom_colors(*_):
            for key in ('key_color','key_background'):self.fields[key].setEnabled(self.fields['key_style'].currentText()=='Custom')
        self.fields['key_style'].currentTextChanged.connect(custom_colors);custom_colors()
        number("Camera","camera_radius","Rounded corners",0,100,18)
        for key,label,default in [("camera_mirror","Flip camera",False),("camera_shrink","Shrink camera on zoom",False),("camera_shadow","Camera shadow",True)]:
            field=QCheckBox(label);field.setChecked(options.get(key,default));self.fields[key]=field;pages["Camera"].addRow(field);field.toggled.connect(self.emit_changed)
        self.defaults=self.options()
    def update_color(self,field):
        value=field.property("color");field.setText(value)
        swatch=QPixmap(20,20);swatch.fill(QColor(value));field.setIcon(QIcon(swatch))
    def options(self):
        result=copy.deepcopy(self.original)
        for key,field in self.fields.items():
            if isinstance(field,QFontComboBox):value=field.currentFont().family()
            elif isinstance(field,(QComboBox,PositionGrid,CursorStyle)):value=field.currentText()
            elif isinstance(field,(QCheckBox,KeyMode)):value=field.isChecked()
            elif isinstance(field,(QSpinBox,QDoubleSpinBox,KeySize)):value=field.value()
            else:value=field.property("color")
            result[key]=value
        return result
    def sync_cursor_colors(self):
        self.fields['cursor_style'].set_colors(self.fields['cursor_color'].property('color'),self.fields['cursor_outline'].property('color'))
    def emit_changed(self,*args):self.sync_cursor_colors();self.changed.emit(self.options())
    def set_options(self,options):
        self.original=copy.deepcopy(options)
        for key,field in self.fields.items():
            if key not in options:continue
            value=options[key]
            with QSignalBlocker(field):
                if isinstance(field,QFontComboBox):field.setCurrentFont(QFont(value))
                elif isinstance(field,(QComboBox,PositionGrid,CursorStyle)):field.setCurrentText(value)
                elif isinstance(field,(QCheckBox,KeyMode)):field.setChecked(bool(value))
                elif isinstance(field,(QSpinBox,QDoubleSpinBox,KeySize)):field.setValue(value)
                else:field.setProperty("color",value);self.update_color(field)
        self.sync_cursor_colors()
        for key in ('key_color','key_background'):self.fields[key].setEnabled(self.fields['key_style'].currentText()=='Custom')


class EffectsDialog(QDialog):
    changed=Signal(dict)
    def __init__(self,options,parent=None):
        super().__init__(parent);self.setWindowTitle("Recording effects");self.resize(420,410)
        layout=QVBoxLayout(self);self.controls=EffectsControls(options,self);layout.addWidget(self.controls)
        self.fields=self.controls.fields;self.controls.changed.connect(self.changed)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def options(self):return self.controls.options()


class VideoBackground(QWidget):
    """Adapt the shared background picker to a paused video frame."""
    def __init__(self,editor):
        from .editor import qimage
        super().__init__(editor);self.editor=editor;self.store=editor.store;self.base=qimage(editor.last_frame)
        opts=editor.studio_options();self.background={"color":opts["background"],"color2":opts.get("background2",opts["background"]),"padding":opts["padding"],"radius":opts.get("radius",12),"shadow":opts.get("shadow",True),"aspect":"Auto" if opts["aspect"]=="Original" else opts["aspect"],"align":opts.get("align","Center")}
        if opts.get("background_image_data"):self.background["image_data"]=opts["background_image_data"]
    def render(self):
        from .studio import compose_frame
        return compose_frame(self.editor.last_frame,self.editor.player.position()/1000,self.editor.metadata,{**self.editor.studio_options(),**self.convert(self.background)},self.editor.last_camera)
    @staticmethod
    def convert(bg):
        if not bg:return {"background":"#202633","background2":None,"padding":0,"radius":0,"shadow":False,"aspect":"Original","align":"Center","background_image_data":None}
        return {"background":bg["color"],"background2":bg.get("color2",bg["color"]),"padding":bg["padding"],"radius":bg["radius"],"shadow":bg["shadow"],"aspect":"Original" if bg["aspect"]=="Auto" else bg["aspect"],"align":bg["align"],"background_image_data":bg.get("image_data")}
    def commit(self):
        opts=self.convert(self.background);self.editor.styles.update(opts);self.editor.padding.setValue(opts["padding"]);self.editor.bg_color.setText(opts["background"]);self.editor.aspect.setCurrentText(opts["aspect"]);self.editor.save_edits();self.editor.refresh_preview()


class InputEventsModel(QAbstractTableModel):
    def __init__(self,events,edits,duration,parent=None):
        super().__init__(parent);self.events=events;self.edits=copy.deepcopy(edits);self.duration=duration
        self.rows=[i for i,e in enumerate(events) if e.get("kind")=="click" or e.get("kind")=="key" and e.get("state")==1 and e.get("label")]
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else 4
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if orientation==Qt.Orientation.Horizontal and role==Qt.ItemDataRole.DisplayRole:return ["Show","Time (seconds)","Type","Keystroke label"][section]
        return super().headerData(section,orientation,role)
    def event(self,row):
        i=self.rows[row];return {**self.events[i],**self.edits.get(str(i),{})}
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        event=self.event(index.row());column=index.column()
        if column==0 and role==Qt.ItemDataRole.CheckStateRole:return Qt.CheckState.Unchecked if event.get("hidden") else Qt.CheckState.Checked
        if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.EditRole):
            return [None,round(event["t"],3),"Click" if event["kind"]=="click" else "Keystroke",event.get("label","")][column]
    def flags(self,index):
        flags=super().flags(index)
        if index.column()==0:flags|=Qt.ItemFlag.ItemIsUserCheckable
        elif index.column()==1 or index.column()==3 and self.event(index.row())["kind"]=="key":flags|=Qt.ItemFlag.ItemIsEditable
        return flags
    def setData(self,index,value,role=Qt.ItemDataRole.EditRole):
        if not index.isValid():return False
        column=index.column();key=None
        if column==0 and role==Qt.ItemDataRole.CheckStateRole:key="hidden";value=value!=Qt.CheckState.Checked.value
        elif column==1 and role==Qt.ItemDataRole.EditRole:
            try:value=float(value)
            except (TypeError,ValueError):return False
            if not 0<=value<=self.duration:return False
            key="t"
        elif column==3 and role==Qt.ItemDataRole.EditRole and self.event(index.row())["kind"]=="key":key="label";value=str(value)[:200]
        if key is None:return False
        self.edits.setdefault(str(self.rows[index.row()]),{})[key]=value;self.dataChanged.emit(index,index);return True
    def reset_edits(self):self.beginResetModel();self.edits={};self.endResetModel()


class InputEventsDialog(QDialog):
    def __init__(self,editor):
        super().__init__(editor);self.setWindowTitle("Edit clicks and keystrokes");self.resize(690,470)
        layout=QVBoxLayout(self);layout.addWidget(QLabel("Hide an event or edit its time and label. The original input track is preserved."))
        self.model=InputEventsModel(editor.metadata.get("events",[]),editor.styles.get("event_edits",{}),editor.player.duration()/1000,self)
        table=QTableView();table.setModel(self.model);table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch);table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows);layout.addWidget(table)
        table.clicked.connect(lambda index:editor.player.setPosition(round(self.model.event(index.row())["t"]*1000)))
        reset=QPushButton("Restore original events");reset.clicked.connect(self.model.reset_edits);layout.addWidget(reset)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
