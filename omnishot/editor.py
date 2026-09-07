from __future__ import annotations
from . import ui_scale as ui
from .theme import color as theme_color
import base64
import copy
import json
import math
import secrets
from pathlib import Path
import zipfile
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, QSize, QBuffer, QIODevice, QMimeData, QUrl, Signal, QTimer
from PySide6.QtGui import (QImage, QPixmap, QPainter, QPen, QColor, QBrush, QFont,
    QPainterPath,QPainterPathStroker, QPolygonF, QAction, QKeySequence, QDrag, QLinearGradient, QShortcut, QTransform,QFontMetricsF)
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
    QGraphicsView, QGraphicsScene, QGraphicsObject, QGraphicsItem, QGraphicsPixmapItem, QGraphicsTextItem, QFontDialog,
    QFileDialog, QInputDialog, QMessageBox,  QSpinBox, QLabel, QPushButton,
    QDialog, QFormLayout, QDialogButtonBox, QSlider, QCheckBox, QApplication, QSizePolicy, QMenu,QGraphicsDropShadowEffect,QGraphicsEffect,QGraphicsRectItem)
from PIL import Image
import numpy as np
from .controls import Choice as QComboBox
from . import text_styles
from . import backend
from .rounded_corners import rounded_path
from .images import load_image, save_image as export_image, IMAGE_FILTER,convert_image,convert_color,image_color_space


def qimage(array):
    a=np.ascontiguousarray(array)
    fmt=QImage.Format.Format_RGBA8888 if a.ndim==3 and a.shape[2]==4 else QImage.Format.Format_RGB888
    return QImage(a.data,a.shape[1],a.shape[0],a.strides[0],fmt).copy()


def png_bytes(image):
    buf=QBuffer();buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buf,"PNG"):raise OSError("Could not encode the image")
    return bytes(buf.data())


def error(parent, exception): QMessageBox.warning(parent,"OmniShot",str(exception))


def text_height(props):
    if props.get('text_style') in text_styles.STYLES:return text_styles.height(props)
    font=QFont(props.get("font_family","Inter"),int(props.get("font_size",28)));font.setBold(props.get("bold",True));font.setItalic(props.get("italic",False))
    bounds=QFontMetricsF(font).boundingRect(QRectF(0,0,max(1,props.get("w",300)-12),100000),Qt.TextFlag.TextWordWrap,props.get("text",""))
    return math.ceil(bounds.height()+8)


class InlineText(QGraphicsTextItem):
    def __init__(self,annotation):
        super().__init__(annotation);self.annotation=annotation;self.active=True;self.original=annotation.props.get("text","")
        p=annotation.props;self.setPlainText(self.original);font=QFont(p.get("font_family","Inter"),int(p.get("font_size",28)));font.setBold(p.get("bold",True));font.setItalic(p.get("italic",False));self.setFont(font)
        self.setDefaultTextColor(QColor(p.get("color","#ff5b61")));self.setPos(2,0);self.setTextWidth(max(150,p.get("w",240)-4));self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        if p.get('text_style') in text_styles.STYLES:
            self.setDocument(text_styles.document(p));self.setPos(6,4);self.setTextWidth(max(1,p.get('w',300)-12))
        editor=annotation.editor;self.disabled=[]
        from .annotation_shortcuts import available_while_typing
        for action in editor.findChildren(QShortcut)+[a for a in editor.findChildren(QAction) if not a.shortcut().isEmpty()]:
            if action is editor.pin_shortcut and available_while_typing(action.key()):continue
            self.disabled.append((action,action.isEnabled()));action.setEnabled(False)
        self.setFocus(Qt.FocusReason.MouseFocusReason);cursor=self.textCursor();cursor.select(cursor.SelectionType.Document);self.setTextCursor(cursor)
    def finish(self,cancel=False):
        if not self.active:return
        self.active=False;obj=self.annotation;editor=obj.editor;obj.prepareGeometryChange()
        obj.props["text"]=self.original if cancel else self.toPlainText();obj.props["h"]=max(40,self.document().size().height()+8)
        obj.inline=None;editor.inline=None
        for action,enabled in self.disabled:action.setEnabled(enabled)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction);self.hide();self.setParentItem(None);editor.scene.removeItem(self);self.deleteLater();obj.update();editor.commit()
    def focusOutEvent(self,event):
        super().focusOutEvent(event);self.finish()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.finish(True);event.accept()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and event.modifiers()&Qt.KeyboardModifier.ControlModifier:self.finish();event.accept()
        else:super().keyPressEvent(event)


