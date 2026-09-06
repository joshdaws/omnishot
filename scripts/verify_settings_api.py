"""Native settings URL navigation, theme, shortcut dialog and save/cancel."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import QPoint,QTimer
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QLabel,QPushButton,QScrollArea
from PySide6.QtTest import QTest
from omnishot import backend,theme,__version__
from omnishot.app import Controller
import omnishot.app as application
from omnishot.api import parse_url
from omnishot.widgets import Settings
from omnishot.shortcuts import ShortcutsDialog

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);manager=theme.ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
state=Controller(app);errors=[];application.error=lambda parent,message:errors.append(str(message))
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate):
    end=time.monotonic()+5
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),errors
def client(widget):return next((c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle()),None)
def click(widget,point=None):
    window=widget.window()
    for scroll in window.findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(widget):scroll.ensureWidgetVisible(widget);QTest.qWait(60)
    native=client(window);local=widget.mapTo(window,point or widget.rect().center())
    backend.move_cursor(native['at'][0]+local.x()-2,native['at'][1]+local.y());command('move 2 0');QTest.qWait(70);command('click 272');QTest.qWait(100)
def open_page(tab):
    state.dispatch(parse_url('omnishot://open-settings'+('' if tab is None else '?tab='+tab)))
    dialog=next(w for w in state.windows if isinstance(w,Settings) and w.isVisible());wait(lambda:client(dialog));QTest.qWait(160)
    assert dialog.page_names[dialog.pages.currentIndex()]==(tab or 'general')
    native=client(dialog);bounds=dialog.screen().availableGeometry()
    assert bounds.contains(QPoint(*native['at'])) and bounds.contains(QPoint(native['at'][0]+dialog.width()-1,native['at'][1]+dialog.height()-1))
    return dialog
def cancel(dialog):
    click(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel));wait(lambda:not state.windows)
try:
    before=json.loads(json.dumps(state.store.settings));checked=[]
    for tab in (None,'general','wallpaper','shortcuts','quickaccess','recording','screenshots','annotate','advanced','about','text'):
        dialog=open_page(tab);checked.append(tab or 'default')
        if tab=='about':
            assert any(label.text()==f'Version {__version__}' for label in dialog.findChildren(QLabel))
            assert dialog.palette().window().color()==theme.color('background') and 'theme' not in dialog.fields
            dialog.grab().save(str(out/'about.png'))
        if tab=='shortcuts':
            seen=[]
            def close_shortcuts():
                child=app.activeModalWidget();assert isinstance(child,ShortcutsDialog)
                assert child.fields['scroll'].keySequence().toString();seen.append(True)
                click(child.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel))
            QTimer.singleShot(500,close_shortcuts)
            click(next(b for b in dialog.findChildren(QPushButton) if b.text()=='Customize shortcuts…'))
            assert seen and dialog.isVisible()
        cancel(dialog)
    assert state.store.settings==before
    dialog=open_page('screenshots');original=dialog.fields['include_cursor'].isChecked()
    click(dialog.fields['include_cursor'],QPoint(8,dialog.fields['include_cursor'].height()//2))
    click(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save));wait(lambda:not state.windows)
    assert backend.Store(state.store.root).settings['include_cursor']==(not original)
    dialog=open_page('screenshots');assert dialog.fields['include_cursor'].isChecked()==(not original)
    # Native sidebar navigation retains unsaved edits; Cancel does not persist them.
    click(dialog.fields['include_cursor'],QPoint(8,dialog.fields['include_cursor'].height()//2))
    row=dialog.page_names.index('about');click(dialog.sections.viewport(),dialog.sections.visualItemRect(dialog.sections.item(row)).center())
    assert dialog.page_names[dialog.pages.currentIndex()]=='about';cancel(dialog)
    assert backend.Store(state.store.root).settings['include_cursor']==(not original)
    assert not errors,errors
    state.dispatch(parse_url('omnishot://open-settings?tab=cloud'));assert len(errors)==1 and 'excluded' in errors[0] and not state.windows
    assert not state.store.history()
    report=dict(tabs=checked,native_sidebar=True,shortcut_customize_and_cancel=True,save_and_reopen=True,cancel_preserves_settings=True,about_version=__version__,active_omarchy_theme=True,cloud_exclusion_explicit=True,display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
