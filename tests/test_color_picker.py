import numpy as np
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication,QWidget
from omnishot.backend import Store
from omnishot.color_picker import ColorPicker,color_text,favorite_colors
from omnishot.editor import Editor,Annotation


def test_picker_channels_alpha_favorites_and_failed_save(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');parent=QWidget();picker=ColorPicker('#b48bfa',store,parent)
    try:
        picker.hex.setText('2468AC');picker.hex_changed();picker.channels[3].setValue(50)
        assert picker.color.getRgb()==(36,104,172,128)
        assert color_text(picker.color)=='#802468ac'
        assert not favorite_colors(store.settings)
        picker.add_favorite();assert favorite_colors(Store(store.root).settings)==['#802468ac']
        picker.add_favorite();assert len(picker.favorite_buttons)==1
        picker.set_color(QColor('#123456'));before=favorite_colors(store.settings)
        monkeypatch.setattr(store,'save_settings',lambda:(_ for _ in ()).throw(OSError('disk full')))
        picker.add_favorite();assert favorite_colors(store.settings)==before and 'disk full' in picker.message.text()
        assert favorite_colors({'palette':['#ff5b61','#123456','#123456']})==['#123456']
    finally:picker.close();parent.close()


def test_live_color_change_is_one_undo_and_preserves_other_styles(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');path=store.add(image=np.full((220,400,3),255,np.uint8));editor=Editor(path,store)
    try:
        for x,width in [(30,2),(210,12)]:
            obj=Annotation(dict(kind='rect',x=x,y=40,w=120,h=110,color='#ff0000',width=width),editor);editor.objects.append(obj);editor.scene.addItem(obj);obj.setSelected(True)
        editor.commit();before=editor.render();index=editor.undo_index;editor.pick_color();picker=editor.color_popup
        picker.set_color(QColor('#802468ac'));picker.set_color(QColor('#803a95c4'))
        assert editor.undo_index==index and [o.props['width'] for o in editor.objects]==[2,12]
        assert all(o.props['color']=='#803a95c4' for o in editor.objects)
        picker.close();assert editor.undo_index==index+1;after=editor.render();assert after!=before
        project=tmp_path/'alpha.omnishot';editor.write_project(project);other=Editor(project,store)
        assert other.render()==after;other.close();editor.undo();assert editor.render()==before;editor.redo();assert editor.render()==after
    finally:editor.close()


def test_screen_picker_distinguishes_cancel_from_failure(monkeypatch):
    import subprocess,pytest
    from omnishot.color_picker import sample_screen
    for code,stdout,stderr in [(0,b'#2474AB',b''),(2,b'',b''),(1,b'',b'capture unavailable')]:
        monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess(args,code,stdout,stderr))
        if code==1:
            with pytest.raises(RuntimeError,match='capture unavailable'):sample_screen()
        else:assert sample_screen()==stdout
