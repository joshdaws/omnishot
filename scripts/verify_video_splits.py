"""Native cut-tool shortcuts, source clips, restore/merge, exports and projects."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import cv2
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.studio import export_studio
from omnishot.video_project import write_project
from omnishot.widgets import JOBS
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
def click(widget):point(widget.mapTo(editor,widget.rect().center()));command('click 272');QTest.qWait(100)
def key(code,mods=0):command(f'key {code} {mods}');QTest.qWait(100)
def track(seconds,y=88):point(t.mapTo(editor,QPoint(round(t.x(seconds)),y)));command('click 272');QTest.qWait(100)
def ready():return all(k in t.thumbnails.images and t.thumbnails.images[k] is not None for k,_,_ in t.thumbnail_tiles())
def inspect(path,times):
    cap=cv2.VideoCapture(str(path));duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/cap.get(cv2.CAP_PROP_FPS);colors=[]
    for seconds in times:
        cap.set(cv2.CAP_PROP_POS_MSEC,seconds*1000);ok,frame=cap.read();assert ok;colors.append(frame[20,20,::-1].tolist())
    cap.release();return duration,colors
source=out/'source.mp4';cmd=['ffmpeg','-v','error','-y']
for color in ('red','green','blue'):cmd+=['-f','lavfi','-i',f'color={color}:size=640x360:rate=15:duration=6']
backend.run(cmd+['-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]','-map','[v]','-c:v','libx264','-threads','1',source])
original=hashlib.sha256(source.read_bytes()).hexdigest();store=backend.Store(out/'data');editor=VideoEditor(source,store);editor.show();t=editor.timeline
try:
    wait(lambda:editor.last_frame is not None and t.duration==18 and t.fps==15);editor.player.pause();wait(lambda:not t.thumbnails.running)
    click(editor.tool_buttons['Motion']);click(editor.cut_tool);assert t.cut_mode;key(1);assert not t.cut_mode
    key(48);assert t.cut_mode and editor.cut_tool.isChecked() and editor.tool_buttons['Motion'].isChecked()
    track(6);assert editor.splits==[6.] and not editor.cuts
    key(1);assert not t.cut_mode and not editor.cut_tool.isChecked()
    track(12,15);key(48,4);assert editor.splits==[6.,12.] and not editor.cuts
    key(48,4);assert editor.splits==[6.,12.]
    wait(ready);QTest.qWait(100);editor.grab().save(str(out/'split-clips.png'))
    screen=backend.grab();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==editor.windowTitle());scale=backend.hypr('monitors')[0]['scale'];boundary_colors=[]
    for seconds,channel in [(6.2,1),(12.2,2)]:
        local=t.mapTo(editor,QPoint(round(t.x(seconds)),88));color=screen[round((client['at'][1]+local.y())*scale),round((client['at'][0]+local.x())*scale),:3].astype(int);boundary_colors.append(color.tolist());assert color[channel]>100 and color[channel]>max(color[(channel+1)%3],color[(channel+2)%3])*3,color
    before=editor.edit_options();click(editor.timeline_plus);assert editor.edit_options()==before
    t.set_zoom(0)
    export_studio(source,out/'split-only.mp4',editor.metadata,dict(before,width=160,fps=5))
    duration,colors=inspect(out/'split-only.mp4',[2,8,14]);assert abs(duration-18)<.1 and [max(range(3),key=lambda i:c[i]) for c in colors]==[0,1,2]
    track(9);assert t.selected==('clip',1);key(111);assert editor.cuts==[[6.,12.]]
    editor.player.setPosition(5900);editor.player.play();wait(lambda:editor.player.position()>12000);editor.player.pause()
    export_studio(source,out/'deleted.mp4',editor.metadata,dict(editor.edit_options(),width=160,fps=5))
    cut_duration,cut_colors=inspect(out/'deleted.mp4',[2,8]);assert abs(cut_duration-12)<.1 and [max(range(3),key=lambda i:c[i]) for c in cut_colors]==[0,2]
    # Restore the removed interval using the existing cut-range action.
    track(9);assert t.selected==('cut',0);key(111);assert not editor.cuts
    # Native context-menu removal of a split merges adjacent source clips.
    errors=[]
    def remove_split():
        try:
            menu=app.activePopupWidget();assert menu
            for _ in range(4):
                if menu.activeAction() and menu.activeAction().text()=='Remove split':command('key 28 0');return
                command('key 108 0');QTest.qWait(70)
            raise AssertionError('Remove split was not reached')
        except Exception as exc:errors.append(repr(exc));command('key 1 0')
    QTimer.singleShot(250,remove_split);point(t.mapTo(editor,QPoint(round(t.x(6)),88)));command('click 273');QTest.qWait(400);assert not errors and editor.splits==[12.],errors
    # Normal letter input must not switch the tool while editing text.
    click(editor.tool_buttons['Background']);click(editor.bg_color);key(30,4);key(48);assert editor.bg_color.text()=='b' and not t.cut_mode
    editor.bg_color.setText('#202633');editor.refresh_preview()
    editor.resize(900,650);QTest.qWait(150);assert editor.width()==900 and editor.height()==650 and editor.cut_tool.isVisible();wait(ready);editor.grab().save(str(out/'compact.png'))
    expected=editor.edit_options();project=out/'split.omnishot-video';write_project(project,source,editor.metadata,expected)
    editor.close();wait(lambda:not JOBS);editor=VideoEditor(project,store);editor.player.pause();assert editor.edit_options()==expected and editor.splits==[12.];editor.close();wait(lambda:not JOBS)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    report=dict(native_cut_tool=True,native_B=True,native_Ctrl_B=True,duplicate_split_ignored=True,inspector_selection_preserved=True,native_boundary_thumbnail_colors=boundary_colors,split_only_duration=duration,split_only_colors=colors,delete_clip_duration=cut_duration,delete_clip_colors=cut_colors,playback_skips_deleted_clip=True,restore_clip=True,native_merge=True,text_input_untouched=True,portable_project_reopen=True,source_unchanged=True,compact_size=[900,650])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    editor.close();command('button 272 0');command('mods 0');fixture.stdin.close();fixture.wait(timeout=3)