class Annotation(QGraphicsObject):
    def __init__(self, props, editor):
        super().__init__()
        self.props=copy.deepcopy(props); self.editor=editor
        if props["kind"]=="text":self.props["h"]=max(props.get("h",40),text_height(self.props))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(props.get("x",0),props.get("y",0))
        if props.get("transform"):self.setTransform(QTransform(*props["transform"]))
        self.setAcceptHoverEvents(True)
        self.resizing=False
        self.effect_image=None;self.effect_key=None
        if props["kind"] in ("blur","pixelate"):self.props.setdefault("effect_seed",secrets.randbits(63))
        if self.props.get("shadow") and self.props["kind"] in ("arrow","line","ellipse","rect","fill","pencil","text","counter"):
            shadow=QGraphicsDropShadowEffect();shadow.setBlurRadius(6);shadow.setOffset(0,2);shadow.setColor(QColor(0,0,0,135));self.setGraphicsEffect(shadow)
        self.setZValue(props.get("z",1))

    def data_dict(self):
        p=copy.deepcopy(self.props);p.update(x=self.x(),y=self.y());return p

    def boundingRect(self):
        p=self.props
        if p["kind"]=="spotlight":return self.mapFromScene(QRectF(self.editor.base.rect())).boundingRect().united(QRectF(0,0,p.get("w",100),p.get("h",40)))
        margin=max(20,p.get("width",4)*4+5) if p["kind"]=="arrow" else max(20,p.get("width",4)/2+5)
        return QRectF(-margin,-margin,max(1,p.get("w",100))+2*margin,max(1,p.get("h",40))+2*margin)

    def content_bounds(self):
        p=self.props;kind=p["kind"];w=p.get("w",100);h=p.get("h",40);width=p.get("width",4)
        bounds=QRectF(0,0,w,h)
        if kind in ("arrow","line"):
            a=QPointF(p.get("ax",0)*w,p.get("ay",0)*h);b=QPointF(p.get("bx",1)*w,p.get("by",1)*h);path=QPainterPath(a)
            if kind=="arrow" and p.get("style")=="curved":control=(a+b)/2+QPointF(0,-max(40,h*.45));path.quadTo(control,b);direction=b-control
            else:path.lineTo(b);direction=b-a
            bounds=path.boundingRect().adjusted(-width/2,-width/2,width/2,width/2)
            if kind=="arrow":
                angle=math.atan2(direction.y(),direction.x());size=max(13,width*4)
                for point,angle in [(b,angle)]+([(a,angle+math.pi)] if p.get("style")=="double" else []):
                    head=QPolygonF([point,point-QPointF(math.cos(angle-.5)*size,math.sin(angle-.5)*size),point-QPointF(math.cos(angle+.5)*size,math.sin(angle+.5)*size)])
                    bounds=bounds.united(head.boundingRect())
            if kind=='arrow' and p.get('style')=='standard' and p.get('arrow_taper',False):
                from .arrow_geometry import tapered_arrow
                bounds=tapered_arrow(a,b,width).boundingRect()
        margin=width/2+1 if kind in ("arrow","line","ellipse","rect","fill","pencil") else 0
        bounds=bounds.adjusted(-margin,-margin,margin,margin)
        if self.graphicsEffect():bounds=self.graphicsEffect().boundingRectFor(bounds)
        return self.sceneTransform().mapRect(bounds)

    def shape(self):
        p=self.props;w=p.get("w",100);h=p.get("h",40);path=QPainterPath()
        if p["kind"] in ("line","arrow"):
            a=QPointF(p.get("ax",0)*w,p.get("ay",0)*h);b=QPointF(p.get("bx",1)*w,p.get("by",1)*h);path.moveTo(a)
            if p["kind"]=="arrow" and p.get("style")=="curved":
                control=(a+b)/2+QPointF(0,-max(40,h*.45));path.quadTo(control,b);direction=b-control
            else:path.lineTo(b);direction=b-a
            stroke=QPainterPathStroker();stroke.setWidth(max(14,p.get("width",4)+8));path=stroke.createStroke(path)
            if p['kind']=='arrow' and p.get('style')=='standard' and p.get('arrow_taper',False):
                from .arrow_geometry import tapered_arrow
                head=tapered_arrow(a,b,p.get('width',4));path=path.united(head).united(stroke.createStroke(head))
            elif p['kind']=='arrow':
                angle=math.atan2(direction.y(),direction.x());size=max(13,p.get('width',4)*4)
                for tip,theta in [(b,angle)]+([(a,angle+math.pi)] if p.get('style')=='double' else []):
                    left=tip-QPointF(math.cos(theta-.5)*size,math.sin(theta-.5)*size);right=tip-QPointF(math.cos(theta+.5)*size,math.sin(theta+.5)*size)
                    head=QPainterPath(left);head.lineTo(tip);head.lineTo(right)
                    if p.get('style')!='open':head.closeSubpath();path=path.united(head)
                    path=path.united(stroke.createStroke(head))
        else:path.addRect(QRectF(0,0,w,h))
        if self.isSelected():
            for point in self.handles().values():path.addRect(QRectF(point.x()-6,point.y()-6,12,12))
        path.setFillRule(Qt.FillRule.WindingFill)
        return path

    def paint(self,painter,option,widget=None):
        if self.editor.background and not self.editor.exporting:
            opts=self.editor.background;clip=rounded_path(QRectF(self.editor.base.rect()),opts.get('radius',12),opts.get('radius_power',2));painter.setClipPath(self.mapFromScene(clip),Qt.ClipOperation.IntersectClip)
        p=self.props;kind=p["kind"];w=p.get("w",100);h=p.get("h",40)
        rect=QRectF(0,0,w,h);color=self.editor.paint_color(p.get("color","#ff5b61"));width=p.get("width",4)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color,width,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if kind in ("rect","fill","ellipse","highlight","redact"):
            if kind in ("fill","redact"): painter.setBrush(color)
            if kind=="highlight":
                color.setAlpha(max(0,min(255,round(p.get('highlight_alpha',100)))));painter.setBrush(color);painter.setPen(Qt.PenStyle.NoPen)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            if kind=="ellipse":painter.drawEllipse(rect)
            else:painter.drawRoundedRect(rect,2,2)
        elif kind in ("line","arrow"):
            a=QPointF(p.get("ax",0)*w,p.get("ay",0)*h)
            b=QPointF(p.get("bx",1)*w,p.get("by",1)*h)
            style=p.get("style","standard")
            if kind=='arrow' and style=='standard' and p.get('arrow_taper',False):
                from .arrow_geometry import tapered_arrow
                painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color);painter.drawPath(tapered_arrow(a,b,width))
            elif kind=="arrow" and style=="curved":
                path=QPainterPath(a);control=(a+b)/2+QPointF(0,-max(40,h*.45));path.quadTo(control,b);painter.drawPath(path)
                direction=b-control
            else:painter.drawLine(a,b);direction=b-a
            if kind=="arrow" and not (style=='standard' and p.get('arrow_taper',False)):
                angle=math.atan2(direction.y(),direction.x());size=max(13,width*4)
                def head(point,angle):
                    points=[point,point-QPointF(math.cos(angle-.5)*size,math.sin(angle-.5)*size),
                            point-QPointF(math.cos(angle+.5)*size,math.sin(angle+.5)*size)]
                    if style=="open":painter.drawPolyline(QPolygonF([points[1],points[0],points[2]]))
                    else:painter.setBrush(color);painter.drawPolygon(QPolygonF(points))
                head(b,angle)
                if style=="double":head(a,angle+math.pi)
        elif kind=="pencil":
            points=p.get("points",[])
            if points:
                path=QPainterPath(QPointF(*points[0]))
                if p.get("smooth",True):
                    for i in range(1,len(points)-1):
                        a=QPointF(*points[i]);b=QPointF(*points[i+1]);path.quadTo(a,(a+b)/2)
                    if len(points)>1:path.lineTo(QPointF(*points[-1]))
                else:
                    for point in points[1:]:path.lineTo(QPointF(*point))
                painter.drawPath(path)
        elif kind=='text' and p.get('text_style') in text_styles.STYLES:
            if getattr(self,'inline',None):return
            text_styles.paint(self,painter,color)
        elif kind in ("text","counter"):
            if getattr(self,"inline",None):return
            size=p.get("font_size",28)
            font=QFont(p.get("font_family","Inter"),int(size));font.setBold(p.get("bold",True));font.setItalic(p.get("italic",False));font.setUnderline(p.get("underline",False));painter.setFont(font)
            style=p.get("text_style","plain")
            if kind=="counter":
                style=p.get("counter_style","Circle");painter.setBrush(Qt.BrushStyle.NoBrush if style=="Outline" else QBrush(color));painter.setPen(QPen(color,3) if style=="Outline" else Qt.PenStyle.NoPen)
                if style=="Square":painter.drawRoundedRect(rect,5,5)
                else:painter.drawEllipse(rect)
                painter.setPen(color if style=="Outline" else QColor("white"));painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,p.get("text","1"))
            else:
                if style in ("solid","rounded","outline","dark","light"):
                    fill=color if style in ("solid","rounded") else self.editor.paint_color("#20222a" if style=="dark" else "#ffffff")
                    painter.setBrush(Qt.BrushStyle.NoBrush if style=="outline" else QBrush(fill))
                    painter.setPen(QPen(color,2));painter.drawRoundedRect(rect,10 if style=="rounded" else 3,10 if style=="rounded" else 3)
                    painter.setPen(QColor("white") if style in ("solid","rounded","dark") else color)
                if style=="shadow":
                    painter.setPen(QColor(0,0,0,150));painter.drawText(rect.adjusted(9,9,-3,-3),Qt.TextFlag.TextWordWrap,p.get("text",""));painter.setPen(color)
                painter.drawText(rect.adjusted(6,4,-6,-4),Qt.TextFlag.TextWordWrap,p.get("text",""))
        elif kind in ("blur","pixelate"):
            if w>0 and h>0:
                from .annotation_effects import render_effect
                transform=self.sceneTransform()
                key=(self.editor.base.cacheKey(),transform.m11(),transform.m12(),transform.m21(),transform.m22(),transform.dx(),transform.dy(),w,h,p.get("strength",18),p.get("blur_mode","Smooth"),p.get("pixelate_mode","Classic"),p.get("effect_seed",0))
                if key!=self.effect_key:
                    self.effect_image=render_effect(self.editor.base,transform,p);self.effect_key=key
                effect=QImage(self.effect_image);effect.setColorSpace(image_color_space(self.editor.base))
                painter.drawImage(rect,convert_image(effect,self.editor.paint_space()))
        elif kind=="spotlight":
            from .spotlight import aperture
            area=QPainterPath();area.addRect(QRectF(self.editor.base.rect()));area=self.mapFromScene(area)
            hole=aperture(rect,p)
            # SourceAtop darkens existing content without adding opaque pixels
            # to transparent captures. Subtraction also clips off-canvas holes.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            painter.setPen(Qt.PenStyle.NoPen);painter.fillPath(area.subtracted(hole),QColor(0,0,0,max(0,min(255,round(p.get('spotlight_alpha',155))))))
        elif kind=="image":
            key=(p["image"],self.editor.paint_space())
            if getattr(self,"inserted_key",None)!=key:
                self.inserted_key=key;self.inserted_image=convert_image(QImage.fromData(base64.b64decode(p["image"])),self.editor.paint_space())
            painter.drawImage(rect,self.inserted_image)
        if self.isSelected() and not self.editor.exporting:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(theme_color("accent"),1,Qt.PenStyle.DashLine));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRect(rect)
            painter.setBrush(QColor("#ffffff"))
            for point in self.handles().values():painter.drawRect(QRectF(point.x()-4,point.y()-4,8,8))

    def handles(self):
        p=self.props;w=p.get("w",100);h=p.get("h",40)
        if p["kind"] in ("line","arrow"):
            return {"a":QPointF(p.get("ax",0)*w,p.get("ay",0)*h),"b":QPointF(p.get("bx",1)*w,p.get("by",1)*h)}
        return {"lt":QPointF(0,0),"t":QPointF(w/2,0),"rt":QPointF(w,0),"r":QPointF(w,h/2),"rb":QPointF(w,h),"b":QPointF(w/2,h),"lb":QPointF(0,h),"l":QPointF(0,h/2)}

    def mousePressEvent(self,event):
        if self.editor.view.tool!="select":event.ignore();return
        self.resizing=next((key for key,point in self.handles().items() if (point-event.pos()).manhattanLength()<12),None) if self.isSelected() else None
        self.drag_scene=event.scenePos();self.drag_props=self.data_dict();self.drag_transform=self.sceneTransform();self.duplicated=False
        if self.resizing:event.accept()
        else:super().mousePressEvent(event)
        self.drag_group={obj:obj.pos() for obj in self.editor.scene.selectedItems() if isinstance(obj,Annotation)}

    def mouseMoveEvent(self,event):
        if self.resizing:
            inverse,valid=self.drag_transform.inverted()
            if not valid:return
            point=inverse.map(event.scenePos());p=self.drag_props;w=p.get("w",100);h=p.get("h",40)
            if self.props["kind"] in ("line","arrow"):
                a=QPointF(p.get("ax",0)*w,p.get("ay",0)*h);b=QPointF(p.get("bx",1)*w,p.get("by",1)*h)
                if self.resizing=="a":a=point
                else:b=point
                if event.modifiers()&Qt.KeyboardModifier.ShiftModifier:
                    fixed=b if self.resizing=="a" else a;delta=point-fixed;angle=round(math.atan2(delta.y(),delta.x())/(math.pi/4))*math.pi/4;length=math.hypot(delta.x(),delta.y());point=fixed+QPointF(math.cos(angle)*length,math.sin(angle)*length)
                    if self.resizing=="a":a=point
                    else:b=point
                r=QRectF(a,b).normalized();nw=max(1,r.width());nh=max(1,r.height())
                self.prepareGeometryChange();self.props.update(w=nw,h=nh,ax=(a.x()-r.x())/nw,ay=(a.y()-r.y())/nh,bx=(b.x()-r.x())/nw,by=(b.y()-r.y())/nh)
            else:
                from .annotation_resize import resize_rect
                r=resize_rect(w,h,self.resizing,point,bool(event.modifiers()&Qt.KeyboardModifier.ShiftModifier))
                self.prepareGeometryChange();self.props.update(w=max(8,r.width()),h=max(8,r.height()))
                if self.props["kind"]=="text":self.props["h"]=max(self.props["h"],text_height(self.props))
                if self.props["kind"]=="pencil":
                    self.props['points']=[[x*self.props['w']/w if w else 0,y*self.props['h']/h if h else 0] for x,y in p.get('points',[])]
            # Preserve any rotation/scale already applied to the annotation.
            offset=self.drag_transform.map(r.topLeft())-self.drag_transform.map(QPointF(0,0))
            self.setPos(QPointF(p.get("x",0),p.get("y",0))+offset);self.update();event.accept()
        else:
            delta=event.scenePos()-self.drag_scene
            if event.modifiers()&Qt.KeyboardModifier.ShiftModifier:delta=QPointF(delta.x(),0) if abs(delta.x())>=abs(delta.y()) else QPointF(0,delta.y())
            if delta.manhattanLength()>1 and not self.duplicated and event.modifiers()&Qt.KeyboardModifier.AltModifier:
                for obj in self.drag_group:
                    props=obj.data_dict();origin=self.drag_group[obj];props.update(x=origin.x(),y=origin.y());clone=Annotation(props,self.editor);self.editor.scene.addItem(clone);self.editor.objects.append(clone)
                self.duplicated=True
            for obj,origin in self.drag_group.items():obj.setPos(origin+delta)
            event.accept()

    def mouseReleaseEvent(self,event):
        if not self.resizing:super().mouseReleaseEvent(event)
        self.resizing=False;self.editor.commit()

    def mouseDoubleClickEvent(self,event):
        if self.props["kind"]=="text":
            self.editor.edit_text(self);event.accept()
        elif self.props["kind"]=="counter":
            value,ok=QInputDialog.getInt(self.editor,"Counter","Number",int(self.props.get("text","1")),0,999)
            if ok:self.props["text"]=str(value);self.update();self.editor.commit()
        else:super().mouseDoubleClickEvent(event)


