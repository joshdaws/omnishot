"""Native cursor tiles, size/motion edits, undo, project reopening and export."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtCore import QPoint,QTimer,Qt
from PySide6.QtWidgets import QApplication,QScrollArea,QFileDialog,QStyle,QStyleOptionSlider,QCheckBox,QDialogButtonBox,QColorDialog,QLineEdit
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.theme import ThemeManager
from omnishot.recording import VideoEditor
from omnishot.widgets import JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);theme=ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=7):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate()
def pointer(widget,point=None):
    top=widget.window();client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==top.windowTitle())
    point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(60)
def visible(widget):
    for scroll in e.findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(widget):scroll.ensureWidgetVisible(widget);QTest.qWait(90)
def click(widget):visible(widget);pointer(widget,QPoint(8,widget.height()//2) if isinstance(widget,QCheckBox) else None);command('click 272');QTest.qWait(130)
def source_frame():
    e.player.setPosition(800);wait(lambda:e.player.position()==800);QTest.qWait(80);e.refresh_preview();return e.preview_image.copy()
def file_dialog(path):
    wait(lambda:any(isinstance(w,QFileDialog) and w.isVisible() for w in app.topLevelWidgets()))
    QTest.qWait(100);command('key 38 4');QTest.qWait(60);backend.copy_text(str(path));command('key 47 4');QTest.qWait(60);command('key 28 0')
def save_via(button,path):
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(lambda:file_dialog(path));timer.start(180);click(button)
    wait(lambda:path.exists() and e.export_cancel is None,12)
def effects(style,accept,color=None):
    from omnishot.video_styles import EffectsDialog
    failures=[];finished=[];renders=[]
    def interact():
        if not isinstance(app.activeModalWidget(),EffectsDialog):timer.start(50);return
        try:
            dialog=app.activeModalWidget();QTest.qWait(100)
            assert dialog.fields['cursor_color'].isVisible() and dialog.fields['cursor_outline'].isVisible()
            click(dialog.fields['cursor_style'].buttons[style])
            if color:
                def choose_color():
                    if not isinstance(app.activeModalWidget(),QColorDialog):color_timer.start(50);return
                    try:
                        chooser=app.activeModalWidget();QTest.qWait(100)
                        field=next(w for w in chooser.findChildren(QLineEdit) if w.isVisible() and w.text().startswith('#'))
                        pointer(field);command('click 272');QTest.qWait(60);backend.copy_text(color);command('key 30 4');command('key 47 4');QTest.qWait(100)
                        click(chooser.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok))
                    except Exception as exc:
                        failures.append(repr(exc));app.activeModalWidget().reject()
                color_timer=QTimer();color_timer.setSingleShot(True);color_timer.timeout.connect(choose_color);color_timer.start(150)
                click(dialog.fields['cursor_color']);assert not failures,failures
            renders.append(source_frame())
            pointer(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok if accept else QDialogButtonBox.StandardButton.Cancel));command('click 272')
            finished.append(True)
        except Exception as exc:
            failures.append(repr(exc))
            for widget in app.topLevelWidgets():
                if isinstance(widget,(EffectsDialog,QColorDialog)):widget.reject()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(interact);timer.start(150)
    click(e.effect_controls['Cursor'].cursor_more);assert finished and not failures,failures
    return renders[0]
source=out/'cursor.mp4';backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=white:s=320x200:r=5:duration=2','-c:v','libx264','-threads','1','-y',str(source)])
metadata=dict(cursor=[dict(t=t,x=x,y=.25) for t,x in [(0,.2),(.4,.7),(.8,.3),(1.2,.65),(1.6,.25),(2,.6)]],events=[dict(kind='click',t=.68,x=.3,y=.25)])
source.with_suffix('.studio.json').write_text(json.dumps(metadata));original=hashlib.sha256(source.read_bytes()).hexdigest();store=backend.Store(out/'data')
e=VideoEditor(source,store);e.player.pause();e.show()
try:
    wait(lambda:e.last_frame is not None and e.timeline.duration==2);QTest.qWait(200)
    h=e.edit_history;h.flush(True);before=h.snapshot();depth=len(h.past)
    assert e.cursor_size.label.text()=='1×' and e.smoothing.buttons['Smooth'].isChecked()
    slider=e.cursor_size.slider;visible(slider);option=QStyleOptionSlider();slider.initStyleOption(option)
    a=slider.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,slider).center();b=QPoint(round(slider.width()*.65),a.y())
    pointer(slider,a);command('button 272 1');QTest.qWait(70)
    for i in range(1,7):pointer(slider,a+(b-a)*i/6)
    command('button 272 0');wait(lambda:len(h.past)==depth+1)
    size=e.cursor_size.value();label=e.cursor_size.label.text();assert size>50 and e.studio_options()['cursor_size']==size
    click(e.undo_button);assert h.snapshot()==before and e.cursor_size.label.text()=='1×'
    click(e.redo_button);assert e.cursor_size.value()==size and e.cursor_size.label.text()==label
    panel=e.effect_controls['Cursor'];choices=panel.fields['cursor_style'];renders={}
    assert not panel.fields['cursor_color'].isVisible() and not panel.fields['cursor_outline'].isVisible()
    assert not choices.buttons['Crosshair'].isVisible()
    for name in ('Arrow','Rounded Arrow','Dot'):
        click(choices.buttons[name]);assert choices.currentText()==name and choices.buttons[name].isChecked()
        renders[name]=source_frame()
    h.flush(True);before=h.snapshot();depth=len(h.past);original_preview=source_frame()
    discarded=effects('Crosshair',False,'#40a060')
    assert source_frame()==original_preview and h.snapshot()==before and len(h.past)==depth,dict(preview_equal=source_frame()==original_preview,options_equal=h.snapshot()==before,depth=[depth,len(h.past)],before=before,after=h.snapshot())
    effects('Crosshair',True,'#40a060');wait(lambda:len(h.past)==depth+1)
    assert choices.buttons['Crosshair'].isVisible() and choices.buttons['Crosshair'].isChecked()
    assert e.styles['cursor_color'].lower()=='#ff40a060'
    renders['Crosshair']=source_frame();assert renders['Crosshair']==discarded
    click(e.undo_button);assert h.snapshot()==before and not choices.buttons['Crosshair'].isVisible()
    click(e.redo_button);assert choices.buttons['Crosshair'].isVisible() and source_frame()==renders['Crosshair']
    assert all(renders[a]!=renders[b] for i,a in enumerate(renders) for b in list(renders)[i+1:])
    click(choices.buttons['Rounded Arrow']);smooth=source_frame();click(e.smoothing.buttons['Natural'])
    assert not choices.buttons['Crosshair'].isVisible()
    assert not e.smoothing.isChecked() and e.studio_options()['smoothing']==0;natural=source_frame();assert natural!=smooth
    click(e.undo_button);assert e.smoothing.buttons['Smooth'].isChecked() and source_frame()==smooth
    click(e.redo_button);assert e.smoothing.buttons['Natural'].isChecked() and source_frame()==natural
    click(e.smoothing.buttons['Smooth']);assert source_frame()==smooth
    # The two effects can be enabled alone or together. Old project defaults
    # retain their ripple and do not acquire cursor compression automatically.
    assert not e.press_effect.isChecked() and e.show_clicks.isChecked()
    ripple=source_frame();click(e.show_clicks);assert not e.show_clicks.isChecked();plain=source_frame()
    click(e.press_effect);assert e.press_effect.isChecked();pressed=source_frame()
    click(e.show_clicks);assert e.press_effect.isChecked() and e.show_clicks.isChecked();both=source_frame()
    effect_frames=[plain,pressed,ripple,both];assert all(a!=b for i,a in enumerate(effect_frames) for b in effect_frames[i+1:])
    click(e.undo_button);assert e.press_effect.isChecked() and not e.show_clicks.isChecked() and source_frame()==pressed
    click(e.redo_button);assert e.press_effect.isChecked() and e.show_clicks.isChecked() and source_frame()==both
    e.resize(900,650);QTest.qWait(150)
    scroll=e.inspector.currentWidget();assert scroll.widget().width()<=scroll.viewport().width()
    scroll.verticalScrollBar().setValue(0);QTest.qWait(150);e.grab().save(str(out/'cursor-inspector.png'))
    assert scroll.viewport().rect().contains(e.show_clicks.mapTo(scroll.viewport(),e.show_clicks.rect().bottomRight()))
    e.fps.setValue(5);e.size.setCurrentText('Original');h.flush(True);options=e.edit_options()
    project=out/'cursor.omnishot-video';save_via(e.project_btn,project);e.close();wait(lambda:not JOBS)
    e=VideoEditor(project,store);e.player.pause();e.show();wait(lambda:e.last_frame is not None)
    assert e.edit_options()==options and e.cursor_size.value()==size and e.cursor_size.label.text()==label
    assert e.effect_controls['Cursor'].fields['cursor_style'].buttons['Rounded Arrow'].isChecked() and e.smoothing.buttons['Smooth'].isChecked()
    assert e.press_effect.isChecked() and e.show_clicks.isChecked()
    expected=source_frame();export=out/'cursor-export.mp4';save_via(e.export_btn,export)
    cap=cv2.VideoCapture(str(export));cap.set(cv2.CAP_PROP_POS_MSEC,800);ok,actual=cap.read();cap.release();assert ok
    expected=expected.convertToFormat(expected.Format.Format_RGB888)
    raw=np.asarray(expected.bits(),dtype=np.uint8).reshape(expected.height(),expected.bytesPerLine())[:,:expected.width()*3].reshape(expected.height(),expected.width(),3)
    delta=np.abs(actual[:,:,::-1].astype(int)-raw.astype(int));assert delta.mean()<2 and np.count_nonzero(actual<150)>20
    e.close();wait(lambda:not JOBS);assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    report=dict(native_size_drag=True,size_pixels=size,multiplier_label=label,one_undo_step_per_drag=True,undo_redo_updates_controls=True,visual_cursor_styles=list(renders),distinct_cursor_renders=True,three_primary_cursor_tiles=True,advanced_colors_and_crosshair_native_dialog=True,advanced_cancel_restores_preview=True,advanced_accept_one_undo_step=True,legacy_crosshair_visible_when_selected=True,click_controls_visible_at_compact_size=True,natural_smooth_native_toggle=True,motion_undo_redo=True,independent_press_ripple_native_controls=True,four_distinct_effect_combinations=True,effect_undo_redo=True,legacy_defaults_preserved=True,compact_layout=[900,650],portable_project_reopening=True,press_and_ripple_reopened=True,native_mp4_export=True,export_mean_channel_difference=float(delta.mean()),source_unchanged=True,display_scale=1.6)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('button 272 0');command('mods 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
