"""Native full-screen composition, transport, keyboard and display placement."""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QPoint,Qt,QRectF
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication,QStyle,QStyleOptionSlider
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
second=bool(os.environ.get('OMNISHOT_SECOND_SCREEN'))
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors')),'Requires isolated compositor'
if second:
    backend.run(['hyprctl','output','create','headless','HEADLESS-2'])
    config=Path(os.environ['XDG_RUNTIME_DIR'])/'hyprland.lua';assert config.parent.name.startswith('os-') and config.parent.parent==Path('/tmp')
    with config.open('a') as f:f.write('\nhl.monitor({output="HEADLESS-2",mode="1920x1080@60",position="1800x0",scale=1})\n')
    backend.run(['hyprctl','reload'])
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.015)
    assert predicate()
def client(widget):return next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle())
def point(window,local,settle=True):
    c=client(window);backend.move_cursor(c['at'][0]+local.x()-2,c['at'][1]+local.y());command('move 2 0')
    if settle:QTest.qWait(70)
def seek_handle(preview):
    option=QStyleOptionSlider();preview.seek.initStyleOption(option)
    rect=preview.seek.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,preview.seek)
    return preview.seek.mapTo(preview,rect.center())
def click(widget):
    window=widget.window();point(window,widget.mapTo(window,widget.rect().center()));command('click 272');QTest.qWait(140)
def key(code,mods=0):command(f'key {code} {mods}');QTest.qWait(150)
def begin(button=True):
    if button:click(editor.video.expand)
    else:key(87)
    wait(lambda:editor.fullscreen_preview is not None)
    p=editor.fullscreen_preview;wait(lambda:client(p).get('fullscreen',0)!=0)
    wait(lambda:backend.hypr('activewindow').get('title')==p.windowTitle());QTest.qWait(120)
    assert p.screen().name()==target and client(p)['monitor']==monitor['id']
    assert client(p)['size']==[round(monitor['width']/monitor['scale']),round(monitor['height']/monitor['scale'])],client(p)
    return p
source=out/'source.mp4';camera=out/'camera.mp4'
backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=15:duration=12','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','12','-c:v','libx264','-threads','1','-c:a','aac',source])
backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc=size=240x180:rate=15:duration=12','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',camera])
metadata={'camera_path':str(camera),'cursor':[{'t':0,'x':.2,'y':.3},{'t':12,'x':.8,'y':.7}],'events':[{'kind':'click','t':1,'x':.4,'y':.5},{'kind':'key','state':1,'t':1,'label':'Ctrl+C'}]}
source.with_suffix('.studio.json').write_text(json.dumps(metadata));store=backend.Store(out/'data')
editor=VideoEditor(source,store);editor.player.pause();editor.padding.setValue(32);editor.styles.update(background2='#4869bc',radius=12,shadow=True);editor.refresh_preview()
target='HEADLESS-2' if second else 'HEADLESS-1';wait(lambda:any(s.name()==target for s in app.screens()));screen=next(s for s in app.screens() if s.name()==target)
editor.winId();editor.windowHandle().setScreen(screen);editor.show();wait(lambda:editor.last_frame is not None and bool(editor.player.audioTracks()))
QTest.qWait(250);monitor=next(m for m in backend.hypr('monitors') if m['name']==target)
if second:
    address=client(editor)['address']
    backend.run(['hyprctl','eval',f'hl.dispatch(hl.dsp.window.move({{window="address:{address}",monitor="HEADLESS-2",follow=true}}))'])
    wait(lambda:client(editor)['monitor']==monitor['id'] and editor.screen().name()==target)
