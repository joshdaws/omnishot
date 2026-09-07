"""Desktop text scaling must reflow UI without resampling captured content."""
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QWidget,QPushButton,QLabel
from omnishot import ui_scale as ui,theme,backend
from omnishot.widgets import Settings,QuickOverlay
from omnishot.editor import Editor,Annotation


def test_shell_theme_and_user_override_merge(tmp_path):
    palette=tmp_path/'theme.toml';override=tmp_path/'user.toml'
    palette.write_text('[font]\nbase-size=14\n[spacing]\nscale=1.2\nscale-with-font=true\n')
    override.write_text('[font]\nbase-size=20\n')
    appearance=ui.read([palette,override])
    assert appearance.font_size==20
    assert appearance.factor==2
    override.write_text('[spacing]\nscale-with-font=false\n')
    assert ui.read([palette,override]).factor==1.2
    override.write_text('[font]\nbase-size=')
    assert ui.read([palette,override]) is None


def test_live_text_size_change_reflows_windows_and_preserves_capture(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    previous=ui.current;old_font=app.font();old_style=app.styleSheet()
    config=tmp_path/'shell.toml';config.write_text('[font]\nbase-size=12\n')
    manager=theme.ThemeManager(app,[],[config]);manager.timer.stop()
    monkeypatch.setattr('omnishot.widgets.place_window',lambda *args:None)
    store=backend.Store(tmp_path/'data');store.settings['overlay_timeout']=0
    image=QImage(640,360,QImage.Format.Format_RGB32);image.fill(QColor('#123456'))
    path=store.add(image=image)
    editor=Editor(path,store)
    annotation=Annotation(dict(kind='text',x=30,y=40,w=200,h=90,text='Unchanged pixels',font_size=24,color='#ff0000'),editor)
    editor.scene.addItem(annotation);editor.objects.append(annotation);editor.commit()
    settings=Settings(store);preview=QuickOverlay(path,store)
    settings.show();preview.show();app.processEvents()
    rendered=editor.render();source=path.read_bytes();width=preview.width();thumbnail=preview.thumbnail.size()
    try:
        config.write_text('[font]\nbase-size=20\n')
        assert manager.reload()
        app.processEvents()
        assert settings.fields['output_dir'].font().pixelSize()==20
        assert settings.sections.width()==round(165*20/12)
        assert preview.width()==round(width*20/12)
        assert preview.thumbnail.width()==round(thumbnail.width()*20/12)
        assert abs(preview.thumbnail.height()-round(thumbnail.height()*20/12))<=1
        assert editor.toolbar.iconSize()==QSize(33,33)
        assert editor.render()==rendered and path.read_bytes()==source
        for button in preview.findChildren(QPushButton):
            if button.isVisible() and button.text():
                assert button.width()>=button.fontMetrics().horizontalAdvance(button.text())
        config.write_text('[font]\nbase-size=12\n')
        assert manager.reload();app.processEvents()
        assert preview.width()==width and preview.thumbnail.size()==thumbnail
        assert settings.sections.width()==165
        assert editor.render()==rendered
    finally:
        editor.close();preview.close();settings.close();manager.deleteLater()
        ui.apply(app,previous);app.setFont(old_font);app.setStyleSheet(old_style)


def test_resizing_ui_does_not_change_qt_device_scale():
    app=QApplication.instance() or QApplication([])
    previous=ui.current;old_font=app.font();widget=QWidget()
    ui.set(widget,'setFixedSize',180,90)
    before=widget.devicePixelRatioF()
    try:
        ui.apply(app,ui.Appearance(20))
        assert widget.size()==QSize(300,150)
        assert widget.devicePixelRatioF()==before
        ui.apply(app,ui.Appearance(12))
        assert widget.size()==QSize(180,90)
    finally:
        widget.close();widget.deleteLater();ui.apply(app,previous);app.setFont(old_font)


def test_timeline_tracks_and_hit_targets_scale_without_changing_times():
    from PySide6.QtCore import QPointF
    from omnishot.timeline import Timeline
    app=QApplication.instance() or QApplication([]);previous=ui.current;old_font=app.font()
    timeline=Timeline();timeline.resize(800,136);timeline.set_duration(10000)
    timeline.zooms=[dict(start=2.,end=4.,scale=2.)]
    try:
        ui.apply(app,ui.Appearance(20));app.processEvents()
        assert timeline.height()==round(136*20/12)
        rect=timeline.clip_rect('zoom',0)
        assert timeline.hit(rect.center())==('zoom',0,'move')
        assert abs(timeline.time_at(rect.center().x())-3)<.001
        assert timeline.zooms==[dict(start=2.,end=4.,scale=2.)]
        assert timeline.grab().height()==timeline.height()
    finally:
        timeline.close();timeline.deleteLater();ui.apply(app,previous);app.setFont(old_font)
