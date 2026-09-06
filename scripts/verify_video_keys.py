"""Native keystroke inspector controls, filtering and export."""
import copy,hashlib,json,os,subprocess,sys,time
from pathlib import Path
import cv2
from PIL import Image
from PySide6.QtCore import QPoint,Qt,QTimer
from PySide6.QtWidgets import QApplication,QMenu,QFileDialog
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.studio import zoom_at
from omnishot.widgets import JOBS
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.015)
    assert predicate()
def pointer(widget,point=None):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==e.windowTitle())
    local=widget.mapTo(e,point or widget.rect().center());x,y=client['at'][0]+local.x(),client['at'][1]+local.y()
    backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(70)
def click(widget,point=None,right=False):
    assert widget.isVisible() and widget.isEnabled()
    pointer(widget,point);command('click 273' if right else 'click 272');QTest.qWait(120)
def enter(widget,value):
    click(widget);backend.copy_text(str(value));command('key 30 4');command('key 47 4');command('key 28 0');QTest.qWait(100)
def drag(widget,a,b,cancel=False):
    pointer(widget,a);command('button 272 1');QTest.qWait(70)
    for n in range(1,9):
        pointer(widget,a+(b-a)*n/8)
    if cancel:command('key 1 0');QTest.qWait(100)
    command('button 272 0');QTest.qWait(130)
def save_dialog(path):
    wait(lambda:any(isinstance(w,QFileDialog) and w.isVisible() for w in app.topLevelWidgets()))
    QTest.qWait(120);command('key 38 4');QTest.qWait(60);backend.copy_text(str(path));command('key 47 4');QTest.qWait(60);command('key 28 0')
def screenshot(name):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==e.windowTitle())
    data=backend.grab_window(client);Image.fromarray(data).save(out/(name+'.png'));return data
import numpy as np
from omnishot.video_position import POSITIONS
from omnishot.video_keys import visible_keys
source=out/'source.mp4';backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=black:size=640x360:rate=15:duration=3','-c:v','libx264','-threads','1',source])
meta={'capture_options':{'keys':True,'commands_only':False},'events':[dict(t=.1,kind='key',state=1,label='A',command=False),dict(t=.7,kind='key',state=1,label='Ctrl+K',command=True)]}
source.with_suffix('.studio.json').write_text(json.dumps(meta));digest=hashlib.sha256(source.read_bytes()).hexdigest();store=backend.Store(out/'data');e=VideoEditor(source,store);e.player.pause();e.show();t=e.timeline

def labels():return visible_keys(meta['events'],e.player.position()/1000,e.edit_options(),meta)
def preview():
    e.refresh_preview();image=e.preview_image
    return np.asarray(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3).copy()
try:
    wait(lambda:e.last_frame is not None and t.duration>=3);click(e.tool_buttons['Keystrokes']);e.player.setPosition(1000);wait(lambda:e.player.position()==1000)
    panel=e.effect_controls['Keystrokes'];fields=panel.fields;grid=fields['key_position'];centers=[]
    for i,position in enumerate(POSITIONS):
        click(grid.buttons[i]);assert fields['key_position'].currentText()==position
        pixels=preview();ys,xs=np.where(pixels.max(axis=2)>30);centers.append([float(xs.mean()),float(ys.mean())])
    assert len({tuple(c) for c in centers})==9
    assert labels()==['A','Ctrl+K'];click(fields['key_commands_only'].commands);assert labels()==['Ctrl+K']
    click(e.undo_button);assert labels()==['A','Ctrl+K'] and fields['key_commands_only'].all.isChecked()
    click(e.redo_button);assert labels()==['Ctrl+K'] and fields['key_commands_only'].commands.isChecked()
    click(fields['key_style']);command('key 102 0');command('key 108 0');command('key 28 0');QTest.qWait(130);assert fields['key_style'].currentText()=='Light'
    light=preview();click(e.undo_button);assert fields['key_style'].currentText()=='Dark' and not np.array_equal(preview(),light)
    click(e.redo_button);assert np.array_equal(preview(),light)
    slider=fields['key_size'].slider;old=fields['key_size'].value();depth=len(e.edit_history.past)
    drag(slider,QPoint(slider.width()//6,slider.height()//2),QPoint(slider.width()//2,slider.height()//2));wait(lambda:len(e.edit_history.past)==depth+1);assert fields['key_size'].value()!=old
    size=fields['key_size'].value();click(e.undo_button);assert fields['key_size'].value()==old;click(e.redo_button);assert fields['key_size'].value()==size
    click(grid.buttons[4]);e.resize(900,650);QTest.qWait(180)
    wait(lambda:all(t.thumbnails.images.get(k) is not None for k,_,_ in t.thumbnail_tiles()));QTest.qWait(100);screenshot('keystroke-inspector')
    e.fps.setValue(15);e.size.setCurrentText('400');e.edit_history.flush(True)
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(lambda:save_dialog(out/'keys.omnishot-video'));timer.start(180);click(e.project_btn);wait(lambda:(out/'keys.omnishot-video').exists() and e.export_cancel is None)
    expected=e.edit_options();e.close();e=VideoEditor(out/'keys.omnishot-video',store);e.player.pause();wait(lambda:e.last_frame is not None);assert e.edit_options()==expected
    e.show();QTest.qWait(150);timer.timeout.disconnect();timer.timeout.connect(lambda:save_dialog(out/'keys.mp4'));timer.start(180);click(e.export_btn);wait(lambda:(out/'keys.mp4').exists() and e.export_cancel is None)
    cap=cv2.VideoCapture(str(out/'keys.mp4'));means=[]
    for seconds in (.4,1):
        cap.set(cv2.CAP_PROP_POS_MSEC,seconds*1000);ok,frame=cap.read();assert ok;means.append(float(frame.mean()))
    cap.release();assert means[0]<1 and means[1]>10,means
    e.close();wait(lambda:not JOBS);assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    report=dict(native_nine_positions=centers,native_command_filter_undo_redo=True,native_style_undo_redo=True,native_size_drag_grouping=True,portable_reopening=True,native_export_filtered_frame_means=means,source_unchanged=True,compact_layout=[900,650])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('button 272 0');command('mods 0');fixture.stdin.close();fixture.wait(timeout=3)
    for widget in app.topLevelWidgets():widget.close()
