"""Crop size popover, anchored like the annotation color panel."""
from .theme import color as theme_color
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPixmap,QPainter,QPainterPath,QColor,QPen,QIcon
from PySide6.QtWidgets import QWidget,QFormLayout,QSpinBox,QPushButton,QCheckBox,QStyle,QStyleOptionButton


class SnapCheckBox(QCheckBox):
    def paintEvent(self,event):
        super().paintEvent(event);option=QStyleOptionButton();self.initStyleOption(option)
        rect=QRectF(self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator,option,self)).adjusted(1,1,-1,-1)
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(QPen(theme_color("border"),1));p.setBrush(theme_color("accent") if self.isChecked() else Qt.BrushStyle.NoBrush);p.drawRoundedRect(rect,2,2)
        if self.isChecked():
            p.setPen(QPen(QColor('white'),1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));a=QPointF(rect.left()+rect.width()*.2,rect.center().y());b=QPointF(rect.left()+rect.width()*.43,rect.top()+rect.height()*.73);c=QPointF(rect.left()+rect.width()*.8,rect.top()+rect.height()*.25);p.drawLine(a,b);p.drawLine(b,c)


def fill_icon(color):
    pixmap=QPixmap(24,24);pixmap.fill(Qt.GlobalColor.transparent);p=QPainter(pixmap);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    circle=QPainterPath();circle.addEllipse(QRectF(3,3,18,18));p.setClipPath(circle)
    for y in range(0,24,4):
        for x in range(0,24,4):p.fillRect(x,y,4,4,QColor('#c4c8ce' if (x+y)//4%2 else '#7f8791'))
    p.fillPath(circle,color);p.setClipping(False);p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(theme_color("border"),1));p.drawPath(circle);p.end();return QIcon(pixmap)


def show_below(popup,button,editor):
    popup.adjustSize();position=button.mapToGlobal(button.rect().bottomLeft());bounds=editor.screen().availableGeometry()
    popup.move(max(bounds.left(),min(position.x(),bounds.right()-popup.width())),max(bounds.top(),min(position.y()+6,bounds.bottom()-popup.height())))
    popup.show()


class CropSizePopup(QWidget):
    def __init__(self,session):
        super().__init__(session.editor,Qt.WindowType.Popup|Qt.WindowType.FramelessWindowHint);self.session=session;self.setWindowTitle('OmniShot Crop Image Size')
        layout=QFormLayout(self);layout.setContentsMargins(14,14,14,14);self.dimensions=[]
        for index,label in enumerate(('Width','Height')):
            spin=QSpinBox();spin.setRange(2,100000);spin.setKeyboardTracking(False);spin.setSuffix(' px');spin.setFixedWidth(140);spin.setAccessibleName('Crop '+label.lower());layout.addRow(label,spin);self.dimensions.append(spin)
            spin.editingFinished.connect(lambda i=index:session.size_changed(i))
        self.done=QPushButton('Done');self.done.setObjectName('primary');self.done.clicked.connect(self.close);layout.addRow(self.done)
    def closeEvent(self,event):
        super().closeEvent(event)
        if self.session.editor.crop_session is self.session:self.session.editor.view.setFocus()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.close()
        else:super().keyPressEvent(event)
