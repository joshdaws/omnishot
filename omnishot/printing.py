"""Shared screenshot printing, including readable pages for scrolling captures."""
from pathlib import Path
from PySide6.QtCore import QRectF,QTimer,QStandardPaths
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QDialog
from PySide6.QtPrintSupport import QPrinter,QPrintDialog
from .images import convert_image


class ScreenshotPrintDialog(QPrintDialog):
    def __init__(self,printer,parent):
        super().__init__(printer,parent)
        self.position_timer=QTimer(self);self.position_timer.setSingleShot(True);self.position_timer.timeout.connect(self.center_on_display)
    def showEvent(self,event):
        super().showEvent(event);self.position_timer.start(30)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'position_timer'):self.position_timer.start(30)
    def center_on_display(self):
        if not self.isVisible():return
        from .widgets import place_window
        parent=self.parentWidget();bounds=(parent.screen() if parent else self.screen()).availableGeometry()
        place_window(self,bounds.x()+max(0,(bounds.width()-self.width())//2),bounds.y()+max(0,(bounds.height()-self.height())//2))


def page_slices(image,printer):
    if image.isNull():raise ValueError('There is no image to print.')
    page=printer.pageRect(QPrinter.Unit.DevicePixel)
    if page.width()<=0 or page.height()<=0:raise ValueError('The selected paper margins leave no printable area.')
    scale=page.width()/image.width();height=max(1,int(page.height()/scale))
    return [(y,min(height,image.height()-y)) for y in range(0,image.height(),height)],scale


def page_order(count,printer):
    pages=list(range(count));ranges=printer.pageRanges()
    if printer.printRange()==QPrinter.PrintRange.PageRange and not ranges.isEmpty():
        pages=[page for page in pages if ranges.contains(page+1)]
    if not pages:raise ValueError(f'The selected range contains no pages. This capture has {count} pages with the selected paper settings.')
    if printer.pageOrder()==QPrinter.PageOrder.LastPageFirst:pages.reverse()
    copies=1 if printer.supportsMultipleCopies() else max(1,printer.copyCount())
    return pages*copies if printer.collateCopies() else [page for page in pages for _ in range(copies)]


def paint_image(image,printer):
    slices,scale=page_slices(image,printer);pages=page_order(len(slices),printer)
    image=convert_image(image);painter=QPainter()
    if not painter.begin(printer):raise OSError('Could not start printing. Check the printer or output file destination.')
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.LosslessImageRendering)
        page=printer.pageRect(QPrinter.Unit.DevicePixel)
        x,y=(page.x(),page.y()) if printer.fullPage() else (0,0)
        for index,number in enumerate(pages):
            if index and not printer.newPage():raise OSError('Printing stopped before all pages were written.')
            start,height=slices[number]
            painter.drawImage(QRectF(x,y,image.width()*scale,height*scale),image,QRectF(0,start,image.width(),height))
    except Exception:
        printer.abort();painter.end();raise
    if not painter.end() or printer.printerState() in (QPrinter.PrinterState.Error,QPrinter.PrinterState.Aborted):
        raise OSError('The printer could not finish the document.')
    return len(pages)


def print_image(image,parent,title='OmniShot capture'):
    if image.isNull():raise ValueError('There is no image to print.')
    printer=QPrinter(QPrinter.PrinterMode.HighResolution);printer.setDocName(title);printer.setCreator('OmniShot')
    # Qt only derives its default PDF filename on X11, leaving a directory on
    # Wayland. Supply a useful name while retaining the selected physical printer.
    folder=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
    if not folder.is_dir():folder=Path.home()
    output_format=printer.outputFormat();printer.setOutputFileName(str(folder/(Path(title).stem+'.pdf')));printer.setOutputFormat(output_format)
    dialog=ScreenshotPrintDialog(printer,parent);dialog.setWindowTitle('OmniShot — Print')
    dialog.setOption(QPrintDialog.PrintDialogOption.PrintPageRange,True)
    dialog.setOption(QPrintDialog.PrintDialogOption.PrintSelection,False)
    dialog.setOption(QPrintDialog.PrintDialogOption.PrintCurrentPage,False)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return False
    paint_image(image,printer);return True
