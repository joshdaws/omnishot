import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtGui import QImage,QColor,QColorSpace
from omnishot.clipboard import read_content,local_files
from omnishot.backend import Store
from omnishot.editor import png_bytes


def test_clipboard_local_media_files_preserve_uri_semantics(tmp_path):
    source=tmp_path/'A movie with spaces & accents é.mp4';source.write_bytes(b'fixture')
    uri=source.as_uri()
    assert local_files(('#comment\r\n'+uri+'\r\n'+uri).encode())==(source,)
    assert local_files(('cut\n'+uri).encode())==(source,)
    assert source.read_bytes()==b'fixture'
    with pytest.raises(ValueError,match='local'):local_files(b'https://example.com/video.mp4')
    with pytest.raises(ValueError,match='local'):local_files(b'file://remote-server/video.mp4')
    with pytest.raises(ValueError,match='available'):local_files((tmp_path/'missing.mp4').as_uri().encode())


def test_file_offer_wins_over_thumbnail_and_plain_text_is_not_opened(tmp_path,monkeypatch):
    source=tmp_path/'clip.mp4';source.write_bytes(b'fixture');calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return b'text/uri-list\nimage/png\n' if '--list-types' in args else source.as_uri().encode()
    monkeypatch.setattr('omnishot.clipboard.backend.run',run)
    result=read_content();assert result.files==(source,) and result.image is None
    assert calls[-1][calls[-1].index('--type')+1]=='text/uri-list'
    monkeypatch.setattr('omnishot.clipboard.backend.run',lambda *args,**kwargs:b'text/plain\n')
    with pytest.raises(ValueError,match='Copy an image'):read_content()


def test_clipboard_rgba_and_icc_survive_history(tmp_path,monkeypatch):
    image=QImage(80,60,QImage.Format.Format_RGBA8888);image.fill(QColor(100,50,20,64));image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3));data=png_bytes(image)
    monkeypatch.setattr('omnishot.clipboard.backend.run',lambda args,**kwargs:b'image/png\n' if '--list-types' in args else data)
    result=read_content();store=Store(tmp_path/'data');path=store.add(image=result.image);loaded=QImage(str(path))
    assert loaded.convertToFormat(QImage.Format.Format_RGBA8888)==image and loaded.colorSpace()==image.colorSpace()