try:
    editor.player.setPosition(1000);QTest.qWait(180);editor.refresh_preview();initial=editor.edit_options();initial_client=client(editor);player=editor.player
    p=begin();assert editor.player is player and editor.player.position()==1000 and not editor.player.isPlaying()
    assert p.image==editor.preview_image and p.image.width()==704 and p.image.height()==424
    point(p,QPoint(12,90));p.grab().save(str(out/'fullscreen.png'))
    # Compare compositor pixels to the full-resolution composed image. Control
    # overlay and the harness's startup banner are outside the compared area.
    actual=backend.grab(output=target);expected=QImage(monitor['width'],monitor['height'],QImage.Format.Format_RGB888);expected.fill(QColor('black'))
    scale=monitor['scale'];r=p.image_rect();painter=QPainter(expected);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QRectF(r.x()*scale,r.y()*scale,r.width()*scale,r.height()*scale),editor.preview_image);painter.end()
    raw=np.asarray(expected.bits(),dtype=np.uint8).reshape(expected.height(),expected.bytesPerLine())[:,:expected.width()*3].reshape(expected.height(),expected.width(),3)
    region=np.s_[round(120*scale):round((p.controls.y()-20)*scale),round(40*scale):round((p.width()-40)*scale)]
    delta=np.abs(actual[region][:,:,:3].astype(int)-raw[region].astype(int));agreement=float(np.mean(delta.max(2)<=3));maximum_delta=int(delta.max());assert agreement>.99,agreement
    original_frame=editor.last_frame.copy();click(p.next);assert 1050<=editor.player.position()<=1090 and not editor.player.isPlaying()
    assert not np.array_equal(editor.last_frame,original_frame)
    click(p.previous);assert 995<=editor.player.position()<=1005 and np.array_equal(editor.last_frame,original_frame)
    point(p,QPoint(12,90));key(1);wait(lambda:editor.fullscreen_preview is None)
    assert client(editor)['size']==initial_client['size'] and client(editor)['at']==initial_client['at'] and editor.edit_options()==initial
    p=begin(False);point(p,QPoint(12,90));key(57);assert editor.player.isPlaying();p.setFocus()
    wait(lambda:not p.controls.isVisible(),4);assert p.cursor().shape()==Qt.CursorShape.BlankCursor
    point(p,QPoint(15,94));wait(lambda:p.controls.isVisible());assert p.cursor().shape()!=Qt.CursorShape.BlankCursor
    key(57);assert not editor.player.isPlaying() and p.controls.isVisible()
    key(106);stepped=editor.player.position();assert not editor.player.isPlaying()
    key(105);assert abs(editor.player.position()-(stepped-67))<=1
    key(50);assert editor.audio_muted.isChecked();key(50);assert not editor.audio_muted.isChecked()
    editor.start.setValue(.4);editor.end.setValue(9)
    key(102);assert editor.player.position()==400
    key(107);assert editor.player.position()==9000
    key(105,1);assert editor.player.position()==8000
    # Real slider handle drag seeks without starting paused playback.
    editor.player.setPosition(1000);QTest.qWait(100)
    a=seek_handle(p);b=p.seek.mapTo(p,QPoint(round(p.seek.width()*.43),p.seek.height()//2))
    point(p,a);command('button 272 1');QTest.qWait(80);command(f'move {b.x()-a.x()} 0');QTest.qWait(130);command('button 272 0');QTest.qWait(180)
    assert 4500<editor.player.position()<6000 and not editor.player.isPlaying(),editor.player.position()
    click(p.play);assert editor.player.isPlaying()
    a=seek_handle(p)
    b=p.seek.mapTo(p,QPoint(round(p.seek.width()*.57),p.seek.height()//2))
    # The handle keeps moving while playing: press without the usual pointer
    # settling delay, using the widget's styled handle rather than an estimate.
    point(p,a,settle=False);command('button 272 1');QTest.qWait(70)
    assert p.scrubbing and not editor.player.isPlaying(),(a,seek_handle(p),p.seek.value(),p.seek.isSliderDown())
    command(f'move {b.x()-a.x()} 0');QTest.qWait(100);command('button 272 0');QTest.qWait(150)
    assert editor.player.isPlaying() and 6200<editor.player.position()<7800
    click(p.play);assert not editor.player.isPlaying()
    click(p.exit);wait(lambda:editor.fullscreen_preview is None)
    # Double-click enters without changing playback, then exits without the
    # single-click playback timer firing after the full-screen window is gone.
    point(editor,editor.video.mapTo(editor,editor.video.rect().center()));command('click 272');QTest.qWait(70);command('click 272');wait(lambda:editor.fullscreen_preview is not None)
    p=editor.fullscreen_preview;QTest.qWait(200);assert not editor.player.isPlaying()
    point(p,QPoint(200,200));command('click 272');QTest.qWait(70);command('click 272');wait(lambda:editor.fullscreen_preview is None);QTest.qWait(450);assert not editor.player.isPlaying()
    p=begin(False);key(87);wait(lambda:editor.fullscreen_preview is None)
    options=editor.edit_options();editor.grab().save(str(out/'editor-restored.png'));p=begin();editor.close();wait(lambda:editor.fullscreen_preview is None)
    wait(lambda:not any(c['pid']==os.getpid() for c in backend.hypr('clients')))
    report=dict(native_expand_button=True,native_f11=True,native_escape=True,native_double_click=True,native_transport=True,source_frame_step_15fps=True,source_seek_slider=True,scrub_restores_playing_state=True,trim_home_end=True,shift_seek=True,shared_player=True,composed_camera_background_cursor=True,compositor_pixel_agreement=agreement,maximum_channel_difference=maximum_delta,controls_auto_hide=True,cursor_restored=True,editor_geometry_preserved=True,editor_options_preserved=True,monitor=target,scale=scale,fullscreen_pixels=[monitor['width'],monitor['height']],editor_close_cleans_preview=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    editor.close();command('mods 0');command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
