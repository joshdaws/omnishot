"""Native audio preferences, setup persistence and accessible dialog controls."""
import json
from pathlib import Path
import subprocess
import sys
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import RecordSetup,VideoEditor
from omnishot.widgets import Settings

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def click(widget,window,checkbox=False):
    QTest.qWait(80);assert widget.isVisible()
    client=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());point=widget.mapTo(window,widget.rect().center())
    if checkbox:point=widget.mapTo(window,widget.rect().topLeft());point.setX(point.x()+8);point.setY(point.y()+widget.height()//2)
    backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(80);command('click 272');QTest.qWait(150)
def choose(widget,window,down):
    click(widget,window);command('key 102 0')
    for _ in range(down):command('key 108 0')
    command('key 28 0');QTest.qWait(150)
store=backend.Store(out/'data');settings=Settings(store,'recording');settings.show();QTest.qWait(250)
try:
    # Scroll the settings page to make every GIF preference reachable.
    page=settings.fields['gif_width'].parentWidget()
    from PySide6.QtWidgets import QScrollArea
    scroll=next(w for w in settings.findChildren(QScrollArea) if w.widget() and w.widget().isAncestorOf(settings.fields['gif_quality']))
    scroll.ensureWidgetVisible(settings.fields['gif_quality']);QTest.qWait(150)
    choose(settings.fields['gif_fps'],settings,1);choose(settings.fields['gif_width'],settings,2)
    click(settings.fields['gif_quality'],settings);command('key 107 0');QTest.qWait(100)
    click(settings.fields['gif_optimize'],settings,True)
    box=settings.findChild(QDialogButtonBox);click(box.button(QDialogButtonBox.StandardButton.Save),settings)
    assert store.settings['gif_fps']==10 and store.settings['gif_width']==600 and store.settings['gif_quality']==100 and not store.settings['gif_optimize']
    setup=RecordSetup(store);setup.show();QTest.qWait(250);choose(setup.format,setup,1)
    assert not setup.mic.isEnabled() and setup.fps.currentText()=='10' and setup.gif_width.currentData()==600 and setup.gif_quality.value()==100 and not setup.gif_optimize.isChecked()
    choose(setup.format,setup,0);assert setup.fps.currentText()=='30';choose(setup.format,setup,1);assert setup.fps.currentText()=='10'
    setup.grab().save(str(out/'gif-record-setup.png'))
    box=setup.findChild(QDialogButtonBox);click(box.button(QDialogButtonBox.StandardButton.Ok),setup);opts=setup.options()
    assert opts['format']=='GIF' and opts['fps']==10 and opts['gif_width']==600 and opts['size']=='Native'
    assert store.settings['fps']==30 and store.settings['gif_fps']==10
    source=out/'generated.mp4';backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=240x160:r=15:d=1','-c:v','libx264','-threads','1',source])
    editor=VideoEditor(source,store);editor.show();QTest.qWait(300);click(editor.tool_buttons['Export'],editor);choose(editor.format,editor,1)
    assert editor.audio.isMuted() and editor.fps.value()==10 and editor.size.currentText()=='600' and editor.gif_quality.value()==100 and not editor.gif_optimize.isChecked()
    editor.grab().save(str(out/'gif-export-editor.png'));editor.save_edits();editor.close();other=VideoEditor(source,store)
    assert other.audio.isMuted() and other.format.currentText()=='GIF' and other.fps.value()==10 and other.size.currentText()=='600' and other.gif_quality.value()==100 and not other.gif_optimize.isChecked()
    report=dict(native_gif_preferences=True,setup_profile_switching=True,video_fps_preserved=True,native_editor_format_switch=True,export_profile_reopened=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
