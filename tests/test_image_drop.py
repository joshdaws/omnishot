import pytest
from PySide6.QtCore import Qt, QPointF, QMimeData, QUrl
from PySide6.QtGui import QImage, QColor, QDropEvent
from PySide6.QtWidgets import QApplication
from omnishot.backend import Store
from omnishot.editor import Editor
import omnishot.editor as module


@pytest.fixture
def editor(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    base = QImage(600, 400, QImage.Format.Format_ARGB32)
    base.fill(QColor('white'))
    path = tmp_path / 'base.png'
    base.save(str(path))
    instance = Editor(path, Store(tmp_path / 'data'))
    monkeypatch.setattr(module, 'error', lambda *args: None)
    yield instance
    instance.close()


def drop(editor, mime):
    event = QDropEvent(QPointF(140, 120), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    position = editor.view.mapToScene(event.position().toPoint())
    editor.view.dropEvent(event)
    return event, position


def picture(color):
    image = QImage(80, 60, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


def test_image_only_drop_inserts_editable_image_at_pointer(editor, tmp_path):
    mime = QMimeData()
    mime.setImageData(picture('#8033aaff'))
    event, position = drop(editor, mime)
    assert event.isAccepted() and len(editor.objects) == 1
    obj = editor.objects[0]
    assert obj.props['kind'] == 'image' and obj.pos() == position
    assert obj.isSelected() and editor.view.tool == 'select'
    project = tmp_path / 'dropped.omnishot'
    editor.write_project(project)
    other = Editor(project, editor.store)
    assert other.render() == editor.render()
    other.close()
    editor.undo()
    assert not editor.objects
    editor.redo()
    assert len(editor.objects) == 1


def test_multiple_file_drop_is_one_undo_and_uses_files_once(editor, tmp_path):
    paths = []
    for i, color in enumerate(('red', 'blue')):
        path = tmp_path / f'{i}.png'
        picture(color).save(str(path))
        paths.append(QUrl.fromLocalFile(str(path)))
    mime = QMimeData()
    mime.setUrls(paths)
    mime.setImageData(picture('green'))
    event, position = drop(editor, mime)
    assert event.isAccepted() and len(editor.objects) == 2
    assert editor.objects[0].pos() == position
    assert editor.objects[1].pos() == position + QPointF(20, 20)
    editor.undo()
    assert not editor.objects


def test_invalid_batch_is_rejected_without_partial_insert(editor, tmp_path):
    path = tmp_path / 'valid.png'
    picture('red').save(str(path))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)), QUrl.fromLocalFile(str(tmp_path / 'missing.png'))])
    original = editor.render()
    index = editor.undo_index
    event, _ = drop(editor, mime)
    assert not event.isAccepted() and not editor.objects
    assert editor.render() == original and editor.undo_index == index


def test_remote_url_without_pixels_is_not_accepted(editor):
    mime = QMimeData()
    mime.setUrls([QUrl('https://example.test/image.png')])
    event, _ = drop(editor, mime)
    assert not event.isAccepted() and not editor.objects


def test_remote_url_with_pixels_uses_image_payload(editor):
    mime = QMimeData()
    mime.setUrls([QUrl('https://example.test/image.png')])
    mime.setImageData(picture('blue'))
    event, _ = drop(editor, mime)
    assert event.isAccepted() and len(editor.objects) == 1


def test_png_payload_preserves_alpha_when_generic_image_is_opaque(editor):
    from omnishot.editor import png_bytes
    import base64
    image = picture('#8033aaff')
    mime = QMimeData()
    mime.setImageData(picture('black'))
    mime.setData('image/png', png_bytes(image))
    event, _ = drop(editor, mime)
    assert event.isAccepted()
    restored = QImage.fromData(base64.b64decode(editor.objects[0].props['image']))
    assert restored.pixelColor(20, 20) == image.pixelColor(20, 20)
