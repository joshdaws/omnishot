import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy,time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from omnishot.timeline import Timeline
from omnishot.studio import zoom_at


def test_click_drag_cancel_join_and_context_zoom_actions():
    app=QApplication.instance() or QApplication([]);t=Timeline();t.resize(1100,136);t.set_frame_rate(30);t.set_duration(18000);t.show();app.processEvents()
    point=lambda seconds:QPoint(round(t.x(seconds)),44)
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,pos=point(2));assert len(t.zooms)==1 and t.selected==('zoom',0)
    assert t.zooms[0]['scale']==1.5 and t.zooms[0]['follow']
    QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=point(8));QTest.mouseMove(t,point(11));QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=point(11))
    assert len(t.zooms)==2 and abs(t.zooms[1]['end']-11)<.04
    assert all(abs(z[k]*t.fps-round(z[k]*t.fps))<1e-6 for z in t.zooms for k in ('start','end'))
    before=copy.deepcopy(t.zooms);QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=point(14));QTest.mouseMove(t,point(17));QTest.keyClick(t,Qt.Key.Key_Escape);QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=point(17));assert t.zooms==before
    # Move a zoom to its neighbor; the boundary snaps and cannot overlap it.
    QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=point(9.5));QTest.mouseMove(t,point(6.5));QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=point(6.5))
    assert t.zooms[1]['start']==pytest.approx(t.zooms[0]['end'])
    t.change_zoom(scale=2.3,follow=False,x=.7,y=.4);t.apply_zoom_level_to_all();assert all(z['scale']==2.3 for z in t.zooms)
    t.set_position(round((t.zooms[1]['start']+1)*1000));assert t.split_zoom_at_playhead();assert len(t.zooms)==3
    assert t.zooms[1]['end']==t.zooms[2]['start'] and not t.split_zoom_at_playhead()
    assert t.duplicate_zoom();assert len(t.zooms)==4
    QTest.keyClick(t,Qt.Key.Key_Backspace);assert len(t.zooms)==3
    t.close()


def test_joined_zoom_transitions_never_zoom_out():
    a=dict(start=1,end=3,scale=2,x=.25,y=.5);b=dict(start=3,end=5,scale=3,x=.75,y=.5)
    assert zoom_at([a,b],3)==(2,.25,.5)
    for mode in ('Smooth','Dynamic'):
        values=[zoom_at([a,b],t/1000,animation=mode) for t in range(2950,3501,10)]
        assert min(v[0] for v in values)>=2
        assert all(x[0]<=y[0] and x[1]<=y[1] for x,y in zip(values,values[1:]))
        assert values[-1]==(3,.75,.5)
    assert zoom_at([a],3)[0]==1
    assert zoom_at([a,b],1.1,animation='Dynamic')[0]>zoom_at([a,b],1.1)[0]
    assert zoom_at([dict(a,follow=True)],2,dict(x=.6,y=.4))==(2,.6,.4)


def test_automatic_zoom_seeds_and_user_clear_survive_reopening(tmp_path):
    import json
    from omnishot import backend
    from omnishot.recording import VideoEditor
    from omnishot.studio import smart_zooms
    app=QApplication.instance() or QApplication([]);source=tmp_path/'source.mp4'
    backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:size=160x90:rate=15:duration=4','-c:v','libx264',source])
    events=[dict(kind='click',t=1,x=.3,y=.4),dict(kind='click',t=3.8,x=.8,y=.5),dict(kind='click',t=3.9,x=2,y=.5)]
    zooms=smart_zooms(events,limit=4)
    assert zooms and max(z['end'] for z in zooms)<=4
    assert all(a['end']<=b['start'] for a,b in zip(zooms,zooms[1:]))
    meta=dict(version=1,cursor=[],events=events,initial_zooms=zooms,capture_options=dict(studio=True,clicks=False,keys=False,cursor=False))
    source.with_suffix('.studio.json').write_text(json.dumps(meta));store=backend.Store(tmp_path/'data')
    e=VideoEditor(source,store);e.player.pause();assert e.zooms==zooms and not e.show_clicks.isChecked() and not e.show_cursor.isChecked()
    e.timeline.select(('zoom',0));assert e.inspector.currentWidget()==e.zoom_inspector
    e.zoom_inspector.level.setValue(240);assert e.zooms[0]['scale']==2.4
    e.zoom_inspector.modes[False].click();assert e.zoom_inspector.focus.isVisibleTo(e.zoom_inspector)
    e.zoom_animation.setCurrentText('Dynamic');assert e.edit_options()['zoom_animation']=='Dynamic'
    deadline=time.monotonic()+3
    while e.timeline.duration<4 and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert e.timeline.split_at(2)
    assert e.inspector.currentWidget()!=e.zoom_inspector and e.tool_buttons['Cursor'].isChecked()
    e.clear_zooms();assert not e.zooms;e.close()
    e=VideoEditor(source,store);e.player.pause();assert not e.zooms and e.zoom_animation.currentText()=='Dynamic'
    assert meta['initial_zooms']==zooms
    e.close();app.processEvents()
