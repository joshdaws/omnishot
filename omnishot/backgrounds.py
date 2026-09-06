"""Local background presets and a live, reversible image background editor."""
import base64
import copy
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel,
    QCheckBox,  QSpinBox, QPushButton, QFileDialog, QColorDialog,
    QDialogButtonBox, QInputDialog)
from .controls import Choice as QComboBox
from .images import load_image, IMAGE_FILTER

PRESETS = {
    "Lavender": ("#9f86ed", "#515dbb"), "Ocean": ("#46c7e7", "#184496"),
    "Sunset": ("#ffb56b", "#d65b94"), "Forest": ("#8ed7a4", "#245c60"),
    "Slate": ("#566176", "#202733"), "Cream": ("#f1e6d4", "#d6bca5"),
    "Rose": ("#f8c4d6", "#c56b91"), "Peach": ("#ffe0b6", "#f49891"),
    "Mint": ("#cef8dd", "#64afad"), "Indigo": ("#8994f0", "#33386d"),
    "Glacier": ("#e7f5ff", "#93b8d7"), "Dusk": ("#bc91c9", "#4b5a91"),
    "Citrus": ("#f6e5a0", "#d7af54"), "Coral": ("#ffaaa0", "#d56663"),
    "Sage": ("#d5ddc1", "#8a9d83"), "Sand": ("#eddbc0", "#ad927b"),
    "Midnight": ("#344465", "#111827"), "Lilac": ("#ebdfff", "#b7a4d9"),
    "White": ("#ffffff", "#ffffff"), "Black": ("#151515", "#151515"),
}


def default_background(store):
    name=store.settings.get("background_preset","None")
    if name in PRESETS:return {"color":PRESETS[name][0],"color2":PRESETS[name][1],"padding":64,"radius":12,"shadow":True,"aspect":"Auto","align":"Center"}
    return copy.deepcopy(store.settings.get("background_presets",{}).get(name))


class BackgroundDialog(QDialog):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor; self.setWindowTitle("Background"); self.resize(980,620)
        self.original = copy.deepcopy(editor.background)
        self.opts = copy.deepcopy(editor.background or {"color":"#9f86ed", "color2":"#515dbb", "padding":64, "radius":12, "shadow":True, "aspect":"Auto", "align":"Center"})
        layout=QHBoxLayout(self); self.preview=QLabel(); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMinimumSize(580,500); layout.addWidget(self.preview,1)
        panel=QVBoxLayout(); form=QFormLayout(); panel.addLayout(form); layout.addLayout(panel)
        self.enabled=QCheckBox("Add background");self.enabled.setChecked(True);form.addRow(self.enabled)
        self.presets=QComboBox();self.presets.addItem("Custom");self.presets.addItems(list(PRESETS)+list(editor.store.settings.get("background_presets",{})));form.addRow("Preset",self.presets)
        self.pad=QSpinBox();self.pad.setRange(0,600);form.addRow("Padding",self.pad)
        self.radius=QSpinBox();self.radius.setRange(0,200);form.addRow("Corners",self.radius)
        self.aspect=QComboBox();self.aspect.addItems(["Auto","1:1","16:9","9:16","4:3","3:2","4:5","5:4","21:9"]);form.addRow("Aspect",self.aspect)
        self.align=QComboBox();self.align.addItems(["Center","Top","Bottom","Left","Right","Top Left","Top Right","Bottom Left","Bottom Right"]);form.addRow("Alignment",self.align)
        self.shadow=QCheckBox("Drop shadow");form.addRow(self.shadow)
        for label,slot in [("First color…",lambda:self.color("color")),("Second color…",lambda:self.color("color2")),("Choose image…",self.image),("Auto balance",self.balance),("Save preset…",self.save_preset)]:
            button=QPushButton(label);button.clicked.connect(slot);form.addRow(button)
        panel.addStretch(); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);panel.addWidget(buttons);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        self.read_options()
        for widget in [self.pad,self.radius]:widget.valueChanged.connect(self.update_preview)
        for widget in [self.aspect,self.align]:widget.currentTextChanged.connect(self.update_preview)
        for widget in [self.shadow,self.enabled]:widget.toggled.connect(self.update_preview)
        self.presets.currentTextChanged.connect(self.select_preset);self.update_preview()

    def read_options(self):
        for widget in [self.pad,self.radius,self.aspect,self.align,self.shadow]:widget.blockSignals(True)
        self.pad.setValue(self.opts.get("padding",64));self.radius.setValue(self.opts.get("radius",12));self.aspect.setCurrentText(self.opts.get("aspect","Auto"));self.align.setCurrentText(self.opts.get("align","Center"));self.shadow.setChecked(self.opts.get("shadow",True))
        for widget in [self.pad,self.radius,self.aspect,self.align,self.shadow]:widget.blockSignals(False)

    def update_preview(self,*args):
        self.opts.update(padding=self.pad.value(),radius=self.radius.value(),aspect=self.aspect.currentText(),align=self.align.currentText(),shadow=self.shadow.isChecked())
        self.editor.background=self.opts if self.enabled.isChecked() else None
        rendered=self.editor.render(convert_srgb=True)
        self.preview.setPixmap(QPixmap.fromImage(rendered).scaled(640,550,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def select_preset(self,name):
        if name in PRESETS:
            self.opts.update(color=PRESETS[name][0],color2=PRESETS[name][1]);self.opts.pop("image",None);self.opts.pop("image_data",None)
        elif name in self.editor.store.settings.get("background_presets",{}):
            self.opts=copy.deepcopy(self.editor.store.settings["background_presets"][name]);self.read_options()
        self.enabled.setChecked(True);self.update_preview()

    def color(self,key):
        color=QColorDialog.getColor(QColor(self.opts[key]),self,"Background color")
        if color.isValid():
            self.opts[key]=color.name();self.opts.pop("image",None);self.opts.pop("image_data",None);self.presets.setCurrentIndex(0);self.update_preview()

    def image(self):
        path,_=QFileDialog.getOpenFileName(self,"Background image","",IMAGE_FILTER)
        if path:
            from .editor import png_bytes
            image=load_image(path)
            if not image.isNull():
                self.opts["image_data"]=base64.b64encode(png_bytes(image)).decode();self.opts.pop("image",None);self.presets.setCurrentIndex(0);self.update_preview()

    def balance(self):
        self.align.setCurrentText("Center");self.pad.setValue(round(min(self.editor.base.width(),self.editor.base.height())*.1));self.update_preview()

    def save_preset(self):
        name,ok=QInputDialog.getText(self,"Save background preset","Preset name")
        if ok and name.strip():
            name=name.strip();self.editor.store.settings.setdefault("background_presets",{})[name]=copy.deepcopy(self.opts);self.editor.store.save_settings()
            if self.presets.findText(name)<0:self.presets.addItem(name)
            self.presets.setCurrentText(name)

    def done(self,result):
        self.editor.background=copy.deepcopy(self.opts) if result==QDialog.DialogCode.Accepted and self.enabled.isChecked() else (None if result==QDialog.DialogCode.Accepted else self.original)
        if result==QDialog.DialogCode.Accepted:self.editor.commit()
        super().done(result)
