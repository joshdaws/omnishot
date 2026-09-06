"""Installed URL handler → private IPC → mixed-scale screen/file OCR → clipboard.

Only generated text and disposable headless outputs are captured. No production
methods are replaced except the error presenter, to report failures without a
blocking error dialog. The installed user's socket and preferences stay untouched.
"""
import hashlib,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.parse import urlencode
from PIL import Image,ImageDraw,ImageFont
from PySide6.QtGui import QColor,QFont,QPainter
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtNetwork import QLocalServer
from PySide6.QtTest import QTest
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.widgets import JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
backend.run(['hyprctl','output','create','headless','HEADLESS-2'])
config=Path(os.environ['XDG_RUNTIME_DIR'])/'hyprland.lua'
assert config.parent.name.startswith('os-') and config.parent.parent==Path('/tmp')
with config.open('a') as stream:
    stream.write('\nhl.monitor({output="HEADLESS-2",mode="1920x1080@60",position="-1920x0",scale=1})\n')
backend.run(['hyprctl','reload'])
socket_dir=Path(tempfile.mkdtemp(prefix='ot-',dir='/tmp'))
os.environ.update(TMPDIR=str(socket_dir),OMNISHOT_DATA_DIR=str(out/'data'),XDG_CONFIG_HOME=str(out/'config'))
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot')
state=Controller(app);state.store.settings.update(ocr_languages='eng',ocr_detect_links=False,ocr_linebreaks=True)
errors=[];application.error=lambda parent,message:errors.append(str(message))
server=QLocalServer();server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
assert server.listen(f'omnishot-{os.getuid()}'),server.errorString()
assert Path(server.fullServerName()).parent==socket_dir
sockets=[];received=[];stage='initialization'
def connection():
    socket=server.nextPendingConnection();sockets.append(socket);socket.setProperty('buffer',b'')
    def read():
        data=socket.property('buffer')+bytes(socket.readAll());socket.setProperty('buffer',data)
        if b'\n' in data:
            args=json.loads(data.split(b'\n',1)[0]);received.append(args);socket.disconnectFromServer();state.dispatch(args)
    socket.readyRead.connect(read)
server.newConnection.connect(connection)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate(),dict(stage=stage,errors=errors,received=received)
def launch(**args):
    global stage
    stage='omnishot://capture-text?'+urlencode(args);before=len(received)
    (out/'progress.json').write_text(json.dumps(dict(stage=stage,received=received),indent=2))
    with (out/'launch.log').open('ab') as log:
        subprocess.run(['gio','launch',str(Path.home()/'.local/share/applications/org.omarchy.OmniShot.desktop'),stage],stdout=log,stderr=log,check=True,timeout=3)
    wait(lambda:len(received)==before+1)
def clipboard():return backend.run(['wl-paste','--type','text/plain','--no-newline']).decode()
def recognize(expected,linebreaks=None,**args):
    backend.copy_text('Awaiting generated OCR result')
    if linebreaks is not None:args['linebreaks']=str(linebreaks).lower()
    launch(**args);wait(lambda:not state.busy and not JOBS and clipboard()!='Awaiting generated OCR result')
    text=clipboard();assert not errors,errors
    assert ' '.join(text.split())==' '.join(expected),repr(text)
    keep=state.store.settings['ocr_linebreaks'] if linebreaks is None else linebreaks
    assert ('\n' in text)==keep,repr(text)
    return text
class Pattern(QWidget):
    def __init__(self,words):super().__init__();self.words=words
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('white'))
        font=QFont('DejaVu Sans');font.setPixelSize(32);painter.setFont(font);painter.setPen(QColor('black'))
        painter.drawText(130,80,'Outside capture region')
        painter.drawText(130,self.height()-200,self.words[0]);painter.drawText(130,self.height()-145,self.words[1])
sources=[];results=[]
try:
    wait(lambda:len(app.screens())==2)
    words={'HEADLESS-1':['Silver meadow','Amber sunrise'],'HEADLESS-2':['Velvet forest','Copper valley']}
    for name,text in words.items():
        window=Pattern(text);window.setWindowTitle('Generated OCR '+name);window.winId()
        window.windowHandle().setScreen(next(s for s in app.screens() if s.name()==name));window.showFullScreen();sources.append(window);QTest.qWait(180)
    monitors=backend.capture_monitors();assert {m['name']:m['scale'] for m in monitors}=={'HEADLESS-1':1.6,'HEADLESS-2':1}
    coords=dict(x=100,y=100,width=600,height=180)
    # Explicit display must override the cursor, and a missing display follows it.
    for name,explicit,linebreaks in [('HEADLESS-1',True,True),('HEADLESS-2',True,False),('HEADLESS-2',False,True)]:
        target=next(m for m in monitors if m['name']==name)
        pointer=next(m for m in monitors if m['name']!=name) if explicit else target
        backend.move_cursor(pointer['x']+48,300);command('move 2 0');QTest.qWait(100)
        args=dict(coords)
        if explicit:args['display']=monitors.index(target)+1
        before=len(state.store.history());text=recognize(words[name],linebreaks,**args)
        assert len(state.store.history())==before+1
        from omnishot.clean_capture import monitor_bounds
        _,_,_,height=monitor_bounds(target)
        expected=[target['x']+100,target['y']+height-280,600,180]
        assert state.store.settings['previous_area']==expected,state.store.settings['previous_area']
        image=Image.open(state.store.history()[0]['path']);size=(round(600*target['scale']),round(180*target['scale']))
        assert image.size==size,(image.size,size)
        image.save(out/(name+('-explicit' if explicit else '-cursor')+'.png'))
        results.append(dict(display=name,explicit=explicit,geometry=expected,pixels=image.size,text=text,linebreaks=linebreaks))
    source=out/'text #é + original.png';image=Image.new('RGB',(700,210),'white');draw=ImageDraw.Draw(image)
    font_path=backend.run(['fc-match','-f','%{file}','DejaVu Sans']).decode()
    font=ImageFont.truetype(font_path,38)
    file_words=['Golden orchard','Quiet river']
    for y,text in zip((25,100),file_words):draw.text((25,y),text,font=font,fill='black')
    image.save(source);digest=hashlib.sha256(source.read_bytes()).hexdigest();before=state.store.history()
    for preference,override in [(True,False),(False,True),(False,None)]:
        state.store.settings['ocr_linebreaks']=preference
        text=recognize(file_words,override,filepath=str(source))
        results.append(dict(file=source.name,preference=preference,override=override,text=text))
    assert state.store.history()==before and hashlib.sha256(source.read_bytes()).hexdigest()==digest
    backend.copy_text('Keep clipboard on invalid coordinates');launch(**{**coords,'display':3})
    wait(lambda:bool(errors));assert 'display' in errors.pop().lower()
    assert clipboard()=='Keep clipboard on invalid coordinates' and state.store.history()==before
    report=dict(installed_desktop_entry_cli_ipc=True,lower_left_coordinates=True,mixed_scales=[1.6,1],negative_display_origin=True,explicit_display_overrides_cursor=True,unspecified_display_follows_cursor=True,screen_and_file_ocr=True,linebreak_override_and_preference=True,encoded_file_path=True,file_unchanged_and_not_imported=True,invalid_display_preserves_clipboard_history=True,results=results)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    (out/'progress.json').write_text(json.dumps(dict(stage=stage,errors=errors,received=received),indent=2))
    server.close();state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3);backend.run(['wl-copy','--clear']);shutil.rmtree(socket_dir)
