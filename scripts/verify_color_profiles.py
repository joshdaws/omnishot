"""Native color preference, annotation, preview and clipboard on an SDR surface."""
import json,subprocess,sys
from pathlib import Path
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QColor,QColorSpace
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.images import save_image,load_image,convert_image
from omnishot.editor import Editor
from omnishot.widgets import Settings
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def move(widget,point):
    top=widget.window();client=next(c for c in backend.hypr('clients') if c['pid']==__import__('os').getpid() and c['title']==top.windowTitle())
    local=widget.mapTo(top,point);x,y=client['at'][0]+local.x(),client['at'][1]+local.y()
    backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(100)
def click(widget):move(widget,widget.rect().center());command('click 272');QTest.qWait(100)
store=backend.Store(out/'data');store.settings['clipboard_mode']='image'
original=QImage(800,500,QImage.Format.Format_RGBA8888);original.fill(QColor(160,100,40));original.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3));source=out/'source-p3.png';save_image(original,source);owned=store.import_file(source);editor=Editor(owned,store)
try:
    editor.show();QTest.qWait(350)
    sample=editor.view.mapFromScene(QPointF(600,350));preview=editor.view.viewport().grab().toImage();scale=preview.devicePixelRatio();actual=preview.pixelColor(round(sample.x()*scale),round(sample.y()*scale));expected=convert_image(original).pixelColor(600,350)
    assert actual==expected,(actual.getRgb(),expected.getRgb())
    editor.set_tool('fill');QTest.qWait(80);a=editor.view.mapFromScene(QPointF(100,100));b=editor.view.mapFromScene(QPointF(220,200));move(editor.view.viewport(),a);command('button 272 1');QTest.qWait(50);command(f'move {b.x()-a.x()} {b.y()-a.y()}');QTest.qWait(80);command('button 272 0');QTest.qWait(150)
    assert len(editor.objects)==1 and editor.objects[0].props['kind']=='fill'
    srgb=editor.render();assert srgb.colorSpace()==QColorSpace(QColorSpace.NamedColorSpace.SRgb);assert srgb.pixelColor(600,350)==expected
    settings=Settings(store,'screenshots');settings.show();QTest.qWait(250);box=settings.fields['convert_srgb'];move(box,__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint(8,box.height()//2));command('click 272');QTest.qWait(80);assert not box.isChecked();click(settings.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save));assert not backend.Store(store.root).settings['convert_srgb']
    preserved=editor.render();assert preserved.colorSpace()==original.colorSpace() and preserved.pixelColor(600,350)==original.pixelColor(600,350)
    assert convert_image(preserved)==srgb
    for enabled in (False,True):
        store.settings['convert_srgb']=enabled;backend.copy_image(source,store);QTest.qWait(100);pasted=QImage.fromData(backend.run(['wl-paste','--type','image/png']))
        assert pasted.colorSpace()==(QColorSpace(QColorSpace.NamedColorSpace.SRgb) if enabled else original.colorSpace())
        assert pasted.pixelColor(600,350)==(expected if enabled else original.pixelColor(600,350))
    save_image(editor.render(),out/'annotated-srgb.png');editor.grab().save(str(out/'annotate.png'))
    report=dict(native_annotation=True,native_color_preference=True,sdr_preview_converted=True,source_profile_preserved=True,srgb_export_pixels=True,native_clipboard_profiles_and_pixels=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('button 272 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3);backend.run(['wl-copy','--clear'])
