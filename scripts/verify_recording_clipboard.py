"""Native Copy button and independent file consumers in an isolated desktop."""
import json,os,subprocess,sys,time
from pathlib import Path
from urllib.parse import unquote,urlparse
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.widgets import QuickOverlay,JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate()
def snapshot():
    types=backend.run(['wl-paste','--list-types']).decode().splitlines()
    assert 'text/uri-list' in types and 'x-special/gnome-copied-files' in types and 'image/png' not in types,types
    uri=backend.run(['wl-paste','--type','text/uri-list','--no-newline']).decode().strip()
    assert backend.run(['wl-paste','--type','x-special/gnome-copied-files','--no-newline']).decode()=='copy\n'+uri
    assert backend.run(['wl-paste','--type','application/x-kde-cutselection','--no-newline'])==b'0'
    return Path(unquote(urlparse(uri).path))
store=backend.Store(out/'data');source=out/'generated.mp4'
backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=240x160:r=15:d=1','-c:v','libx264','-threads','1',source])
path=store.add(source=source,kind='video');store.rename(path,'A recording with spaces & accents é')
overlay=QuickOverlay(path,store);overlay.show();QTest.qWait(300)
try:
    button=next(b for b in overlay.findChildren(QPushButton) if b.text()=='Copy')
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==overlay.windowTitle());point=button.mapTo(overlay,button.rect().center())
    backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(100);command('click 272')
    wait(lambda:not overlay.isVisible() and not JOBS)
    copied=snapshot();assert copied.name==store.display_name(path) and copied.read_bytes()==source.read_bytes()
    original=copied.read_bytes();path.write_bytes(b'changed original');assert copied.read_bytes()==original
    store.remove(path);assert copied.exists() and copied.read_bytes()==original
    # File-only offers have no PNG limit or media-sized memory allocation.
    large=out/'large sparse.mp4'
    with large.open('wb') as file:file.write(b'sparse fixture');file.truncate(1024*1024*1024+17)
    copied_large=backend.copy_file(large,store,name='Large recording.mp4');assert snapshot()==copied_large
    assert copied_large.stat().st_size==large.stat().st_size
    owners=[]
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args=(proc/'cmdline').read_bytes().split(b'\0')
            if args and args[0].endswith(b'clipboard-helper') and os.fsencode(copied_large) in args:
                status=(proc/'status').read_text();rss=int(next(line.split()[1] for line in status.splitlines() if line.startswith('VmRSS:')));owners.append(rss)
        except (OSError,StopIteration):pass
    assert owners and max(owners)<32*1024,owners
    large.unlink();copied_large.unlink()
    report=dict(native_copy_button=True,readable_filename=True,gnome_and_kde_formats=True,snapshot_survives_edit_and_deletion=True,large_file_bytes=1024*1024*1024+17,clipboard_owner_rss_kib=owners)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    overlay.close();fixture.stdin.close();fixture.wait(timeout=3);backend.run(['wl-copy','--clear'])
