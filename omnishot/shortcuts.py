"""Manage only OmniShot's marked section of user-owned Hyprland Lua."""
from . import ui_scale as ui
import json
import os
from pathlib import Path
import re
import time
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog,QFormLayout,QKeySequenceEdit,QDialogButtonBox,QLabel,QMessageBox,QVBoxLayout,QScrollArea,QWidget
from . import backend

MARKER="-- OmniShot managed bindings"
END="-- End OmniShot managed bindings"
DEFAULTS={"menu":"Print","area":"Ctrl+Print","fullscreen":"Shift+Print","record":"Alt+Print","scroll":"Meta+Shift+Print","ocr":"Meta+Ctrl+Print"}
ACTIONS={"menu":"Capture menu","area":"Capture area","area-copy":"Capture area & copy","area-save":"Capture area & save","area-annotate":"Capture area & annotate","area-pin":"Capture area & pin","window":"Capture window","fullscreen":"Capture display","desktop":"Capture all displays","previous":"Previous area","scroll":"Scrolling capture","scroll-horizontal":"Horizontal scrolling","timer":"Self timer","ocr":"Capture text","ocr-lines":"Capture text with line breaks","ocr-single-line":"Capture text without line breaks","record":"Record screen","stop":"Stop recording","pause":"Pause recording","restart":"Restart recording","history":"Capture history","last-screenshot":"Annotate last screenshot","restore":"Restore preview","save-all":"Save all previews","close-all":"Close all previews","toggle-pins":"Hide/show pinned images","close-pins":"Close all pinned images","clipboard":"Annotate clipboard"}


def key_to_lua(sequence):
    value=sequence.toString(QKeySequence.SequenceFormat.PortableText)
    if not value:return ""
    if "," in value:raise ValueError("Global shortcuts must use one key combination")
    parts=value.split("+");key=parts[-1].upper();mods=[{"CTRL":"CTRL","SHIFT":"SHIFT","ALT":"ALT","META":"SUPER"}[s.upper()] for s in parts[:-1]]
    if not re.fullmatch(r"[A-Z0-9]|F(?:[1-9]|1[0-9]|2[0-4])|PRINT|SPACE|PAUSE|HOME|END|INSERT|DELETE",key):raise ValueError(f"Unsupported shortcut key: {key}")
    if not mods and not (key=="PRINT" or re.fullmatch(r"F\d+",key)):raise ValueError("Letter shortcuts need Ctrl, Alt, Shift, or Super")
    return " + ".join(mods+[key])


def replace_section(text,block):
    lines=text.splitlines(keepends=True)
    try:start=next(i for i,line in enumerate(lines) if line.rstrip()==MARKER)
    except StopIteration:return text.rstrip()+"\n\n"+block
    end=start+1
    while end<len(lines):
        if lines[end].rstrip()==END:end+=1;break
        if end+1<len(lines) and re.fullmatch(r'hl\.unbind\("[^"]+"\)\s*',lines[end]) and re.match(r'o\.bind\("[^"]+", "OmniShot ',lines[end+1]):end+=2
        else:break
    return "".join(lines[:start])+block+"".join(lines[end:])


def write_shortcuts(values,store):
    from .annotation_shortcuts import validate_pin
    validate_pin(store.settings.get('annotation_pin_shortcut',''),values)
    converted={command:key_to_lua(QKeySequence(value)) for command,value in values.items() if value}
    if len(set(converted.values()))!=len(converted):raise ValueError("Two OmniShot actions use the same shortcut")
    launcher=Path.home()/".local/bin/omnishot"
    if not launcher.exists():raise ValueError("Install OmniShot before changing global shortcuts")
    block=MARKER+"\n"
    for command,key in converted.items():
        block+=f'hl.unbind({json.dumps(key)})\no.bind({json.dumps(key)}, {json.dumps("OmniShot "+ACTIONS[command].lower())}, {json.dumps(str(launcher)+" "+command)})\n'
    block+=END+"\n"
    path=Path(os.environ.get("XDG_CONFIG_HOME",Path.home()/".config"))/"hypr/bindings.lua";original=path.read_text();updated=replace_section(original,block)
    backups=store.root/"config-backups";backups.mkdir(exist_ok=True);(backups/("bindings-"+time.strftime("%Y%m%d-%H%M%S")+".lua")).write_text(original)
    path.write_text(updated)
    try:
        backend.run(["hyprctl","reload"]);errors=backend.run(["hyprctl","configerrors"]).decode().strip()
        if errors:raise RuntimeError(errors)
    except Exception:
        path.write_text(original);backend.run(["hyprctl","reload"]);raise
    store.settings["shortcuts"]=values;store.save_settings()


class ShortcutsDialog(QDialog):
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store;self.setWindowTitle("Keyboard shortcuts");layout=QVBoxLayout(self);self.fields={}
        self.resize(620,min(720,self.screen().availableGeometry().height()-80));ui.set(self,"setMinimumSize",420,360)
        values=store.settings.get("shortcuts",DEFAULTS)
        help=QLabel("Click a field and press a shortcut. Clear it to disable.\nSuper is shown as Meta. Existing bindings on the chosen keys\nwill be replaced; the previous configuration is backed up.");help.setWordWrap(True);layout.addWidget(help)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame);content=QWidget();form=QFormLayout(content);scroll.setWidget(content);layout.addWidget(scroll,1)
        for command,label in ACTIONS.items():
            field=QKeySequenceEdit(QKeySequence(values.get(command,"")));field.setMaximumSequenceLength(1);self.fields[command]=field;form.addRow(label.replace('&','&&'),field)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject)
    def save(self):
        try:
            values={command:field.keySequence().toString(QKeySequence.SequenceFormat.PortableText) for command,field in self.fields.items()};write_shortcuts(values,self.store);self.accept()
        except Exception as exc:QMessageBox.warning(self,"Keyboard shortcuts",str(exc))
