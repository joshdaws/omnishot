"""Capture filename tokens and the local customization dialog."""
from datetime import datetime,timezone
import re
import uuid

DEFAULT_FORMAT="OmniShot %y-%m-%d at %H.%M.%S"
TOKENS=[("Year","%y"),("Month (numeric)","%m"),("Month (name)","%n"),("Day","%d"),("Day of week","%w"),("Window title","%t"),("App name","%a"),("Hour","%H"),("Minutes","%M"),("Seconds","%S"),("AM/PM","%p"),("Random characters","%r"),("Auto-increment","%i")]


def format_name(pattern=DEFAULT_FORMAT,*,created=None,utc=False,context=None,sequence=1,random_token=None,remove_illegal=True):
    when=datetime.fromtimestamp(created,tz=timezone.utc if utc else None) if created is not None else datetime.now(timezone.utc if utc else None)
    context=context or {}
    values={"y":when.strftime("%Y"),"m":when.strftime("%m"),"n":when.strftime("%B"),"d":when.strftime("%d"),"w":when.strftime("%A"),"H":when.strftime("%H"),"M":when.strftime("%M"),"S":when.strftime("%S"),"p":when.strftime("%p"),"t":context.get("title",""),"a":context.get("app",""),"r":random_token or uuid.uuid4().hex[:6],"i":str(sequence),"%":"%"}
    name=re.sub(r"%(.)",lambda m:str(values.get(m[1],m[0])),str(pattern)[:512])
    # Slashes and NUL can never be literal filename characters on Linux.
    name=name.replace("/","-").replace("\0","")
    if remove_illegal:name=re.sub(r'[<>:"\\|?*\x01-\x1f\x7f]',"",name)
    name=name.strip(" .")
    name=name.encode("utf-8")[:230].decode("utf-8",errors="ignore").rstrip(" .")
    return name or "OmniShot"


def scale_suffix(ratio):
    """Use the capture's actual density, including fractional Wayland scales."""
    import math
    try:ratio=float(ratio)
    except (TypeError,ValueError):return ""
    return f"@{ratio:.3g}x" if math.isfinite(ratio) and 1.001<ratio<=16 else ""


def customize(settings,parent=None):
    from PySide6.QtCore import Qt,QMimeData
    from PySide6.QtGui import QDrag
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QGridLayout,QPushButton,QCheckBox,QDialogButtonBox
    dialog=QDialog(parent);dialog.setWindowTitle("OmniShot — File Name Format");dialog.resize(650,530);layout=QVBoxLayout(dialog)
    label=QLabel("Type text and click or drag tokens to create a custom filename.");label.setWordWrap(True);layout.addWidget(label)
    pattern=QLineEdit(settings.get("filename_format",DEFAULT_FORMAT));pattern.setObjectName("filenameFormat");pattern.setMaxLength(512);layout.addWidget(pattern)
    preview=QLabel();preview.setObjectName("filenamePreview");preview.setTextFormat(Qt.TextFormat.PlainText);preview.setWordWrap(True);layout.addWidget(preview)
    grid=QGridLayout();layout.addLayout(grid);grid.setHorizontalSpacing(20)
    class Token(QPushButton):
        def mousePressEvent(self,event):self.origin=event.position().toPoint();super().mousePressEvent(event)
        def mouseMoveEvent(self,event):
            if event.buttons()&Qt.MouseButton.LeftButton and hasattr(self,"origin") and (event.position().toPoint()-self.origin).manhattanLength()>10:
                mime=QMimeData();mime.setText(self.text());drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.DropAction.CopyAction);self.setDown(False)
    for index,(name,token) in enumerate(TOKENS):
        row,column=index%7,(index//7)*2;grid.addWidget(QLabel(name),row,column)
        button=Token(token);button.setAccessibleName(name+" token");button.clicked.connect(lambda checked=False,text=token:pattern.insert(text));grid.addWidget(button,row,column+1)
    remove=QCheckBox("Remove illegal characters");remove.setChecked(settings.get("filename_remove_illegal",True));layout.addWidget(remove)
    utc=QCheckBox("Use UTC time zone");utc.setChecked(settings.get("filename_utc",False));layout.addWidget(utc)
    def update():preview.setText("Preview: "+format_name(pattern.text(),utc=utc.isChecked(),remove_illegal=remove.isChecked(),context=dict(title="Project notes",app="Text Editor"),sequence=settings.get("filename_counter",0)+1,random_token="a1b2c3")+".png")
    pattern.textChanged.connect(update);utc.toggled.connect(update);remove.toggled.connect(update);update()
    row=QHBoxLayout();restore=QPushButton("Restore Defaults");restore.clicked.connect(lambda:(pattern.setText(DEFAULT_FORMAT),remove.setChecked(True),utc.setChecked(False)));row.addWidget(restore);row.addStretch()
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);row.addWidget(buttons);layout.addLayout(row)
    result=dict(filename_format=pattern.text(),filename_utc=utc.isChecked(),filename_remove_illegal=remove.isChecked()) if dialog.exec() else None
    dialog.deleteLater();return result
