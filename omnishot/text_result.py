"""Recognized text and explicit actions for links found locally in it."""
from . import ui_scale as ui
import re
from pathlib import Path
from urllib.parse import urlsplit
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices,QKeySequence,QShortcut
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPlainTextEdit,QListWidget,QDialogButtonBox
from . import backend

DIALOGS=set()
# IANA root-zone snapshot, 2026-09-05: https://data.iana.org/TLD/tlds-alpha-by-domain.txt
_TLDS=set(Path(__file__).with_name('data').joinpath('tlds-alpha-by-domain.txt').read_text().splitlines()[1:])
_CANDIDATE=re.compile(r'''(?<![\w@./-])(?:https?://[^\s<>"“”]+|www\.[^\s<>"“”]+|(?:[^\W_](?:[\w-]*[^\W_])?\.)+[^\W\d_](?:[\w-]*[^\W_])?(?::\d{1,5})?(?:[/?\#][^\s<>"“”]*)?)''',re.IGNORECASE)


def detected_links(text):
    """Keep recognized spelling; add HTTPS only for scheme-less web addresses."""
    links=[];seen=set()
    for match in _CANDIDATE.finditer(text):
        value=match.group().rstrip('.,;:!\'’')
        for left,right in (('(',')'),('[',']'),('{','}')):
            while value.endswith(right) and value.count(right)>value.count(left):value=value[:-1]
        explicit=bool(re.match(r'https?://',value,re.I))
        url=value if explicit else 'https://'+value
        if len(url)>8192 or any(ord(c)<32 for c in url):continue
        try:
            parsed=urlsplit(url);host=parsed.hostname
            if parsed.scheme.lower() not in ('http','https') or not host or parsed.port==0:continue
            # A malformed authority must not be handed to a protocol handler.
            if not QUrl(url,QUrl.ParsingMode.StrictMode).isValid():continue
            if host!='localhost' and '.' not in host and ':' not in host:continue
            ascii_host=host.encode('idna').decode()
            if not explicit and ascii_host.rsplit('.',1)[-1].upper() not in _TLDS:continue
        except (ValueError,UnicodeError):continue
        if url not in seen:links.append((value,url));seen.add(url)
        if len(links)>=128:break
    return links


def extract(path,languages='auto',linebreaks=True):
    """Read text and QR codes independently; OCR noise must not hide a QR link."""
    text=qr='';errors=[]
    try:text=backend.ocr(path,languages,linebreaks)
    except Exception as exc:errors.append(exc)
    try:qr=backend.read_qr(path)
    except Exception as exc:errors.append(exc)
    if not text and not qr and errors:raise errors[0]
    parts=[text] if text else [];known=set(text.splitlines())|{url for _,url in detected_links(text)}
    for value in qr.splitlines():
        if value and value not in known:parts.append(value);known.add(value)
    return ('\n\n' if linebreaks else ' ').join(parts)


class TextResultDialog(QDialog):
    def __init__(self,text,detect=True,parent=None,copied=False):
        super().__init__(parent);self.setWindowTitle('OmniShot — Recognized Text');ui.set(self,"resize",600,400);self.detect=detect;self.copied=copied
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout=QVBoxLayout(self);ui.set(layout,"setContentsMargins",20,20,20,20);ui.set(layout,"setSpacing",12)
        self.status=QLabel('Text copied to clipboard' if copied else 'Review or edit the recognized text');layout.addWidget(self.status)
        self.text=QPlainTextEdit();self.text.setPlainText(text);self.text.setAccessibleName('Recognized text');layout.addWidget(self.text,1)
        self.link_label=QLabel('Detected links');layout.addWidget(self.link_label)
        self.links=QListWidget();self.links.setAccessibleName('Detected links');ui.set(self.links,"setMaximumHeight",140);layout.addWidget(self.links)
        buttons=QDialogButtonBox();layout.addWidget(buttons)
        self.copy_button=buttons.addButton('Copy Text',QDialogButtonBox.ButtonRole.ActionRole)
        self.open_button=buttons.addButton('Open Link',QDialogButtonBox.ButtonRole.ActionRole)
        self.close_button=buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.copy_button.clicked.connect(self.copy);self.open_button.clicked.connect(self.open_link);buttons.rejected.connect(self.reject)
        self.links.currentRowChanged.connect(lambda row:self.open_button.setEnabled(row>=0))
        self.text.textChanged.connect(self.text_changed);self.refresh_links()
        QShortcut(QKeySequence('Ctrl+Return'),self,activated=self.copy)
        self.close_button.setDefault(True)

    def text_changed(self):
        self.copied=False;self.status.setText("Edited text — copy to use your changes");self.refresh_links()

    def refresh_links(self):
        self.links.clear()
        for label,url in detected_links(self.text.toPlainText()) if self.detect else []:
            self.links.addItem(label);self.links.item(self.links.count()-1).setData(Qt.ItemDataRole.UserRole,url);self.links.item(self.links.count()-1).setToolTip(url)
        present=self.links.count()>0
        self.links.setVisible(present);self.link_label.setVisible(present);self.open_button.setVisible(present)
        if present:self.links.setCurrentRow(0)
        self.open_button.setEnabled(present);self.copy_button.setEnabled(bool(self.text.toPlainText()))

    def copy(self):
        try:backend.copy_text(self.text.toPlainText());self.copied=True;self.status.setText('Text copied to clipboard')
        except Exception as exc:self.status.setText(f'Could not copy text: {exc}')

    def open_link(self):
        item=self.links.currentItem()
        if item and not QDesktopServices.openUrl(QUrl(item.data(Qt.ItemDataRole.UserRole))):self.status.setText('Could not open the link. Copy the text to open it manually.')


def present(text,settings,parent=None,review=False):
    """Ordinary OCR stays a copy action; recognized links offer an explicit Open."""
    copy_error=None
    if text and not review:
        try:backend.copy_text(text)
        except Exception as exc:copy_error=str(exc)
    detect=settings.get('ocr_detect_links',True)
    if not review and copy_error is None and (not detect or not detected_links(text)):return None
    dialog=TextResultDialog(text,detect,parent,copied=bool(text) and not review and copy_error is None)
    if copy_error:dialog.status.setText(f'Could not copy text: {copy_error}')
    DIALOGS.add(dialog);dialog.destroyed.connect(lambda:DIALOGS.discard(dialog));dialog.show();return dialog