class AnnotationComposition(QGraphicsEffect):
    """Composite annotation blends against the image, not the view background."""
    def __init__(self,editor):super().__init__();self.editor=editor
    def boundingRectFor(self,rect):
        visible=self.editor.view.mapToScene(self.editor.view.viewport().rect()).boundingRect()
        visible=visible.adjusted(-2,-2,2,2)
        transform=getattr(self,'buffer_transform',None)
        # Crop only the device-space pixmap request; scene geometry stays whole.
        if transform is None:return rect
        return rect.intersected(transform.mapRect(visible))
    def draw(self,painter):
        if self.editor.exporting:self.drawSource(painter);return
        offset=QPoint();self.buffer_transform=painter.worldTransform()
        try:pixmap=self.sourcePixmap(Qt.CoordinateSystem.DeviceCoordinates,offset,QGraphicsEffect.PixmapPadMode.PadToEffectiveBoundingRect)
        finally:self.buffer_transform=None
        painter.save();painter.setWorldTransform(QTransform());painter.drawPixmap(offset,pixmap);painter.restore()


class SourceImage(QGraphicsPixmapItem):
    def __init__(self,editor):super().__init__(QPixmap.fromImage(editor.base));self.editor=editor
    def paint(self,painter,option,widget=None):
        if self.editor.background and not self.editor.exporting:
            opts=self.editor.background;clip=rounded_path(QRectF(self.editor.base.rect()),opts.get('radius',12),opts.get('radius_power',2));painter.setClipPath(clip,Qt.ClipOperation.IntersectClip)
        key=(self.editor.base.cacheKey(),self.editor.paint_space())
        if getattr(self,"paint_key",None)!=key:
            self.paint_key=key;self.paint_image=convert_image(self.editor.base,self.editor.paint_space())
        painter.drawImage(0,0,self.paint_image)


class Canvas(QGraphicsView):
    def __init__(self,editor):
        super().__init__(editor.scene);self.editor=editor;self.tool="select";self.start=None;self.draft=None
        from .canvas_pan import CanvasPan
        self.pan=CanvasPan(self)
        self.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True);self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def drawBackground(self,painter,rect):
        painter.fillRect(rect,theme_color("base"))

    def sync_composition_bounds(self):
        if hasattr(self.editor,"zoom_button"):
            button=self.editor.zoom_button;button.setText(f"{round(self.transform().m11()*100,1):g}%")
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text())+40)
        from shiboken6 import isValid
        root=getattr(self.editor,'composition_root',None)
        if root is not None and isValid(root):root.graphicsEffect().updateBoundingRect();root.graphicsEffect().update()
    def scrollContentsBy(self,dx,dy):
        super().scrollContentsBy(dx,dy);self.sync_composition_bounds()
    def resizeEvent(self,event):
        super().resizeEvent(event);self.sync_composition_bounds()
    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        if self.editor.crop_session:self.editor.crop_session.paint(painter,rect)
    def drawBackground(self,painter,rect):
        super().drawBackground(painter,rect)
        if self.editor.crop_session:self.editor.crop_session.draw_background(painter)
        if self.editor.background:
            w,h,content=self.editor.background_layout();painter.save();painter.translate(-content.x(),-content.y());self.editor.paint_background(painter,w,h,content);painter.restore()

    def mousePressEvent(self,event):
        if self.pan.press(event):event.accept();return
        if self.editor.crop_session:self.editor.crop_session.press(event);return
        if event.button()!=Qt.MouseButton.LeftButton or self.tool=="select":super().mousePressEvent(event);return
        self.start=self.mapToScene(event.position().toPoint());x,y=self.start.x(),self.start.y()
        if not QRectF(self.editor.base.rect()).contains(self.start):self.start=None;return
        props={"kind":self.tool,"x":x,"y":y,"w":1,"h":1,"color":self.editor.color,
               "width":self.editor.width.value(),"style":self.editor.arrow_style.currentText(),"strength":self.editor.effect_strength.value(),"z":len(self.editor.objects)+1,
               "shadow":self.editor.store.settings.get("annotation_shadow",True),"smooth":self.editor.store.settings.get("smooth_drawing",True)}
        if self.tool=="text":
            props.update(text="Text",w=300,h=60,text_style=self.editor.text_style.style(),font_size=self.editor.font_size.value(),
                         font_family=self.editor.text_font.family(),bold=self.editor.text_font.bold(),italic=self.editor.text_font.italic(),underline=self.editor.text_font.underline())
        if self.tool=="counter":
            number=max(self.editor.counter_number.value(),1+max([int(o.props.get("text","0")) for o in self.editor.objects if o.props["kind"]=="counter"] or [-1]))
            props.update(w=44,h=44,text=str(number),font_size=20,counter_style=self.editor.counter_style.currentText())
        if self.tool in ("blur","pixelate"):props.update(blur_mode=self.editor.blur_mode.currentText(),pixelate_mode=self.editor.pixelate_mode.currentText())
        if self.tool=="spotlight":props.update(self.editor.spotlight.values())
        if self.tool=='arrow':props['arrow_taper']=True
        if self.tool=="highlight":props['highlight_alpha']=self.editor.highlight_alpha
        if self.tool=="pencil":props["points"]=[[0,0]]
        self.draft=Annotation(props,self.editor);self.editor.scene.addItem(self.draft)
        self.editor.order_annotations(self.draft)
        if self.tool in ("text","counter"):
            obj=self.draft;self.editor.objects.append(obj);self.editor.commit();self.draft=None;self.start=None
            if self.tool=="text":self.editor.set_tool("select");self.editor.edit_text(obj)

    def mouseMoveEvent(self,event):
        if self.pan.move(event):event.accept();return
        if self.editor.crop_session:self.editor.crop_session.move(event);return
        if self.start is None or self.draft is None:super().mouseMoveEvent(event);return
        pos=self.mapToScene(event.position().toPoint());delta=pos-self.start
        self.draft.prepareGeometryChange();p=self.draft.props
        if self.tool=="pencil":
            # Keep the live path inside its item bounds in every direction.
            # Points are relative to the moving top-left, not the initial press.
            p['points'].append([pos.x()-self.draft.x(),pos.y()-self.draft.y()])
            xs=[v[0] for v in p['points']];ys=[v[1] for v in p['points']];left,top=min(xs),min(ys)
            self.draft.setPos(self.draft.x()+left,self.draft.y()+top)
            p.update(points=[[x-left,y-top] for x,y in p['points']],w=max(xs)-left,h=max(ys)-top)
        else:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if self.tool in ("line","arrow"):
                    angle=round(math.atan2(delta.y(),delta.x())/(math.pi/4))*math.pi/4;length=math.hypot(delta.x(),delta.y());delta=QPointF(math.cos(angle)*length,math.sin(angle)*length)
                else:
                    size=max(abs(delta.x()),abs(delta.y()));delta=QPointF(math.copysign(size,delta.x()),math.copysign(size,delta.y()))
            end=self.start+delta;r=QRectF(self.start,end).normalized()
            self.draft.setPos(r.topLeft());p.update(w=max(1,r.width()),h=max(1,r.height()),
                ax=0 if delta.x()>=0 else 1,ay=0 if delta.y()>=0 else 1,bx=1 if delta.x()>=0 else 0,by=1 if delta.y()>=0 else 0)
            if self.tool=="arrow" and (self.editor.store.settings.get("inverse_arrows",False)^bool(event.modifiers()&Qt.KeyboardModifier.AltModifier)):
                p["ax"],p["bx"]=p["bx"],p["ax"];p["ay"],p["by"]=p["by"],p["ay"]
        self.draft.update()

    def mouseReleaseEvent(self,event):
        if self.pan.release(event):event.accept();return
        if self.editor.crop_session:self.editor.crop_session.release(event);return
        if self.start is None or self.draft is None:super().mouseReleaseEvent(event);return
        obj=self.draft;self.draft=None;self.start=None
        if obj.props["w"]>3 or obj.props["h"]>3:
            if self.tool=="pencil":
                points=obj.props["points"];xs=[v[0] for v in points];ys=[v[1] for v in points];left,top=min(xs),min(ys)
                obj.setPos(obj.x()+left,obj.y()+top);obj.props.update(points=[[x-left,y-top] for x,y in points],w=max(xs)-left,h=max(ys)-top)
            if self.tool=="highlight" and not event.modifiers()&Qt.KeyboardModifier.ControlModifier:self.editor.smart_highlight(obj)
            self.editor.objects.append(obj);self.editor.commit()
        else:self.editor.scene.removeItem(obj)

    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor=1.15 if event.angleDelta().y()>0 else 1/1.15
            scale=self.transform().m11()*factor
            if .025<=scale<=12:self.scale(factor,factor);self.sync_composition_bounds()
        else:super().wheelEvent(event)

    def keyPressEvent(self,event):
        if self.pan.key_press(event):event.accept();return
        if self.editor.crop_session and self.editor.crop_session.key(event):event.accept();return
        if not self.editor.inline and self.tool=="select":
            selected=[obj for obj in self.editor.scene.selectedItems() if isinstance(obj,Annotation)]
            delta={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}.get(event.key())
            if selected and delta:
                step=10 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1
                for obj in selected:obj.setPos(obj.pos()+QPointF(delta[0]*step,delta[1]*step))
                self.editor.commit();event.accept();return
            if event.modifiers()&Qt.KeyboardModifier.ControlModifier and event.key()==Qt.Key.Key_D and selected:
                self.editor.scene.clearSelection()
                for obj in selected:
                    props=obj.data_dict();props.update(x=obj.x()+12,y=obj.y()+12);clone=Annotation(props,self.editor);self.editor.scene.addItem(clone);self.editor.objects.append(clone);clone.setSelected(True)
                self.editor.commit();event.accept();return
        super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if self.pan.key_release(event):event.accept();return
        super().keyReleaseEvent(event)

    def focusOutEvent(self,event):
        self.pan.cancel();super().focusOutEvent(event)

    def dragEnterEvent(self,event):
        mime=event.mimeData()
        if (not self.editor.crop_session and event.possibleActions()&Qt.DropAction.CopyAction
                and (mime.hasImage() or mime.hasFormat('image/png') or any(url.isLocalFile() for url in mime.urls()))):
            event.setDropAction(Qt.DropAction.CopyAction);event.accept()
        else:event.ignore()
    def dragMoveEvent(self,event):self.dragEnterEvent(event)
    def dropEvent(self,event):
        event.ignore()
        if self.editor.crop_session or not event.possibleActions()&Qt.DropAction.CopyAction:return
        pos=self.mapToScene(event.position().toPoint())
        try:
            if self.editor.drop_images(event.mimeData(),pos):
                event.setDropAction(Qt.DropAction.CopyAction);event.accept()
        except Exception as exc:error(self.editor,exc)


