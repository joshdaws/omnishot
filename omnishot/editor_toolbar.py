"""Annotation tool groups and direct manipulation of the rendered capture."""
from PySide6.QtCore import Qt,QRectF,QPointF,QSize
from PySide6.QtGui import QIcon,QIconEngine,QPainter,QPen,QPolygonF,QPixmap,QAction
from PySide6.QtWidgets import QToolBar,QToolButton,QPushButton,QMenu,QWidget,QSizePolicy,QApplication
from .theme import color

TOOLS=(('select','Select','V'),('rect','Rectangle','R'),('fill','Filled rectangle','F'),
       ('ellipse','Ellipse','E'),('line','Line','L'),('arrow','Arrow','A'),('text','Text','T'),
       ('pixelate','Pixelate','X'),('blur','Blur','B'),('redact','Black Out','D'),
       ('spotlight','Spotlight','S'),('counter','Counter','N'),('pencil','Pencil','P'),('highlight','Highlighter','H'))
HIDDEN_TOOLS=('pixelate','blur','redact')


class ToolIcon(QIconEngine):
    def __init__(self,name):super().__init__();self.name=name
    def clone(self):return ToolIcon(self.name)
    def pixmap(self,size,mode,state):
        pix=QPixmap(size);pix.fill(Qt.GlobalColor.transparent);p=QPainter(pix);self.paint(p,QRectF(pix.rect()),mode,state);p.end();return pix
    def paint(self,p,r,mode,state):
        p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing);p.translate(r.x(),r.y());p.scale(r.width()/24,r.height()/24)
        ink=color('muted' if mode==QIcon.Mode.Disabled else 'on_accent' if state==QIcon.State.On else 'foreground')
        p.setPen(QPen(ink,1.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin));p.setBrush(Qt.BrushStyle.NoBrush);n=self.name
        if n=='crop':
            p.drawLine(7,3,7,17);p.drawLine(7,17,21,17);p.drawLine(3,7,17,7);p.drawLine(17,7,17,21)
        elif n in ('insert','background'):
            p.drawRoundedRect(QRectF(3,4,18,16),2,2);p.drawEllipse(QRectF(6,7,3,3));p.drawPolyline(QPolygonF([QPointF(4,17),QPointF(10,12),QPointF(13,15),QPointF(16,11),QPointF(20,16)]))
            if n=='insert':p.fillRect(14,14,10,10,color('surface'));p.drawLine(19,15,19,23);p.drawLine(15,19,23,19)
        elif n=='select':
            p.setBrush(ink);p.drawPolygon(QPolygonF([QPointF(5,3),QPointF(19,13),QPointF(12,14),QPointF(9,21)]))
        elif n in ('rect','fill','redact'):
            if n!='rect':p.setBrush(ink)
            p.drawRect(QRectF(4,9 if n=='redact' else 5,16,6 if n=='redact' else 14))
        elif n=='ellipse':p.drawEllipse(QRectF(4,4,16,16))
        elif n in ('line','arrow'):
            p.drawLine(5,19,19,5)
            if n=='arrow':p.drawLine(10,5,19,5);p.drawLine(19,5,19,14)
        elif n=='text':p.drawLine(5,5,19,5);p.drawLine(12,5,12,20);p.drawLine(8,20,16,20)
        elif n in ('pixelate','blur'):
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(ink)
            for x in range(3):
                for y in range(3):
                    if n=='pixelate':
                        if (x+y)%2==0:p.drawRect(QRectF(4+x*5,4+y*5,5,5))
                    else:p.drawEllipse(QRectF(5+x*5,5+y*5,2,2))
        elif n=='spotlight':p.drawRoundedRect(QRectF(3,4,18,16),2,2);p.drawRect(QRectF(7,8,10,8))
        elif n=='counter':
            p.setBrush(ink);p.drawEllipse(QRectF(4,4,16,16));p.setPen(color('accent' if state==QIcon.State.On else 'surface'));p.drawLine(11,8,13,7);p.drawLine(13,7,13,17)
        elif n in ('pencil','highlight'):
            p.drawPolygon(QPolygonF([QPointF(5,19),QPointF(6,14),QPointF(15,5),QPointF(19,9),QPointF(10,18)]));p.drawLine(13,7,17,11)
            if n=='highlight':p.drawLine(4,21,20,21)
        elif n=='copy':p.drawRoundedRect(QRectF(7,7,13,14),2,2);p.drawLine(4,17,4,3);p.drawLine(4,3,16,3)
        elif n=='trash':
            p.drawLine(4,6,20,6);p.drawRoundedRect(QRectF(6,6,12,15),2,2);p.drawLine(9,3,15,3);p.drawLine(9,3,9,6);p.drawLine(15,3,15,6);p.drawLine(10,10,10,17);p.drawLine(14,10,14,17)
        elif n=='pin':
            p.drawPolygon(QPolygonF([QPointF(10,3),QPointF(21,14),QPointF(17,14),QPointF(13,18),QPointF(6,11),QPointF(10,7)]));p.drawLine(9,15,3,21)
        elif n=='more':
            p.setBrush(ink)
            for x in (5,12,19):p.drawEllipse(QRectF(x-1,11,2,2))
        elif n in ('lock','unlock'):
            p.drawRoundedRect(QRectF(5,11,14,10),2,2)
            p.drawArc(QRectF(8,3,8,12),0 if n=='lock' else 30*16,180*16 if n=='lock' else 150*16)
            p.drawLine(12,15,12,17)
        elif n=='cursor-click':
            p.setBrush(ink);p.drawPolygon(QPolygonF([QPointF(10,9),QPointF(20,14),QPointF(16,16),QPointF(14,21)]))
            for x,y,u,v in [(9,2,9,5),(3,4,5,6),(2,10,5,10),(4,16,6,14),(14,4,12,6)]:p.drawLine(x,y,u,v)
        elif n=='keyboard':
            p.drawRoundedRect(QRectF(2,5,20,14),2,2)
            for y in (9,12):
                for x in (6,10,14,18):p.drawPoint(x,y)
            p.drawLine(7,16,17,16)
        elif n in ('volume','mute'):
            p.setBrush(ink);p.drawPolygon(QPolygonF([QPointF(3,9),QPointF(7,9),QPointF(12,5),QPointF(12,19),QPointF(7,15),QPointF(3,15)]));p.setBrush(Qt.BrushStyle.NoBrush)
            if n=='mute':p.drawLine(16,9,21,15);p.drawLine(16,15,21,9)
            else:p.drawArc(QRectF(10,7,9,10),-65*16,130*16);p.drawArc(QRectF(9,3,14,18),-55*16,110*16)
        elif n=='camera':
            p.setBrush(ink);p.drawRoundedRect(QRectF(2,6,13,12),2,2)
            p.drawPolygon(QPolygonF([QPointF(17,10),QPointF(22,7),QPointF(22,17),QPointF(17,14)]))
        elif n=='motion':
            p.setBrush(ink);p.drawEllipse(QRectF(10,6,12,12));p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(6,6,9,12),90*16,180*16);p.drawArc(QRectF(2,8,7,8),90*16,180*16)
        elif n=='cut':
            p.drawEllipse(QRectF(3,3,6,6));p.drawEllipse(QRectF(3,15,6,6));p.drawLine(8,8,21,19);p.drawLine(8,16,21,5)
        elif n=='export':
            p.drawLine(4,14,4,21);p.drawLine(4,21,20,21);p.drawLine(20,21,20,14)
            p.drawLine(12,3,12,16);p.drawLine(7,8,12,3);p.drawLine(12,3,17,8)
        elif n in ('play','pause','previous','next'):
            p.setBrush(ink);p.setPen(Qt.PenStyle.NoPen)
            if n=='pause':p.drawRoundedRect(QRectF(6,4,4,16),1,1);p.drawRoundedRect(QRectF(14,4,4,16),1,1)
            else:
                if n=='previous':p.translate(24,0);p.scale(-1,1)
                p.drawPolygon(QPolygonF([QPointF(6,4),QPointF(19,12),QPointF(6,20)]))
                if n!='play':p.drawRoundedRect(QRectF(19,4,3,16),1,1)
        elif n in ('undo','redo'):
            if n=='redo':p.translate(24,0);p.scale(-1,1)
            p.drawArc(QRectF(5,6,15,14),-60*16,235*16);p.drawLine(4,4,4,11);p.drawLine(4,11,11,11)
        elif n=='expand':
            for x,y,dx,dy in [(3,3,1,1),(21,3,-1,1),(3,21,1,-1),(21,21,-1,-1)]:
                p.drawLine(x,y,x+dx*6,y);p.drawLine(x,y,x,y+dy*6)
        p.restore()


