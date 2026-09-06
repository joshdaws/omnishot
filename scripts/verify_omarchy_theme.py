"""Native live theme replacement; never changes the desktop's actual theme."""
import json,sys,time,subprocess,os
from pathlib import Path
from PySide6.QtGui import QImage,QColor,QPalette,QIcon
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.theme import ThemeManager,paths,color
from omnishot.editor import Editor,Annotation
from omnishot.widgets import Settings,History
from omnishot.color_picker import ColorPicker
from omnishot.recording import VideoEditor

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False)
source=next(path for path in paths() if path.is_file());original=source.read_bytes()
owned=out/'current/theme/colors.toml';owned.parent.mkdir(parents=True);owned.write_bytes(original)
manager=ThemeManager(app,[owned]);store=backend.Store(out/'data')
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
image=QImage(800,450,QImage.Format.Format_RGB32);image.fill(QColor('#e2e9f1'));path=store.add(image=image)
editor=Editor(path,store);editor.show();settings=Settings(store);settings.show()
obj=Annotation(dict(kind='arrow',x=80,y=120,w=330,h=90,color='#ef4060'),editor);editor.scene.addItem(obj);editor.objects.append(obj);editor.commit();before=editor.render()
def wait(predicate):
    end=time.monotonic()+6
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate()
def settle():
    end=time.monotonic()+.3
    while time.monotonic()<end:app.processEvents();time.sleep(.02)
video=None
try:
    settle();settings.grab().save(str(out/'omarchy-settings.png'));settings.close();editor.fit();settle()
    editor.grab().save(str(out/'omarchy-editor.png'))
    editor.set_color('#ef4060');client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==editor.windowTitle());point=editor.color_btn.mapTo(editor,editor.color_btn.rect().center())
    backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());fixture.stdin.write('move 2 0\n');fixture.stdin.flush();settle();fixture.stdin.write('click 272\n');fixture.stdin.flush()
    wait(lambda:getattr(editor,'color_popup',None) is not None);picker=editor.color_popup;settle();picker.grab().save(str(out/'omarchy-color-picker.png'))
    first=dict(manager.applied)
    def toolbar_ink():
        image=editor.tools['select'].icon().pixmap(24,24,QIcon.Mode.Normal,QIcon.State.Off).toImage();scale=image.devicePixelRatio()
        return image.pixelColor(round(10*scale),round(11*scale)).name()
    assert toolbar_ink()==first['foreground'],(toolbar_ink(),first['foreground'])
    owned.parent.rename(owned.parent.with_name('previous-theme'));owned.parent.mkdir()
    owned.write_text('background="#f4efe7"\nforeground="#202830"\naccent="#864400"\n')
    wait(lambda:app.palette().color(QPalette.ColorRole.Window).name()=='#f4efe7');settle()
    assert editor.render()==before and picker.color.name()=='#ef4060'
    assert toolbar_ink()=='#202830'
    picker.grab().save(str(out/'fixture-color-picker.png'));picker.close();editor.grab().save(str(out/'fixture-editor.png'))
    owned.write_bytes(original);wait(lambda:manager.applied==first);settle();assert editor.render()==before
    history=History(store);history.show();settle();history.grab().save(str(out/'omarchy-history.png'));history.close()
    media=out/'theme-video.mp4'
    backend.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=5:duration=1','-c:v','libx264','-threads','1','-y',str(media)])
    video=VideoEditor(media,store);video.player.pause();video.show()
    wait(lambda:video.last_frame is not None)
    wait(lambda:all(video.timeline.thumbnails.images.get(k) is not None for k,_,_ in video.timeline.thumbnail_tiles()))
    settle();video_before=video.edit_options();video_pixels=QImage(video.preview_image)
    def video_ink():
        controls=list(video.tool_buttons.values())+[video.cut_tool,video.play_button,video.undo_button,video.redo_button,video.video.expand]
        for control in controls:
            for mode,state,ink in [(QIcon.Mode.Normal,QIcon.State.Off,'foreground'),(QIcon.Mode.Normal,QIcon.State.On,'on_accent'),(QIcon.Mode.Disabled,QIcon.State.Off,'muted')]:
                pixels=control.icon().pixmap(24,24,mode,state).toImage()
                assert any(pixels.pixelColor(x,y).alpha()==255 and pixels.pixelColor(x,y).name()==color(ink).name() for x in range(pixels.width()) for y in range(pixels.height())),(control.accessibleName(),ink)
    video_ink();video.grab().save(str(out/'omarchy-video.png'))
    owned.write_text('background="#f4efe7"\nforeground="#202830"\naccent="#864400"\n')
    wait(lambda:manager.applied['foreground']=='#202830');settle();video_ink()
    assert video.edit_options()==video_before and video.preview_image==video_pixels
    video.grab().save(str(out/'fixture-video.png'))
    owned.write_bytes(original);wait(lambda:manager.applied==first);settle();video_ink()
    video.close()
    assert source.read_bytes()==original
    report=dict(display_scale=backend.capture_monitors()[0]['scale'],palette_source=str(source),background=first['background'],accent=first['accent'],native_open_editor_and_popup_recolored=True,toolbar_vector_icons_recolored=True,video_vector_icons_normal_selected_disabled_recolored=True,video_options_and_composition_unchanged=True,atomic_directory_swap_detected=True,restored_palette_without_restart=True,annotation_and_export_pixels_unchanged=True,desktop_theme_file_unchanged=True,no_light_dark_setting='theme' not in settings.fields)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if video:video.close()
    editor.close();settings.close();manager.timer.stop();fixture.stdin.close();fixture.wait(timeout=3)
