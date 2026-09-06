"""Native audio preferences, setup persistence and accessible dialog controls."""
import json
from pathlib import Path
import subprocess
import sys
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import RecordSetup
from omnishot.widgets import Settings

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def click(widget,window,checkbox=False):
    from PySide6.QtWidgets import QScrollArea
    for scroll in window.findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(widget):scroll.ensureWidgetVisible(widget);QTest.qWait(100)
    QTest.qWait(80);assert widget.isVisible()
    client=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());point=widget.mapTo(window,widget.rect().center())
    if checkbox:point=widget.mapTo(window,widget.rect().topLeft());point.setX(point.x()+8);point.setY(point.y()+widget.height()//2)
    backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(80);command('click 272');QTest.qWait(150)
store=backend.Store(out/'data');settings=Settings(store,'recording');settings.show();QTest.qWait(250)
try:
    for key in ('record_show_controls','record_show_time','record_dnd','record_clicks','record_keys'):
        click(settings.fields[key],settings,True)
    click(settings.fields['record_countdown'],settings);command('key 30 4');command('key 11 0');command('key 15 0');QTest.qWait(100)
    click(settings.fields['record_scale_video'],settings,True)
    click(settings.fields['record_max_resolution'],settings);command('key 102 0');command('key 108 0');command('key 28 0');QTest.qWait(100)
    from PySide6.QtWidgets import QScrollArea
    scroll=next(w for w in settings.findChildren(QScrollArea) if w.widget() and w.widget().isAncestorOf(settings.fields['record_audio_tracks']))
    scroll.ensureWidgetVisible(settings.fields['record_audio_tracks']);QTest.qWait(100)
    click(settings.fields['record_audio_mono'],settings,True);click(settings.fields['record_audio_tracks'],settings);command('key 108 0');command('key 28 0');QTest.qWait(150)
    assert settings.fields['record_audio_tracks'].currentData()=='separate'
    box=settings.findChild(QDialogButtonBox);click(box.button(QDialogButtonBox.StandardButton.Save),settings)
    setup=RecordSetup(store);setup.show();QTest.qWait(350)
    assert setup.delay.value()==0
    assert not setup.dnd.isChecked() and setup.clicks.isChecked() and setup.keys.isChecked()
    assert setup.scale_video.isChecked() and setup.size.currentData()=='3840x2160'
    assert setup.mono.isChecked() and setup.audio_tracks.currentData()=='separate' and not setup.mic.isChecked()
    client=next(c for c in backend.hypr('clients') if c['title']==setup.windowTitle());bounds=app.primaryScreen().availableGeometry()
    setup.grab().save(str(out/'record-setup.png'))
    assert client['at'][1]>=bounds.top() and client['at'][1]+client['size'][1]<=bounds.bottom()+1,client
    box=setup.findChild(QDialogButtonBox);click(box.button(QDialogButtonBox.StandardButton.Ok),setup);opts=setup.options()
    assert not opts['show_controls'] and not opts['show_time'] and not opts['dnd'] and opts['clicks'] and opts['keys'] and opts['studio']
    assert opts['scale_video'] and opts['size']=='3840x2160'
    assert opts['mono'] and opts['separate_audio'] and opts['quality']==store.settings['quality'];loaded=backend.Store(store.root)
    assert loaded.settings['record_audio_mono'] and loaded.settings['record_audio_tracks']=='separate'
    report=dict(native_audio_preferences=True,native_resolution_preferences=True,native_general_preferences=True,setup_restoration=True,setup_fits_display=True,record_button_accessible=True,persisted_options=True,physical_microphone_used=False)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
