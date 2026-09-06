"""Native thumbnail, zoom, scroll, edit, cancellation and project workflow."""
import copy,json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QPoint,Qt
from PySide6.QtWidgets import QApplication,QStyleOptionSlider,QStyle
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.widgets import JOBS
from omnishot.video_project import write_project,read_project
from omnishot.studio import export_studio
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.015)
    assert predicate()
def point(local):
    c=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==editor.windowTitle());backend.move_cursor(c['at'][0]+local.x()-2,c['at'][1]+local.y());command('move 2 0');QTest.qWait(70)
def click(widget):point(widget.mapTo(editor,widget.rect().center()));command('click 272');QTest.qWait(120)
def key(code,mods=0):command(f'key {code} {mods}');QTest.qWait(120)
def trackpoint(seconds,kind):return t.mapTo(editor,QPoint(round(t.x(seconds)),44 if kind=='zoom' else 88))
def drag(a,b,cancel=False):
    point(a);command('button 272 1');QTest.qWait(60);command(f'move {b.x()-a.x()} {b.y()-a.y()}');QTest.qWait(130)
    if cancel:key(1)
    command('button 272 0');QTest.qWait(120)
def ready():return all(key in t.thumbnails.images and t.thumbnails.images[key] is not None for key,_,_ in t.thumbnail_tiles())
def pan(end):
    option=QStyleOptionSlider();t.scroll.initStyleOption(option);r=t.scroll.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar,option,QStyle.SubControl.SC_ScrollBarSlider,t.scroll)
    point(t.scroll.mapTo(editor,r.center()));command('click 272');QTest.qWait(70);key(107 if end else 102);wait(ready)
source=out/'source.mp4';cmd=['ffmpeg','-v','error','-y']
for color in ['red','green','blue']:cmd+=['-f','lavfi','-i',f'color={color}:size=640x360:rate=15:duration=8']
backend.run(cmd+['-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]','-map','[v]','-c:v','libx264','-threads','1',source])
store=backend.Store(out/'data');editor=VideoEditor(source,store);editor.player.pause();editor.show();t=editor.timeline
try:
    wait(lambda:editor.last_frame is not None and t.duration==24 and t.fps==15);wait(ready)
    editor.zooms=[dict(start=3,end=5,scale=1.8,x=.5,y=.5)];editor.cuts=[[18,20]];editor.sync_timeline();QTest.qWait(180)
    original_options=editor.edit_options();editor.grab().save(str(out/'timeline-fit.png'))
    # Real compositor pixels prove the strip represents different source times.
    screen=backend.grab();c=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==editor.windowTitle());scale=backend.hypr('monitors')[0]['scale'];colors=[]
    for seconds,channel in [(2,0),(12,1),(22,2)]:
        local=trackpoint(seconds,'trim');pixel=screen[round((c['at'][1]+local.y())*scale),round((c['at'][0]+local.x())*scale),:3].astype(int);colors.append(pixel.tolist());assert pixel[channel]>100 and pixel[channel]>max(pixel[(channel+1)%3],pixel[(channel+2)%3])*3,pixel
    click(editor.timeline_plus);assert t.zoom_level==10
    click(editor.timeline_zoom);key(107);assert t.zoom_level==100 and t.scroll.maximum()>0;wait(ready)
    assert editor.edit_options()==original_options
    drag(trackpoint(4,'zoom'),trackpoint(5,'zoom'));assert abs(editor.zooms[0]['start']-4)<.03
    drag(trackpoint(6,'zoom'),trackpoint(7,'zoom'));assert abs(editor.zooms[0]['end']-7)<.03
    before=copy.deepcopy(editor.zooms);drag(trackpoint(5,'zoom'),trackpoint(5.5,'zoom'),cancel=True);assert editor.zooms==before
    # Holding a clip at the viewport edge pans without releasing the drag.
    a=trackpoint(5.5,'zoom');b=t.mapTo(editor,QPoint(t.width()-22,44));point(a);command('button 272 1');QTest.qWait(60)
    command(f'move {b.x()-a.x()} 0');QTest.qWait(350);assert t.offset()>.5 and editor.zooms[0]['start']>before[0]['start']
    key(1);command('button 272 0');QTest.qWait(100);assert editor.zooms==before and not t.auto_scroll.isActive();pan(False)
    drag(trackpoint(0,'trim')+QPoint(3,0),trackpoint(1,'trim')+QPoint(3,0));assert abs(editor.start.value()-1)<.04
    pan(True);assert t.offset()>10
    drag(trackpoint(24,'trim')-QPoint(3,0),trackpoint(22,'trim')-QPoint(3,0));assert abs(editor.end.value()-22)<.04
    point(trackpoint(19,'cut'));command('click 272');QTest.qWait(100);key(111);assert not editor.cuts
    editor.grab().save(str(out/'timeline-scrolled.png'))
    pan(False);assert t.offset()==0
    # Native seeking pauses during a drag and resumes only if it was playing.
    click(editor.play_button);assert editor.player.isPlaying()
    a=t.mapTo(editor,QPoint(round(t.x(2)),15));b=t.mapTo(editor,QPoint(round(t.x(6)),15));point(a);command('button 272 1');QTest.qWait(80);assert not editor.player.isPlaying()
    command(f'move {b.x()-a.x()} 0');QTest.qWait(100);command('button 272 0');QTest.qWait(130);assert editor.player.isPlaying() and 5800<editor.player.position()<6500
    click(editor.play_button);assert not editor.player.isPlaying()
    # Keyboard fit must agree with the transport control and preserve edits.
    point(t.mapTo(editor,QPoint(90,15)));command('click 272');QTest.qWait(70);key(11,4);assert t.zoom_level==0 and editor.timeline_zoom.value()==0
    editor.resize(900,650);QTest.qWait(220);assert editor.width()==900 and editor.height()==650
    assert t.isVisible() and editor.video.height()>=220;wait(ready);editor.grab().save(str(out/'timeline-compact.png'))
    expected=editor.edit_options();project=out/'timeline.omnishot-video';write_project(project,source,editor.metadata,expected)
    export_studio(source,out/'edited.mp4',editor.metadata,dict(expected,fps=5,width=160))
    probe=json.loads(backend.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',out/'edited.mp4']));assert abs(float(probe['format']['duration'])-21)<.3,probe
    count=len(t.thumbnails.images);memory=sum(i.sizeInBytes() for i in t.thumbnails.images.values() if i is not None)
    editor.close();wait(lambda:not JOBS)
    editor=VideoEditor(project,store);editor.player.pause();assert editor.edit_options()==expected;editor.close();wait(lambda:not JOBS)
    report=dict(native_chronological_thumbnails=colors,native_zoom_control=True,native_scrollbar=True,zoom_pan_preserve_edits=True,native_zoom_move_resize=True,native_drag_cancel=True,native_edge_scroll_cancel=True,native_trim_both_ends=True,native_cut_delete=True,native_seek_resumes_playback=True,native_fit_shortcut=True,compact_size=[900,650],editable_project_reopen=True,edited_export_duration=float(probe['format']['duration']),cached_thumbnails=count,cache_bytes=memory,background_decode_cleanup=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    editor.close();command('mods 0');command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
