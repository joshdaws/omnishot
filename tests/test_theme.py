import json
from pathlib import Path
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtGui import QPalette,QImage,QColor
from PySide6.QtWidgets import QApplication,QLabel
from omnishot import theme,backend
from omnishot.editor import Editor,Annotation
from omnishot.widgets import Settings


def write_palette(path,background='#102030',foreground='#e0edf4',accent='#45c9d6'):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(f'background="{background}"\nforeground="{foreground}"\naccent="{accent}"\n')


def test_palette_directory_replacement_updates_open_windows_and_preserves_pixels(tmp_path):
    app=QApplication.instance() or QApplication([]);old_palette=app.palette();old_style=app.styleSheet();old_current=theme._current
    path=tmp_path/'current/theme/colors.toml';write_palette(path);manager=theme.ThemeManager(app,[path]);manager.timer.setInterval(20)
    store=backend.Store(tmp_path/'data');image=QImage(400,240,QImage.Format.Format_RGB32);image.fill(QColor('#efeff1'))
    editor=Editor(store.add(image=image),store);editor.show();settings=Settings(store);settings.show()
    obj=Annotation(dict(kind='arrow',x=20,y=20,w=180,h=80,color='#ff0000'),editor);editor.scene.addItem(obj);editor.objects.append(obj);editor.commit()
    before=editor.render();changes=[];manager.changed.connect(lambda:changes.append(True))
    try:
        assert 'theme' not in settings.fields
        assert any('Follows your Omarchy theme'==label.text() for label in settings.findChildren(QLabel))
        assert app.palette().color(QPalette.ColorRole.Window).name()=='#102030'
        # Match Omarchy's directory swap, not just an in-place write.
        path.parent.rename(path.parent.with_name('old-theme'));write_palette(path,'#f4efe7','#202830','#864400')
        loop=QEventLoop();QTimer.singleShot(100,loop.quit);loop.exec()
        assert changes and app.palette().color(QPalette.ColorRole.Window).name()=='#f4efe7'
        assert theme.color('accent').name()=='#864400'
        assert editor.render()==before and obj.props['color']=='#ff0000'
        assert editor.isVisible() and settings.isVisible()
        last=dict(manager.applied);path.write_text('background=');assert not manager.reload() and manager.applied==last
        path.unlink();assert not manager.reload() and manager.applied==last
    finally:
        editor.close();settings.close();manager.timer.stop();manager.deleteLater();theme._current=old_current;app.setPalette(old_palette);app.setStyleSheet(old_style)


def test_legacy_theme_setting_is_discarded(tmp_path):
    (tmp_path/'settings.json').write_text(json.dumps(dict(theme='light',history_days=12)))
    store=backend.Store(tmp_path);assert 'theme' not in store.settings and store.settings['history_days']==12
    store.save_settings();assert 'theme' not in json.loads(store.settings_path.read_text())


def test_palette_validation_and_contrasting_accent_text(tmp_path):
    path=tmp_path/'colors.toml';write_palette(path)
    assert theme.read_palette([path])['on_accent']=='#000000'
    write_palette(path,accent='#003355');assert theme.read_palette([path])['on_accent']=='#ffffff'
    write_palette(path,accent='red; padding:90px');assert theme.read_palette([path]) is None
    path.write_text('background="#123456"');assert theme.read_palette([path]) is None
