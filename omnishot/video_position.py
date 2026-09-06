"""Nine-position inspector control and bounded camera placement."""
from PySide6.QtCore import Qt,Signal,QRectF
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QWidget,QGridLayout,QToolButton,QButtonGroup

POSITIONS=('Top Left','Top Center','Top Right','Center Left','Center','Center Right','Bottom Left','Bottom Center','Bottom Right')


class PositionButton(QToolButton):
    def __init__(self,index,grid):
        super().__init__(grid);self.index=index;self.grid=grid
        self.setCheckable(True);self.setFixedSize(38,30);self.setStyleSheet('padding:0;')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(POSITIONS[index]);self.setToolTip(POSITIONS[index])

    def paintEvent(self,event):
        super().paintEvent(event);p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor('white') if self.isChecked() else self.palette().buttonText().color();color.setAlpha(255 if self.isChecked() else 160)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(color)
        p.drawRoundedRect(QRectF(6+(self.index%3)*7,5+(self.index//3)*6,12,8),2,2);p.end()

    def keyPressEvent(self,event):
        row,col=divmod(self.index,3);key=event.key()
        if key in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down):
            col=max(0,min(2,col+(key==Qt.Key.Key_Right)-(key==Qt.Key.Key_Left)))
            row=max(0,min(2,row+(key==Qt.Key.Key_Down)-(key==Qt.Key.Key_Up)))
            button=self.grid.buttons[row*3+col];button.setFocus();button.click();event.accept();return
        super().keyPressEvent(event)


class PositionGrid(QWidget):
    currentTextChanged=Signal(str)

    def __init__(self,current='Bottom Right',parent=None):
        super().__init__(parent);self.group=QButtonGroup(self);self.buttons=[]
        layout=QGridLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        for i in range(9):
            button=PositionButton(i,self);self.buttons.append(button);self.group.addButton(button,i);layout.addWidget(button,i//3,i%3)
        self.setFixedSize(126,102);self.setCurrentText(current)
        self.group.idClicked.connect(lambda i:self.currentTextChanged.emit(POSITIONS[i]))

    def currentText(self):return POSITIONS[max(0,self.group.checkedId())]
    def setCurrentText(self,value):
        if value not in POSITIONS:return
        changed=self.group.checkedId()!=POSITIONS.index(value);self.buttons[POSITIONS.index(value)].setChecked(True)
        if changed:self.currentTextChanged.emit(value)


def camera_rect(width,height,aspect,options,zoom=1):
    if options.get('camera_fullscreen'):return QRectF(0,0,width,height)
    placement=options.get('camera_placement')
    if placement is not None:
        x,y,size=placement;size=max(1.,width*size)
        if options.get('camera_shrink'):size*=1-.15*min(1.,max(0.,zoom-1))
        ratio=1. if options.get('camera_shape','Circle') in ('Circle','Square') else max(.01,aspect)
        return QRectF(width*x,height*y,size,size*ratio)
    margin=min(20.,max(0.,(min(width,height)-2)/2))
    size=max(1.,width*max(.01,float(options.get('camera_size',.22))))
    if options.get('camera_shrink'):size*=1-.15*min(1.,max(0.,zoom-1))
    ratio=1. if options.get('camera_shape','Circle') in ('Circle','Square') else max(.01,aspect)
    size=min(size,width-2*margin,(height-2*margin)/ratio);camera_height=size*ratio
    position=options.get('camera_position','Bottom Right')
    x=margin if 'Left' in position else width-size-margin if 'Right' in position else (width-size)/2
    y=margin if 'Top' in position else height-camera_height-margin if 'Bottom' in position else (height-camera_height)/2
    return QRectF(x,y,size,camera_height)
