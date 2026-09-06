"""GIO desktop-entry launches through the installed CLI and private native IPC.

Run images, videos, chooser and record modes separately in the disposable compositor. No user
file associations, default applications, or running OmniShot socket are changed.
"""
import hashlib,io,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.parse import urlencode
from PIL import Image
from PySide6.QtCore import Qt,QPointF,QTimer
from PySide6.QtWidgets import QApplication,QFileDialog,QLineEdit,QDialogButtonBox
from PySide6.QtNetwork import QLocalServer
from PySide6.QtTest import QTest
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.editor import Editor,png_bytes
from omnishot.recording import VideoEditor
from omnishot.history import History
from omnishot.widgets import JOBS,place_window
from omnishot.theme import ThemeManager

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
mode=sys.argv[3];assert mode in ('images','videos','chooser','record')
socket_dir=Path(tempfile.mkdtemp(prefix='of-',dir='/tmp'))
os.environ.update(TMPDIR=str(socket_dir),OMNISHOT_DATA_DIR=str(out/'data'),XDG_CONFIG_HOME=str(out/'config'))
if mode=='chooser':QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot')
app.setStyle('Fusion');theme=ThemeManager(app)
state=Controller(app);state.store.settings.update(overlay_timeout=0,background_preset='None')
errors=[];application.error=lambda parent,message:errors.append(str(message))
desktop=Path.home()/'.local/share/applications/org.omarchy.OmniShot.desktop'
assert desktop.is_file()
server=QLocalServer();server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
assert server.listen(f'omnishot-{os.getuid()}'),server.errorString()
assert Path(server.fullServerName()).parent==socket_dir
sockets=[];received=[];stage='initialization'
def connection():
    socket=server.nextPendingConnection();sockets.append(socket);socket.setProperty('buffer',b'')
    def read():
        data=socket.property('buffer')+bytes(socket.readAll());socket.setProperty('buffer',data)
        if b'\n' in data:
            args=json.loads(data.split(b'\n',1)[0]);received.append(args);socket.disconnectFromServer();state.dispatch(args)
    socket.readyRead.connect(read)
server.newConnection.connect(connection)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=7):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate(),dict(stage=stage,errors=errors,received=received)
def launch(value):
    global stage
    stage=value;before=len(received)
    with (out/'launch.log').open('ab') as log:
        subprocess.run(['gio','launch',str(desktop),value],check=True,stdout=log,stderr=log,timeout=3)
    wait(lambda:len(received)==before+1)
def url(command,**args):return 'omnishot://'+command+('?' + urlencode(args) if args else '')
def close_results():
    for window in list(state.windows):window.close()
    state.close_pins();state.close_all_overlays()
    wait(lambda:not state.windows and not state.pins and not state.overlays and not JOBS)
def opened(kind):
    wait(lambda:any(isinstance(w,kind) for w in state.windows))
    window=next(w for w in state.windows if isinstance(w,kind))
    if kind is VideoEditor:wait(lambda:window.last_frame is not None);window.player.pause()
    return window
