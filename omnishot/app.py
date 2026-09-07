from __future__ import annotations
import argparse
import io
import json
import os
if "OMNISHOT_PREVIOUS_PRELOAD" in os.environ:
    previous_preload=os.environ.pop("OMNISHOT_PREVIOUS_PRELOAD")
    if previous_preload:os.environ["LD_PRELOAD"]=previous_preload
    else:os.environ.pop("LD_PRELOAD",None)
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QTimer,QUrl,QProcess
from PySide6.QtGui import QIcon,QPixmap,QPainter,QColor,QFont,QImage,QKeySequence,QShortcut
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QFileDialog,QSystemTrayIcon,QMenu,QMessageBox)
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from . import backend
from .theme import ThemeManager,color as theme_color
from .editor import Editor,png_bytes,error
from .widgets import button,background,cursor_position,QuickOverlay,Pin,History,Settings,ScrollPanel
from .selection import Selector
from .images import load_image, save_image


class Controller:
    def __init__(self,app):
        self.app=app;self.theme=ThemeManager(app);self.store=backend.Store();self.windows=[];self.overlays=[];self.pins=[];self.selectors=[];self.busy=False;self.last_closed=None
        self.panel=None;self.recorder=None;self.selection_mirror=None;self.quit_after_recording=False;self.hidden_for_capture=[];self.store.expire();self.app.setQuitOnLastWindowClosed(False)
        self.icon=self.make_icon();self.app.setWindowIcon(self.icon)
        self.theme.changed.connect(self.apply_theme)
        self.tray=QSystemTrayIcon(self.icon,self.app);self.tray.setToolTip("OmniShot — Capture & Annotate")
        self.menu=QMenu()
        for name,command in [("All-In-One…","all-in-one"),("Capture Area","area"),("Capture Window","window"),("Capture Fullscreen","fullscreen"),
            ("Capture Previous Area","previous"),("Scrolling Capture…","scroll"),("Horizontal Scrolling…","scroll-horizontal"),
            ("Self Timer…","timer"),("Capture Text (OCR)","ocr"),("Record Screen…","record"),("Open Image…","open"),
            ("Open from Clipboard","clipboard"),("Capture History","history"),("Restore Last Overlay","restore"),("Settings…","settings")]:
            self.menu.addAction(name,lambda checked=False,c=command:self.dispatch({"command":c}))
        self.menu.addAction("Stop Recording",lambda:self.dispatch({"command":"stop"}))
        self.menu.addAction("Pause / Resume Recording",lambda:self.dispatch({"command":"pause"}))
        self.menu.addSeparator();self.menu.addAction("Hide/show pinned images",self.toggle_pins);self.menu.addAction("Unlock pinned images",self.unlock_pins)
        self.menu.addAction("Close all pinned images",self.close_pins)
        self.menu.addAction("Quit OmniShot",self.request_quit);self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason:self.show_menu() if reason==QSystemTrayIcon.ActivationReason.Trigger else None)
        self.shell_probe_pending=False;self.shell_available=False
        self.shell_timer=QTimer(self.app);self.shell_timer.setInterval(10000);self.shell_timer.timeout.connect(self.refresh_shell_panel);self.shell_timer.start()
        self.refresh_shell_panel()
        self.app.aboutToQuit.connect(self.cleanup)
        interrupted=list(self.store.captures.glob("*.recording.json"))+list(self.store.captures.glob("*.discarding.json"))
        if interrupted:QTimer.singleShot(500,lambda:self.recover_interrupted(interrupted))

    def recover_interrupted(self,markers):
        from .recording_journal import recover_interrupted
        def done(result):
            if result["pending"]:QTimer.singleShot(1000,lambda:self.recover_interrupted(result["pending"]))
            for path,message in result["recovered"]:self.recovered_recording(path,message)
            if result["failed"]:
                error(None,"An interrupted recording could not be recovered automatically. Its source files were kept:\n\n"+"\n".join(result["failed"]))
        background(lambda:recover_interrupted(self.store,markers),done,lambda msg:error(None,msg))

    def make_icon(self):
        pix=QPixmap(64,64);pix.fill(Qt.GlobalColor.transparent);p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setBrush(theme_color("accent"));p.setPen(Qt.PenStyle.NoPen);p.drawRoundedRect(3,3,58,58,15,15);p.setPen(theme_color("on_accent"));p.setFont(QFont("sans-serif",38));p.drawText(pix.rect(),Qt.AlignmentFlag.AlignCenter,"⌗");p.end();return QIcon(pix)

    def retain(self,window):
        self.track_window(window,self.windows);window.show();return window

    def track_window(self,window,collection):
        collection.append(window);window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(lambda:collection.remove(window) if window in collection else None)

    def hide_capture_windows(self):
        self.hidden_for_capture=[]
        from .text_result import DIALOGS
        for window in dict.fromkeys(self.windows+self.overlays+self.pins+list(DIALOGS)):
            if window.isVisible():self.hidden_for_capture.append(window);window.hide()
        if self.panel:self.panel.hide()

    def restore_capture_windows(self):
        from shiboken6 import isValid
        for window in self.hidden_for_capture:
            if isValid(window):window.show()
        self.hidden_for_capture=[]

    def dispatch(self,args):
        command=args.get("command","menu");path=args.get("path")
        try:
            if args.get("via_url") and not self.store.settings.get("url_api_enabled",True):raise ValueError("URL commands are disabled. Enable the URL scheme API in Advanced settings to use this link.")
            if command in backend.OCR_SHORTCUTS:
                args={**args,"linebreaks":backend.OCR_SHORTCUTS[command]};command="ocr"
            if args.get("url_coordinates"):
                from .api import url_geometry
                args["geometry"]=backend.geometry_text(url_geometry(args["url_coordinates"],backend.capture_monitors(),backend.hypr("cursorpos")))
            if command=="menu":self.show_menu()
            elif command=="all-in-one":self.capture("select",args)
            elif command in backend.AREA_SHORTCUTS:self.capture("area",{**args,"action":args.get("action",command)})
            elif command=="open":
                if not path:path,_=QFileDialog.getOpenFileName(None,"Open in OmniShot","","Images, videos and projects (*.png *.jpg *.jpeg *.webp *.heic *.heif *.omnishot *.omnishot-video *.mp4 *.gif *.webm *.mov *.mkv)")
                if path:self.edit(path)
            elif command=="clipboard":
                from .clipboard import read_content
                def opened(content):
                    try:
                        if content.files:
                            for source in content.files:self.edit(source)
                        else:self.edit(self.store.add(image=content.image))
                    except Exception as exc:error(None,exc)
                background(read_content,opened,lambda message:error(None,message))
            elif command=="pin":
                if not path:path,_=QFileDialog.getOpenFileName(None,"Pin image","","Images (*.png *.jpg *.jpeg *.webp *.heic *.heif)")
                if path:self.pin(path)
            elif command=="overlay":
                if not path:raise ValueError("An overlay needs an image or video filepath")
                self.overlay(path)
            elif command=="ocr" and path:
                self.recognize_text(path,args.get("linebreaks"))
            elif command=="history":self.history()
            elif command=="save-all":self.save_all_overlays()
            elif command=="close-all":self.close_all_overlays()
            elif command=="toggle-pins":self.toggle_pins()
            elif command=="close-pins":self.close_pins()
            elif command=="unlock-pins":self.unlock_pins()
            elif command=="settings":
                if args.get("tab")=="cloud":raise ValueError("Cloud services are excluded from OmniShot. Captures stay on your device.")
                settings=Settings(self.store,args.get("tab","general"));settings.accepted.connect(self.apply_theme);settings.accepted.connect(lambda:[pin.refresh_appearance() for pin in self.pins]);settings.accepted.connect(lambda:[window.apply_annotation_shortcuts() for window in self.windows if isinstance(window,Editor)]);self.retain(settings)
            elif command=="restore":
                path=self.last_closed or (self.store.history()[0]["path"] if self.store.history() else None)
                if path:self.overlay(path)
            elif command=="last":
                if self.store.history():self.edit(self.store.history()[0]["path"])
            elif command=="last-screenshot":
                latest=next((row for row in self.store.history() if row.get('kind') in ('image','scroll') and row.get('capture_named') and not row.get('source_path')),None)
                if latest:self.edit(latest['path'])
            elif command=="record":self.start_record_dialog(backend.parse_geometry(args["geometry"]) if args.get("geometry") else None)
            elif command=="stop":
                if self.recorder:self.recorder.stop()
            elif command=="pause":
                if self.recorder:self.recorder.pause()
            elif command=="restart":
                if self.recorder:self.restart_recording()
            elif command=="scroll-done":
                if self.panel:self.panel.finish()
            elif command=="quit":self.request_quit()
            elif command in ("area","select","timer","previous","window","fullscreen","desktop","scroll","scroll-horizontal","ocr"):self.capture(command,args)
            else:raise ValueError(f"Unknown OmniShot command: {command}")
        except Exception as exc:error(None,exc)

    def refresh_shell_panel(self):
        if self.shell_probe_pending:return
        from .shell_panel import available
        self.shell_probe_pending=True
        def done(present):
            self.shell_probe_pending=False;self.shell_available=present;self.tray.setVisible(not present)
        background(available,done,lambda _:done(False))

    def notify(self,title,message):
        started,_=QProcess.startDetached("notify-send",["--app-name=OmniShot",title,str(message)])
        if not started:self.tray.showMessage(title,str(message))

    def show_menu(self):
        from .shell_panel import show
        background(show,lambda shown:None if shown else self.show_standalone_menu(),lambda _:self.show_standalone_menu())

    def show_standalone_menu(self):
        win=QWidget();win.setWindowTitle("OmniShot — Capture");win.setFixedWidth(540)
        escape=QShortcut(QKeySequence("Escape"),win,activated=win.close)
        escape.setContext(Qt.ShortcutContext.WindowShortcut)
        layout=QVBoxLayout(win);layout.setContentsMargins(24,24,24,24)
        title=QLabel("Capture. Make it clear.");title.setStyleSheet("font-size:24px;font-weight:600");layout.addWidget(title)
        subtitle=QLabel("Select an area, annotate it, and put it to work.");subtitle.setObjectName("muted");layout.addWidget(subtitle)
        for items in [[("All-In-One","select"),("Area","area"),("Window","window")],[("Fullscreen","fullscreen"),("Previous area","previous"),("Self timer","timer")],
             [("Scrolling capture","scroll"),("Horizontal scroll","scroll-horizontal")],[("Record screen","record"),("Capture text","ocr")],
             [("Open image","open"),("From clipboard","clipboard")],[("History","history"),("Settings","settings")]]:
            row=QHBoxLayout()
            for label,cmd in items:
                def activate(_,c=cmd):win.close();self.dispatch({"command":c})
                row.addWidget(button(label,activate,label=="Scrolling capture"))
            layout.addLayout(row)
        help_label=QLabel("After capture: annotate, copy, save, pin, or drag the preview.");help_label.setObjectName("muted");layout.addWidget(help_label)
        self.retain(win)

    def capture(self,mode,args):
        if self.busy:return
        if self.panel and not self.panel.closed:self.notify("OmniShot","Finish or cancel the scrolling capture first.");return
        rect=backend.parse_geometry(args["geometry"]) if args.get("geometry") else None
        delay=float(args.get("delay",self.store.settings["delay"] if mode=="timer" else 0))
        if not 0<=delay<=86400:raise ValueError("Capture delay must be between 0 and 86400 seconds")
        name_context=self.store.capture_name_context();self.busy=True;self.hide_capture_windows()
        action=args.get("action");capture_scale={};capture_modifiers={"mask":0}
        def fail(message):
            self.busy=False;self.restore_capture_windows()
            if message and message!="selection cancelled" and "slurp failed" not in message and "live-selector failed" not in message:error(None,message)
        def execute():
            if mode=="window" and not rect:self.window_selection(action,name_context);return
            if mode=="select" or (mode in ("area","timer") and not rect and self.store.settings["freeze"]):
                initial=rect or (self.store.settings.get("previous_area") if mode=="select" and self.store.settings.get("remember_selection",True) else None)
                self.frozen_selection("select" if mode=="select" else "area",action,initial,name_context,capture_kind="Self timer" if mode=="timer" else None,timer_delay=delay if mode=="timer" else None);return
            def work():
                selected=rect
                if mode=="previous":
                    selected=self.store.settings.get("previous_area")
                    if not selected:raise ValueError("Capture an area first")
                if not selected and mode not in ("fullscreen","desktop"):
                    selected,capture_modifiers["mask"]=backend.select_region(mode=="window",with_modifiers=True)
                if mode in ("scroll","scroll-horizontal","timer"):return selected,None
                output=None
                if mode in ("fullscreen","desktop") and not selected:
                    monitors=backend.hypr("monitors")
                    if mode=="fullscreen":
                        monitor=next((m for m in monitors if m["focused"]),monitors[0]);output=monitor["name"];capture_scale["ratio"]=monitor["scale"]
                    else:capture_scale["ratio"]=max(m["scale"] for m in monitors)
                return selected,backend.grab(selected,self.store.settings["include_cursor"],output)
            def done(result):
                self.busy=False;selected,frame=result
                if selected:self.store.settings["previous_area"]=list(selected);self.store.save_settings()
                if mode=="timer":
                    self.timed_capture(selected,action,None,bool(capture_modifiers["mask"]&1),name_context,bool(capture_modifiers["mask"]&4),delay)
                elif frame is None:
                    self.scroll(selected,mode=="scroll-horizontal",skip_background=bool(capture_modifiers["mask"]&1),force_copy=bool(capture_modifiers["mask"]&4),name_context=name_context)
                    panel=self.panel
                    if "autoscroll" in args:panel.set_auto(args["autoscroll"])
                    if args.get("start"):QTimer.singleShot(250,panel.start)
                else:self.finished_capture(frame,action,ocr=mode=="ocr",linebreaks=args.get("linebreaks"),pixel_ratio=frame.shape[1]/selected[2] if selected else capture_scale.get("ratio"),skip_background=bool(capture_modifiers["mask"]&1),force_copy=bool(capture_modifiers["mask"]&4),name_context=name_context)
            background(work,done,fail)
        def begin(_=None):QTimer.singleShot(180 if mode=="timer" else int(delay*1000)+180,execute)
        if getattr(self,"shell_available",False):
            from .shell_panel import call
            background(lambda:call("shell","hide","local.omnishot"),begin,begin)
        else:begin()

    def window_selection(self,action,name_context=None):
        from .window_selection import WindowSelector
        token=object();self.selection_token=token
        def prepare():
            monitors=backend.capture_monitors();visible={m["activeWorkspace"]["id"] for m in monitors}
            clients=[c for c in backend.hypr("clients") if c.get("mapped") and not c.get("hidden") and (c.get("workspace",{}).get("id") in visible or c.get("pinned"))]
            if not clients:raise ValueError("There are no windows to capture")
            return [(m,backend.grab(output=m["name"])) for m in monitors],clients
        def selected(client,transparent,force_copy=False):
            self.cancel_selection();self.capture_window(client,action,transparent,force_copy,name_context)
        def ready(result):
            if self.selection_token is not token:return
            rows,clients=result;pointer=cursor_position()
            for monitor,frame in rows:
                selector=WindowSelector(monitor,frame,clients);self.selectors.append(selector);selector.selected.connect(lambda client,transparent,s=selector:selected(client,transparent,s.force_copy))
                selector.cancelled.connect(lambda:(self.cancel_selection(),self.restore_capture_windows()));selector.showFullScreen()
            self.activate_selection(pointer)
        def failed(message):self.cancel_selection();self.restore_capture_windows();error(None,message)
        background(prepare,ready,failed)

    def capture_window(self,client,action,transparent=False,force_copy=False,name_context=None):
        self.busy=True;context={**(name_context or {}),**self.store.capture_name_context(client)}
        rect=(*client['at'],*client['size'])
        def capture():
            frame=backend.grab_window(client,self.store.settings['include_cursor'])
            style=backend.window_background(client,frame,self.store.settings['window_shadow'],self.store,transparent)
            return frame,style
        def done(result):
            self.busy=False;frame,style=result;self.store.settings['previous_area']=list(rect);self.store.save_settings()
            self.finished_capture(frame,action,capture_background=style,pixel_ratio=frame.shape[1]/rect[2],skip_background=transparent,name_context=context,force_copy=force_copy)
        def failed(message):self.busy=False;self.restore_capture_windows();error(None,message)
        background(capture,done,failed)

    def frozen_selection(self,mode,action,initial=None,name_context=None,capture_kind=None,timer_delay=None):
        token=object();self.selection_token=token
        live=mode=="select" and not self.store.settings["freeze"]
        from .clean_capture import SelectionMirror
        mirror=SelectionMirror() if live else None
        def work():
            try:
                if mirror:mirror.start()
                monitors=backend.capture_monitors();visible={m['activeWorkspace']['id'] for m in monitors}
                clients=[c for c in backend.hypr('clients') if c.get('mapped') and not c.get('hidden') and (c.get('workspace',{}).get('id') in visible or c.get('pinned'))]
                return [(m,backend.grab(output=m["name"],cursor=self.store.settings["include_cursor"],scale=m["scale"])) for m in monitors],clients
            except Exception:
                if mirror:mirror.stop()
                raise
        def done(result):
            if self.selection_token is not token:
                if mirror:mirror.stop()
                return
            rows,clients=result;self.selection_mirror=mirror;pointer=cursor_position()
            for monitor,frame in rows:
                selector=Selector(monitor,frame,mode,initial,settings=self.store.settings,live=live,clients=clients,capture_kind=capture_kind);self.selectors.append(selector)
                selector.selected.connect(lambda rect,img,kind,s=selector:self.selection_done(rect,img,kind,s.capture_action or action,s.skip_background,name_context,s.force_copy,s.capture_scale(),timer_delay));selector.cancelled.connect(lambda:(self.cancel_selection(),self.restore_capture_windows()));selector.showFullScreen()
            from .selection_group import SelectionGroup
            SelectionGroup(self.selectors,initial)
            self.activate_selection(pointer)
        background(work,done,lambda msg:(self.cancel_selection(),self.restore_capture_windows(),error(None,msg)))
    def activate_selection(self,pointer):
        if not self.selectors:return
        target=next((s for s in self.selectors if hasattr(s,"selection") and s.selection.intersects(s.rect())),None)
        target=target or next((s for s in self.selectors if s.monitor.get("focused")),self.selectors[0])
        for selector in self.selectors:
            local=selector.mapFromGlobal(pointer)
            if hasattr(selector,"hover"):selector.hover(local)
            else:selector.pointer=local;selector.update()
        def activate():
            from shiboken6 import isValid
            if not (isValid(target) and target in self.selectors and target.isVisible()):return
            if QApplication.platformName()=="wayland":
                try:
                    client=next((c for c in backend.hypr("clients") if c.get("pid")==os.getpid() and c.get("title")==target.windowTitle()),None)
                    if client and backend.hypr("activewindow").get("address")!=client["address"]:
                        backend.focus_window(client["address"])
                        if target.geometry().contains(pointer):backend.move_cursor(pointer.x(),pointer.y())
                    return
                except Exception:pass
            target.raise_();target.activateWindow();target.setFocus()
        activate();QTimer.singleShot(150,activate)

    def cancel_selection(self):
        self.selection_token=None;selectors=self.selectors;self.selectors=[];self.busy=False
        for selector in selectors:selector.terminal=True;selector.close();selector.deleteLater()
        mirror=getattr(self,"selection_mirror",None);self.selection_mirror=None
        if mirror:mirror.stop()
    def selection_done(self,rect,image,kind,action,skip_background=False,name_context=None,force_copy=False,source_scale=None,timer_delay=None):
        mirror=None
        if image is None and kind in ("Screenshot","Fullscreen","Text (OCR)"):
            mirror=getattr(self,"selection_mirror",None);self.selection_mirror=None
        self.cancel_selection();self.store.settings["previous_area"]=list(rect);self.store.save_settings()
        if kind=='Window':self.capture_window(image,action,skip_background,force_copy,name_context)
        elif kind=='Self timer':self.timed_capture(rect,action,source_scale,skip_background,name_context,force_copy,timer_delay)
        elif kind in ("Scrolling","Horizontal scrolling"):
            QTimer.singleShot(200,lambda:self.scroll(rect,kind=="Horizontal scrolling",skip_background,name_context,force_copy))
        elif kind=="Record video":QTimer.singleShot(200,lambda:self.start_record_dialog(rect))
        else:
            def captured(frame):
                self.busy=False;self.finished_capture(frame,action,ocr=kind=="Text (OCR)",pixel_ratio=frame.shape[1]/rect[2],skip_background=skip_background,name_context=name_context,force_copy=force_copy)
            if image is None:
                self.busy=True
                def capture():
                    try:return backend.grab(rect,self.store.settings["include_cursor"],scale=source_scale)
                    finally:
                        if mirror:mirror.stop()
                def failed(message):self.busy=False;self.restore_capture_windows();error(None,message)
                background(capture,captured,failed)
            else:captured(np.array(Image.open(io.BytesIO(png_bytes(image))).convert("RGB")))

    def timed_capture(self,rect,action,scale,skip_background,name_context,force_copy,delay=None):
        from .capture_countdown import CaptureCountdown
        self.busy=True;countdown=CaptureCountdown(self.store.settings['delay'] if delay is None else delay);self.retain(countdown)
        def cancelled():self.busy=False;self.restore_capture_windows()
        def capture():
            def done(frame):
                self.busy=False;self.finished_capture(frame,action,pixel_ratio=frame.shape[1]/rect[2],skip_background=skip_background,name_context=name_context,force_copy=force_copy)
            def failed(message):cancelled();error(None,message)
            background(lambda:backend.grab(rect,self.store.settings['include_cursor'],scale=scale),done,failed)
        countdown.cancelled.connect(cancelled);countdown.finished.connect(lambda:QTimer.singleShot(180,capture))
    def finished_capture(self,frame,action=None,kind="image",ocr=False,linebreaks=None,capture_background=None,pixel_ratio=None,skip_background=False,name_context=None,force_copy=False):
        self.restore_capture_windows()
        original_ratio=pixel_ratio
        if not ocr:
            frame,pixel_ratio=backend.prepare_screenshot(frame,pixel_ratio,self.store.settings)
            if capture_background and original_ratio and pixel_ratio!=original_ratio:
                capture_background=dict(capture_background)
                for key in ("padding","radius"):
                    if key in capture_background:capture_background[key]=round(capture_background[key]/original_ratio)
        path=self.store.add(image=frame,kind=kind)
        metadata=self.store.metadata(path)
        if pixel_ratio:metadata.update(pixel_ratio=pixel_ratio,original_pixel_ratio=original_ratio)
        if skip_background:metadata["skip_background"]=True
        self.store.atomic_json(path.with_suffix(".json"),metadata)
        self.store.name_capture(path,name_context)
        if ocr:
            self.recognize_text(path,linebreaks);return
        if (not skip_background and self.store.settings.get("background_preset","None")!="None") or capture_background:
            temporary=Editor(path,self.store)
            if skip_background or self.store.settings.get("background_preset","None")=="None":temporary.background=capture_background;temporary.commit()
            temporary.close();temporary.deleteLater()
        if not self.choose_capture_name(path):return
        actions=backend.screenshot_actions(self.store.settings,action)
        if force_copy and self.store.settings.get("capture_ctrl_copy",True):actions.add("copy")
        self.perform_capture_actions(path,actions)
    def recognize_text(self,path,linebreaks=None):
        from .text_result import extract,present
        settings=dict(self.store.settings)
        def done(text):
            dialog=present(text,settings)
            if dialog and not dialog.copied:return
            self.notify("OmniShot","Recognized text copied to clipboard" if text else "No text or QR code found")
        background(lambda:extract(path,settings["ocr_languages"],settings["ocr_linebreaks"] if linebreaks is None else linebreaks),done,lambda msg:error(None,msg))

    def choose_capture_name(self,path):
        if not self.store.settings.get("ask_capture_name"):return True
        from .capture_name import CaptureNameDialog
        dialog=CaptureNameDialog(self.store,path)
        result=dialog.exec();dialog.deleteLater()
        return result!=CaptureNameDialog.DISCARDED
    def finished_recording(self,path):
        self.restore_capture_windows()
        if not self.store.metadata(path).get("capture_named"):
            self.store.name_capture(path,getattr(getattr(self,"recorder",None),"name_context",None))
        if not self.choose_capture_name(path):return
        actions=backend.capture_actions(self.store.settings,recording=True)
        if getattr(self,"quit_after_recording",False):actions=[a for a in actions if a not in ("annotate","edit","overlay","pin")]
        self.perform_capture_actions(Path(path),actions,recording=True)
    def recovered_recording(self,path,message):
        self.quit_after_recording=False
        self.restore_capture_windows()
        if not self.store.metadata(path).get("capture_named"):
            try:self.store.name_capture(path,getattr(getattr(self,"recorder",None),"name_context",None))
            except OSError:pass
        QMessageBox.warning(None,"Recording recovered",f"Your recorded video was kept. Recording or final processing did not finish normally.\n\n{message}\n\nThe video editor will open so you can review and export it.")
        self.edit(path)
    def perform_capture_actions(self,path,actions,recording=False):
        for current in ("copy","save","pin","annotate","overlay"):
            if current not in actions and not (current=="annotate" and "edit" in actions):continue
            try:
                if current=="annotate":self.edit(path)
                elif current=="copy":
                    if recording:
                        name=self.store.display_name(path)
                        background(lambda:backend.copy_file(path,self.store,name=name),lambda _:None,lambda msg:error(None,msg))
                    else:backend.copy_image(self.store.display_image(path),self.store,name=self.store.display_name(path))
                elif current=="pin":self.pin(path)
                elif current=="save":
                    dest=self.store.export_target(path,extension=None if recording else self.store.settings["format"])
                    if recording:__import__("shutil").copy2(path,dest)
                    else:save_image(load_image(self.store.display_image(path)),dest,convert_srgb=self.store.settings.get("convert_srgb",True))
                    self.store.remember_auto_save(path,dest)
                else:self.overlay(path)
            except Exception as exc:error(None,exc)
    def scroll(self,rect,horizontal=False,skip_background=False,name_context=None,force_copy=False):
        panel=ScrollPanel(rect,self.store,horizontal);self.panel=panel
        panel.completed.connect(lambda a:self.finished_capture(a,kind="scroll",pixel_ratio=a.shape[0]/panel.rect_capture[3] if horizontal else a.shape[1]/panel.rect_capture[2],skip_background=skip_background,name_context=name_context,force_copy=force_copy));panel.cancelled.connect(self.restore_capture_windows);panel.show()
    def overlay(self,path):
        if Path(path).resolve().parent!=self.store.captures.resolve():
            background(lambda:self.store.import_file(path),self.overlay,lambda msg:error(None,msg));return
        if Path(path).suffix.lower()==".omnishot-video":self.edit(path);return
        if Path(path).suffix.lower()==".omnishot" and self.store.display_image(path)==Path(path):
            temporary=Editor(path,self.store);temporary.close();temporary.deleteLater()
        overlay=QuickOverlay(path,self.store,len([o for o in self.overlays if o.isVisible()]));self.track_window(overlay,self.overlays)
        overlay.annotate.connect(lambda p:(overlay.close(),self.edit(p)));overlay.pin.connect(self.pin);overlay.dismissed.connect(self.dismissed)
        overlay.transform_requested.connect(self.transform_capture);overlay.save_all_requested.connect(self.save_all_overlays);overlay.trash_requested.connect(self.trash_capture);overlay.show()
        overlay.close_all_requested.connect(self.close_all_overlays)
    def trash_capture(self,path):
        editors=[w for w in self.windows if hasattr(w,"path") and Path(w.path).resolve()==Path(path).resolve()]
        if any(getattr(w,"export_cancel",None) is not None for w in editors):error(None,"Finish or cancel this recording’s export before moving it to Trash.");return
        for editor in editors:editor.close()
        affected=[overlay for overlay in self.overlays if overlay.path.resolve()==Path(path).resolve()]
        for overlay in affected:overlay.hide()
        def done(result):
            for overlay in affected:overlay.close()
            if self.last_closed==str(path):self.last_closed=None
            message="Capture and editable project moved to Trash"
            if result.get('kept_saved_files'):message+=". Saved files changed outside OmniShot were kept."
            self.notify("OmniShot",message)
        def fail(message):
            for overlay in affected:overlay.show()
            error(None,message)
        background(lambda:self.store.trash(path),done,fail)
    def transform_capture(self,path,action):
        editor=next((w for w in self.windows if isinstance(w,Editor) and w.path.resolve()==Path(path).resolve()),None);temporary=editor is None
        try:
            if temporary:editor=Editor(path,self.store)
            if editor.inline:editor.inline.finish()
            if action=="rotate":editor.rotate()
            elif action=="rotate-left":
                for _ in range(3):editor.rotate()
            elif action=="flip":editor.flip()
            elif action=="flip-vertical":editor.flip(True)
            elif action=="scale":
                metadata=self.store.metadata(path);ratio=metadata.get("pixel_ratio",1)
                if ratio>1:
                    if editor.background:
                        for key in ("padding","radius"):
                            if key in editor.background:editor.background[key]=round(editor.background[key]/ratio)
                    editor.resize_to(round(editor.base.width()/ratio));self.store.set_pixel_ratio(path,1)
            editor.save_draft()
            self.refresh_capture_views(path)
        except Exception as exc:error(None,exc)
        finally:
            if temporary and editor:editor.close();editor.deleteLater()
    def save_all_overlays(self):
        from shiboken6 import isValid
        overlays=[o for o in self.overlays if isValid(o) and o.isVisible()]
        if not overlays or getattr(self,'saving_overlays',False):return
        self.saving_overlays=True
        for overlay in overlays:overlay.timer.stop();overlay.hover_keys.stop()
        try:
            folder=QFileDialog.getExistingDirectory(None,"Save all captures",str(Path(self.store.settings["output_dir"]).expanduser()))
            if not folder:return
            saved=set()
            for overlay in overlays:
                if not isValid(overlay) or not overlay.isVisible():continue
                try:
                    if overlay.path not in saved:overlay.export_to(folder);saved.add(overlay.path)
                    overlay.close()
                except Exception as exc:error(None,exc);break
            if saved:self.notify("OmniShot",f"Saved {len(saved)} captures")
        finally:
            self.saving_overlays=False
            for overlay in overlays:
                if isValid(overlay):overlay.resume_timer();overlay.rearm_hover_keys()
    def close_all_overlays(self):
        for overlay in list(self.overlays):overlay.close()
    def dismissed(self,path):self.last_closed=path
    def refresh_capture_views(self,path):
        target=Path(path).resolve()
        for window in list(self.overlays)+list(self.pins):
            if window.path.resolve()==target:window.refresh_content()
    def edit(self,path):
        if Path(path).resolve().parent!=self.store.captures.resolve():
            background(lambda:self.store.import_file(path),self.edit,lambda msg:error(None,msg));return
        try:
            existing=next((w for w in self.windows if isinstance(w,Editor) and w.path.resolve()==Path(path).resolve()),None)
            if existing:existing.show();existing.raise_();existing.activateWindow();return
            if Path(path).suffix.lower()==".omnishot-video":
                from .video_project import read_project
                from .recording import VideoEditor
                def ready(prepared):
                    try:self.retain(VideoEditor(path,self.store,prepared))
                    except Exception as exc:error(None,exc)
                background(lambda:read_project(path,self.store),ready,lambda msg:error(None,msg));return
            if Path(path).suffix.lower() in (".mp4",".gif",".webm",".mov",".mkv"):
                from .recording import VideoEditor
                self.retain(VideoEditor(path,self.store));return
            editor=Editor(path,self.store);editor.pin_requested.connect(self.pin);editor.draft_updated.connect(self.refresh_capture_views);self.retain(editor)
        except Exception as exc:error(None,exc)
    def pin(self,path):
        if Path(path).resolve().parent!=self.store.captures.resolve():
            background(lambda:self.store.import_file(path),self.pin,lambda msg:error(None,msg));return
        if Path(path).suffix.lower()=='.omnishot' and self.store.display_image(path)==Path(path):
            editor=None
            try:
                editor=Editor(path,self.store)
                if not editor.save_draft():raise RuntimeError(editor.draft_error)
                if editor.draft_preview_error:raise RuntimeError(editor.draft_preview_error)
            except Exception as exc:error(None,exc);return
            finally:
                if editor:editor.draft_timer.stop();editor.deleteLater()
        try:
            index=getattr(self,'next_pin_id',0);self.next_pin_id=index+1
            pin=Pin(str(path),index,self.store);pin.annotate_requested.connect(self.edit);self.track_window(pin,self.pins);pin.show()
        except Exception as exc:error(None,exc)
    def toggle_pins(self):
        show=not any(p.isVisible() for p in self.pins)
        for pin in self.pins:pin.setVisible(show)
    def unlock_pins(self):
        for pin in self.pins:pin.unlock()
    def close_pins(self):
        for pin in list(self.pins):pin.close()
    def history(self):
        h=History(self.store,self.remove_history);h.open_capture.connect(self.edit);h.restore_capture.connect(self.overlay);h.pin_capture.connect(self.pin);self.retain(h)
    def remove_history(self,paths):
        selected={Path(p).resolve() for p in paths}
        editors=[w for w in self.windows if hasattr(w,'path') and Path(w.path).resolve() in selected]
        if any(getattr(w,'export_cancel',None) is not None for w in editors):raise ValueError('Finish or cancel the recording export before removing it from History.')
        for window in editors:
            if not window.close():raise ValueError('The open editor could not preserve its edits. Close it before removing this capture.')
        for window in list(self.overlays)+list(self.pins):
            if Path(window.path).resolve() in selected:window.close()
        for path in paths:
            self.store.remove(path)
            if self.last_closed==str(path):self.last_closed=None
    def start_record_dialog(self,rect=None):
        if self.busy:return
        from .recording import RecordSetup,Recorder
        if self.panel and not self.panel.closed:
            self.notify("OmniShot","Finish or cancel the scrolling capture first.");return
        if self.recorder:
            self.restore_capture_windows();self.notify("OmniShot","A recording is already active. Use Stop or Pause from the OmniShot menu.");return
        setup=RecordSetup(self.store)
        if setup.exec():
            opts=setup.options();self.hide_capture_windows()
            def start(selected):
                self.launch_recorder(selected,opts)
            if rect:start(rect)
            elif opts["mode"]=="Fullscreen":start(None)
            elif opts["mode"]=="Area":self.recording_selection(opts)
            else:background(lambda:backend.select_region(True),start,lambda msg:(self.restore_capture_windows(),error(None,msg)))
        else:self.restore_capture_windows()
    def recording_selection(self,opts):
        self.busy=True;token=object();self.selection_token=token
        initial=self.store.settings.get("previous_recording_area") if opts.get("remember_selection",True) else None
        def selected(rect,image,kind):
            self.cancel_selection();QTimer.singleShot(200,lambda:self.launch_recorder(rect,opts))
        def done(rows):
            if self.selection_token is not token:return
            pointer=cursor_position()
            for monitor,frame in rows:
                selector=Selector(monitor,frame,"select",initial,settings=self.store.settings,capture_kind="Record video");self.selectors.append(selector)
                selector.selected.connect(selected);selector.cancelled.connect(lambda:(self.cancel_selection(),self.restore_capture_windows()));selector.showFullScreen()
            from .selection_group import SelectionGroup
            SelectionGroup(self.selectors,initial)
            self.activate_selection(pointer)
        background(lambda:[(m,backend.grab(output=m["name"])) for m in backend.capture_monitors()],done,lambda msg:(self.cancel_selection(),self.restore_capture_windows(),error(None,msg)))
    def recording_closed(self):
        self.recorder=None;self.restore_capture_windows()
        if self.quit_after_recording:QTimer.singleShot(0,self.request_quit)
    def launch_recorder(self,rect,opts):
        from .recording import Recorder
        if rect:
            self.store.settings["previous_recording_area"]=list(rect)
            try:self.store.save_settings()
            except OSError:pass
        self.recorder=Recorder(self.store,rect,opts);self.recorder.completed.connect(self.finished_recording)
        self.recorder.recovered.connect(self.recovered_recording)
        self.recorder.restart_requested.connect(self.restart_recording)
        self.recorder.destroyed.connect(self.recording_closed);self.retain(self.recorder)
    def restart_recording(self):
        previous=self.recorder
        if previous is None or previous.stopping:return
        rect=previous.rect_capture;opts=dict(previous.opts)
        previous.destroyed.connect(lambda:QTimer.singleShot(200,lambda:(self.hide_capture_windows(),self.launch_recorder(rect,opts))))
        previous.cancel()
    def request_quit(self):
        from shiboken6 import isValid
        from .recording import VideoEditor
        if self.selectors:self.cancel_selection();self.restore_capture_windows()
        if self.busy:
            self.notify("OmniShot","Finish or cancel the current capture before quitting.");return False
        self.quit_after_recording=False
        for window in list(self.windows):
            if isValid(window) and isinstance(window,(Editor,VideoEditor)) and not window.close():return False
        if self.panel and not self.panel.closed:
            if self.panel.stitcher.output is not None:self.panel.finish()
            else:self.panel.close()
            QTimer.singleShot(150,self.request_quit);return False
        if self.recorder and isValid(self.recorder):
            self.quit_after_recording=True;self.recorder.stop();return False
        from .widgets import JOBS
        if JOBS:QTimer.singleShot(150,self.request_quit);return False
        self.app.quit();return True

    def cleanup(self):
        if self.panel:self.panel.close()
        if self.recorder:self.recorder.shutdown()

    def apply_theme(self):
        self.icon=self.make_icon();self.app.setWindowIcon(self.icon);self.tray.setIcon(self.icon)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description="OmniShot native capture and annotation for Omarchy")
    parser.add_argument("command",nargs="?",default="menu",help="menu, all-in-one, area, area-copy, area-save, area-annotate, area-pin, window, fullscreen, desktop, scroll, scroll-horizontal, previous, timer, ocr, ocr-lines, ocr-single-line, open, clipboard, pin, overlay, history, restore, last, last-screenshot, save-all, close-all, toggle-pins, close-pins, settings, record, stop, pause, restart, scroll-done, quit; also accepts a local filepath or omnishot:// URL")
    parser.add_argument("path",nargs="?");parser.add_argument("--geometry",help="logical pixels: 'X,Y WxH'")
    parser.add_argument("--action",choices=["overlay","annotate","copy","save","pin"]);parser.add_argument("--delay",type=int)
    args={k:v for k,v in vars(parser.parse_args(argv)).items() if v is not None}
    if args["command"].startswith("file://"):
        url=QUrl(args["command"])
        if not url.isLocalFile() or url.host() not in ("","localhost"):raise ValueError("Open a local file")
        args["path"]=url.toLocalFile();args["command"]="open"
    elif "://" in args["command"]:
        from .api import parse_url
        args.update(parse_url(args["command"]))
    elif Path(args["command"]).is_file():args["path"]=args["command"];args["command"]="open"
    return args


