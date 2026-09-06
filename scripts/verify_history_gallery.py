"""Native History tabs, media previews, multi-restore and clear/cancel flow."""
import json,os,sys,subprocess,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QPainter,QColor,QFont
from PySide6.QtWidgets import QApplication,QMessageBox,QMenu
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.history import History,thumbnail_key

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=10):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate(),[(w.windowTitle(),w.isVisible()) for w in app.topLevelWidgets()]
def click(widget,window,local=None):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle());point=widget.mapTo(window,local or widget.rect().center())
    backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(70);command('click 272');QTest.qWait(100)
def select(index,control=False):
    QTest.qWait(app.doubleClickInterval()+40)
    if control:command('mods 4')
    click(history.list.viewport(),history,history.list.visualItemRect(history.list.item(index)).center())
    if control:command('mods 0')
def clear_history(accept):
    chosen=[False];dialog=[False];timer=QTimer();timer.setInterval(75)
    def navigate():
        menu=app.activePopupWidget();modal=app.activeModalWidget()
        if isinstance(modal,QMessageBox) and any(c['title']==modal.windowTitle() and c['pid']==os.getpid() for c in backend.hypr('clients')):
            assert 'all 5 captures' in modal.text(),modal.text();dialog[0]=True;timer.stop()
            click(modal.button(QMessageBox.StandardButton.Yes if accept else QMessageBox.StandardButton.Cancel),modal)
        elif isinstance(menu,QMenu):
            if menu.activeAction() and menu.activeAction().text()=='Clear History…':chosen[0]=True;command('key 28 0')
            else:command('key 108 0')
    timer.timeout.connect(navigate);timer.start();click(history.more,history);wait(lambda:dialog[0]);assert chosen[0]
state=Controller(app);state.store.settings.update(overlay_timeout=0,theme='Omarchy');state.apply_theme()
def add_card(name,color,kind='image'):
    image=QImage(640,420,QImage.Format.Format_RGB32);image.fill(QColor(color));p=QPainter(image);p.setPen(QColor('white'));p.setFont(QFont('sans-serif',28));p.drawText(image.rect(),Qt.AlignmentFlag.AlignCenter,name);p.end()
    source=out/(name+'.png');image.save(str(source));path=state.store.add(source=source,kind=kind);state.store.rename(path,name);return path
paths=[add_card('Project notes','#41738d'),add_card('Long capture','#66518e','scroll')]
gif=out/'Animation.gif';Image.new('RGB',(640,420),'#32b47f').save(gif,save_all=True,append_images=[Image.new('RGB',(640,420),'#4279bb')],duration=200,loop=0);paths.append(state.store.import_file(gif))
video=out/'Recording.mp4';backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0xdb5347:s=640x420:r=10','-t','0.5','-c:v','libx264','-threads','1','-y',video]);paths.append(state.store.import_file(video))
try:
    state.history();history=next(w for w in state.windows if isinstance(w,History));QTest.qWait(150)
    wait(lambda:len(history.images)==4 and not history.pending)
    assert all(not image.isNull() for image in history.images.values())
    record=next(r for r in history.rows if r['kind']=='video');pixel=history.images[thumbnail_key(record)].pixelColor(20,20);assert pixel.red()>180 and pixel.green()<110
    history.grab().save(str(out/'history-gallery.png'))
    select(0);command('key 107 0');QTest.qWait(150);assert history.list.currentRow()==3 and history.list.horizontalScrollBar().value()>0
    click(history.filters['video'],history);assert len(history.rows)==1 and history.rows[0]['kind']=='video'
    click(history.filters['gif'],history);assert len(history.rows)==1 and history.rows[0]['kind']=='gif'
    click(history.filters['image'],history);assert len(history.rows)==2
    select(0);select(1,True);assert len(history.selected())==2
    click(history.restore_button,history);wait(lambda:len(state.overlays)==2)
    assert {str(o.path) for o in state.overlays}==set(map(str,paths[:2]))
    for overlay in list(state.overlays):overlay.close()
    added=add_card('New capture','#92734e');paths.append(added);wait(lambda:len(history.rows)==3)
    assert set(history.selected())==set(map(str,paths[:2]))
    click(history.filters['gif'],history);assert len(history.rows)==1
    clear_history(False);assert all(p.exists() for p in paths)
    # Keep an editor open while clearing from a different filtered tab.
    state.edit(paths[0]);wait(lambda:any(hasattr(w,'path') for w in state.windows));QTest.qWait(150)
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']=='OmniShot — Annotate');backend.move_window(client['address'],50,700);QTest.qWait(150)
    clear_history(True);wait(lambda:not state.store.history())
    assert history.list.count()==0 and not any(p.exists() for p in paths)
    assert not any(hasattr(w,'path') for w in state.windows)
    assert all((out/name).exists() for name in ['Project notes.png','Long capture.png','Animation.gif','Recording.mp4','New capture.png'])
    assert not list((state.store.root/'image-edits').glob('*'))
    report=dict(display_scale=backend.capture_monitors()[0]['scale'],horizontal_filmstrip=True,native_horizontal_keyboard_navigation=True,theme='Omarchy',screenshot_filter_includes_scrolls=True,video_and_gif_thumbnails=True,native_multi_select_and_restore=True,live_refresh_preserves_selection=True,clear_cancel_preserves_all=True,clear_ignores_filter=True,clear_closes_editor_and_removes_draft=True,external_sources_preserved=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    command('mods 0');fixture.stdin.close();fixture.wait(timeout=3)
