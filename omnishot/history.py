"""Capture-history filmstrip, with lazy previews and local recovery actions."""
from .theme import color as theme_color
from collections import OrderedDict
from pathlib import Path
from threading import Event
import datetime
from PySide6.QtCore import Qt,QSize,QRectF,QTimer,Signal,QFileSystemWatcher,QItemSelectionModel
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QImage,QKeySequence,QShortcut
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QListWidget,QListWidgetItem,
    QListView,QAbstractItemView,QStyledItemDelegate,QStyle,QPushButton,QButtonGroup,QLabel,QMenu,QMessageBox)
from .images import load_image,convert_image

ROW_ROLE=int(Qt.ItemDataRole.UserRole)+1


def thumbnail(row,store,cancel):
    path=Path(row.get('preview',row['path']))
    if cancel.is_set():return QImage()
    if path.suffix.lower()=='.omnishot':
        from .image_project import read_project
        image=read_project(path)[0]
    elif row['kind']=='video':
        if path.suffix.lower()=='.omnishot-video':
            from .video_project import read_project
            path=read_project(path,store)[0]
        if cancel.is_set():return QImage()
        from .timeline_thumbnails import decode
        image=decode(path,[0],cancel,maximum=(480,320)).get(0) or QImage()
    else:image=load_image(path,QSize(480,320))
    return convert_image(image.scaled(480,320,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))


def thumbnail_key(row):
    path=Path(row.get('preview',row['path']))
    try:stat=path.stat();return str(path),stat.st_mtime_ns,stat.st_size
    except OSError:return str(path),0,0


class Filmstrip(QListWidget):
    viewport_changed=Signal()
    delete_pressed=Signal()
    def __init__(self,parent):
        super().__init__(parent);self.setViewMode(QListView.ViewMode.IconMode);self.setFlow(QListView.Flow.LeftToRight);self.setWrapping(False)
        self.setMovement(QListView.Movement.Static);self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.setUniformItemSizes(True)
        self.setGridSize(QSize(260,190));self.setSpacing(9);self.setFixedHeight(212)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel);self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet('QListWidget { border:0; background:transparent; outline:0; }')
        self.horizontalScrollBar().valueChanged.connect(self.viewport_changed)
    def resizeEvent(self,event):super().resizeEvent(event);self.viewport_changed.emit()
    def wheelEvent(self,event):
        delta=event.pixelDelta().x() or event.pixelDelta().y() or event.angleDelta().x()/2 or event.angleDelta().y()/2
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-round(delta));event.accept()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Delete:self.delete_pressed.emit();event.accept()
        else:super().keyPressEvent(event)


class CardDelegate(QStyledItemDelegate):
    def __init__(self,history):super().__init__(history.list);self.history=history
    def sizeHint(self,option,index):return QSize(260,190)
    def paint(self,painter,option,index):
        row=index.data(ROW_ROLE);image=self.history.images.get(thumbnail_key(row));rect=QRectF(option.rect).adjusted(5,5,-5,-5)
        selected=bool(option.state&QStyle.StateFlag.State_Selected)
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing);clip=QPainterPath();clip.addRoundedRect(rect,16,16)
        painter.setClipPath(clip);painter.fillRect(rect,theme_color('surface'))
        if image is not None and not image.isNull():
            size=image.size().scaled(rect.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
            target=QRectF(0,0,size.width(),size.height());target.moveCenter(rect.center());painter.drawImage(target,image)
        else:
            painter.setPen(theme_color('muted'));label='Video' if row['kind']=='video' else 'GIF' if row['kind']=='gif' else 'Screenshot'
            painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,label)
        if row['kind'] in ('video','gif'):
            badge=QRectF(rect.left()+10,rect.bottom()-30,48,21);painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(0,0,0,165));painter.drawRoundedRect(badge,6,6);painter.setPen(QColor('white'));painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,'▶' if row['kind']=='video' else 'GIF')
        painter.setClipping(False)
        if selected:
            painter.setPen(QPen(theme_color('accent'),4));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRoundedRect(rect.adjusted(-1,-1,1,1),17,17)
        painter.restore()