class Editor(QMainWindow):
    saved=Signal(str)
    draft_updated=Signal(str)
    pin_requested=Signal(str)
    def __init__(self,path,store):
        super().__init__();self.store=store;self.path=Path(path);self.setWindowTitle("OmniShot — Annotate")
        ui.set(self,"resize",1120,800);self.base=load_image(path);self.original_image=None;self.source_transform=QTransform();self.objects=[];self.exporting=False;self.crop_session=None;self.clipboard_token=None
        self.scene=QGraphicsScene(self);self.color=store.settings["palette"][0];self.highlight_alpha=100;self.undo_states=[];self.undo_index=-1
        self.background=None;self.inline=None;self.text_font=QFont(text_styles.family("Standard"),28);self.text_font.setBold(True);self.view=Canvas(self);self.setCentralWidget(self.view)
        self.expand_canvas=store.settings.get("auto_expand_canvas",False)
        self.draft_path=store.image_edit_path(path) if self.path.resolve().parent==store.captures.resolve() else None
        self.draft_timer=QTimer(self);self.draft_timer.setSingleShot(True);self.draft_timer.timeout.connect(self.save_draft)
        from . import editor_toolbar
        editor_toolbar.tools(self)
        for key,label,shortcut in (*editor_toolbar.TOOLS,('crop','Crop','C')):
            QShortcut(QKeySequence(shortcut),self,activated=lambda k=key:self.set_tool(k))
        self.color_btn=QPushButton();ui.set(self.color_btn,"setFixedSize",28,28);self.color_btn.clicked.connect(self.pick_color);self.color_action=self.toolbar.addWidget(self.color_btn)
        self.width=QSpinBox();self.width.setRange(1,40);self.width.setValue(4);self.width.setToolTip("Stroke width");self.width.valueChanged.connect(self.change_selected_style);self.width_action=self.toolbar.addWidget(self.width)
        ui.set(self.width,"setFixedWidth",54)
        self.arrow_style=QComboBox();self.arrow_style.addItems(["standard","open","double","curved"]);self.arrow_style.setToolTip("Arrow style");self.arrow_style_action=self.toolbar.addWidget(self.arrow_style)
        self.text_style=text_styles.StyleChoice();ui.set(self.text_style,"setMaximumWidth",190);self.text_style.setToolTip("Text style");self.text_style_action=self.toolbar.addWidget(self.text_style)
        self.font_size=QSpinBox();self.font_size.setRange(8,160);self.font_size.setValue(28);self.font_size.setSuffix(" pt");self.font_size_action=self.toolbar.addWidget(self.font_size)
        self.effect_strength=QSpinBox();self.effect_strength.setRange(2,80);self.effect_strength.setValue(18);self.effect_strength.setToolTip("Blur / pixelation strength");self.effect_strength_action=self.toolbar.addWidget(self.effect_strength);self.effect_strength.valueChanged.connect(self.change_selected_style)
        self.blur_mode=QComboBox();self.blur_mode.addItems(["Secure","Smooth"]);self.blur_mode.setToolTip("Secure replaces the selected pixels with an opaque texture. Smooth applies Gaussian blur. Export an image for sharing; editable projects retain the original.");self.blur_mode_action=self.toolbar.addWidget(self.blur_mode)
        self.pixelate_mode=QComboBox();self.pixelate_mode.addItems(["Randomized","Classic"]);self.pixelate_mode.setToolTip("Pixelation pattern. Use Secure blur or Black Out when the original content must be removed from an exported image.");self.pixelate_mode_action=self.toolbar.addWidget(self.pixelate_mode)
        for control in (self.blur_mode,self.pixelate_mode):control.currentTextChanged.connect(self.change_selected_style)
        from .spotlight import SpotlightControls
        self.spotlight=SpotlightControls(self);self.spotlight_action=self.toolbar.addWidget(self.spotlight)
        self.counter_style=QComboBox();self.counter_style.addItems(["Circle","Square","Outline"]);self.counter_style.setToolTip("Counter style");self.counter_style_action=self.toolbar.addWidget(self.counter_style);self.counter_style.currentTextChanged.connect(self.change_selected_style)
        self.counter_number=QSpinBox();self.counter_number.setRange(0,999);self.counter_number.setValue(1);self.counter_number.setToolTip("Counter starting number");self.counter_number_action=self.toolbar.addWidget(self.counter_number)
        self.arrow_style.currentTextChanged.connect(self.change_selected_style)
        self.text_style.currentTextChanged.connect(self.change_text_preset)
        self.font_size.valueChanged.connect(self.change_selected_style)
        editor_toolbar.finish(self)
        menu=self.menuBar().addMenu("File")
        for label,slot,shortcut in [("Open…",self.open_file,"Ctrl+O"),("Save image…",self.save_image,"Ctrl+S"),
            ("Save editable project…",self.save_project,"Ctrl+Shift+S"),("Insert image…",self.insert_dialog,"Ctrl+I"),
            ("Copy",self.copy_selection,"Ctrl+C"),("Paste",self.paste_image,"Ctrl+V"),("Print…",self.print_image,"Ctrl+P")]:
            action=menu.addAction(label,slot);action.setShortcut(shortcut)
        menu.addAction("Combine images…",self.combine_dialog)
        edit_menu=self.menuBar().addMenu("Edit")
        for label,slot in [("Undo",self.undo),("Redo",self.redo),("Rotate clockwise",self.rotate),("Flip horizontally",self.flip),("Resize…",self.resize_image),("Background…",self.background_dialog)]:edit_menu.addAction(label,slot)
        edit_menu.addAction("Text font…",self.pick_font)
        self.expand_action=edit_menu.addAction("Automatically expand canvas");self.expand_action.setCheckable(True);self.expand_action.setChecked(self.expand_canvas);self.expand_action.toggled.connect(self.set_expand_canvas)
        for seq,slot in [("Ctrl+Z",self.undo),("Ctrl+Shift+Z",self.redo),("Delete",self.delete_selected),("Backspace",self.delete_selected)]:QShortcut(QKeySequence(seq),self,activated=slot)
        self.pin_shortcut=QShortcut(QKeySequence(),self,activated=self.pin);self.pin_shortcut.setAutoRepeat(False);self.apply_annotation_shortcuts()
        self.set_color(self.color);self.set_tool("select")
        self.scene.selectionChanged.connect(self.selection_changed)
        if self.draft_path and self.draft_path.exists():self.load_project(self.draft_path)
        elif self.path.suffix==".omnishot":self.load_project(self.path)
        else:
            if self.base.isNull():raise ValueError("Cannot open this image")
            from .backgrounds import default_background
            self.background=None if self.store.metadata(self.path).get("skip_background") else default_background(self.store)
            self.rebuild();self.commit()

    def apply_annotation_shortcuts(self):
        sequence=QKeySequence(self.store.settings.get('annotation_pin_shortcut',''))
        self.pin_shortcut.setKey(sequence);self.pin_button.setToolTip('Pin'+(' ('+sequence.toString(QKeySequence.SequenceFormat.NativeText)+')' if not sequence.isEmpty() else ''))

    def set_tool(self,key):
        self.view.pan.cancel()
        if self.inline:self.inline.finish()
        if self.crop_session:
            if key=='crop':return
            self.crop_session.cancel()
        self.view.tool=key
        if key=='crop':
            from .crop import CropSession
            CropSession(self);return
        from .editor_toolbar import properties,HIDDEN_TOOLS
        properties(self,key)
        if key in HIDDEN_TOOLS:self.hide_button.setDefaultAction(self.tools[key])
        for k,a in self.tools.items():a.setChecked(k==key)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag if key=="select" else QGraphicsView.DragMode.NoDrag)
        for obj in self.objects:obj.setAcceptedMouseButtons(Qt.MouseButton.LeftButton if key=="select" else Qt.MouseButton.NoButton)
        self.view.setCursor(Qt.CursorShape.ArrowCursor if key=="select" else Qt.CursorShape.CrossCursor)
        ui.set(self.color_btn,"setStyleSheet",f"background:{self.picker_color()};border:2px solid palette(mid);border-radius:14px")
        self.statusBar().showMessage(f"{key.title()} · Space + drag pans · Shift constrains proportions · Ctrl + wheel zooms")

    def set_color(self,color,commit=True):
        self.color=color
        selected=[obj for obj in self.scene.selectedItems() if isinstance(obj,Annotation)]
        if self.view.tool=='highlight' or any(obj.props['kind']=='highlight' for obj in selected):self.highlight_alpha=QColor(color).alpha()
        for obj in selected:
            obj.props['color']=color
            if obj.props['kind']=='highlight':obj.props['highlight_alpha']=self.highlight_alpha
            obj.update()
        ui.set(self.color_btn,"setStyleSheet",f"background:{self.picker_color()};border:2px solid palette(mid);border-radius:14px")
        if selected and commit:self.commit()

    def picker_color(self):
        selected=[obj for obj in self.scene.selectedItems() if isinstance(obj,Annotation)]
        color=QColor(self.color)
        if (len(selected)==1 and selected[0].props['kind']=='highlight') or (not selected and self.view.tool=='highlight'):color.setAlpha(self.highlight_alpha)
        return color.name(QColor.NameFormat.HexArgb if color.alpha()!=255 else QColor.NameFormat.HexRgb)

    def pick_color(self):
        from .color_picker import ColorPicker
        from shiboken6 import isValid
        existing=getattr(self,'color_popup',None)
        if existing and isValid(existing) and existing.isVisible():existing.close();return
        initial=[(obj,obj.props.get('color'),obj.props.get('highlight_alpha')) for obj in self.scene.selectedItems() if isinstance(obj,Annotation)]
        popup=ColorPicker(self.picker_color(),self.store,self);self.color_popup=popup
        popup.changed.connect(lambda value:self.set_color(value,commit=False))
        def finished():
            if any(isValid(obj) and obj in self.objects and (obj.props.get('color'),obj.props.get('highlight_alpha'))!=(color,alpha) for obj,color,alpha in initial):self.commit()
        popup.finished.connect(finished);popup.screen_requested.connect(lambda:self.screen_color(reopen=True))
        position=self.color_btn.mapToGlobal(self.color_btn.rect().bottomLeft());bounds=self.screen().availableGeometry()
        popup.move(max(bounds.left(),min(position.x(),bounds.right()-popup.width())),max(bounds.top(),min(position.y()+6,bounds.bottom()-popup.height())))
        popup.show()
    def custom_color(self):
        self.pick_color()

    def screen_color(self,reopen=False):
        from .widgets import background
        from shiboken6 import isValid
        def done(value):
            if not isValid(self):return
            import re
            match=re.search(r"#[0-9a-fA-F]{6}",value.decode())
            if match:self.set_color(match.group())
            if reopen:self.pick_color()
        def failed(message):
            if not isValid(self):return
            self.statusBar().showMessage(f"Could not pick a screen color: {message}")
            if reopen:self.pick_color()
        from .color_picker import sample_screen
        QTimer.singleShot(150,lambda:background(sample_screen,done,failed) if isValid(self) else None)
    def pick_font(self):
        ok,font=QFontDialog.getFont(self.text_font,self,"Text font")
        if ok:
            self.text_font=font;self.font_size.blockSignals(True);self.font_size.setValue(font.pointSize());self.font_size.blockSignals(False)
            for obj in self.scene.selectedItems():
                if isinstance(obj,Annotation) and obj.props["kind"]=="text":
                    obj.prepareGeometryChange();obj.props.update(font_family=font.family(),font_size=font.pointSize(),bold=font.bold(),italic=font.italic(),underline=font.underline())
                    obj.props['h']=max(obj.props.get('h',40),text_height(obj.props));obj.update()
            self.commit()
    def edit_text(self,obj):
        if self.inline:self.inline.finish()
        obj.setSelected(True)
        self.inline=InlineText(obj);obj.inline=self.inline;obj.update()

    def change_text_preset(self,*args):
        style=self.text_style.style()
        if style not in text_styles.STYLES:return
        self.text_font.setFamily(text_styles.family(style))
        for obj in self.scene.selectedItems():
            if isinstance(obj,Annotation) and obj.props['kind']=='text':obj.props['font_family']=self.text_font.family()
        self.change_selected_style()

    def change_selected_style(self,*args):
        selected=[o for o in self.scene.selectedItems() if isinstance(o,Annotation)]
        for obj in selected:
            obj.prepareGeometryChange()
            if obj.props['kind']=='arrow' and self.sender()==self.arrow_style:obj.props['arrow_taper']=self.arrow_style.currentText()=='standard'
            obj.props.update(color=self.color,width=self.width.value(),style=self.arrow_style.currentText(),
                             text_style=self.text_style.style(),font_size=self.font_size.value(),strength=self.effect_strength.value(),counter_style=self.counter_style.currentText(),blur_mode=self.blur_mode.currentText(),pixelate_mode=self.pixelate_mode.currentText())
            if obj.props["kind"]=="text":obj.props["h"]=max(obj.props["h"],text_height(obj.props))
            obj.update()
        if selected:self.commit()
    def selection_changed(self):
        selected=[obj for obj in self.scene.selectedItems() if isinstance(obj,Annotation)]
        from .editor_toolbar import properties
        if len(selected)!=1:
            properties(self,self.view.tool);return
        p=selected[0].props
        if p["kind"]=="spotlight":self.spotlight.load(p)
        if p["kind"]=="text":self.text_font=text_styles.font_for(p)
        if p['kind']=='highlight':self.highlight_alpha=p.get('highlight_alpha',100)
        self.color=p.get("color",self.color);ui.set(self.color_btn,"setStyleSheet",f"background:{self.picker_color()};border:2px solid palette(mid);border-radius:14px")
        for widget,value in [(self.width,p.get("width",4)),(self.font_size,p.get("font_size",28)),(self.effect_strength,p.get("strength",18)),(self.arrow_style,p.get("style","standard")),(self.text_style,p.get("text_style","plain")),(self.blur_mode,p.get("blur_mode","Smooth")),(self.pixelate_mode,p.get("pixelate_mode","Classic"))]:
            widget.blockSignals(True)
            if isinstance(widget,text_styles.StyleChoice):widget.set_style(value)
            elif isinstance(widget,QComboBox):widget.setCurrentText(value)
            else:widget.setValue(round(value))
            widget.blockSignals(False)
        if self.view.tool=="select":
            properties(self,p['kind']);self.counter_style.blockSignals(True);self.counter_style.setCurrentText(p.get("counter_style","Circle"));self.counter_style.blockSignals(False)

    def snapshot(self):return {"base":QImage(self.base),"original_image":QImage(self.original_image) if self.original_image is not None else None,"source_transform":QTransform(self.source_transform),"objects":[o.data_dict() for o in self.objects],"background":copy.deepcopy(self.background),"expand_canvas":self.expand_canvas}
    def order_annotations(self,extra=None):
        objects=list(self.objects)
        extra=extra or getattr(self.view,"draft",None)
        if extra is not None and extra not in objects:objects.append(extra)
        spotlight=any(obj.props['kind']=='spotlight' for obj in objects)
        root=getattr(self,'composition_root',None)
        if spotlight and root is None:
            root=QGraphicsRectItem(QRectF(self.base.rect()));root.setPen(QPen(Qt.PenStyle.NoPen));root.setBrush(Qt.BrushStyle.NoBrush)
            root.setAcceptedMouseButtons(Qt.MouseButton.NoButton);self.scene.addItem(root);root.setGraphicsEffect(AnnotationComposition(self));self.composition_root=root
        if root is not None:
            for item in objects+[i for i in self.scene.items() if isinstance(i,SourceImage)]:
                if item.parentItem() is not root:item.setParentItem(root)
            root.graphicsEffect().setEnabled(spotlight)
        # Counter markers stay readable above every other annotation type.
        # Rank rather than adding a fixed offset, including imported z values.
        for index,obj in enumerate(sorted(objects,key=lambda o:(o.props["kind"]=="counter",o.props.get("z",1)))):obj.setZValue(index+1)
    def commit(self):
        self.order_annotations()
        if self.crop_session:self.update_canvas_bounds();return
        expanded=self.expand_to_annotations() if self.expand_canvas else True
        self.update_canvas_bounds()
        self.undo_states=self.undo_states[:self.undo_index+1];self.undo_states.append(self.snapshot())
        if len(self.undo_states)>35:self.undo_states.pop(0)
        self.undo_index=len(self.undo_states)-1
        self.statusBar().showMessage(f"{self.base.width()} × {self.base.height()} px · {len(self.objects)} annotations")
        if expanded is False:self.statusBar().showMessage("Could not expand the canvas. The limit is 120 megapixels; move the annotation closer to the image.")
        if self.draft_path:self.draft_timer.start(1200)
    def save_draft(self):
        self.draft_timer.stop()
        self.draft_preview_error=None
        if not self.draft_path or self.inline or self.crop_session:return True
        try:
            self.draft_path.parent.mkdir(parents=True,exist_ok=True)
            self.write_project(self.draft_path)
        except Exception as exc:
            self.draft_error=str(exc);self.statusBar().showMessage(f"Could not preserve edits: {exc}");return False
        try:export_image(self.render(convert_srgb=False),self.draft_path.with_suffix(".png"))
        except Exception as exc:
            self.draft_preview_error=str(exc)
            self.statusBar().showMessage(f"Edits preserved; could not update the history preview: {exc}")
        else:self.draft_updated.emit(str(self.path))
        return True
    def closeEvent(self,event):
        if self.crop_session:self.crop_session.cancel()
        if self.inline:self.inline.finish()
        while not self.save_draft():
            reply=QMessageBox.warning(self,"Could not preserve edits",self.draft_error+"\n\nKeep this window open to save an editable project elsewhere, or retry after freeing space.",QMessageBox.StandardButton.Retry|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if reply==QMessageBox.StandardButton.Discard:break
            if reply!=QMessageBox.StandardButton.Retry:event.ignore();return
        self.clipboard_token=None
        super().closeEvent(event)
    def restore(self,state):
        self.original_image=QImage(state['original_image']) if state.get('original_image') is not None else None;self.source_transform=QTransform(state.get('source_transform',QTransform()))
        self.base=QImage(state["base"]);self.background=copy.deepcopy(state["background"]);self.expand_canvas=state.get("expand_canvas",False);self.expand_action.blockSignals(True);self.expand_action.setChecked(self.expand_canvas);self.expand_action.blockSignals(False);self.rebuild(state["objects"])
        if self.draft_path:self.draft_timer.start(1200)
    def undo(self):
        if self.undo_index>0:self.undo_index-=1;self.restore(self.undo_states[self.undo_index])
    def redo(self):
        if self.undo_index<len(self.undo_states)-1:self.undo_index+=1;self.restore(self.undo_states[self.undo_index])
    def rebuild(self,props=None):
        if props is None:props=[o.data_dict() for o in self.objects]
        self.view.draft=None;self.view.start=None
        self.scene.clear();self.objects=[];self.composition_root=None
        image=SourceImage(self);self.scene.addItem(image);image.setZValue(-1)
        self.update_canvas_bounds()
        for p in props:
            obj=Annotation(p,self);self.scene.addItem(obj);self.objects.append(obj)
        self.order_annotations()
        self.set_tool(self.view.tool)
    def fit(self):self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio);self.view.sync_composition_bounds()
    def set_expand_canvas(self,value):self.expand_canvas=value;self.commit()
    def expand_to_annotations(self):
        bounds=QRectF(self.base.rect())
        for obj in self.objects:
            if obj.props["kind"]!="spotlight":bounds=bounds.united(obj.content_bounds())
        bounds=bounds.toAlignedRect()
        if bounds==self.base.rect():return
        if bounds.width()*bounds.height()>120_000_000 or max(bounds.width(),bounds.height())>100000:
            return False
        canvas=QImage(bounds.size(),QImage.Format.Format_ARGB32_Premultiplied)
        if canvas.isNull():return False
        canvas.setColorSpace(image_color_space(self.base));canvas.fill(Qt.GlobalColor.transparent)
        from .image_original import remember
        remember(self,QTransform.fromTranslate(-bounds.x(),-bounds.y()))
        painter=QPainter(canvas);painter.drawImage(-bounds.x(),-bounds.y(),self.base);painter.end();self.base=canvas
        for item in self.scene.items():
            if isinstance(item,SourceImage):item.setPixmap(QPixmap.fromImage(canvas));break
        for obj in self.objects:obj.setPos(obj.pos()-QPointF(bounds.topLeft()))
    def update_canvas_bounds(self):
        root=getattr(self,'composition_root',None)
        if root is not None:root.setRect(QRectF(self.base.rect()))
        if self.background:
            w,h,r=self.background_layout();self.scene.setSceneRect(QRectF(-r.x(),-r.y(),w,h))
        else:self.scene.setSceneRect(QRectF(self.base.rect()))
        self.scene.update();self.view.viewport().update()
    def zoom_to(self,percent):
        center=self.view.mapToScene(self.view.viewport().rect().center());self.view.resetTransform();self.view.scale(percent/100,percent/100);self.view.centerOn(center);self.view.sync_composition_bounds()
    def actual_size(self):self.zoom_to(100)
    def showEvent(self,event):super().showEvent(event);self.fit()
    def delete_selected(self):
        for obj in list(self.scene.selectedItems()):
            if obj in self.objects:self.objects.remove(obj);self.scene.removeItem(obj)
        self.commit()
    def paint_space(self):
        if self.exporting:return image_color_space(self.base)
        from PySide6.QtGui import QColorSpace
        return QColorSpace(QColorSpace.NamedColorSpace.SRgb)
    def paint_color(self,color):return convert_color(color,self.paint_space())
    def render(self,with_background=True,convert_srgb=None):
        self.order_annotations()
        result=QImage(self.base.size(),QImage.Format.Format_ARGB32_Premultiplied);result.setColorSpace(image_color_space(self.base));result.fill(Qt.GlobalColor.transparent)
        self.exporting=True
        root=getattr(self,'composition_root',None);effect=root.graphicsEffect() if root is not None else None
        effect_enabled=effect.isEnabled() if effect else False
        if effect_enabled:effect.setEnabled(False)
        for obj in self.objects:obj.update()
        painter=QPainter(result)
        try:
            self.scene.render(painter,QRectF(result.rect()),QRectF(self.base.rect()));painter.end()
            if with_background and self.background:result=self.render_background(result)
            return convert_image(result) if (self.store.settings.get("convert_srgb",True) if convert_srgb is None else convert_srgb) else result
        finally:
            if painter.isActive():painter.end()
            self.exporting=False
            if effect_enabled:effect.setEnabled(True)
            for obj in self.objects:obj.update()
    def background_layout(self):
        opts=self.background;pad=int(opts.get("padding",64));w=self.base.width()+pad*2;h=self.base.height()+pad*2
        aspect=opts.get("aspect","Auto")
        if aspect!="Auto":
            a,b=map(float,aspect.split(":"));w=max(w,int(h*a/b));h=max(h,int(w*b/a))
        align=opts.get("align","Center");x=(w-self.base.width())/2;y=(h-self.base.height())/2
        if "Left" in align:x=pad
        if "Right" in align:x=w-self.base.width()-pad
        if "Top" in align:y=pad
        if "Bottom" in align:y=h-self.base.height()-pad
        return w,h,QRectF(x,y,self.base.width(),self.base.height())
    def paint_background(self,p,w,h,r):
        opts=self.background;p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform);area=QRectF(0,0,w,h)
        if opts.get("image_data") or opts.get("image"):
            key=(opts.get("image_data") or opts.get("image"),self.paint_space())
            if getattr(self,"_background_image_key",None)!=key:
                self._background_image_key=key;self._background_image=convert_image(QImage.fromData(base64.b64decode(opts["image_data"])) if opts.get("image_data") else load_image(opts["image"]),self.paint_space())
            bg=self._background_image
            if not bg.isNull():
                ratio=max(w/bg.width(),h/bg.height());sw=w/ratio;sh=h/ratio;p.drawImage(area,bg,QRectF((bg.width()-sw)/2,(bg.height()-sh)/2,sw,sh))
        else:
            gradient=QLinearGradient(0,0,w,h);gradient.setColorAt(0,self.paint_color(opts["color"]));gradient.setColorAt(1,self.paint_color(opts.get("color2",opts["color"])));p.fillRect(area,gradient)
        radius=opts.get("radius",12)
        if opts.get("shadow",True):
            for i in range(22,0,-1):p.setBrush(QColor(0,0,0,2));p.setPen(Qt.PenStyle.NoPen);p.drawPath(rounded_path(r.adjusted(-i,-i/2,i,i),radius+i,opts.get('radius_power',2)))
    def render_background(self,image):
        w,h,r=self.background_layout();result=QImage(w,h,QImage.Format.Format_ARGB32_Premultiplied);result.setColorSpace(image_color_space(self.base));result.fill(self.paint_color(self.background["color"]));p=QPainter(result);self.paint_background(p,w,h,r);radius=self.background.get("radius",12)
        clip=rounded_path(r,radius,self.background.get('radius_power',2));p.setClipPath(clip);p.drawImage(r,image);p.end();return result
    def crop(self,rect,expand=False,fill=None):
        r=rect if expand else rect.intersected(self.base.rect())
        if r.width()<2 or r.height()<2:return False
        if max(r.width(),r.height())>100000 or r.width()*r.height()>120_000_000:
            self.statusBar().showMessage('Crop is too large. The limit is 120 megapixels.');return False
        if expand:
            canvas=QImage(r.size(),QImage.Format.Format_ARGB32_Premultiplied)
            if canvas.isNull():self.statusBar().showMessage('Could not allocate the cropped image.');return False
            canvas.setColorSpace(image_color_space(self.base));canvas.fill(fill if fill is not None else Qt.GlobalColor.transparent)
            painter=QPainter(canvas);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);painter.drawImage(-r.x(),-r.y(),self.base);painter.end()
        else:canvas=self.base.copy(r)
        # A deliberate crop fixes this image's canvas; retained editable
        # objects outside the crop must not immediately grow it back again.
        expanding=self.expand_canvas;self.expand_canvas=False;self.expand_action.blockSignals(True);self.expand_action.setChecked(False);self.expand_action.blockSignals(False)
        from .image_original import remember
        remember(self,QTransform.fromTranslate(-r.x(),-r.y()));self.base=canvas
        props=[o.data_dict() for o in self.objects]
        for p in props:p["x"]-=r.x();p["y"]-=r.y()
        self.rebuild(props);self.commit();self.fit()
        if expanding:self.statusBar().showMessage("Cropped. Automatic canvas expansion is off for this image; re-enable it from Edit.")
    def resize_image(self):
        w,ok=QInputDialog.getInt(self,"Resize image","Width (aspect ratio preserved)",self.base.width(),8,30000)
        if not ok:return
        self.resize_to(w)
    def resize_to(self,w):
        w=max(2,min(30000,int(w)))
        from .image_original import remember
        factor=w/self.base.width();remember(self,QTransform.fromScale(factor,factor));self.base=self.base.scaledToWidth(w,Qt.TransformationMode.SmoothTransformation)
        props=[o.data_dict() for o in self.objects]
        for p in props:
            for k in ("x","y","w","h","width","font_size"):
                if k in p:p[k]*=factor
            if "points" in p:p["points"]=[[x*factor,y*factor] for x,y in p["points"]]
        self.rebuild(props);self.commit();self.fit()
    def rotate(self):
        height=self.base.height();props=[o.data_dict() for o in self.objects]
        from .image_original import remember
        remember(self,QTransform(0,1,-1,0,height,0))
        rotation=QTransform().rotate(90)
        for p in props:
            p["x"],p["y"]=height-p["y"],p["x"]
            t=QTransform(*p.get("transform",[1,0,0,1,0,0]))*rotation
            p["transform"]=[t.m11(),t.m12(),t.m21(),t.m22(),t.dx(),t.dy()]
        self.base=self.base.transformed(rotation);self.rebuild(props);self.commit();self.fit()
    def flip(self,vertical=False):
        props=[o.data_dict() for o in self.objects]
        from .image_original import remember
        remember(self,QTransform(1 if vertical else -1,0,0,-1 if vertical else 1,0 if vertical else self.base.width(),self.base.height() if vertical else 0))
        for p in props:
            if vertical:p["y"]=self.base.height()-p["y"]
            else:p["x"]=self.base.width()-p["x"]
            t=QTransform(*p.get("transform",[1,0,0,1,0,0]))*QTransform.fromScale(1 if vertical else -1,-1 if vertical else 1)
            p["transform"]=[t.m11(),t.m12(),t.m21(),t.m22(),t.dx(),t.dy()]
        self.base=self.base.flipped(Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal);self.rebuild(props);self.commit()

    def smart_highlight(self,obj):
        """Snap the stroke vertically to text ink around its center line."""
        p=obj.props
        for padding in (20,40,80,160,320,640):
            r=QRectF(obj.x(),obj.y()-padding,p['w'],p['h']+2*padding).toRect().intersected(self.base.rect())
            if r.isEmpty():return
            sample=self.base.copy(r).convertToFormat(QImage.Format.Format_Grayscale8)
            a=np.asarray(sample.bits(),dtype=np.uint8).reshape(sample.height(),sample.bytesPerLine())[:,:sample.width()]
            border=np.median(np.concatenate([a[0],a[-1]]));ink=np.abs(a.astype(float)-border)>45
            rows=np.where(np.sum(ink,axis=1)>max(3,r.width()*.015))[0]
            if len(rows)<3:return
            groups=np.split(rows,np.where(np.diff(rows)>3)[0]+1);center=obj.y()+p['h']/2-r.y()
            group=min(groups,key=lambda g:abs((g[0]+g[-1])/2-center))
            # Expand only when the candidate line reaches the search boundary.
            # Otherwise large source fonts are mistaken for clipped text rows.
            if (group[0]<2 and r.top()>0) or (group[-1]>=r.height()-2 and r.bottom()<self.base.height()-1):continue
            if group[-1]-group[0]>3:
                obj.prepareGeometryChange()
                obj.setY(r.y()+int(group[0])-3);p['h']=int(group[-1]-group[0])+7
            return
    def temporary_export(self):
        path=self.store.root/"exports";path.mkdir(exist_ok=True)
        import uuid
        target=path/("OmniShot-"+uuid.uuid4().hex[:10]+".png")
        if not self.render().save(str(target)):raise RuntimeError("Could not write image")
        return target
    def copy_image(self):
        try:
            backend.copy_image(self.temporary_export(),self.store,name=self.store.display_name(self.path));self.statusBar().showMessage("Copied image")
            if not QApplication.keyboardModifiers()&Qt.KeyboardModifier.AltModifier:self.close()
        except Exception as exc:error(self,exc)
    def save_image(self):
        direct=bool(QApplication.keyboardModifiers()&Qt.KeyboardModifier.AltModifier)
        extension=self.store.settings.get("format","png")
        folder=self.store.settings.get("annotation_save_dir") if not direct else None
        if folder and not Path(folder).is_dir():folder=None
        try:destination=self.store.export_target(self.path,folder=folder,extension=extension)
        except OSError as exc:error(self,exc);return
        if direct:path=str(destination)
        else:path,_=QFileDialog.getSaveFileName(self,"Save capture",str(destination),"PNG (*.png);;JPEG (*.jpg);;WebP (*.webp);;HEIC (*.heic)")
        if path:
            try:
                export_image(self.render(),path)
                if not direct:
                    self.store.settings["annotation_save_dir"]=str(Path(path).resolve().parent)
                    try:self.store.save_settings()
                    except OSError as exc:
                        self.saved.emit(path);self.statusBar().showMessage(f"Saved {Path(path).name}; could not remember folder: {exc}");return
                self.saved.emit(path);self.statusBar().showMessage(f"Saved {Path(path).name}")
                if not direct and not QApplication.keyboardModifiers()&Qt.KeyboardModifier.AltModifier:self.close()
            except Exception as exc:error(self,exc)
    def drag_image(self):
        from .drag import execute
        keep=bool(QApplication.keyboardModifiers()&Qt.KeyboardModifier.AltModifier)
        try:
            if self.inline:self.inline.finish()
            path=self.temporary_export();mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(path))]);mime.setImageData(self.render())
            drag=QDrag(self);drag.setMimeData(mime);drag.setPixmap(QPixmap.fromImage(self.render()).scaled(160,120,Qt.AspectRatioMode.KeepAspectRatio))
            if execute(drag) and not keep:self.close()
        except Exception as exc:error(self,exc)
    def pin(self):
        try:
            if self.inline:self.inline.finish()
            if self.crop_session:self.statusBar().showMessage('Finish or cancel the crop before pinning.');return
            if self.draft_path:
                if not self.save_draft():raise RuntimeError(self.draft_error)
                if self.draft_preview_error:raise RuntimeError(self.draft_preview_error)
                self.pin_requested.emit(str(self.path))
            else:self.pin_requested.emit(str(self.temporary_export()))
        except Exception as exc:error(self,exc)
    def insert_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,"Insert image",str(Path.home()),IMAGE_FILTER)
        if path:self.insert_image(path,QPointF(20,20))
    def insert_image(self,path,pos):
        image=load_image(path)
        if image.isNull():error(self,"Could not open image");return
        self.insert_qimage(image,pos)
    def insert_qimage(self,image,pos):
        p={"kind":"image","x":pos.x(),"y":pos.y(),"w":image.width(),"h":image.height(),"image":base64.b64encode(png_bytes(image)).decode(),"z":len(self.objects)+1}
        obj=Annotation(p,self);self.objects.append(obj);self.scene.addItem(obj);self.commit()
    def drop_images(self,mime,pos):
        paths=[url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
        if paths:images=[load_image(path) for path in paths]
        elif mime.hasFormat('image/png'):
            # Qt's generic Wayland image negotiation may choose an opaque
            # representation. Request PNG explicitly to retain transparency.
            images=[QImage.fromData(mime.data('image/png'))]
        elif mime.hasImage():
            payload=mime.imageData()
            images=[payload.toImage() if isinstance(payload,QPixmap) else QImage(payload)]
        else:return False
        # Validate the whole drop before adding anything, so a bad file cannot
        # leave a partial batch or cause the source to discard the originals.
        if any(image.isNull() for image in images):raise ValueError('Could not open a dropped image.')
        if sum(image.width()*image.height() for image in images)>120_000_000:
            raise ValueError('Dropped images exceed the 120 megapixel limit.')
        objects=[];first=max((obj.props.get('z',1) for obj in self.objects),default=0)+1
        for index,image in enumerate(images):
            objects.append(Annotation(dict(kind='image',x=pos.x()+20*index,y=pos.y()+20*index,
                w=image.width(),h=image.height(),image=base64.b64encode(png_bytes(image)).decode(),z=first+index),self))
        if self.inline:self.inline.finish()
        self.scene.clearSelection()
        for obj in objects:self.objects.append(obj);self.scene.addItem(obj);obj.setSelected(True)
        self.commit();self.set_tool('select');return True
    def combine_dialog(self):
        paths,_=QFileDialog.getOpenFileNames(self,"Combine images","",IMAGE_FILTER)
        if not paths:return
        direction,ok=QInputDialog.getItem(self,"Combine images","Attach images",["Below","Right","Above","Left"],0,False)
        if ok:
            for path in paths:
                image=load_image(path)
                if not image.isNull():self.combine(image,direction)
    def combine(self,image,direction):
        w,h=self.base.width(),self.base.height();iw,ih=image.width(),image.height();props=[o.data_dict() for o in self.objects]
        nw,nh=(max(w,iw),h+ih) if direction in ("Above","Below") else (w+iw,max(h,ih))
        canvas=QImage(nw,nh,QImage.Format.Format_ARGB32_Premultiplied);canvas.setColorSpace(image_color_space(self.base));canvas.fill(Qt.GlobalColor.transparent)
        dx=iw if direction=="Left" else 0;dy=ih if direction=="Above" else 0
        from .image_original import remember
        remember(self,QTransform.fromTranslate(dx,dy))
        painter=QPainter(canvas);painter.drawImage(dx,dy,self.base);painter.end()
        for p in props:p["x"]+=dx;p["y"]+=dy
        self.base=canvas;self.rebuild(props)
        pos=QPointF(0,h) if direction=="Below" else QPointF(w,0) if direction=="Right" else QPointF(0,0)
        self.insert_qimage(image,pos);self.fit()
    def copy_selection(self):
        selected=sorted((obj for obj in self.objects if obj.isSelected()),key=lambda obj:obj.zValue())
        if not selected:return self.copy_image()
        from .annotation_clipboard import encode,publish
        try:
            data=encode([obj.data_dict() for obj in selected])
            publish(data,png_bytes(self.render()),self.store)
            self.statusBar().showMessage(f"Copied {len(selected)} editable annotations")
        except Exception as exc:error(self,exc)
    def paste_content(self,content):
        from .annotation_clipboard import decode
        if self.crop_session:raise ValueError('Finish cropping before pasting')
        if content.annotations is not None:
            props=decode(content.annotations)
        else:
            images=content.images or ([content.image] if content.image is not None else [load_image(path) for path in content.files])
            if not images or any(image.isNull() for image in images):raise ValueError('Paste an image into Annotate. Use Open from clipboard for video files.')
            props=[dict(kind='image',x=20+index*20,y=20+index*20,w=image.width(),h=image.height(),image=base64.b64encode(png_bytes(image)).decode()) for index,image in enumerate(images)]
        # Construct every object before changing the document or its undo history.
        first=max((obj.props.get('z',1) for obj in self.objects),default=0)+1
        objects=[]
        for index,p in enumerate(props):
            p['z']=first+index
            if content.annotations is not None:p.update(x=p.get('x',0)+20,y=p.get('y',0)+20)
            objects.append(Annotation(p,self))
        if content.annotations is not None and objects:
            bounds=QRectF()
            for obj in objects:bounds=bounds.united(obj.content_bounds())
            canvas=QRectF(self.base.rect())
            if not bounds.intersects(canvas):
                offset=canvas.center()-bounds.center()
                for obj in objects:obj.setPos(obj.pos()+offset)
        self.scene.clearSelection()
        for obj in objects:self.scene.addItem(obj);self.objects.append(obj);obj.setSelected(True)
        self.commit();self.set_tool('select')
    def paste_image(self):
        from .clipboard import read_for_paste
        from .widgets import background
        from shiboken6 import isValid
        if self.crop_session:self.statusBar().showMessage('Finish cropping before pasting');return
        token=object();self.clipboard_token=token;path=self.path;state=self.undo_states[self.undo_index]
        def current():return isValid(self) and self.clipboard_token is token and self.path==path and self.undo_states[self.undo_index] is state and not self.crop_session
        def done(content):
            if not current():return
            try:self.paste_content(content)
            except Exception as exc:error(self,exc)
        background(read_for_paste,done,lambda message:error(self,message) if current() else None)
    def save_project(self):
        try:destination=self.store.export_target(self.path,extension="omnishot")
        except OSError as exc:error(self,exc);return
        path,_=QFileDialog.getSaveFileName(self,"Save editable project",str(destination),"OmniShot project (*.omnishot)")
        if path:
            if not path.lower().endswith(".omnishot"):path+=".omnishot"
            try:self.write_project(path);self.statusBar().showMessage("Editable project saved")
            except Exception as exc:error(self,exc)
    def write_project(self,path):
        from .image_original import values
        background=copy.deepcopy(self.background)
        if background and background.get("image") and not background.get("image_data"):
            background["image_data"]=base64.b64encode(png_bytes(load_image(background.pop("image")))).decode()
        from .storage import atomic_output
        with atomic_output(path) as temporary:
            with zipfile.ZipFile(temporary,"w",zipfile.ZIP_DEFLATED) as z:
                data={"version":2,"objects":[o.data_dict() for o in self.objects],"background":background,"expand_canvas":self.expand_canvas}
                if self.original_image is not None:
                    data.update(original_image='original.png',source_transform=values(self.source_transform));z.writestr('original.png',png_bytes(self.original_image))
                z.writestr("image.png",png_bytes(self.base));z.writestr("project.json",json.dumps(data))
                if sum(info.file_size for info in z.infolist())>512_000_000:raise ValueError('Project is too large')
    def load_project(self,path):
        from .image_project import read_project
        image,data,original,transform=read_project(path)
        self.base=image;self.original_image=original;self.source_transform=transform
        self.background=data.get("background");self.expand_canvas=bool(data.get("expand_canvas",False));self.expand_action.blockSignals(True);self.expand_action.setChecked(self.expand_canvas);self.expand_action.blockSignals(False);self.rebuild(data["objects"]);self.commit()
    def open_file(self):
        path,_=QFileDialog.getOpenFileName(self,"Open image or project","",IMAGE_FILTER+";;OmniShot project (*.omnishot)")
        if path:
            if self.inline:self.inline.finish()
            if not self.save_draft():error(self,"Could not preserve the current edits. Save an editable project before opening another image.\n"+self.draft_error);return
            try:path=str(self.store.import_file(path))
            except Exception as exc:error(self,exc);return
            draft=self.store.image_edit_path(path);previous=self.snapshot();undo_states=self.undo_states;undo_index=self.undo_index
            self.draft_timer.stop();self.undo_states=[];self.undo_index=-1
            try:
                if draft.exists():self.load_project(draft)
                elif path.endswith(".omnishot"):self.load_project(path)
                else:
                    image=load_image(path)
                    if image.isNull():raise ValueError("Could not open image")
                    from .backgrounds import default_background
                    self.base=image;self.original_image=None;self.source_transform=QTransform();self.background=default_background(self.store);self.expand_canvas=self.store.settings.get("auto_expand_canvas",False)
                    self.expand_action.blockSignals(True);self.expand_action.setChecked(self.expand_canvas);self.expand_action.blockSignals(False)
                    self.rebuild([]);self.commit()
            except Exception as exc:
                self.restore(previous);self.undo_states=undo_states;self.undo_index=undo_index;self.draft_timer.stop();error(self,exc);return
            self.path=Path(path);self.draft_path=draft;self.draft_timer.start(1200);self.fit()
    def extract_text(self):
        from .widgets import background
        from shiboken6 import isValid
        path=self.temporary_export();languages=self.store.settings["ocr_languages"];linebreaks=self.store.settings["ocr_linebreaks"]
        self.statusBar().showMessage("Recognizing text…")
        from .text_result import extract,present
        def work():return extract(path,languages,linebreaks)
        def done(value):
            if not isValid(self):return
            self.statusBar().showMessage("Text recognized" if value else "No text found")
            present(value,self.store.settings,self,review=True)
        background(work,done,lambda msg:error(self,msg) if isValid(self) else None)
    def print_image(self):
        from .printing import print_image
        try:
            if self.inline:self.inline.finish()
            if self.crop_session:self.statusBar().showMessage('Finish or cancel the crop before printing.');return
            print_image(self.render(),self,self.store.display_name(self.path))
        except Exception as exc:error(self,exc)
    def background_dialog(self):
        from .backgrounds import BackgroundDialog
        BackgroundDialog(self).exec()
