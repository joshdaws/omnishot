from PySide6.QtCore import QSizeF,QSize,QMarginsF
from PySide6.QtGui import QImage,QColor,QPageSize,QPageLayout,QPageRanges,QPainter
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtPdf import QPdfDocument
import pytest
from omnishot import printing


def sample():
    image=QImage(100,250,QImage.Format.Format_RGB32);p=QPainter(image)
    for y,color in [(0,'red'),(100,'green'),(200,'blue')]:p.fillRect(0,y,100,100,QColor(color))
    p.end();return image


def printer(path):
    app=QApplication.instance() or QApplication([])
    p=QPrinter();p.setOutputFormat(QPrinter.OutputFormat.PdfFormat);p.setOutputFileName(str(path));p.setResolution(72)
    p.setPageSize(QPageSize(QSizeF(120,120),QPageSize.Unit.Point));p.setPageMargins(QMarginsF(10,10,10,10),QPageLayout.Unit.Point)
    return app,p


def rendered(path):
    doc=QPdfDocument();assert doc.load(str(path))==QPdfDocument.Error.None_
    return [doc.render(page,QSize(120,120)) for page in range(doc.pageCount())]


def test_long_capture_pages_preserve_every_row_and_margins(tmp_path):
    path=tmp_path/'long.pdf';app,p=printer(path);assert printing.paint_image(sample(),p)==3
    pages=rendered(path);assert len(pages)==3
    for image,color in zip(pages,['red','green','blue']):
        assert image.pixelColor(50,20)==QColor(color)
        assert image.pixelColor(5,20).alpha()==0
    assert pages[0].pixelColor(50,108)==QColor('red') and pages[1].pixelColor(50,108)==QColor('green')
    assert pages[2].pixelColor(50,58)==QColor('blue') and pages[2].pixelColor(50,70).alpha()==0


@pytest.mark.parametrize('collate,colors',[(True,['blue','red','blue','red']),(False,['blue','blue','red','red'])])
def test_disjoint_range_reverse_and_copies_are_honored_in_pdf(tmp_path,collate,colors):
    path=tmp_path/'selected.pdf';app,p=printer(path);p.setPageRanges(QPageRanges.fromString('1,3'));p.setPrintRange(QPrinter.PrintRange.PageRange)
    p.setPageOrder(QPrinter.PageOrder.LastPageFirst);p.setCopyCount(2);p.setCollateCopies(collate)
    assert printing.paint_image(sample(),p)==4
    assert [page.pixelColor(50,20) for page in rendered(path)]==[QColor(color) for color in colors]


def test_landscape_and_grayscale_use_the_selected_printer_settings(tmp_path):
    path=tmp_path/'landscape.pdf';app,p=printer(path);p.setPageSize(QPageSize(QSizeF(120,160),QPageSize.Unit.Point));p.setPageOrientation(QPageLayout.Orientation.Landscape);p.setColorMode(QPrinter.ColorMode.GrayScale)
    assert printing.paint_image(sample(),p)==4
    doc=QPdfDocument();doc.load(str(path));assert doc.pagePointSize(0)==QSizeF(160,120)
    color=doc.render(0,QSize(160,120)).pixelColor(50,20);assert color.red()==color.green()==color.blue() and 0<color.red()<255


def test_invalid_range_and_output_errors_leave_source_unchanged(tmp_path,monkeypatch):
    image=sample();before=QImage(image);path=tmp_path/'range.pdf';app,p=printer(path);p.setFromTo(9,10);p.setPrintRange(QPrinter.PrintRange.PageRange)
    with pytest.raises(ValueError,match='no pages'):printing.paint_image(image,p)
    assert not path.exists()
    p.setPrintRange(QPrinter.PrintRange.AllPages);p.setOutputFileName(str(tmp_path/'missing'/'output.pdf'))
    with pytest.raises(OSError,match='start printing'):printing.paint_image(image,p)
    p.setOutputFileName(str(tmp_path/'failure.pdf'));monkeypatch.setattr(p,'newPage',lambda:False)
    with pytest.raises(OSError,match='before all pages'):printing.paint_image(image,p)
    assert image==before


def test_cancel_does_not_start_printing(tmp_path,monkeypatch):
    app,p=printer(tmp_path/'unused.pdf');calls=[]
    monkeypatch.setattr(printing.QPrintDialog,'exec',lambda self:QDialog.DialogCode.Rejected)
    monkeypatch.setattr(printing,'paint_image',lambda *args:calls.append(args))
    assert printing.print_image(sample(),None)==False and calls==[]


def test_editor_print_finishes_text_and_preview_prints_latest_annotations(tmp_path,monkeypatch):
    from omnishot.backend import Store
    from omnishot.editor import Editor,Annotation
    from omnishot.widgets import QuickOverlay
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');path=store.add(image=sample());source=path.read_bytes()
    e=Editor(path,store);overlay=QuickOverlay(path,store);calls=[]
    monkeypatch.setattr(printing,'print_image',lambda image,parent,title:calls.append(QImage(image)))
    try:
        obj=Annotation(dict(kind='text',text='Original',x=0,y=0,w=100,h=70,font_size=12),e);e.objects.append(obj);e.scene.addItem(obj);e.edit_text(obj);e.inline.setPlainText('Latest text')
        e.print_image();assert e.inline is None and obj.props['text']=='Latest text' and calls[0]==e.render()
        e.save_draft();overlay.print_image()
        assert calls[1].convertToFormat(QImage.Format.Format_RGBA8888)==calls[0].convertToFormat(QImage.Format.Format_RGBA8888)
        assert path.read_bytes()==source
    finally:e.close();overlay.close()
