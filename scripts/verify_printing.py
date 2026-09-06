"""Real Wayland Ctrl+P and preview context menu → PDF, without physical printing."""
import json,os,subprocess,sys,time,hashlib
from pathlib import Path
from PySide6.QtCore import QTimer,QSize
from PySide6.QtGui import QImage,QPainter,QColor,QFont
from PySide6.QtWidgets import QApplication,QMenu,QWidget,QPushButton,QComboBox,QLineEdit,QSpinBox,QCheckBox,QRadioButton
from PySide6.QtPrintSupport import QPrintDialog,QPrinter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.app import Controller
from omnishot.theme import ThemeManager
from omnishot.widgets import place_window
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=5):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),'Native printing timed out'
def client(widget):return next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle())
def pointer(widget):
    top=widget.window();c=client(top);local=widget.mapTo(top,widget.rect().center());backend.move_cursor(c['at'][0]+local.x()-2,c['at'][1]+local.y());command('move 2 0');QTest.qWait(65)
def click(widget):pointer(widget);command('click 272');QTest.qWait(100)
def text(widget,value):
    click(widget);QTest.qWait(180)
    for _ in range(12):
        if app.focusWidget() is widget or (app.focusWidget() and widget.isAncestorOf(app.focusWidget())):break
        command('key 15 0');QTest.qWait(80)
    assert app.focusWidget() is widget or widget.isAncestorOf(app.focusWidget()),widget.objectName()
    app.clipboard().setText(str(value));QTest.qWait(100);command('key 30 4');QTest.qWait(100);command('key 47 4');QTest.qWait(180);assert widget.text()==str(value),(widget.objectName(),widget.text())
def button(parent,label):return next(b for b in parent.findChildren(QPushButton) if label in b.text().replace('&',''))
state=Controller.__new__(Controller);state.app=app;state.store=backend.Store(out/'data');state.windows=[];state.overlays=[];state.pins=[];state.store.settings.update(background_preset='None',overlay_timeout=2)
image=QImage(800,2400,QImage.Format.Format_RGB32);p=QPainter(image);p.setFont(QFont('sans-serif',34))
for y,color in [(0,'#ffdddd'),(1200,'#ddddff')]:p.fillRect(0,y,800,1200,QColor(color))
for row in range(24):p.setPen(QColor('#243648'));p.drawText(40,70+row*100,f'Printed capture — row {row+1}')
p.end();path=state.store.add(image=image);digest=hashlib.sha256(path.read_bytes()).hexdigest();state.edit(path);e=state.windows[0];errors=[];dialog_settings=[]
def configure_dialog(name,selected=False,cancel=False):
    try:
        d=app.activeModalWidget();assert isinstance(d,QPrintDialog);QTest.qWait(180)
        combo=d.findChild(QComboBox,'printers');click(combo);command('key 107 0');command('key 28 0');QTest.qWait(140)
        assert 'PDF' in combo.currentText(),'PDF destination must be selected before Print'
        assert d.findChild(QLineEdit,'filename').text().endswith('.pdf')
        target=out/(name+'.pdf');text(d.findChild(QLineEdit,'filename'),target)
        click(button(d,'Options'));QTest.qWait(100)
        if selected:
            click(d.findChild(QRadioButton,'printRange'));text(d.findChild(QSpinBox,'from'),'2');text(d.findChild(QSpinBox,'to'),'2')
            text(d.findChild(QSpinBox,'copies'),'2');click(d.findChild(QCheckBox,'collate'));click(d.findChild(QCheckBox,'reverse'))
        QTest.qWait(180);geometry=client(d);bounds=d.screen().availableGeometry();assert bounds.contains(geometry['at'][0],geometry['at'][1]) and bounds.contains(geometry['at'][0]+d.width()-1,geometry['at'][1]+d.height()-1)
        d.grab().save(str(out/(name+'-dialog.png')))
        click(button(d,'Cancel' if cancel else 'Print'));QTest.qWait(180)
        if d.isVisible():
            command('key 1 0');QTest.qWait(100);raise AssertionError('Native Print button did not submit')
        if not cancel:
            assert d.printer().outputFormat()==QPrinter.OutputFormat.PdfFormat
            dialog_settings.append({'range':d.printer().printRange().name,'copies':d.printer().copyCount(),'reverse':d.printer().pageOrder().name,'output':target.name})
    except Exception as exc:
        errors.append(repr(exc));modal=app.activeModalWidget()
        if modal:modal.reject()
        print('DIALOG ERROR',errors,flush=True)
try:
    wait(lambda:any(c['pid']==os.getpid() and c['title']==e.windowTitle() for c in backend.hypr('clients')));place_window(e,30,40);QTest.qWait(150)
    pointer(e.view.viewport());QTimer.singleShot(300,lambda:configure_dialog('editor'));command('key 25 4');wait(lambda:(out/'editor.pdf').exists() or errors)
    assert not errors,errors
    doc=QPdfDocument();assert doc.load(str(out/'editor.pdf'))==QPdfDocument.Error.None_;assert doc.pageCount()>=2
    doc.render(0,QSize(595,842)).save(str(out/'editor-first-page.png'));doc.render(doc.pageCount()-1,QSize(595,842)).save(str(out/'editor-last-page.png'))
    page_count=doc.pageCount();e.close();wait(lambda:not state.windows);state.overlay(path);overlay=state.overlays[0];QTest.qWait(200)
    def menu_print():
        try:
            menu=app.activePopupWidget();assert isinstance(menu,QMenu);actions=[a for a in menu.actions() if not a.isSeparator() and a.isEnabled()];index=next(i for i,a in enumerate(actions) if a.text()=='Print…')
            for _ in range(index+1):command('key 108 0')
            QTimer.singleShot(280,lambda:configure_dialog('overlay',True));command('key 28 0')
        except Exception as exc:errors.append(repr(exc));app.activePopupWidget().close()
    pointer(overlay.preview);QTimer.singleShot(250,menu_print);command('click 273');wait(lambda:(out/'overlay.pdf').exists() or errors)
    assert not errors,errors
    doc2=QPdfDocument();assert doc2.load(str(out/'overlay.pdf'))==QPdfDocument.Error.None_;assert doc2.pageCount()==2
    assert doc2.render(0,QSize(595,842))==doc.render(1,QSize(595,842));assert doc2.render(1,QSize(595,842))==doc.render(1,QSize(595,842))
    assert overlay.isVisible();overlay.timer.stop()
    QTimer.singleShot(220,lambda:configure_dialog('cancelled',cancel=True));overlay.print_image();assert not (out/'cancelled.pdf').exists() and overlay.isVisible()
    assert not errors,errors;assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    report=dict(native_editor_ctrl_p_pdf=True,dialog_stays_on_display_after_options_expand=True,pdf_default_filename=True,native_preview_menu_print=True,page_range_and_two_copies=True,matching_editor_overlay_pixels=True,cancel_retains_capture=True,source_unchanged=True,full_capture_page_count=page_count,settings=dialog_settings,display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0')
    for window in list(state.windows)+list(state.overlays):window.close()
    fixture.stdin.close();fixture.wait(timeout=3)