def pointer(widget,point=None):
    top=widget.window();native=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==top.windowTitle())
    point=widget.mapTo(top,point or widget.rect().center())
    backend.move_cursor(native['at'][0]+point.x()-2,native['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def pixels(image):
    loaded=Image.open(io.BytesIO(png_bytes(image))).convert('RGBA')
    return loaded.size,loaded.tobytes()
def choose(command_name,path=None):
    failures=[];finished=[]
    def interact():
        # Return to the event loop until the modal exists. Waiting recursively
        # here can dispatch the CLI request inside that wait and strand the
        # interaction callback outside the new dialog's nested event loop.
        if not isinstance(app.activeModalWidget(),QFileDialog):timer.start(50);return
        try:
            dialog=app.activeModalWidget()
            wait(lambda:any(c['pid']==os.getpid() and c['title']==dialog.windowTitle() for c in backend.hypr('clients')))
            client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==dialog.windowTitle())
            backend.focus_window(client['address']);wait(lambda:backend.hypr('activewindow').get('title')==dialog.windowTitle());QTest.qWait(100)
            if path is None:command('key 1 0')
            else:
                if path.suffix=='.heif':assert '*.heif' in ' '.join(dialog.nameFilters())
                field=dialog.findChild(QLineEdit,'fileNameEdit');assert field and field.isVisible()
                pointer(field);command('click 272');QTest.qWait(80);backend.copy_text(str(path));command('key 30 4');command('key 47 4');QTest.qWait(150)
                assert field.text()==str(path)
                popup=app.activePopupWidget()
                if popup and popup.isVisible():command('key 1 0');QTest.qWait(70)
                dialog.grab().save(str(out/('chooser-'+command_name+path.suffix+'.png')))
                control=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open)
                pointer(control);command('click 272')
            wait(lambda:not dialog.isVisible());finished.append(True)
        except Exception as exc:
            failures.append(repr(exc))
            for widget in app.topLevelWidgets():
                if isinstance(widget,QFileDialog):widget.reject()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(interact);timer.start(180)
    (out/'progress.json').write_text(json.dumps(dict(stage=command_name,path=str(path),received=received),indent=2))
    launch(url(command_name));assert finished and not failures,failures