def main(argv=None):
    args=parse_args(argv);app=QApplication(sys.argv[:1]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot")
    name=f"omnishot-{os.getuid()}";client=QLocalSocket();client.connectToServer(name)
    if client.waitForConnected(300):
        client.write(json.dumps(args).encode()+b"\n");client.waitForBytesWritten(1000);client.disconnectFromServer();return 0
    QLocalServer.removeServer(name);server=QLocalServer();server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(name):print(server.errorString(),file=sys.stderr);return 1
    app.setStyle("Fusion");controller=Controller(app);controller.apply_theme();clients=[]
    def connection():
        sock=server.nextPendingConnection();clients.append(sock);sock.setProperty("buffer",b"")
        sock.disconnected.connect(lambda:(clients.remove(sock) if sock in clients else None,sock.deleteLater()))
        def read():
            data=sock.property("buffer")+bytes(sock.readAll())
            if b"\n" in data:
                try:controller.dispatch(json.loads(data.split(b"\n",1)[0]))
                except Exception as exc:error(None,exc)
                sock.disconnectFromServer()
            else:sock.setProperty("buffer",data)
        sock.readyRead.connect(read)
    server.newConnection.connect(connection);QTimer.singleShot(0,lambda:controller.dispatch(args));return app.exec()


if __name__=="__main__":sys.exit(main())
