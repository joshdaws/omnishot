"""Native scrolling guide, controls, live preview and annotation handoff."""
import json,os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QPointF,QTimer
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QScrollArea,QLabel,QMenu,QFileDialog
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.widgets import ScrollPanel,QuickOverlay,place_window
from omnishot.editor import Editor

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);horizontal="--horizontal" in sys.argv
live_selection='--live-selection' in sys.argv
restore_original='--restore-original' in sys.argv
pencil='--pencil' in sys.argv
complete_page='--complete-page' in sys.argv or restore_original
os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready"
def command(value):fixture.stdin.write(value+"\n");fixture.stdin.flush()
def wait(predicate,seconds=12):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:
        app.processEvents();time.sleep(.02)
    if not predicate():
        Image.fromarray(backend.grab()).save(out/"capture-failure-screen.png")
        if panel is None:raise AssertionError(('Scrolling panel did not open',len(state.selectors),backend.hypr('activewindow').get('title')))
        raise AssertionError((panel.status.text(),panel.stitcher.accepted,panel.busy,panel.auto,area.verticalScrollBar().value(),area.horizontalScrollBar().value(),backend.hypr("cursorpos")))
def click(widget,window):
    client=next(c for c in backend.hypr("clients") if c["title"]==window.windowTitle())
    point=widget.mapTo(window,widget.rect().center());backend.move_cursor(client["at"][0]+point.x()-2,client["at"][1]+point.y())
    command("move 2 0");QTest.qWait(70);command("click 272");QTest.qWait(150)
store=backend.Store(out/"data");store.settings.update(scroll_interval=250 if complete_page else 400,scroll_step=5 if complete_page else 3,overlay_timeout=0)
window=QWidget();window.setWindowTitle("OmniShot Scroll Interface Test");window.resize(790,660)
layout=QVBoxLayout(window);layout.addWidget(QLabel("Generated scrolling content"));area=QScrollArea();layout.addWidget(area)
image=QImage(3600 if horizontal else 710,550 if horizontal else 3600,QImage.Format.Format_RGB888);image.fill(QColor("white"));painter=QPainter(image);painter.setFont(QFont("sans-serif",18))
if horizontal:
    for x in range(0,3600,130):
        for y in range(0,550,80):
            painter.fillRect(x+5,y+5,120,70,QColor.fromHsv((x+y)%360,70,240));painter.setPen(QColor("#243756"));painter.drawText(x+12,y+46,f"{x//130+1:02d} / {y//80+1}")
else:
    for y in range(0,3600,80):
        painter.fillRect(10,y+5,690,70,QColor("#e6eef8" if y%160 else "white"));painter.setPen(QColor("#243756"));painter.drawText(25,y+46,f"Row {y//80+1:02d} · unique marker {y*73+42}")
painter.end();label=QLabel();label.setPixmap(QPixmap.fromImage(image));area.setWidget(label);window.show();QTest.qWait(150);place_window(window,450,160);QTest.qWait(250)
client=next(c for c in backend.hypr("clients") if c["title"]==window.windowTitle());offset=area.viewport().mapTo(window,QPoint(0,0))
# Stay inside the viewport: its antialiased top border is stationary chrome,
# not scrolling content, at fractional display scales.
rect=(client["at"][0]+offset.x()+2,client["at"][1]+offset.y()+2,area.viewport().width()-4 if horizontal and complete_page else 700,area.viewport().height()-4 if restore_original else min(540,area.viewport().height()-4))
backend.move_cursor(100,100);command("move 1 0");QTest.qWait(100)
baseline=backend.grab(rect);state=None;panel=None
if live_selection:
    from omnishot.app import Controller
    state=Controller(app);state.store=store;store.settings.update(freeze=False,previous_area=list(rect),capture_actions=['overlay'])
    state.capture('select',{'action':'overlay'});wait(lambda:bool(state.selectors));QTest.qWait(250)
    selector=state.selectors[0];assert selector.live
    if horizontal:
        menu_timer=QTimer();menu_timer.setInterval(90)
        def choose_horizontal():
            menu=app.activePopupWidget()
            if not isinstance(menu,QMenu):return
            if menu.activeAction() and menu.activeAction().text()=='Horizontal scrolling':command('key 28 0');menu_timer.stop()
            else:command('key 108 0')
        menu_timer.timeout.connect(choose_horizontal);menu_timer.start()
        client=next(c for c in backend.hypr('clients') if c['title']==selector.windowTitle());button=selector.controls.buttons['Scrolling'];p=button.mapTo(selector,button.rect().center())
        backend.move_cursor(client['at'][0]+p.x()-2,client['at'][1]+p.y());command('move 2 0');QTest.qWait(80);command('click 273');QTest.qWait(150)
    else:click(selector.controls.buttons['Scrolling'],selector)
    wait(lambda:state.panel is not None);panel=state.panel
    assert not state.selectors and not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