def icon(name):return QIcon(ToolIcon(name))


class DragHandle(QPushButton):
    def __init__(self,editor):
        super().__init__('⋮  Drag Me  ⋮');self.editor=editor;self.origin=None
        self.setAccessibleName('Drag Me');self.setToolTip('Drag the annotated image into another app. Hold Alt to keep the editor open.')
        self.setCursor(Qt.CursorShape.OpenHandCursor);self.setFixedWidth(132);self.setStyleSheet('QPushButton { border-radius:14px; padding:4px 12px; }')
    def mousePressEvent(self,event):
        self.origin=event.position().toPoint() if event.button()==Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.origin is not None and event.buttons()&Qt.MouseButton.LeftButton and (event.position().toPoint()-self.origin).manhattanLength()>=QApplication.startDragDistance():
            self.origin=None;self.setDown(False);self.editor.drag_image();event.accept();return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):self.origin=None;super().mouseReleaseEvent(event)


def tools(editor):
    e=editor;e.toolbar=QToolBar('Annotation tools');e.toolbar.setMovable(False);e.toolbar.setIconSize(QSize(20,20));e.addToolBar(e.toolbar)
    e.toolbar.setStyleSheet('QToolBar { spacing:2px; padding:8px; } QToolButton { border:0; background:transparent; padding:5px; border-radius:12px; } QToolButton:hover { background:palette(light); } QToolButton:checked { background:palette(highlight); color:palette(highlighted-text); } QSpinBox { padding:3px; }')
    e.tools={};crop=QAction(icon('crop'),'Crop',e);crop.setCheckable(True);crop.setToolTip('Crop (C)');crop.triggered.connect(lambda:e.set_tool('crop'));e.tools['crop']=crop;e.toolbar.addAction(crop)
    e.insert_action=e.toolbar.addAction(icon('insert'),'Insert image…',e.insert_dialog);e.background_action=e.toolbar.addAction(icon('background'),'Background…',e.background_dialog);e.toolbar.addSeparator()
    for key,label,shortcut in TOOLS:
        action=QAction(icon(key),label,e);action.setCheckable(True);action.setToolTip(f'{label} ({shortcut})');action.triggered.connect(lambda checked=False,k=key:e.set_tool(k));e.tools[key]=action
        if key=='highlight':action.setToolTip('Highlighter (H) · Hold Ctrl to bypass text snapping')
        if key=='pixelate':
            e.hide_button=QToolButton();e.hide_button.setIconSize(QSize(20,20));e.hide_button.setMinimumWidth(42);e.hide_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            e.hide_button.setStyleSheet('QToolButton { padding-right:16px; } QToolButton::menu-button { width:14px; border:0; background:transparent; }')
            e.hide_menu=QMenu(e.hide_button);e.hide_button.setMenu(e.hide_menu);e.toolbar.addWidget(e.hide_button)
        if key not in HIDDEN_TOOLS:e.toolbar.addAction(action)
    for key in HIDDEN_TOOLS:e.hide_menu.addAction(e.tools[key])
    e.hide_button.setDefaultAction(e.tools['pixelate']);e.hide_button.setAccessibleName('Hide content');e.toolbar.addSeparator()