class History(QDialog):
    open_capture=Signal(str);pin_capture=Signal(str);restore_capture=Signal(str)
    def __init__(self,store,remove_captures=None):
        super().__init__();self.store=store;self.remove_captures=remove_captures or self.remove_owned;self.setWindowTitle('OmniShot — Capture History');self.resize(960,345)
        self.images=OrderedDict();self.pending=set();self.cancel=Event();self.closed=False;self.kind='all';self.rows=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(20,18,20,16);layout.setSpacing(12)
        tabs=QHBoxLayout();tabs.addStretch();self.filters={};self.group=QButtonGroup(self);self.group.setExclusive(True)
        for label,kind in [('All','all'),('Screenshots','image'),('Videos','video'),('GIFs','gif')]:
            b=QPushButton(label);b.setCheckable(True);b.setChecked(kind=='all');b.setMinimumWidth(78);b.clicked.connect(lambda checked,k=kind:self.set_filter(k));self.filters[kind]=b;self.group.addButton(b);tabs.addWidget(b)
            b.setStyleSheet('QPushButton { border:0; border-radius:12px; padding:5px 15px; } QPushButton:checked { background:palette(highlight); color:palette(highlighted-text); }')
        tabs.addStretch();self.more=QPushButton('⋯');self.more.setFixedWidth(36);self.more.setToolTip('History actions');self.more.clicked.connect(self.menu);tabs.addWidget(self.more);layout.addLayout(tabs)
        self.search=QLineEdit();self.search.setPlaceholderText('Search capture names…');self.search.hide();self.search.textChanged.connect(self.refresh);layout.addWidget(self.search)
        self.list=Filmstrip(self);self.list.setItemDelegate(CardDelegate(self));layout.addWidget(self.list)
        footer=QHBoxLayout();self.count=QLabel();self.count.setObjectName('muted');footer.addWidget(self.count,1)
        self.restore_button=QPushButton('↩ Restore');self.restore_button.setObjectName('primary');self.restore_button.setMinimumWidth(130);self.restore_button.clicked.connect(lambda:self.emit_selected(self.restore_capture));footer.addWidget(self.restore_button)
        self.restore_button.setStyleSheet('QPushButton { background:palette(highlight); color:palette(highlighted-text); border:0; border-radius:9px; padding:6px 15px; } QPushButton:hover { background:palette(light); color:palette(window-text); } QPushButton:disabled { background:palette(mid); }')
        right=QLabel('');footer.addWidget(right,1);layout.addLayout(footer)
        self.list.itemDoubleClicked.connect(lambda _:self.emit_selected(self.open_capture));self.list.itemSelectionChanged.connect(self.selection_changed)
        self.list.delete_pressed.connect(self.delete)
        self.list.viewport_changed.connect(self.request_thumbnails);self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.list.customContextMenuRequested.connect(self.menu)
        for sequence,slot in [('Return',lambda:self.emit_selected(self.restore_capture)),('Ctrl+O',lambda:self.emit_selected(self.open_capture)),('Ctrl+P',lambda:self.emit_selected(self.pin_capture)),('Ctrl+F',self.show_search)]:QShortcut(QKeySequence(sequence),self,activated=slot)
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True);self.refresh_timer.setInterval(150);self.refresh_timer.timeout.connect(self.refresh)
        self.watcher=QFileSystemWatcher(self);self.watcher.directoryChanged.connect(lambda _:self.refresh_timer.start());self.watch();self.refresh()
        self.finished.connect(self.shutdown)
    def watch(self):
        paths=[self.store.root,self.store.captures,self.store.root/'image-edits',self.store.root/'video-edits']
        existing=set(self.watcher.directories());added=[str(p) for p in paths if p.is_dir() and str(p) not in existing]
        if added:self.watcher.addPaths(added)
    def show_search(self):self.search.show();self.search.setFocus();self.search.selectAll()
    def set_filter(self,kind):self.kind=kind;self.refresh()
    def current(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
    def selected(self):return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if self.list.item(i).isSelected()]
    def emit_selected(self,signal):
        for path in self.selected():
            if signal==self.pin_capture and next((r['kind'] for r in self.rows if r['path']==path),None)=='video':continue
            signal.emit(path)
    def selection_changed(self):
        count=len(self.selected());self.restore_button.setEnabled(bool(count));self.restore_button.setText(f'↩ Restore {count}' if count>1 else '↩ Restore')
        self.count.setText(f'{len(self.rows)} capture'+('' if len(self.rows)==1 else 's'));self.list.viewport().update()
    def refresh(self):
        if self.closed:return
        self.watch();selected=set(self.selected());current=self.current();scroll=self.list.horizontalScrollBar().value()
        rows=self.store.history(search=self.search.text())
        self.rows=[r for r in rows if self.kind=='all' or r['kind'] in ('image','scroll') and self.kind=='image' or r['kind']==self.kind]
        self.list.blockSignals(True);self.list.clear()
        for row in self.rows:
            item=QListWidgetItem();item.setData(Qt.ItemDataRole.UserRole,row['path']);item.setData(ROW_ROLE,row)
            item.setData(Qt.ItemDataRole.AccessibleTextRole,row['name']);item.setToolTip(row['name']+'\n'+datetime.datetime.fromtimestamp(row['created']).strftime('%b %d, %Y at %H:%M'))
            self.list.addItem(item)
            if row['path']==current:self.list.setCurrentItem(item,QItemSelectionModel.SelectionFlag.NoUpdate)
            item.setSelected(row['path'] in selected)
        if self.list.count() and not self.list.selectedItems():self.list.setCurrentRow(0)
        self.list.blockSignals(False);self.list.horizontalScrollBar().setValue(scroll);self.selection_changed();QTimer.singleShot(0,self.request_thumbnails)
    def request_thumbnails(self):
        if self.closed:return
        viewport=self.list.viewport().rect().adjusted(-260,0,260,0)
        for i,row in enumerate(self.rows):
            if len(self.pending)>=2:break
            if not self.list.visualItemRect(self.list.item(i)).intersects(viewport):continue
            key=thumbnail_key(row)
            if key in self.images or key in self.pending:continue
            self.pending.add(key);cancel=self.cancel
            from .widgets import background
            background(lambda r=dict(row):thumbnail(r,self.store,cancel),lambda image,k=key:self.thumbnail_done(k,image),lambda message,k=key:self.thumbnail_done(k,QImage()))
    def thumbnail_done(self,key,image):
        self.pending.discard(key)
        if self.closed:return
        self.images[key]=image;self.images.move_to_end(key)
        while len(self.images)>96:self.images.popitem(last=False)
        self.list.viewport().update();self.request_thumbnails()
    def remove_owned(self,paths):
        for path in paths:self.store.remove(path)
    def delete(self):self.remove_paths(self.selected())
    def remove_paths(self,paths):
        if not paths:return
        try:self.remove_captures(paths)
        except Exception as exc:QMessageBox.warning(self,'Could not remove capture',str(exc))
        self.refresh()
    def clear(self):
        paths=[row['path'] for row in self.store.history()]
        if not paths:return
        answer=QMessageBox.question(self,'Clear Capture History',f'Remove all {len(paths)} captures and their editable history?\n\nFiles saved outside History will be kept. This cannot be undone.',QMessageBox.StandardButton.Cancel|QMessageBox.StandardButton.Yes,QMessageBox.StandardButton.Cancel)
        if answer==QMessageBox.StandardButton.Yes:self.remove_paths(paths)
    def menu(self,*args):
        menu=QMenu(self);selected=bool(self.selected())
        can_pin=any(r['path'] in self.selected() and r['kind']!='video' for r in self.rows)
        for label,slot in [('Restore',lambda:self.emit_selected(self.restore_capture)),('Open in Annotate',lambda:self.emit_selected(self.open_capture)),('Pin',lambda:self.emit_selected(self.pin_capture)),('Delete',self.delete)]:menu.addAction(label,slot).setEnabled(selected and (label!='Pin' or can_pin))
        menu.addSeparator();menu.addAction('Search…',self.show_search);menu.addAction('Clear History…',self.clear).setEnabled(bool(self.store.history()))
        menu.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))
    def closeEvent(self,event):
        self.shutdown();super().closeEvent(event)
    def shutdown(self,*args):
        self.closed=True;self.cancel.set();self.refresh_timer.stop();self.images.clear()