else:panel=ScrollPanel(rect,store,horizontal)
received=[];panel.completed.connect(received.append)
try:
    panel.show();QTest.qWait(400)
    guided=backend.grab(rect)
    if not np.array_equal(guided,baseline):
        Image.fromarray(baseline).save(out/"baseline.png");Image.fromarray(guided).save(out/"guided.png");Image.fromarray(backend.grab()).save(out/"guide-failure-screen.png")
        (out/"guide-clients.json").write_text(json.dumps(backend.hypr("clients"),indent=2))
        yy,xx=np.where(np.any(guided!=baseline,axis=2))
        raise AssertionError((int(np.max(np.abs(guided.astype(int)-baseline))),[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())],rect))
    Image.fromarray(backend.grab()).save(out/"ready-screen.png")
    click(panel.start_btn,panel);wait(lambda:panel.stitcher.accepted>=1)
    wait(lambda:not panel.busy and time.monotonic()>=panel.visuals.ready_at);QTest.qWait(150)
    backend.move_cursor(rect[0]+rect[2]//2,rect[1]+rect[3]//2);command('move 1 0');QTest.qWait(120)
    cursorless=backend.grab(rect)
    if not np.array_equal(cursorless,baseline):
        Image.fromarray(cursorless).save(out/'cursorless.png');Image.fromarray(baseline).save(out/'baseline.png')
    assert np.array_equal(cursorless,baseline), 'The pointer must not change captured content'
    assert not np.array_equal(backend.grab(rect,cursor=True),baseline), 'Explicit cursor capture must still work'
    assert panel.outside;click(panel.auto_btn,panel)
    wait(lambda:getattr(panel,'reached_end',False) if complete_page else panel.stitcher.accepted>=7,20)
    panel.auto=False;wait(lambda:not panel.busy)
    QTest.qWait(250)
    assert panel.visuals.preview.isVisible() and panel.visuals.preview_outside
    preview_client=next(c for c in backend.hypr("clients") if c["title"]==panel.preview.windowTitle())
    (out/"preview-geometry.json").write_text(json.dumps(dict(compositor=preview_client["size"],widget=[panel.preview.width(),panel.preview.height()],pixmap=[panel.preview.pixmap.width(),panel.preview.pixmap.height()]),indent=2))
    assert preview_client["size"]==[panel.preview.width(),panel.preview.height()],preview_client
    position=(area.horizontalScrollBar() if horizontal else area.verticalScrollBar()).value();assert position>0
    Image.fromarray(backend.grab()).save(out/"capturing-screen.png")
    tail=backend.grab(rect)
    panel.preview.grab().save(str(out/"live-preview.png"));click(panel.done_btn,panel);wait(lambda:bool(received))
    assert not any(g.isVisible() for g in panel.visuals.guides) and not panel.preview.isVisible()
    assert not panel.mirror.enabled and not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
    result=received[0];axis=1 if horizontal else 0;assert result.shape[axis]>baseline.shape[axis]*1.7
    if complete_page and horizontal:
        assert area.horizontalScrollBar().value()==area.horizontalScrollBar().maximum()
        assert np.array_equal(result[:,:baseline.shape[1]],baseline)
        assert np.array_equal(result[:,-tail.shape[1]:],tail)
        scale=backend.capture_monitors()[0]['scale'];columns=[]
        assert abs(result.shape[1]-(image.width()-4)*scale)<=1,(result.shape,image.width(),scale)
        for x in range(0,3600,130):
            expected=QColor.fromHsv(x%360,70,240).getRgb()[:3]
            pixel=result[round(8*scale),round((x+13)*scale)]
            assert max(abs(int(a)-b) for a,b in zip(pixel,expected))<=1,(x,pixel,expected)
            columns.append(x//130+1)
        Image.fromarray(result).save(out/'complete-horizontal.png')
    if state:
        wait(lambda:bool(state.overlays));overlay=state.overlays[0];editors=state.windows
    else:
        path=store.add(image=result,kind="scroll");overlay=QuickOverlay(path,store);editors=[]
        def annotate(value):
            editor=Editor(value,store);editors.append(editor);editor.show();overlay.close()
        overlay.annotate.connect(annotate);overlay.show()
    QTest.qWait(250);click(overlay.preview,overlay);wait(lambda:bool(editors))
    editor=editors[0];QTest.qWait(200)
    if restore_original:
        import re,hashlib
        assert not horizontal
        assert area.verticalScrollBar().value()==area.verticalScrollBar().maximum()
        Image.fromarray(result).save(out/'complete-scroll.png');Image.fromarray(tail).save(out/'tail.png')
        if not np.array_equal(result[-tail.shape[0]:],tail):
            difference=np.any(result[-tail.shape[0]:]!=tail,axis=2);yy,xx=np.where(difference)
            print('TAIL DIFFERENCE',result.shape,tail.shape,[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())],float(difference.mean()),flush=True)
        assert np.array_equal(result[:baseline.shape[0]],baseline)
        assert np.array_equal(result[-tail.shape[0]:],tail)
        captured=out/'complete-scroll.png';Image.fromarray(result).save(captured)
        text=backend.run(['tesseract',captured,'stdout','--psm','6']).decode()
        rows=[int(n) for n in re.findall(r'Row\s*(\d{2})',text)]
        assert rows==list(range(1,46)),rows
        original=editor.base.copy();digest=hashlib.sha256(editor.path.read_bytes()).hexdigest()
        def pointer(local):
            client=next(c for c in backend.hypr('clients') if c['title']==editor.windowTitle())
            backend.move_cursor(client['at'][0]+local.x()-2,client['at'][1]+local.y());command('move 2 0');QTest.qWait(60)
        def draw(a,b):
            points=[editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(*v))) for v in (a,b)]
            pointer(points[0]);command('button 272 1');QTest.qWait(60);command(f'move {points[1].x()-points[0].x()} {points[1].y()-points[0].y()}');QTest.qWait(90);command('button 272 0');QTest.qWait(120)
        click(editor.toolbar.widgetForAction(editor.tools['pencil' if pencil else 'arrow']),editor)
        draw((500,450),(100,200)) if pencil else draw((100,200),(500,450))
        assert len(editor.objects)==1
        if pencil:assert editor.objects[0].props['kind']=='pencil' and editor.objects[0].props['w']>300 and editor.objects[0].props['h']>150
        click(editor.toolbar.widgetForAction(editor.tools['crop']),editor);session=editor.crop_session
        draw((original.width()/2,0),(original.width()/2,500));draw((original.width()/2,original.height()),(original.width()/2,original.height()-650));crop=session.rect.toRect();click(session.apply_button,editor)
        assert editor.base.height()<original.height()-900
        click(editor.toolbar.widgetForAction(editor.tools['rect']),editor);draw((150,150),(650,600));assert len(editor.objects)==2
        added_position=editor.objects[-1].pos()+QPointF(crop.topLeft());cropped=editor.render();project=out/'scroll-original.omnishot'
        def save_dialog():
            wait(lambda:any(isinstance(w,QFileDialog) and w.isVisible() for w in app.topLevelWidgets()))
            QTest.qWait(80);command('key 38 4');QTest.qWait(60);backend.copy_text(str(project));command('key 47 4');QTest.qWait(60);command('key 28 0')
        timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(save_dialog);timer.start(180);command('key 31 5');wait(project.exists)
        source_path=editor.path;editor.close();editor=Editor(project,store);editor.show();QTest.qWait(150);assert editor.render()==cropped
        click(editor.toolbar.widgetForAction(editor.tools['crop']),editor);session=editor.crop_session;click(session.reset_button,editor)
        assert editor.base==original and (editor.objects[-1].pos()-added_position).manhattanLength()<.01
        click(session.apply_button,editor);restored=editor.render();command('key 44 4');QTest.qWait(100);assert editor.render()==cropped;command('key 44 5');QTest.qWait(100);assert editor.render()==restored
        editor.grab().save(str(out/'scroll-restored-editor.png'));restored.save(str(out/'scroll-restored.png'))
        assert hashlib.sha256(source_path.read_bytes()).hexdigest()==digest
        editor.write_project(out/'scroll-restored.omnishot');editor.close()
    else:
        click(editor.toolbar.widgetForAction(editor.tools['arrow']),editor)
        start=editor.view.mapFromScene(QPointF(100,100));end=editor.view.mapFromScene(QPointF(380,240))
        client=next(c for c in backend.hypr('clients') if c['title']==editor.windowTitle());point=editor.view.viewport().mapTo(editor,start)
        backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(70);command('button 272 1');QTest.qWait(60);command(f'move {end.x()-start.x()} {end.y()-start.y()}');QTest.qWait(90);command('button 272 0');QTest.qWait(120)
        assert len(editor.objects)==1;expected=editor.render();editor.grab().save(str(out/'horizontal-editor.png'));project=out/'scroll-annotated.omnishot';editor.write_project(project);editor.close()
        reopened=Editor(project,store);assert reopened.render()==expected;reopened.close()
    report=dict(live_all_in_one_handoff=live_selection,axis="horizontal" if horizontal else "vertical",display_scale=backend.capture_monitors()[0]["scale"],software_cursor_excluded=True,explicit_cursor_capture_preserved=True,mirror_released=True,guide_pixels_excluded=True,native_buttons=True,native_scroll_through_guide=True,frames=panel.stitcher.accepted,scroll_position=position,live_preview=True,result_size=[result.shape[1],result.shape[0]],guide_cleanup=True,preview_to_annotation=True,editable_project=True)
    if restore_original:report.update(complete_page_rows=rows,top_and_bottom_pixels_exact=True,native_annotation_and_crop=True,native_project_save=True,reopened_crop_exact=True,native_original_restoration=True,native_undo_redo=True,source_unchanged=True)
    if pencil and restore_original:report.update(native_up_left_pencil_on_full_scroll=True)
    if complete_page and horizontal:report.update(complete_page_columns=columns,left_and_right_pixels_exact=True,native_annotation=True,editable_reopen_pixels=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    panel.auto=False;panel.close();wait(lambda:not panel.busy,4)
    if state:state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    command("button 272 0");fixture.stdin.close();fixture.wait(timeout=3)