report=dict(mode=mode,desktop_entry_launch=True,installed_cli_private_ipc=True)
originals={}
try:
    if mode=='images':
        source=out/'résumé #1 + sample.png';Image.new('RGB',(480,300),'#308acd').save(source);originals[source]=digest(source)
        launch(url('open-annotate',filepath=str(source)));editor=opened(Editor);owned=editor.path
        assert owned!=source and editor.base.width()==480 and not errors
        place_window(editor,40,50);QTest.qWait(180)
        pointer(editor.toolbar.widgetForAction(editor.tools['arrow']));command('click 272');QTest.qWait(100)
        a=editor.view.mapFromScene(QPointF(40,60));b=editor.view.mapFromScene(QPointF(300,180));pointer(editor.view.viewport(),a)
        command('button 272 1');QTest.qWait(60);command(f'move {b.x()-a.x()} {b.y()-a.y()}');QTest.qWait(100);command('button 272 0');QTest.qWait(120)
        assert len(editor.objects)==1;expected=editor.render();editor.grab().save(str(out/'annotate.png'));close_results()
        launch(url('pin',filepath=str(source)));wait(lambda:len(state.pins)==1)
        assert state.pins[0].path==owned and pixels(state.pins[0].image)==pixels(expected);close_results()
        launch(url('add-quick-access-overlay',filepath=str(source)));wait(lambda:len(state.overlays)==1)
        assert state.overlays[0].path==owned;close_results()
        launch(url('restore-recently-closed'));wait(lambda:len(state.overlays)==1)
        assert state.overlays[0].path==owned;close_results()
        backend.clipboard_write('text/uri-list',(source.as_uri()+'\r\n').encode())
        launch(url('open-from-clipboard'));editor=opened(Editor)
        assert editor.path==owned and len(editor.objects)==1;close_results()
        launch(url('open-history'));history=opened(History)
        assert len(history.rows)==1 and Path(history.rows[0]['path'])==owned;close_results()
        # Disabling URL commands must leave ordinary file-manager Open With usable.
        state.store.settings['url_api_enabled']=False
        launch(url('open-annotate',filepath=str(source)));wait(lambda:bool(errors))
        assert 'disabled' in errors.pop() and not state.windows
        launch(source.as_uri());editor=opened(Editor)
        assert editor.path==owned and len(editor.objects)==1;close_results()
        jpeg=out/'another #é photo.jpg';Image.new('RGB',(320,200),'#62b482').save(jpeg);originals[jpeg]=digest(jpeg)
        launch(jpeg.as_uri());editor=opened(Editor)
        assert editor.base.width()==320 and len(state.store.history())==2;close_results()
        report.update(encoded_path_preserved=True,native_annotation=True,pin_uses_current_edits=True,overlay_restore=True,clipboard_file_reopens_edits=True,history_deduplicates=True,disabled_urls_preserve_file_open=True,jpeg_file_uri=True)
    elif mode=='videos':
        source=out/'movie #é + original.mp4'
        backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=0x308acd:s=320x200:r=10','-t','0.6','-c:v','libx264','-threads','1','-y',str(source)])
        files=[source]
        for suffix,codec in [('gif',None),('mov','copy'),('mkv','copy'),('webm','libvpx-vp9')]:
            path=source.with_suffix('.'+suffix);args=['ffmpeg','-v','error','-i',str(source)]
            if codec:args+=['-c:v',codec]
            backend.run(args+['-threads','1','-y',str(path)]);files.append(path)
        originals={path:digest(path) for path in files};formats=[];decoded_colors={}
        for path in files:
            launch(path.as_uri());editor=opened(VideoEditor)
            assert editor.path!=path and editor.path.suffix==path.suffix and editor.timeline.duration>0
            assert editor.last_frame.shape[:2]==(200,320)
            # FFmpeg's default GIF palette quantizes the generated input color.
            expected=Image.open(path).convert('RGB').getpixel((160,100)) if path.suffix=='.gif' else (48,138,205)
            decoded=editor.last_frame[100,160].tolist()
            assert max(abs(a-b) for a,b in zip(decoded,expected))<8,(path.suffix,decoded,expected)
            decoded_colors[path.suffix]=decoded
            formats.append(path.suffix);close_results()
        assert len(state.store.history())==5
        launch(url('add-quick-access-overlay',filepath=str(source)));wait(lambda:len(state.overlays)==1)
        assert state.overlays[0].is_video;owned=state.overlays[0].path;close_results()
        launch(url('restore-recently-closed'));wait(lambda:len(state.overlays)==1)
        assert state.overlays[0].path==owned and state.overlays[0].is_video;close_results()
        backend.clipboard_write('text/uri-list',(source.as_uri()+'\r\n').encode())
        launch(url('open-from-clipboard'));editor=opened(VideoEditor)
        assert editor.path==owned
        wait(lambda:all(editor.timeline.thumbnails.images.get(key) is not None for key,_,_ in editor.timeline.thumbnail_tiles()))
        QTest.qWait(100);editor.grab().save(str(out/'video.png'));close_results()
        assert len(state.store.history())==5
        report.update(native_decoded_formats=formats,decoded_center_colors=decoded_colors,video_url_overlay=True,video_restore=True,clipboard_video=True,history_deduplicates=True)
    elif mode=='record':
        from PySide6.QtGui import QColor,QPainter
        from PySide6.QtWidgets import QWidget
        from omnishot import recording
        assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
        # GSR maps the Wayland output name to a DRM connector before loading its
        # capture plugin. Give this disposable output a connected connector's
        # name so the production command can run unchanged. Its pixels still
        # come solely from the clean plugin in this private compositor.
        config=Path(os.environ['XDG_RUNTIME_DIR'])/'hyprland.lua'
        assert config.parent.name.startswith('os-') and config.parent.parent==Path('/tmp')
        connector=next(p.name.split('-',1)[1] for p in Path('/sys/class/drm').glob('card*-*') if (p/'status').read_text().strip()=='connected')
        secondary='--second-display' in sys.argv;cursor_display='--cursor-display' in sys.argv;left_display='--left-display' in sys.argv;manual_area='--manual-area' in sys.argv
        fullscreen_countdown='--fullscreen-countdown' in sys.argv
        assert not (manual_area or left_display) or secondary
        assert not fullscreen_countdown or (secondary and not manual_area)
        # Full-output GSR sizing uses the connector's physical aspect ratio.
        # Match this machine's 2880×1800 connector while varying logical scale.
        secondary_mode='2880x1800' if fullscreen_countdown else '1920x1080';secondary_scale=2 if fullscreen_countdown else 1
        if secondary:config.write_text(config.read_text()+f'\nhl.monitor({{output="{connector}",mode="{secondary_mode}@60",position="{"-1920" if left_display else "1800"}x0",scale={secondary_scale}}})\n')
        else:config.write_text(config.read_text().replace('HEADLESS-1',connector))
        backend.run(['hyprctl','reload']);assert not backend.run(['hyprctl','configerrors']).strip()
        backend.run(['hyprctl','output','create','headless',connector])
        if not secondary:backend.run(['hyprctl','output','remove','HEADLESS-1'])
        wait(lambda:len(app.screens())==(2 if secondary else 1) and any(s.name()==connector for s in app.screens()))
        assert backend.capture_monitors()[0]['scale']==1.6
        target_monitor=next(m for m in backend.capture_monitors() if m['name']==connector)
        target_scale=target_monitor['scale'];region_y=round(target_monitor['height']/target_scale)-340
        expected_rect=(target_monitor['x']+120,target_monitor['y']+region_y,320,180)
        expected_size=(round(320*target_scale),round(180*target_scale))
        if fullscreen_countdown:expected_rect=None;expected_size=(round(target_monitor['width']/target_scale),round(target_monitor['height']/target_scale))
        recording.error=lambda parent,message:errors.append(str(message))
        state.store.settings.update(record_system_audio=False,record_microphone=False,record_cursor=False,record_clicks=False,record_keys=False,record_dnd=False,record_countdown=0,record_scale_video=False,record_max_resolution='Native',record_show_controls=True,fps=10,after_recording='edit',after_recording_extra=[])
        if fullscreen_countdown:state.store.settings.update(record_countdown=3,record_scale_video=True)
        class Pattern(QWidget):
            def paintEvent(self,event):
                p=QPainter(self);p.fillRect(self.rect(),QColor('#f07080'))
                p.fillRect(120,region_y,320,90,QColor('#2468ac'));p.fillRect(120,region_y+90,320,90,QColor('#22cc66'))
        source_window=Pattern();source_window.setWindowTitle('Generated recording URL source');source_window.winId();source_window.windowHandle().setScreen(next(s for s in app.screens() if s.name()==connector));source_window.showFullScreen();QTest.qWait(300)
        if fullscreen_countdown:
            other_source=QWidget();other_source.setWindowTitle('Generated other recording display');other_source.setStyleSheet('background:#894bc0');other_source.winId();other_source.windowHandle().setScreen(next(s for s in app.screens() if s.name()=='HEADLESS-1'));other_source.showFullScreen();QTest.qWait(200)
        coords=dict(x=120,y=160,width=320,height=180)
        if not cursor_display:coords['display']=2 if secondary else 1
        def setup_url(accept,coordinates):
            failures=[];finished=[]
            def interact():
                if not isinstance(app.activeModalWidget(),recording.RecordSetup):timer.start(50);return
                try:
                    dialog=app.activeModalWidget()
                    wait(lambda:any(c['pid']==os.getpid() and c['title']==dialog.windowTitle() for c in backend.hypr('clients')))
                    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==dialog.windowTitle())
                    backend.focus_window(client['address']);wait(lambda:backend.hypr('activewindow').get('title')==dialog.windowTitle());QTest.qWait(100)
                    if accept:
                        if fullscreen_countdown:
                            backend.move_window(client['address'],target_monitor['x']+100,target_monitor['y']+80);QTest.qWait(150)
                            pointer(dialog.mode);command('click 272');QTest.qWait(80);command('key 108 0');command('key 108 0');command('key 28 0');QTest.qWait(100)
                            assert dialog.mode.currentText()=='Fullscreen'
                        dialog.grab().save(str(out/'record-setup.png'))
                        pointer(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok));command('click 272')
                    else:command('key 1 0')
                    wait(lambda:not dialog.isVisible());finished.append(True)
                except Exception as exc:
                    failures.append(repr(exc))
                    for widget in app.topLevelWidgets():
                        if isinstance(widget,recording.RecordSetup):widget.reject()
            timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(interact);timer.start(180)
            if cursor_display:backend.move_cursor(target_monitor['x']+200-2,target_monitor['y']+200);command('move 2 0');QTest.qWait(80)
            launch(url('record-screen',**coordinates));assert finished and not failures,failures
        setup_url(False,{})
        assert state.recorder is None and not state.store.history() and not state.selectors
        setup_url(False,coords)
        assert state.recorder is None and not state.store.history() and not state.selectors
        setup_url(True,{} if manual_area or fullscreen_countdown else coords)
        if fullscreen_countdown:
            wait(lambda:state.recorder is not None);assert state.recorder.remaining>0 and not state.recorder.ready
            assert state.recorder.opts['capture_output']==connector,dict(output=state.recorder.opts['capture_output'],cursor=backend.hypr('cursorpos'),monitors=backend.hypr('monitors'))
            other=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==other_source.windowTitle())
            backend.focus_window(other['address']);backend.move_cursor(98,100);command('move 2 0');QTest.qWait(150)
            assert next(m for m in backend.hypr('monitors') if m['focused'])['name']=='HEADLESS-1'
            backend.run(['hyprctl','dismissnotify','-1'])
            if '--disconnect-countdown' in sys.argv:
                pending=state.recorder;assert pending.remaining>0 and not pending.ready
                backend.run(['hyprctl','output','remove',connector])
                wait(lambda:state.recorder is None and bool(errors),8)
                assert len(errors)==1 and 'no longer connected' in errors[0],errors
                assert pending.process is None and not state.store.history() and not JOBS
                report.update(fullscreen_target_disconnected_during_countdown=True,other_display_not_recorded=True,no_encoder_started=True,history_empty=True,error=errors[0],theme_applied=bool(theme.applied))
                (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));sys.exit(0)
        if manual_area:
            wait(lambda:len(state.selectors)==2);QTest.qWait(200)
            # Inclusive drag endpoints cover exactly 320 by 180 logical pixels.
            for x,y,button_state in [(expected_rect[0],expected_rect[1],1),(expected_rect[0]+319,expected_rect[1]+179,0)]:
                backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(100);command(f'button 272 {button_state}');QTest.qWait(100)
            selector=next(s for s in state.selectors if s.monitor['name']==connector)
            assert selector.selection.getRect()==(120,region_y,320,180),selector.selection.getRect()
            selector.grab().save(str(out/'record-selection.png'));command('key 28 0')
        wait(lambda:state.recorder is not None and state.recorder.ready,12)
        rec=state.recorder
        assert rec.rect_capture==expected_rect and not state.selectors,rec.rect_capture
        assert rec.clean_capture.enabled and rec.process.poll() is None
        assert rec.clean_capture.target[0]==connector and rec.clean_capture.target[1]==(None if fullscreen_countdown else (120,region_y,320,180))
        if secondary:
            # Put visible controls directly over the captured second-screen region.
            rec.setStyleSheet('background:#ee3344;color:white;');QTest.qWait(200)
            controls=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==rec.windowTitle())
            backend.move_window(controls['address'],target_monitor['x']+120,target_monitor['y']+region_y+45);QTest.qWait(200)
            control_state=[c for c in backend.hypr('clients') if c['title']==rec.windowTitle()]
            (out/'controls-state.json').write_text(json.dumps(dict(controls=control_state,monitors=backend.hypr('monitors')),indent=2))
            assert len(control_state)==1 and control_state[0]['monitor']==target_monitor['id'] and control_state[0]['pinned']
            # Keep Qt dispatching scale/paint events while exporting a control
            # surface that has just moved between differently scaled outputs.
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as pool:
                capture=pool.submit(backend.grab_window,controls);wait(capture.done,12)
                Image.fromarray(capture.result()).save(out/'visible-controls.png')
        QTest.qWait(1200);pointer(rec.stop_btn);command('click 272')
        wait(lambda:state.recorder is None and len(state.store.history())==1 and not JOBS,15)
        editor=opened(VideoEditor);editor.player.setPosition(500);wait(lambda:editor.last_frame is not None)
        path=editor.path;probe=json.loads(backend.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',path]))
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        assert video['codec_name']=='h264' and (video['width'],video['height'])==expected_size,video
        assert not any(s['codec_type']=='audio' for s in probe['streams'])
        frame=out/'recorded-region.png';backend.run(['ffmpeg','-v','error','-y','-ss','1.0' if secondary else '0.5','-i',path,'-frames:v','1',frame])
        image=Image.open(frame).convert('RGB')
        samples=[((280,region_y+45),(36,104,172)),((280,region_y+135),(34,204,102)),((960,540),(240,112,128))] if fullscreen_countdown else [((expected_size[0]//2,expected_size[1]//4),(36,104,172)),((expected_size[0]//2,expected_size[1]*3//4),(34,204,102))]
        for at,expected in samples:
            assert max(abs(a-b) for a,b in zip(image.getpixel(at),expected))<8,(at,image.getpixel(at))
        if secondary:
            import numpy as np
            pixels=np.array(image);red=(pixels[:,:,0]>160)&(pixels[:,:,1]<100)&(pixels[:,:,2]<120);assert not red.any()
        assert not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
        wait(lambda:all(editor.timeline.thumbnails.images.get(key) is not None for key,_,_ in editor.timeline.thumbnail_tiles()))
        QTest.qWait(100);editor.grab().save(str(out/'record-editor.png'))
        close_results();source_window.close()
        if fullscreen_countdown:other_source.close()
        report.update(parameterless_record_dialog=True,native_cancel_with_and_without_coordinates=True,native_record_and_stop=True,capture_geometry=list(expected_rect) if expected_rect else None,url_lower_left_geometry=not (manual_area or fullscreen_countdown),no_second_selection=not manual_area,native_drag_area=manual_area,fullscreen_keeps_display_during_countdown=fullscreen_countdown,encoded_pixels=list(expected_size),codec='h264',duration=float(probe['format']['duration']),correct_source_region_and_orientation=True,record_to_editor=True,no_audio_or_camera=True,clean_capture_released=True,production_encoder_command=True,disposable_output_connector_name=connector,secondary_display=secondary,cursor_selects_display=cursor_display,controls_excluded_on_secondary=secondary,target_display_scale=target_scale,negative_display_position=left_display,theme_applied=bool(theme.applied))
    else:
        source=out/'résumé #1 + selected.png';heif=out/'selected #é photo.heif'
        Image.new('RGB',(480,300),'#308acd').save(source)
        Image.new('RGB',(320,200),'#62b482').save(heif,format='HEIF',quality=95)
        originals={path:digest(path) for path in (source,heif)}
        for action in ('open-annotate','pin'):
            choose(action);assert not state.store.history() and not state.windows and not state.pins
        choose('open-annotate',source);editor=opened(Editor);owned=editor.path
        assert owned!=source and editor.base.width()==480 and len(state.store.history())==1;close_results()
        choose('pin',source);wait(lambda:len(state.pins)==1)
        assert state.pins[0].path==owned and state.pins[0].image.width()==480 and len(state.store.history())==1;close_results()
        choose('pin',heif);wait(lambda:len(state.pins)==1)
        from omnishot.images import load_image
        assert pixels(state.pins[0].image)==pixels(load_image(heif)) and len(state.store.history())==2
        close_results();before=state.store.history()
        choose('open-annotate');choose('pin')
        assert state.store.history()==before and not state.windows and not state.pins
        report.update(native_qt_file_choosers=True,parameterless_annotate_and_pin=True,native_file_name_entry_and_open=True,heif_in_pin_filter=True,heif_pin_decoded_pixels=True,cancel_empty_history=True,cancel_existing_history=True,history_deduplicates=True)
    assert not errors,errors
    assert all(digest(path)==value for path,value in originals.items())
    report.update(originals_unchanged=True,commands=[args['command'] for args in received],display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    (out/'progress.json').write_text(json.dumps(dict(stage=stage,errors=errors,received=received),indent=2))
    command('button 272 0');command('mods 0');server.close();state.cleanup()
    for window in app.topLevelWidgets():window.close()
    fixture.stdin.close();fixture.wait(timeout=3);shutil.rmtree(socket_dir)
