import os,sys,time,json
from pathlib import Path
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.timeline import Timeline
from PIL import Image
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setStyle('Fusion');theme=ThemeManager(app)
window=QWidget();window.setWindowTitle('OmniShot Ruler Verification');window.resize(1180,300)
layout=QVBoxLayout(window);timeline=Timeline();layout.addWidget(timeline);window.show()
for name,duration,zoom,offset in [('short',8,0,0),('hours',86400,0,0),('frames',8,100,3500)]:
 timeline.set_duration(duration*1000);timeline.set_zoom(zoom);timeline.scroll.setValue(offset);timeline.update()
 end=time.monotonic()+.25
 while time.monotonic()<end:app.processEvents();QTest.qWait(10)
 client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle())
 Image.fromarray(backend.grab_window(client)).save(out/(name+'.png'))
window.close();print(json.dumps(dict(native_wayland=True,scale=1.6,short_seconds=8,long_hours=24,frame_zoom=True)))
