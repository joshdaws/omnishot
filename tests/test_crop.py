import numpy as np
from PySide6.QtCore import QRectF,QPointF,Qt
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtWidgets import QApplication
from omnishot.backend import Store
from omnishot.editor import Editor,Annotation
from omnishot.crop import background_color,resized


def make_editor(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');path=store.add(image=np.full((500,800,3),230,np.uint8));editor=Editor(path,store)
    arrow=Annotation(dict(kind='arrow',x=120,y=90,w=220,h=120,color='#ff0000',width=6),editor);editor.scene.addItem(arrow);editor.objects.append(arrow);editor.commit();return app,editor


def test_crop_apply_is_one_undo_and_cancel_restores_transforms(tmp_path):
    app,e=make_editor(tmp_path)
    try:
        before=e.render();index=e.undo_index;e.set_tool('crop');session=e.crop_session
        session.rect=QRectF(50,40,600,400);session.sync();assert e.render()==before and e.undo_index==index
        session.rotate();session.flip(True);assert e.undo_index==index;session.cancel();assert e.render()==before and e.undo_index==index
        e.set_tool('crop');session=e.crop_session;session.rect=QRectF(50,40,600,400);session.sync();session.apply()
        assert e.render()==before.copy(50,40,600,400) and e.undo_index==index+1
        assert e.objects[0].pos()==QPointF(70,50)
        after=e.render();e.undo();assert e.render()==before;e.redo();assert e.render()==after
        project=tmp_path/'crop.omnishot';e.write_project(project);other=Editor(project,e.store);assert other.render()==after;other.close()
    finally:e.close()


def test_expansion_preserves_alpha_and_cancels_pending_drafts(tmp_path):
    app,e=make_editor(tmp_path)
    try:
        e.save_draft();old=e.draft_path.read_bytes();before=e.render();e.set_tool('crop');session=e.crop_session;session.rotate();assert e.save_draft() and e.draft_path.read_bytes()==old
        session.reset();assert e.render()==before
        session.rect=QRectF(-30,-20,860,540);session.sync();session.apply();result=e.render()
        assert result.size().width()==860 and result.pixelColor(5,5)==QColor(230,230,230)
        assert result.copy(30,20,800,500)==before
        e.undo();assert e.render()==before
        image=QImage(60,40,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
        assert background_color(image).alpha()==0
        p=QPainter(image);p.fillRect(0,0,30,40,QColor('red'));p.end();assert background_color(image).alpha()==0
        index=e.undo_index;e.set_tool('crop');e.crop_session.apply();assert e.undo_index==index
    finally:e.close()


def test_crop_aspect_precision_snapping_and_limit(tmp_path):
    app,e=make_editor(tmp_path)
    try:
        e.set_tool('crop');s=e.crop_session;s.aspect.setCurrentText('16:9');s.dimensions[0].setValue(640);s.size_changed(0);assert s.rect.width()==640 and s.rect.height()==360
        s.swap();assert s.aspect.currentText()=='9:16' and s.rect.width()==360 and s.rect.height()==640
        s.rotate();assert s.aspect.currentText()=='16:9' and s.rect.width()==640 and s.rect.height()==360
        s.reset()
        for handle in ('lt','t','rt','r','rb','b','lb','l'):
            r=resized(QRectF(40,30,160,90),handle,QPointF(210,150),16/9);assert abs(r.width()/r.height()-16/9)<.00001
        image=QImage(300,200,QImage.Format.Format_RGB888);image.fill(QColor('blue'));e.insert_qimage(image,QPointF(70,80))
        assert s.snap_point(QPointF(369,279))==QPointF(370,280)
        s.rect=QRectF(0,0,100000,100000);s.sync();assert not s.apply_button.isEnabled();s.apply();assert e.crop_session is s
        s.cancel();assert len(e.objects)==1
    finally:e.close()


def test_expanding_a_translucent_border_does_not_change_original_alpha(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data')
    original=QImage(80,50,QImage.Format.Format_ARGB32_Premultiplied);original.fill(QColor(120,80,40,128));path=tmp_path/'alpha.png';original.save(str(path));e=Editor(path,store)
    try:
        original=e.render();e.set_tool('crop');e.crop_session.rect=QRectF(-10,-10,100,70);e.crop_session.sync();e.crop_session.apply();expanded=e.render()
        assert expanded.copy(10,10,80,50)==original and expanded.pixelColor(2,2).alpha()==128
    finally:e.close()


def test_custom_ratio_and_fill_keep_original_pixels_and_profile(tmp_path):
    from PySide6.QtGui import QColorSpace
    app,e=make_editor(tmp_path)
    try:
        e.base.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3));e.commit();original=e.render(convert_srgb=False)
        e.set_tool('crop');s=e.crop_session;s.aspect.setCurrentText('Custom');s.ratio_fields[0].setValue(7);s.ratio_fields[1].setValue(4);s.custom_ratio_changed();s.dimensions[0].setValue(840);s.size_changed(0)
        assert s.rect.width()==840 and s.rect.height()==480
        s.set_fill(QColor('#80b47835'));fill=s.resolved_fill();s.open_size();s.size_popup.close();assert e.crop_session is s
        s.apply();result=e.render(convert_srgb=False);assert result.copy(0,0,800,480)==original.copy(0,0,800,480)
        assert result.colorSpace()==original.colorSpace() and result.pixelColor(820,200).alpha()==128
        assert max(abs(a-b) for a,b in zip(result.pixelColor(820,200).getRgb(),fill.getRgb()))<=1
        e.undo();assert e.render(convert_srgb=False)==original
        e.set_tool('crop');s=e.crop_session;s.set_fill(QColor(Qt.GlobalColor.transparent));assert s.resolved_fill().alpha()==0;s.cancel();assert e.render(convert_srgb=False)==original
    finally:e.close()
