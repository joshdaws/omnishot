import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from omnishot.studio import compose_frame
from omnishot.video_clicks import press_scale


def test_press_has_bounded_duration_and_repeated_clicks_do_not_compound():
    events=[dict(kind='click',t=1),dict(kind='click',t=1.05)]
    assert press_scale(events,.9)==1 and press_scale(events,1.3)==1
    assert press_scale(events,1.12)==pytest.approx(.82)
    assert all(.82<=press_scale(events,t)<=1 for t in np.arange(1,1.3,.005))
    assert press_scale([dict(kind='click',t=1,hidden=True),dict(kind='key',t=1)],1.12)==1
    assert press_scale([dict(kind='click',t=1,x=-.1,y=.5),dict(kind='click',t=1,x=.5,y=1.1)],1.12)==1


def test_press_and_ripple_render_independently_and_follow_event_edits():
    app=QApplication.instance() or QApplication([])
    frame=np.full((180,240,3),255,np.uint8)
    metadata=dict(cursor=[dict(t=0,x=.4,y=.3)],events=[dict(kind='click',t=1,x=.4,y=.3)])
    original=copy.deepcopy(metadata);opts=dict(cursor_size=60,cursor_color='#000000',cursor_outline='#000000')
    renders={(press,ripple):compose_frame(frame,1.12,metadata,dict(opts,click_press=press,clicks=ripple)) for press in (False,True) for ripple in (False,True)}
    assert all(a!=b for i,a in enumerate(renders.values()) for b in list(renders.values())[i+1:])
    assert compose_frame(frame,1.12,metadata,dict(opts,clicks=True))==renders[False,True]
    assert compose_frame(frame,1.12,metadata,dict(opts,click_press=True,clicks=False,event_edits={'0':{'hidden':True}}))==renders[False,False]
    assert compose_frame(frame,1.12,metadata,dict(opts,click_press=True,clicks=False,event_edits={'0':{'t':2}}))==renders[False,False]
    assert compose_frame(frame,2.12,metadata,dict(opts,click_press=True,clicks=False,event_edits={'0':{'t':2}}))==renders[True,False]
    assert compose_frame(frame,1.5,metadata,dict(opts,click_press=True,clicks=False))==renders[False,False]
    assert compose_frame(frame,1.12,metadata,dict(opts,cursor=False,click_press=True,clicks=True))==compose_frame(frame,1.12,metadata,dict(opts,cursor=False,clicks=True))
    assert metadata==original
