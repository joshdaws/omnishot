"""Native counter numbering, layering, double-click editing and project reopen."""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QPointF,QTimer
from PySide6.QtWidgets import QApplication,QInputDialog
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.editor import Editor
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=5):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();QTest.qWait(1);time.sleep(.02)
    assert predicate()
def point(local):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==editor.windowTitle())
    backend.move_cursor(client['at'][0]+local.x()-2,client['at'][1]+local.y());command('move 2 0');QTest.qWait(80)
def click(widget):point(widget.mapTo(editor,widget.rect().center()));command('click 272');QTest.qWait(150)
def canvas(x,y):return editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(x,y)))
store=backend.Store(out/'data');source=store.add(image=np.full((500,800,3),255,np.uint8));editor=Editor(source,store);editor.show();QTest.qWait(300)
try:
    click(editor.toolbar.widgetForAction(editor.tools['counter']));assert editor.view.tool=='counter'
    click(editor.counter_number);command('key 30 4');command('key 11 0');command('key 28 0');QTest.qWait(100)
    assert editor.counter_number.value()==0
    for x in (150,300):point(canvas(x,150));command('click 272');QTest.qWait(150)
    assert [o.props['text'] for o in editor.objects]==['0','1']
    click(editor.toolbar.widgetForAction(editor.tools['fill']))
    start=canvas(100,100);end=canvas(420,240);point(start);command('button 272 1');QTest.qWait(70);command(f'move {end.x()-start.x()} {end.y()-start.y()}');QTest.qWait(130)
    assert editor.view.draft.zValue()<editor.objects[0].zValue()
    command('button 272 0');QTest.qWait(150);assert len(editor.objects)==3
    click(editor.toolbar.widgetForAction(editor.tools['select']))
    def edit_number():
        assert any(isinstance(w,QInputDialog) and w.isVisible() for w in app.topLevelWidgets())
        command('key 30 4');command('key 11 0');command('key 28 0')
    point(canvas(320,170));QTimer.singleShot(400,edit_number)
    command('click 272');QTest.qWait(70);command('click 272');QTest.qWait(700)
    assert editor.objects[1].props['text']=='0'
    assert min(o.zValue() for o in editor.objects[:2])>editor.objects[2].zValue()
    editor.scene.clearSelection();before=editor.render();before.save(str(out/'counters-export.png'))
    editor.grab().save(str(out/'counter-editor.png'));project=out/'counters.omnishot';editor.write_project(project)
    reopened=Editor(project,store);assert reopened.render()==before;assert [o.props['text'] for o in reopened.objects[:2]]==['0','0'];reopened.close()
    report=dict(native_zero_start=True,sequential_numbering=True,counter_above_live_draft=True,counter_above_later_fill=True,native_double_click_zero_edit=True,portable_project_render_identical=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    for widget in app.topLevelWidgets():widget.close()
    command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
