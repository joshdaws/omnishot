import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import base64
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from omnishot.editor import png_bytes,qimage
from omnishot.studio import compose_frame,edited_events,zoom_at
from omnishot.video_styles import EffectsDialog,InputEventsModel


def test_recording_background_camera_and_cursor_styles():
    app=QApplication.instance() or QApplication([])
    frame=np.full((240,320,3),240,np.uint8);background=np.full((40,40,3),(50,100,200),np.uint8)
    opts={"padding":30,"background":"#000000","background_image_data":base64.b64encode(png_bytes(qimage(background))).decode(),"cursor_style":"Dot","cursor_color":"#ff0000","cursor_size":28,"keys":False,"clicks":False,"camera_shadow":False}
    metadata={"cursor":[{"t":0,"x":.5,"y":.5}],"events":[]}
    rendered=compose_frame(frame,0,metadata,opts)
    assert rendered.pixelColor(0,0).getRgb()[:3]==(50,100,200)
    assert rendered.pixelColor(190,150).name()=="#ff0000"
    camera=np.zeros((240,320,3),np.uint8);camera[:,:160]=[255,0,0];camera[:,160:]=[0,0,255]
    normal=compose_frame(frame,0,{}, {**opts,"camera_fullscreen":True,"camera_shape":"Rectangle"},camera)
    mirrored=compose_frame(frame,0,{}, {**opts,"camera_fullscreen":True,"camera_shape":"Rectangle","camera_mirror":True},camera)
    assert normal.pixelColor(50,150).name()=="#ff0000" and mirrored.pixelColor(50,150).name()=="#0000ff"


def test_input_event_edits_preserve_original_and_change_rendering():
    app=QApplication.instance() or QApplication([])
    events=[{"kind":"click","t":.2,"x":.5,"y":.5},{"kind":"key","t":.3,"state":1,"label":"Ctrl+C"}]
    model=InputEventsModel(events,{},3);assert model.setData(model.index(0,0),Qt.CheckState.Unchecked.value,Qt.ItemDataRole.CheckStateRole)
    assert model.setData(model.index(1,1),1.2) and model.setData(model.index(1,3),"Ctrl+V")
    assert not model.setData(model.index(1,1),-1)
    edited=edited_events({"events":events},{"event_edits":model.edits});assert edited[0]["hidden"] and edited[1]["label"]=="Ctrl+V" and edited[1]["t"]==1.2
    assert events[1]["label"]=="Ctrl+C" and "hidden" not in events[0]
    frame=np.full((240,320,3),240,np.uint8)
    hidden=compose_frame(frame,.35,{"events":events},{"event_edits":model.edits})
    plain=compose_frame(frame,.35,{},{});visible=compose_frame(frame,.35,{"events":events},{})
    assert hidden==plain and visible!=plain
    zoom={"start":0,"end":3,"scale":2,"x":.3,"y":.3,"follow":True}
    assert zoom_at([zoom],1,{"x":.7,"y":.6})==(2,.7,.6)


def test_effect_controls_return_portable_options():
    app=QApplication.instance() or QApplication([]);dialog=EffectsDialog({"background_image_data":"kept"})
    dialog.fields["cursor_style"].setCurrentText("Crosshair");dialog.fields["click_duration"].setValue(.9);dialog.fields["key_position"].setCurrentText("Top Left");dialog.fields["camera_mirror"].setChecked(True)
    result=dialog.options();assert result["cursor_style"]=="Crosshair" and result["click_duration"]==.9 and result["key_position"]=="Top Left" and result["camera_mirror"] and result["background_image_data"]=="kept"
    dialog.close()
