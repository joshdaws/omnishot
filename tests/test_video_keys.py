import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtWidgets import QApplication
from omnishot.video_keys import command_event,visible_keys,key_colors
from omnishot.video_position import POSITIONS
from omnishot.studio import compose_frame


def test_filter_preserves_commands_and_legacy_capture_intent():
    events=[dict(t=.1,kind='key',state=1,label=label) for label in ('A','Shift+A','Ctrl+K','Alt+Tab','Super+V')]
    assert visible_keys(events,.5,{}, {})==['A','Shift+A','Ctrl+K','Alt+Tab','Super+V']
    assert visible_keys(events,.5,{'key_commands_only':True},{})==['Ctrl+K','Alt+Tab','Super+V']
    assert visible_keys(events,.5,{}, {'capture_options':{'commands_only':True}})==['Ctrl+K','Alt+Tab','Super+V']
    assert not command_event({'label':'Ctrl+K','command':False})
    assert command_event({'label':'Custom label','command':True})
    events[2]['hidden']=True
    assert visible_keys(events,.5,{'key_commands_only':True},{})==['Alt+Tab','Super+V']
    assert not visible_keys(events,3,{}, {})


def test_all_positions_styles_and_repeated_seeks():
    app=QApplication.instance() or QApplication([]);frame=np.full((360,640,3),100,dtype=np.uint8)
    meta={'events':[dict(t=0,kind='key',state=1,label='Ctrl+K')]};centers=[]
    def pixels(image):return np.asarray(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3).copy()
    for position in POSITIONS:
        options={'key_position':position,'key_style':'Light','cursor':False,'clicks':False,'keys':True}
        image=pixels(compose_frame(frame,.5,meta,options));ys,xs=np.where(np.max(abs(image.astype(int)-100),axis=2)>10)
        centers.append([float(xs.mean()),float(ys.mean())]);row,col=divmod(POSITIONS.index(position),3)
        assert abs(xs.mean()-[75,320,565][col])<35 and abs(ys.mean()-[50,180,310][row])<25
        assert np.array_equal(image,pixels(compose_frame(frame,.5,meta,options)))
        assert np.mean(image[ys,xs])>160
    assert len({tuple(c) for c in centers})==9
    assert key_colors({'key_color':'#123456','key_background':'#abcdef'})==('#abcdef','#123456')
    assert key_colors({'key_style':'Light'})!=key_colors({'key_style':'Dark'})


def test_inspector_restores_every_keystroke_control():
    from omnishot.video_styles import EffectsControls
    app=QApplication.instance() or QApplication([]);panel=EffectsControls({},section='Keystrokes');fields=panel.fields
    opts=dict(key_size=40,key_style='Light',key_position='Center',key_commands_only=True)
    panel.set_options(opts)
    assert all(panel.options()[key]==value for key,value in opts.items())
    assert fields['key_size'].label.text()=='2×' and not fields['key_color'].isEnabled()
    panel.set_options(dict(key_style='Custom',key_commands_only=False));assert fields['key_color'].isEnabled() and fields['key_commands_only'].all.isChecked()
    panel.close()
