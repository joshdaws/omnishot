"""Native OCR capture, QR links, explicit opening, preferences and text editing."""
import json,os,subprocess,sys,time
from pathlib import Path
import cv2
from PySide6.QtCore import Qt,QObject,Slot,QPoint,QTimer
from PySide6.QtGui import QImage,QPainter,QFont,QColor,QPixmap,QDesktopServices
from PySide6.QtWidgets import QApplication,QLabel,QDialogButtonBox,QCheckBox
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.text_result import DIALOGS
from omnishot.widgets import Settings,JOBS,place_window
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=15):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();QTest.qWait(1);time.sleep(.02)
    assert predicate()
def point(x,y):backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(80)
def click(widget,window):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle());p=widget.mapTo(window,QPoint(10,widget.height()//2) if isinstance(widget,QCheckBox) else widget.rect().center());point(client['at'][0]+p.x(),client['at'][1]+p.y());command('click 272');QTest.qWait(150)
def clipboard():return subprocess.check_output(['wl-paste','--no-newline','--type','text/plain;charset=utf-8']).decode()
class Opener(QObject):
    def __init__(self):super().__init__();self.urls=[]
    @Slot('QUrl')
    def opened(self,url):self.urls.append(url.toString())
opener=Opener();QDesktopServices.setUrlHandler('https',opener,'opened')
image=QImage(700,380,QImage.Format.Format_RGB888);image.fill(QColor('white'));painter=QPainter(image);painter.setFont(QFont('DejaVu Sans',22));painter.setPen(QColor('black'));painter.drawText(24,55,'https://example.com/capture');painter.drawText(24,135,'Generated QR link')
qr=cv2.QRCodeEncoder_create().encode('https://example.org/qr');qr=cv2.copyMakeBorder(qr,4,4,4,4,cv2.BORDER_CONSTANT,value=255);qr=cv2.resize(qr,(250,250),interpolation=cv2.INTER_NEAREST)
qrimage=QImage(qr.data,250,250,250,QImage.Format.Format_Grayscale8).copy();painter.drawImage(430,110,qrimage);painter.end();source=out/'generated-text-qr.png';image.save(str(source))
window=QLabel();window.setWindowTitle('OmniShot Generated OCR Fixture');window.setPixmap(QPixmap.fromImage(image));window.resize(700,380);window.show();place_window(window,200,200);QTest.qWait(250)
state=Controller(app);state.store.settings['ocr_languages']='eng';errors=[]
import omnishot.app as application
application.error=lambda parent,message:errors.append(str(message))
try:
    client=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());x,y=client['at'];state.capture('ocr',{});QTest.qWait(500)
    point(x+1,y+1);command('button 272 1');QTest.qWait(80);command('move 697 377');QTest.qWait(180);command('button 272 0')
    wait(lambda:bool(DIALOGS) and not JOBS and not state.busy);assert not errors,errors
    dialog=next(iter(DIALOGS));QTest.qWait(180);text=clipboard();assert 'https://example.com/capture' in text and 'https://example.org/qr' in text,text
    assert dialog.links.count()==2 and not opener.urls
    dialog.grab().save(str(out/'recognized-links.png'));click(dialog.open_button,dialog);wait(lambda:bool(opener.urls));assert opener.urls==['https://example.com/capture']
    # Recognition dialogs participate in capture hiding/restoration.
    state.hide_capture_windows();assert not dialog.isVisible();state.restore_capture_windows();assert dialog.isVisible();QTest.qWait(250)
    click(dialog.close_button,dialog);wait(lambda:not DIALOGS)
    settings=Settings(state.store,'text');settings.show();QTest.qWait(200);click(settings.fields['ocr_detect_links'],settings)
    assert not settings.fields['ocr_detect_links'].isChecked();click(settings.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),settings)
    assert not backend.Store(state.store.root).settings['ocr_detect_links']
    state.dispatch({'command':'ocr','path':str(source)})
    wait(lambda:not JOBS);assert not DIALOGS and 'https://example.org/qr' in clipboard()
    state.store.settings['ocr_detect_links']=True
    editor=Editor(source,state.store);editor.show();QTest.qWait(200);editor.extract_text();wait(lambda:bool(DIALOGS) and not JOBS)
    dialog=next(iter(DIALOGS));QTest.qWait(150);click(dialog.text,dialog);command('key 30 4');backend.copy_text('Edited recognition text');command('key 47 4');QTest.qWait(150)
    assert dialog.text.toPlainText()=='Edited recognition text' and dialog.links.count()==0
    click(dialog.copy_button,dialog);assert clipboard()=='Edited recognition text';click(dialog.close_button,dialog);wait(lambda:not DIALOGS);editor.close()
    state.pin(source);pin=state.pins[-1];QTest.qWait(200)
    client=next(c for c in backend.hypr('clients') if c['title']==pin.windowTitle());point(client['at'][0]+100,client['at'][1]+100)
    def choose_pin_text():
        menu=app.activePopupWidget();assert menu is not None
        for _ in range(12):
            if menu.activeAction() and menu.activeAction().text()=='Text / QR':command('key 28 0');return
            command('key 108 0');QTest.qWait(70)
        command('key 1 0');raise AssertionError('Could not reach pinned Text / QR action')
    QTimer.singleShot(400,choose_pin_text);command('click 273');QTest.qWait(600)
    wait(lambda:bool(DIALOGS) and not JOBS);dialog=next(iter(DIALOGS));QTest.qWait(150)
    assert dialog.links.count()==2 and 'https://example.org/qr' in clipboard()
    click(dialog.close_button,dialog);wait(lambda:not DIALOGS);pin.close()
    report=dict(native_region_ocr=True,actual_ocr_and_qr=True,both_links_copied=True,explicit_open_dispatch=True,no_automatic_open=True,detect_links_preference_persists=True,file_api_reads_qr=True,disabled_detection_copies_without_dialog=True,native_editor_review_edit_copy=True,result_hidden_during_capture=True,native_pin_context_menu_ocr=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection();state.cleanup();QDesktopServices.unsetUrlHandler('https')
    for widget in app.topLevelWidgets():widget.close()
    command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
