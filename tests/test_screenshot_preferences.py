import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.app import Controller
from omnishot.editor import Editor


def test_fractional_scaling_preserves_alpha_and_draws_one_output_pixel_border():
    source=np.full((96,160,4),(20,140,220,120),np.uint8)
    output,ratio=backend.prepare_screenshot(source,1.6,dict(scale_screenshots=True,screenshot_border=True))
    assert output.shape==(60,100,4) and ratio==1
    assert np.all(output[0]==(0,0,0,255)) and np.all(output[-1]==(0,0,0,255))
    assert np.all(output[:,0]==(0,0,0,255)) and np.all(output[:,-1]==(0,0,0,255))
    assert output[1,1,3]==120 and output[30,50,3]==120
    assert np.all(source==(20,140,220,120))
    unchanged,ratio=backend.prepare_screenshot(source,1.6,{})
    assert unchanged is source and ratio==1.6


def test_skip_background_survives_first_annotation_and_history_reopen(tmp_path):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/"data")
    store.settings.update(background_preset="Ocean",scale_screenshots=True)
    controller=Controller.__new__(Controller);controller.store=store;controller.restore_capture_windows=lambda:None
    paths=[];controller.overlay=paths.append
    controller.finished_capture(np.full((96,160,3),200,np.uint8),pixel_ratio=1.6,skip_background=True)
    path=paths[0];assert Image.open(path).size==(100,60)
    assert store.metadata(path)["pixel_ratio"]==1 and store.metadata(path)["original_pixel_ratio"]==1.6
    first=Editor(path,store);assert first.background is None and first.render().size()==first.base.size();first.close()
    reopened=Editor(path,store);assert reopened.background is None and reopened.base.width()==100;reopened.close()


def test_window_shadow_padding_scales_with_capture(tmp_path):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/"data");store.settings["scale_screenshots"]=True
    controller=Controller.__new__(Controller);controller.store=store;controller.restore_capture_windows=lambda:None
    paths=[];controller.overlay=paths.append
    background=dict(color="#00000000",color2="#00000000",padding=48,radius=16,shadow=True,aspect="Auto",align="Center")
    controller.finished_capture(np.full((120,200,4),255,np.uint8),pixel_ratio=2,capture_background=background)
    editor=Editor(paths[0],store);assert editor.base.width()==100 and editor.background["padding"]==24 and editor.background["radius"]==8
    assert background["padding"]==48;editor.close()
