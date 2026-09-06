"""Annotation text presets and a shared wrapping layout for editing/export."""
import math
from pathlib import Path
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QFont,QFontDatabase,QTextDocument,QTextOption,QTextCursor,QTextCharFormat,QColor,QPen
from .controls import Choice

STYLES=('Standard','Rounded','Monospaced','Outlined','Boxed','Rounded Boxed','Monospaced Boxed')
_registered=False


def family(style):
    global _registered
    if not _registered:
        for path in (Path(__file__).parent/'data/fonts').glob('*.ttf'):QFontDatabase.addApplicationFont(str(path))
        _registered=True
    if style in ('Rounded','Rounded Boxed'):return 'Nunito'
    if style in ('Monospaced','Monospaced Boxed'):return 'Adwaita Mono'
    return 'Adwaita Sans'


def font_for(props):
    font=QFont(props.get('font_family') or family(props.get('text_style','Standard')),int(props.get('font_size',28)))
    font.setBold(props.get('bold',True));font.setItalic(props.get('italic',False));font.setUnderline(props.get('underline',False))
    if font.family()=='Nunito':font.setVariableAxis(QFont.Tag('wght'),700 if props.get('bold',True) else 400)
    return font


def document(props,color=None,outline=False):
    doc=QTextDocument();doc.setDocumentMargin(0);doc.setDefaultFont(font_for(props))
    option=QTextOption();option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere);doc.setDefaultTextOption(option)
    doc.setPlainText(props.get('text',''));doc.setTextWidth(max(1,props.get('w',300)-12))
    fmt=QTextCharFormat();fmt.setForeground(QColor(color or props.get('color','#ff5b61')))
    if outline and props.get('text_style')=='Outlined':fmt.setTextOutline(QPen(QColor('white'),max(2,props.get('font_size',28)*.15),Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    cursor=QTextCursor(doc);cursor.select(QTextCursor.SelectionType.Document);cursor.mergeCharFormat(fmt)
    return doc


def height(props):return math.ceil(document(props).size().height()+8)


def paint(obj,painter,color):
    p=obj.props;style=p.get('text_style');rect=QRectF(0,0,p.get('w',300),p.get('h',40))
    if style in ('Boxed','Rounded Boxed','Monospaced Boxed'):
        painter.setPen(Qt.PenStyle.NoPen)
        if style=='Monospaced Boxed':
            painter.setBrush(QColor(0,0,0,35));painter.drawRect(rect.translated(0,2));background=QColor('white')
        else:background=QColor(color);background.setAlpha(round(background.alpha()*.14))
        painter.setBrush(background)
        radius=rect.height()/2 if style=='Rounded Boxed' else 4 if style=='Boxed' else 0
        painter.drawRoundedRect(rect,radius,radius)
    key=(p.get('text',''),p.get('w',300),p.get('font_family'),p.get('font_size',28),p.get('bold',True),p.get('italic',False),p.get('underline',False),style,color.rgba())
    if getattr(obj,'text_layout_key',None)!=key:
        obj.text_layout=document(p,color,outline=True);obj.text_layout_key=key
        obj.text_fill=document({**p,'text_style':'Standard'},color) if style=='Outlined' else None
    painter.save();painter.translate(6,4);obj.text_layout.drawContents(painter)
    if obj.text_fill is not None:obj.text_fill.drawContents(painter)
    painter.restore()


class StyleChoice(Choice):
    def __init__(self):
        super().__init__()
        for style in STYLES:self.addItem(style,style)
    def style(self):return self.currentData()
    def set_style(self,style):
        index=self.findData(style)
        if index<0:
            while self.count()>len(STYLES):self.removeItem(self.count()-1)
            self.addItem(style.title()+' (legacy)',style);index=self.count()-1
        self.setCurrentIndex(index)