def finish(editor):
    e=editor;spacer=QWidget();spacer.setStyleSheet('background:transparent');spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);e.toolbar.addWidget(spacer)
    e.save_button=QPushButton('Save as…');e.save_button.setObjectName('primary');e.save_button.setToolTip('Save image (Ctrl+S). Hold Alt to save directly to your capture folder and keep editing.');e.save_button.clicked.connect(e.save_image);e.toolbar.addWidget(e.save_button)
    e.bottom_toolbar=QToolBar('View actions');e.bottom_toolbar.setMovable(False);e.addToolBar(Qt.ToolBarArea.BottomToolBarArea,e.bottom_toolbar)
    bar=e.bottom_toolbar;container=QWidget();container.setStyleSheet('background:transparent');from PySide6.QtWidgets import QHBoxLayout
    layout=QHBoxLayout(container);layout.setContentsMargins(0,0,0,0);left=QWidget();left_layout=QHBoxLayout(left);left_layout.setContentsMargins(0,0,0,0)
    e.zoom_button=QToolButton();e.zoom_button.setText('100%');e.zoom_button.setAccessibleName('Image zoom');e.zoom_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);menu=QMenu(e.zoom_button)
    menu.addAction('Fit to Window',e.fit);menu.addSeparator()
    for percent in (25,50,100,200,400,800):menu.addAction(f'{percent}%',lambda checked=False,value=percent:e.zoom_to(value))
    e.zoom_button.setMenu(menu);left_layout.addWidget(e.zoom_button);left_layout.addStretch()
    e.drag_handle=DragHandle(e);right=QWidget();right_layout=QHBoxLayout(right);right_layout.setContentsMargins(0,0,0,0);right_layout.addStretch()
    e.operations_button=QToolButton();e.operations_button.setIcon(icon('more'));e.operations_button.setAccessibleName('Image actions');e.operations_button.setToolTip('Image actions');e.operations_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);operations=QMenu(e.operations_button)
    for label,slot in [('Rotate clockwise',e.rotate),('Flip horizontally',e.flip),('Resize…',e.resize_image),('Combine images…',e.combine_dialog),('Text / QR',e.extract_text),('Print…',e.print_image)]:operations.addAction(label,slot)
    e.operations_button.setMenu(operations);right_layout.addWidget(e.operations_button)
    for key,label,slot in [('pin','Pin',e.pin),('copy','Copy',e.copy_image)]:
        button=QToolButton();button.setIcon(icon(key));button.setAccessibleName(label);button.setToolTip(label);button.clicked.connect(slot);right_layout.addWidget(button);setattr(e,key+'_button',button)
    layout.addWidget(left,1);layout.addWidget(e.drag_handle);layout.addWidget(right,1);container.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);bar.addWidget(container)


def properties(e,kind):
    e.spotlight_action.setVisible(kind=='spotlight')
    e.width_action.setVisible(kind in ('arrow','line','rect','ellipse','pencil','highlight'))
    e.color_action.setVisible(kind not in ('image','blur','pixelate','redact','spotlight'))
    e.arrow_style_action.setVisible(kind=='arrow');e.text_style_action.setVisible(kind=='text');e.font_size_action.setVisible(kind in ('text','counter'))
    e.effect_strength_action.setVisible(kind in ('blur','pixelate'));e.blur_mode_action.setVisible(kind=='blur');e.pixelate_mode_action.setVisible(kind=='pixelate')
    e.counter_style_action.setVisible(kind=='counter');e.counter_number_action.setVisible(kind=='counter' and e.view.tool!='select')
