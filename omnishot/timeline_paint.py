"""Viewport-sized rendering for the source-time thumbnail timeline."""
from .theme import color as theme_color
import math
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QPolygonF,QBrush,QPalette


def paint(t):
    p=QPainter(t);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    background=theme_color('base');muted=theme_color('muted')
    p.fillRect(t.rect(),background);p.setClipRect(t.plot_rect())
    p.setPen(muted);font=p.font();font.setPointSizeF(8.5);p.setFont(font)
    steps=sorted(set([1/t.fps,2/t.fps,5/t.fps,.1,.2,.5,1,2,5,10,15,30,60,120,300,600,1800,3600,7200,21600,86400]))
    step=next((s for s in steps if s*t.pixels_per_second()>=62),86400)
    left=t.offset();right=min(t.duration,left+t.visible_span());last_label_right=-math.inf
    for i in range(math.floor(left/step),math.ceil(right/step)+1):
        seconds=i*step;x=t.x(seconds)
        if seconds<0 or seconds>t.duration or x<t.plot_rect().left() or x>t.plot_rect().right():continue
        whole=int(seconds);label=f'{whole//3600}:{whole//60%60:02}:{whole%60:02}' if whole>=3600 else f'{whole//60:02}:{whole%60:02}'
        if step<1:label+=f'.{round((seconds-whole)*1000):03}'
        label_width=p.fontMetrics().horizontalAdvance(label)+8
        label_x=max(t.plot_rect().left(),min(t.plot_rect().right()-label_width,x-label_width/2))
        if label_x>=last_label_right+8:
            p.setPen(muted);p.drawText(QRectF(label_x,0,label_width,22),Qt.AlignmentFlag.AlignCenter,label)
            last_label_right=label_x+label_width
        p.setPen(theme_color('border'));p.drawLine(QPointF(x,25),QPointF(x,116))
    zoom_row=QRectF(t.plot_rect().left(),t.ZOOM_Y,t.plot_rect().width(),24)
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(theme_color('surface'));p.drawRoundedRect(zoom_row,5,5)
    if not t.zooms:
        p.setPen(muted);p.drawText(zoom_row,Qt.AlignmentFlag.AlignCenter,'Click or drag to add zoom')
    if t.last_pointer is not None and zoom_row.contains(t.last_pointer) and not t.drag:
        gap=t.zoom_gap(t.time_at(t.last_pointer.x()))
        if gap:
            a,b=gap;hover=QRectF(t.x(a),t.ZOOM_Y,t.x(b)-t.x(a),24).intersected(zoom_row)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(theme_color('hover'));p.drawRoundedRect(hover,5,5)
            if hover.width()>60:p.setPen(muted);p.drawText(hover,Qt.AlignmentFlag.AlignCenter,'+ Zoom')
    for i,zoom in enumerate(t.zooms):
        r=t.clip_rect('zoom',i);visible=r.intersected(t.plot_rect())
        if visible.isEmpty():continue
        selected=t.selected==('zoom',i)
        p.setPen(QPen(theme_color('accent' if selected else 'border'),1.5));p.setBrush(theme_color('accent' if selected else 'hover'));p.drawRoundedRect(visible,5,5)
        p.setPen(theme_color('on_accent' if selected else 'foreground'))
        if visible.width()>62:p.drawText(visible,Qt.AlignmentFlag.AlignCenter,f"Zoom {zoom['scale']*100:.0f}%")
        handles(p,t,r)
    row=QRectF(t.plot_rect().left(),t.VIDEO_Y,t.plot_rect().width(),t.VIDEO_HEIGHT)
    video=QRectF(t.x(0),t.VIDEO_Y,t.x(t.duration)-t.x(0),t.VIDEO_HEIGHT).intersected(row)
    if video.isEmpty():p.end();return
    clip=QPainterPath();edges=[0]+[s for s in t.splits if 0<s<t.duration]+[t.duration]
    for a,b in zip(edges,edges[1:]):
        gap=min(2,max(0,(t.x(b)-t.x(a))/4)) if t.splits else 0
        r=QRectF(t.x(a)+gap,t.VIDEO_Y,max(.1,t.x(b)-t.x(a)-2*gap),t.VIDEO_HEIGHT).intersected(row)
        if not r.isEmpty():clip.addRoundedRect(r,5,5)
    p.save();p.setClipPath(clip,Qt.ClipOperation.IntersectClip)
    p.fillRect(video,theme_color('surface'))
    for milliseconds,a,b in t.thumbnail_tiles():
        tile=QRectF(t.x(a),t.VIDEO_Y,t.x(b)-t.x(a),t.VIDEO_HEIGHT)
        image=t.thumbnails.get(milliseconds) if t.thumbnails else None
        if image is not None:p.drawImage(tile,image)
        else:
            p.setPen(theme_color('border'));p.drawRect(tile.adjusted(1,1,-1,-1))
    for a,b in [(0,t.start),(t.end or t.duration,t.duration)]:
        if b>a:p.fillRect(QRectF(t.x(a),t.VIDEO_Y,t.x(b)-t.x(a),t.VIDEO_HEIGHT).intersected(row),QColor(0,0,0,155))
    for i in range(len(t.cuts)):
        r=t.clip_rect('cut',i);visible=r.intersected(row)
        if visible.isEmpty():continue
        p.fillRect(visible,QColor(130,20,36,120));p.fillRect(visible,QBrush(QColor(255,120,137,150),Qt.BrushStyle.BDiagPattern))
        p.setPen(QPen(theme_color('accent' if t.selected==('cut',i) else 'red'),2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(visible.adjusted(1,1,-1,-1))
        if visible.width()>40:p.drawText(visible,Qt.AlignmentFlag.AlignCenter,'Cut')
        if t.selected==('cut',i):handles(p,t,r)
    p.restore()
    trim=t.clip_rect('trim');p.save();p.setClipPath(clip,Qt.ClipOperation.IntersectClip);p.setPen(QPen(theme_color('accent' if t.selected==('trim',0) else 'foreground'),2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(trim.intersected(row).adjusted(1,1,-1,-1),5,5);handles(p,t,trim);p.restore()
    if t.selected and t.selected[0]=='clip' and t.selected[1]<len(t.clips()):
        r=t.clip_rect('clip',t.selected[1]).intersected(row).adjusted(2,1,-2,-1)
        p.setPen(QPen(theme_color('accent'),2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(r,5,5)
        handles(p,t,t.clip_rect('clip',t.selected[1]))
    if t.cut_mode and t.last_pointer is not None and row.contains(t.last_pointer):
        x=t.x(round(t.time_at(t.last_pointer.x())*t.fps)/t.fps);p.setPen(QPen(muted,1));p.drawLine(QPointF(x,25),QPointF(x,114))
    x=t.x(t.position);p.setPen(QPen(theme_color('red'),1.5));p.drawLine(QPointF(x,23),QPointF(x,118));p.setBrush(theme_color('red'))
    p.drawPolygon(QPolygonF([QPointF(x-4,21),QPointF(x+4,21),QPointF(x+4,25),QPointF(x,29),QPointF(x-4,25)]));p.end()


def handles(p,t,r):
    p.setPen(QPen(theme_color('foreground'),2))
    for x in (r.left()+4,r.right()-4):
        if t.plot_rect().left()<=x<=t.plot_rect().right():p.drawLine(QPointF(x,r.center().y()-5),QPointF(x,r.center().y()+5))
