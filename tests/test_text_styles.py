import json
import pytest
from PySide6.QtGui import QFontMetricsF,QColor,QImage
from omnishot import text_styles
from omnishot.editor import Annotation,Editor,text_height
from omnishot.clipboard import Content
from omnishot.annotation_clipboard import encode
from test_crop import make_editor


def test_seven_presets_have_distinct_font_and_render_behavior(tmp_path):
    app,e=make_editor(tmp_path);e.rebuild([]);e.base.fill(QColor('#555555'));renders={}
    try:
        assert [e.text_style.itemText(i) for i in range(e.text_style.count())]==list(text_styles.STYLES)
        for style in text_styles.STYLES:
            p=dict(kind='text',text='Preset',text_style=style,x=30,y=20,w=250,h=90,font_size=32,color='#111111')
            obj=Annotation(p,e);e.objects=[obj];e.scene.addItem(obj);e.commit();renders[style]=e.render();e.rebuild([])
        assert all(renders[a]!=renders[b] for i,a in enumerate(text_styles.STYLES) for b in text_styles.STYLES[i+1:])
        assert text_styles.font_for(dict(text_style='Rounded')).family()=='Nunito'
        metrics=QFontMetricsF(text_styles.font_for(dict(text_style='Monospaced')))
        assert metrics.horizontalAdvance('iii')==metrics.horizontalAdvance('WWW')
        outline=renders['Outlined'];assert any(outline.pixelColor(x,y).lightness()>220 for x in range(35,180) for y in range(25,75))
        assert outline.pixelColor(30,20)==QColor('#555555') # Glyph outline, not a rectangle border.
        ink=[(x,y) for x in range(35,180) for y in range(25,75) if renders['Standard'].pixelColor(x,y)==QColor('#111111')]
        assert len(ink)>100 and all(abs(outline.pixelColor(x,y).red()-17)<=1 for x,y in ink)
    finally:e.close()


def test_long_word_wrap_and_inline_width_match_saved_layout(tmp_path):
    app,e=make_editor(tmp_path);text='LongUnbrokenIdentifierWithoutSpaces\nمرحبا بالعالم\n日本語テキスト'
    try:
        props=dict(kind='text',text=text,text_style='Standard',x=20,y=20,w=90,h=40,font_size=20)
        obj=Annotation(props,e);e.scene.addItem(obj);e.objects.append(obj);e.commit();doc=text_styles.document(obj.props);doc.size()
        block=doc.begin();lines=0
        while block.isValid():
            layout=block.layout();consumed=0
            for i in range(layout.lineCount()):
                line=layout.lineAt(i);assert line.naturalTextWidth()<=78+.1;consumed+=line.textLength();lines+=1
            assert consumed==len(block.text().encode('utf-16-le'))//2
            block=block.next()
        assert lines>6 and obj.props['h']==text_height(props)
        e.edit_text(obj);assert e.inline.document().textWidth()==doc.textWidth();assert e.inline.document().size()==doc.size()
        e.inline.finish();project=tmp_path/'wrapped.omnishot';e.write_project(project);other=Editor(project,e.store);assert other.render()==e.render();other.close()
    finally:e.close()


def test_preset_change_is_undoable_and_legacy_style_survives_color_change(tmp_path):
    app,e=make_editor(tmp_path)
    try:
        obj=Annotation(dict(kind='text',text='Legacy',text_style='outline',x=20,y=20,w=250,h=90),e);e.scene.addItem(obj);e.objects.append(obj);obj.setSelected(True);e.commit()
        assert e.text_style.style()=='outline';e.set_color('#0077ee');assert obj.props['text_style']=='outline'
        before=e.render();index=e.undo_index;e.text_style.setCurrentText('Rounded Boxed')
        assert obj.props['text_style']=='Rounded Boxed' and obj.props['font_family']=='Nunito' and e.undo_index==index+1
        after=e.render();e.undo();assert e.render()==before;e.redo();assert e.render()==after
        obj=e.objects[-1];obj.setSelected(True);assert e.text_font.family()=='Nunito'
        data=encode([obj.data_dict()]);e.paste_content(Content(annotations=data));assert e.objects[-1].props['font_family']=='Nunito'
    finally:e.close()


def test_selected_resize_handles_have_no_overlap_holes(tmp_path):
    from PySide6.QtCore import QPointF
    app,e=make_editor(tmp_path)
    try:
        for kind in ('rect','ellipse','text','arrow','line'):
            obj=Annotation(dict(kind=kind,w=180,h=120,text='Handle'),e);e.scene.addItem(obj);obj.setSelected(True)
            for center in obj.handles().values():
                for x in (-3,0,3):
                    for y in (-3,0,3):assert obj.shape().contains(center+QPointF(x,y)),(kind,center,x,y)
            e.scene.removeItem(obj)
    finally:e.close()


def test_font_change_reflows_as_one_undo_step(tmp_path,monkeypatch):
    from PySide6.QtGui import QFont
    app,e=make_editor(tmp_path)
    try:
        obj=Annotation(dict(kind='text',text='LongUnbrokenIdentifier',text_style='Standard',x=20,y=20,w=110,h=40,font_size=12),e);e.scene.addItem(obj);e.objects.append(obj);obj.setSelected(True);e.commit()
        before=e.render();index=e.undo_index;font=QFont('Adwaita Mono',32);font.setItalic(True)
        monkeypatch.setattr('omnishot.editor.QFontDialog.getFont',lambda *args:(True,font));e.pick_font()
        assert obj.props['h']>=text_height(obj.props) and obj.props['font_size']==32 and obj.props['italic']
        assert e.undo_index==index+1;e.undo();assert e.render()==before
    finally:e.close()
