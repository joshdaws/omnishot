"""Native area, previous area, display and desktop capture at mixed scales."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from PIL import Image
from omnishot.theme import ThemeManager
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.widgets import JOBS
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
monitors=backend.hypr('monitors');assert monitors and all(m['name'].startswith('HEADLESS-') for m in monitors),'Only run in the isolated compositor'
backend.run(['hyprctl','output','create','headless','HEADLESS-2'])
# Loading a compositor plugin reloads its config. Persist the generated output's
# scale in this disposable harness so the reload does not reset it to autodetect.
config=Path(os.environ['XDG_RUNTIME_DIR'])/'hyprland.lua'
assert config.parent.name.startswith('os-') and config.parent.parent==Path('/tmp') and config.is_file()
left="--left" in sys.argv;second_x=-1920 if left else 1800
with config.open('a') as f:f.write('\nhl.monitor({output="HEADLESS-2",mode="1920x1080@60",position="'+str(second_x)+'x0",scale=1})\n')
backend.run(['hyprctl','reload'])
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False);QTest.qWait(300)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate()
class Pattern(QWidget):
    def __init__(self,color):super().__init__();self.color=color
    def paintEvent(self,event):p=QPainter(self);p.fillRect(self.rect(),QColor(self.color))
sources=[]
for name,color in [('HEADLESS-1','#468ac0'),('HEADLESS-2','#ce9850')]:
    screen=next(s for s in app.screens() if s.name()==name);window=Pattern(color);window.setWindowTitle('OmniShot '+name+' Pattern');window.winId();window.windowHandle().setScreen(screen);window.showFullScreen();sources.append(window);QTest.qWait(150)
state=Controller(app);errors=[];application.error=lambda parent,message:errors.append(str(message))
state.store.settings.update(window_wallpaper=False,freeze=True,background_preset='None',overlay_timeout=0)

def focus(index):
    screen=next(m for m in backend.capture_monitors() if m['name']==f'HEADLESS-{index+1}')
    backend.move_cursor(screen['x']+98,100);command('move 2 0');QTest.qWait(100)
    client=next(c for c in backend.hypr('clients') if c['title']==sources[index].windowTitle());backend.focus_window(client['address']);QTest.qWait(100)
    assert next(m['name'] for m in backend.hypr('monitors') if m['focused'])==screen['name']

def capture(command_name,geometry=None):
    state.close_all_overlays();QTest.qWait(100);before=len(state.store.history())
    args=dict(command=command_name,action='overlay')
    if geometry:args['geometry']=backend.geometry_text(geometry)
    state.dispatch(args);wait(lambda:not state.busy and not JOBS and len(state.store.history())==before+1)
    assert not state.selectors and not errors,errors
    path=Path(state.store.history()[0]['path']);return path,Image.open(path).convert('RGB')

def recolor(index,color):sources[index].color=color;sources[index].update();QTest.qWait(150)

try:
    state.store.settings.pop('previous_area',None);state.dispatch(dict(command='previous'))
    wait(lambda:not state.busy and not JOBS);assert errors==['Capture an area first'] and not state.store.history();errors.clear()
    rect=(second_x+100,150,500,300);path,image=capture('area',rect)
    assert image.size==(500,300) and image.getpixel((200,100))==(206,152,80)
    assert state.store.metadata(path)['pixel_ratio']==1
    assert backend.Store(state.store.root).settings['previous_area']==list(rect)
    recolor(1,'#c85670');focus(0);path,image=capture('previous')
    assert image.size==(500,300) and image.getpixel((200,100))==(200,86,112)
    assert state.store.settings['previous_area']==list(rect)
    # A pin overlaps the remembered region. Capture hides it temporarily, then
    # restores the same pin; its old pixels must not contaminate the new image.
    state.pin(path);wait(lambda:len(state.pins)==1);pin=state.pins[0]
    from omnishot.widgets import place_window
    pin.setFixedSize(200,120);place_window(pin,second_x+150,180);QTest.qWait(150)
    recolor(1,'#54ac76');path,image=capture('previous')
    assert image.getpixel((100,60))==(84,172,118) and pin.isVisible() and state.pins==[pin]
    state.close_pins();QTest.qWait(100)
    boundary=0 if left else 1800;cross=(boundary-100,150,200,200)
    path,image=capture('area',cross);assert image.size==(320,320)
    colors=[(84,172,118),(70,138,192)] if left else [(70,138,192),(84,172,118)]
    assert image.getpixel((60,100))==colors[0] and image.getpixel((260,100))==colors[1]
    assert state.store.metadata(path)['pixel_ratio']==1.6
    path,image=capture('previous');assert image.size==(320,320) and image.getpixel((60,100))==colors[0] and image.getpixel((260,100))==colors[1]
    cross_previous=backend.Store(state.store.root).settings['previous_area']
    focus(1);path,image=capture('fullscreen');assert image.size==(1920,1080) and image.getpixel((500,400))==(84,172,118)
    assert state.store.metadata(path)['pixel_ratio']==1 and state.store.settings['previous_area']==cross_previous
    focus(0);path,image=capture('fullscreen');assert image.size==(2880,1800) and image.getpixel((500,400))==(70,138,192)
    assert state.store.metadata(path)['pixel_ratio']==1.6
    path,image=capture('desktop');assert image.size==(5952,1800),image.size
    offset=-min(0,second_x)
    assert image.getpixel((round((offset+500)*1.6),400))==(70,138,192)
    assert image.getpixel((round((offset+second_x+500)*1.6),400))==(84,172,118)
    assert state.store.metadata(path)['pixel_ratio']==1.6 and state.store.settings['previous_area']==cross_previous
    image.save(out/'desktop.png')
    state.store.settings['scale_screenshots']=True
    path,image=capture('desktop');assert image.size==(3720,1125) and state.store.metadata(path)['pixel_ratio']==1
    assert image.getpixel((offset+500,300))==(70,138,192) and image.getpixel((offset+second_x+500,300))==(84,172,118)
    path,image=capture('previous');assert image.size==(200,200) and state.store.metadata(path)['pixel_ratio']==1
    assert image.getpixel((40,60))==colors[0] and image.getpixel((160,60))==colors[1]
    assert not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
    report=dict(secondary_position=second_x,mixed_scales=[1.6,1],previous_without_capture_error=True,area_on_1x_display=True,previous_uses_current_pixels_and_remembered_region=True,previous_region_persisted=True,pin_hidden_during_capture_and_restored=True,cross_display_area_and_repeat=True,focused_display_capture=True,desktop_dimensions=[5952,1800],desktop_scaled_to_1x=[3720,1125],repeat_scaled_to_1x=[200,200],display_capture_preserves_previous_area=True,scale_metadata_verified=True,mirror_released=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
