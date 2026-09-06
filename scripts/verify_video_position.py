"""Native camera position, shrink, preview pixels, export and project round trip."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import cv2,numpy as np
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QScrollArea,QCheckBox
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.video_position import POSITIONS
from omnishot.video_project import write_project
from omnishot.widgets import JOBS
from omnishot.studio import export_studio
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=5):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.015)
    assert predicate()
def click(widget):
    parent=widget.parentWidget()
    while parent and not isinstance(parent,QScrollArea):parent=parent.parentWidget()
    if parent:parent.ensureWidgetVisible(widget);QTest.qWait(80)
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==editor.windowTitle())
    local=widget.mapTo(editor,QPoint(8,widget.height()//2) if isinstance(widget,QCheckBox) else widget.rect().center())
    backend.move_cursor(client['at'][0]+local.x()-2,client['at'][1]+local.y());command('move 2 0');QTest.qWait(70);command('click 272');QTest.qWait(130)
def key(code,mods=0):command(f'key {code} {mods}');QTest.qWait(100)
def box(pixels):
    y,x=np.where((pixels[:,:,0]>200)&(pixels[:,:,1]<35)&(pixels[:,:,2]<35));return np.array([x.min(),y.min(),x.max()+1,y.max()+1])
def pixels(image):return np.asarray(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3)
def native_match():
    capture=backend.grab();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==editor.windowTitle());scale=backend.hypr('monitors')[0]['scale']
    local=editor.video.mapTo(editor,QPoint(0,0));x=round((client['at'][0]+local.x())*scale);y=round((client['at'][1]+local.y())*scale)
    region=capture[y:y+round(editor.video.height()*scale),x:x+round(editor.video.width()*scale),:3];actual=box(region)
    image=editor.preview_image;expected=box(pixels(image));factor=min(editor.video.width()/image.width(),editor.video.height()/image.height())
    origin=np.array([(editor.video.width()-image.width()*factor)/2,(editor.video.height()-image.height()*factor)/2]*2)
    delta=float(np.max(np.abs(actual-(expected*factor+origin)*scale)));assert delta<3.5,(actual,expected,delta)
    return delta
source=out/'source.mp4';camera=out/'camera.mp4'
for path,color,size in [(source,'#202020','640x360'),(camera,'red','160x90')]:backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color={color}:size={size}:rate=15:duration=4','-c:v','libx264','-threads','1',path])
source.with_suffix('.studio.json').write_text(json.dumps(dict(camera_path=str(camera),cursor=[],events=[])))
original=hashlib.sha256(source.read_bytes()).hexdigest();store=backend.Store(out/'data');editor=VideoEditor(source,store);editor.show()
try:
    wait(lambda:editor.last_camera is not None);editor.player.pause();editor.styles.update(camera_shadow=False);editor.padding.setValue(24)
    click(editor.tool_buttons['Camera']);click(editor.camera_shape);key(102);key(108);key(28);assert editor.camera_shape.currentText()=='Square'
    deltas=[]
    for i,name in enumerate(POSITIONS):
        click(editor.camera_position.buttons[i]);assert editor.camera_position.currentText()==name;deltas.append(native_match())
    key(103);assert editor.camera_position.currentText()=='Center Right';key(105);assert editor.camera_position.currentText()=='Center';deltas.append(native_match())
    editor.zooms=[dict(start=1,end=3,scale=2,x=.5,y=.5)];editor.sync_timeline();editor.player.setPosition(2000);wait(lambda:abs(editor.player.position()-2000)<100);QTest.qWait(200)
    shrink=editor.effect_controls['Camera'].fields['camera_shrink'];normal=box(pixels(editor.preview_image));click(shrink);assert editor.styles['camera_shrink'];small=box(pixels(editor.preview_image))
    ratio=(small[2]-small[0])/(normal[2]-normal[0]);assert .82<ratio<.88;deltas.append(native_match())
    editor.grab().save(str(out/'camera-editor.png'))
    click(editor.camera_fullscreen);assert np.array_equal(box(pixels(editor.preview_image)),[0,0,editor.preview_image.width(),editor.preview_image.height()]);click(editor.camera_fullscreen)
    click(editor.camera_position.buttons[1]);expected=editor.edit_options();project=out/'camera.omnishot-video';write_project(project,source,editor.metadata,expected)
    export_studio(source,out/'edited.mp4',editor.metadata,dict(expected,width=320,fps=5))
    video=cv2.VideoCapture(str(out/'edited.mp4'));widths=[]
    for second in (0,2,3.8):
        video.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,frame=video.read();assert ok;bounds=box(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));widths.append(int(bounds[2]-bounds[0]))
    video.release();assert widths[1]<widths[0]*.9 and abs(widths[0]-widths[2])<=2,widths
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    editor.close();wait(lambda:not JOBS);editor=VideoEditor(project,store);editor.player.pause();assert editor.edit_options()==expected and editor.camera_position.buttons[1].isChecked() and editor.effect_controls['Camera'].fields['camera_shrink'].isChecked();editor.close();wait(lambda:not JOBS)
    report=dict(native_nine_positions=True,native_arrow_navigation=True,square_shape=True,compositor_max_edge_difference=max(deltas),native_shrink_ratio=ratio,fullscreen_ignores_shrink=True,export_camera_widths=widths,portable_project_reopen=True,source_unchanged=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    editor.close();command('button 272 0');command('mods 0');fixture.stdin.close();fixture.wait(timeout=3)
