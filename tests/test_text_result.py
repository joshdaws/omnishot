import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.text_result import detected_links,extract,present,DIALOGS


def test_link_detection_preserves_queries_and_balanced_parentheses():
    text='Visit https://example.com/a_(b)?x=1&y=2. Then (www.example.org/path). example.net/docs#part and https://example.com/a_(b)?x=1&y=2.'
    assert detected_links(text)==[('https://example.com/a_(b)?x=1&y=2','https://example.com/a_(b)?x=1&y=2'),('www.example.org/path','https://www.example.org/path'),('example.net/docs#part','https://example.net/docs#part')]
    assert detected_links('http://localhost:8000/path https://[::1]:8443/a https://例子.中国/页')==[('http://localhost:8000/path','http://localhost:8000/path'),('https://[::1]:8443/a','https://[::1]:8443/a'),('https://例子.中国/页','https://例子.中国/页')]
    assert detected_links('例子.中国/页')==[('例子.中国/页','https://例子.中国/页')]


def test_link_detection_ignores_non_web_actions_and_malformed_urls():
    assert detected_links('file:///tmp/screenshot.png javascript:alert(1) mailto:me@example.com person@sub.example.com image.png example.notarealtld https://[broken https://example.com:99999')==[]


def test_qr_is_read_when_ocr_is_noisy_empty_or_unavailable(monkeypatch):
    monkeypatch.setattr(backend,'read_qr',lambda path:'https://example.com/qr\nhttps://example.org/other')
    for text in ('noise','', 'https://example.com/qr'):
        monkeypatch.setattr(backend,'ocr',lambda *args,t=text:t)
        result=extract('generated.png');assert result.count('https://example.com/qr')==1 and 'https://example.org/other' in result
    def fail(*args):raise RuntimeError('OCR language unavailable')
    monkeypatch.setattr(backend,'ocr',fail);assert extract('qr.png')=='https://example.com/qr\n\nhttps://example.org/other'
    monkeypatch.setattr(backend,'read_qr',lambda path:'')
    with pytest.raises(RuntimeError,match='language'):extract('empty.png')
    monkeypatch.setattr(backend,'ocr',lambda *a:'https://example.com/qr?different=1')
    monkeypatch.setattr(backend,'read_qr',lambda path:'https://example.com/qr')
    assert extract('different-links.png').splitlines()==['https://example.com/qr?different=1','','https://example.com/qr']


def test_result_preference_editing_and_clipboard_failure(monkeypatch):
    app=QApplication.instance() or QApplication([]);copied=[];monkeypatch.setattr(backend,'copy_text',copied.append)
    text='https://example.com/capture';settings={'ocr_detect_links':True}
    dialog=present(text,settings);assert copied==[text] and dialog.links.count()==1
    dialog.text.setPlainText('edited text');assert dialog.links.count()==0 and not dialog.copied
    dialog.copy_button.click();assert copied[-1]=='edited text';dialog.close()
    assert present(text,{'ocr_detect_links':False}) is None and copied[-1]==text
    previous=list(copied);assert present('',settings) is None and copied==previous
    dialog=present('review',settings,review=True);assert copied==previous;dialog.close()
    def fail(text):raise RuntimeError('Clipboard unavailable')
    monkeypatch.setattr(backend,'copy_text',fail);dialog=present('keep this text',settings)
    assert dialog.text.toPlainText()=='keep this text' and 'Could not copy' in dialog.status.text();dialog.close()
    app.processEvents()
