"""Native preset selection, inline typing, wrapped resize and project reopening."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend,text_styles
from omnishot.editor import Editor,Annotation

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate(),'Native text preset workflow timed out'
def pointer(point):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(70)
def click(widget,point=None):
    pointer(widget.mapTo(editor,point or widget.rect().center()));command('click 272');QTest.qWait(100)
def scene_click(x,y):click(editor.view.viewport(),editor.view.mapFromScene(QPointF(x,y)))
def choose(style):
    click(editor.text_style);command('key 102 0')
    for _ in range(text_styles.STYLES.index(style)):command('key 108 0')
    command('key 28 0');QTest.qWait(100);assert editor.text_style.style()==style

def add_text(style,label,x,y):
    scene_click(820,850);command('key 20 0');QTest.qWait(80);assert editor.view.tool=='text'
    choose(style);scene_click(x,y);wait(lambda:editor.inline is not None)
    backend.copy_text(label);command('key 47 4');QTest.qWait(90);command('key 28 4');wait(lambda:editor.inline is None)
    assert editor.objects[-1].props['text']==label and editor.objects[-1].props['text_style']==style

def drag_scene(a,b):
    pointer(editor.view.viewport().mapTo(editor,editor.view.mapFromScene(a)));command('button 272 1');QTest.qWait(80)
    pointer(editor.view.viewport().mapTo(editor,editor.view.mapFromScene(b)));command('button 272 0');QTest.qWait(120)

store=backend.Store(out/'data');store.settings.update(background_preset='None');base=QImage(900,900,QImage.Format.Format_RGB32);base.fill(QColor('#eef0f5'));path=store.add(image=base)
editor=Editor(path,store);editor.resize(1120,1000);editor.set_color('#1d2233');editor.font_size.setValue(24);editor.show();editor.fit();wait(lambda:any(c['pid']==os.getpid() for c in backend.hypr('clients')))
try:
    for index,style in enumerate(text_styles.STYLES):add_text(style,style,30,30+index*110)
    assert [o.props['text_style'] for o in editor.objects]==list(text_styles.STYLES)
    add_text('Standard','LongUnbrokenIdentifierWithoutSpaces',500,420);text=editor.objects[-1]
    old_h=text.props['h'];right=text.x()+text.props['w'];middle=text.y()+text.props['h']/2
    drag_scene(QPointF(right-2,middle),QPointF(right-210,middle));assert 87<text.props['w']<96 and text.props['h']>old_h*2
    doc=text_styles.document(text.props);doc.size();layout=doc.begin().layout();assert layout.lineCount()>5
    for index in range(layout.lineCount()):assert layout.lineAt(index).naturalTextWidth()<=text.props['w']-12+.1
    # Clicking inside the bottom-right handle must resize, not miss its hit area.
    editor.scene.clearSelection();rect=Annotation(dict(kind='rect',x=500,y=190,w=150,h=100,color='#d84960'),editor);editor.scene.addItem(rect);editor.objects.append(rect);rect.setSelected(True);editor.commit();QTest.qWait(80)
    drag_scene(QPointF(647,287),QPointF(697,327));assert 194<rect.props['w']<202 and 134<rect.props['h']<142
    rendered=editor.render();project=out/'text-presets.omnishot';editor.write_project(project);reopened=Editor(project,store);assert reopened.render()==rendered;reopened.close()
    editor.scene.clearSelection();editor.grab().save(str(out/'text-presets.png'));rendered.save(str(out/'text-presets-export.png'))
    report=dict(display_scale=backend.capture_monitors()[0]['scale'],theme='Omarchy',seven_native_preset_selections=True,seven_native_inline_text_entries=True,native_narrow_text_resize=True,long_word_wrap_without_missing_characters=True,native_inner_handle_resize=True,exact_project_render_reopen=True,default_window_width=1120)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:editor.close();fixture.stdin.close();fixture.wait(timeout=3)
