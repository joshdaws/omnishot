import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtCore import Qt,QRectF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot.studio import compose_frame
from omnishot.video_position import PositionGrid,POSITIONS,camera_rect


def bounds(image):
    pixels=np.asarray(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3)
    y,x=np.where((pixels[:,:,0]>200)&(pixels[:,:,1]<30)&(pixels[:,:,2]<30))
    return np.array([x.min(),y.min(),x.max()+1,y.max()+1])


def test_camera_positions_shrink_and_bounds():
    app=QApplication.instance() or QApplication([])
    source=np.zeros((360,640,3),np.uint8);camera=np.zeros((90,160,3),np.uint8);camera[:,:,0]=255
    opts=dict(camera=True,camera_size=.25,camera_shape='Square',camera_shadow=False,camera_radius=0,keys=False,cursor=False,clicks=False)
    for i,name in enumerate(POSITIONS):
        result=bounds(compose_frame(source,0,{},dict(opts,camera_position=name),camera));row,col=divmod(i,3)
        x=[20,240,460][col];y=[20,100,180][row]
        assert np.max(np.abs(result-[x,y,x+160,y+160]))<=1,(name,result)
    zooms=[dict(start=1,end=3,scale=2,x=.5,y=.5)]
    opts.update(camera_shrink=True,zooms=zooms,camera_position='Bottom Right')
    widths=[]
    for time in (0,1,1.175,2,2.825,3,4):
        box=bounds(compose_frame(source,time,{},opts,camera));widths.append(box[2]-box[0]);assert abs(box[2]-620)<=1 and abs(box[3]-340)<=1
    assert widths[0]==widths[1]==widths[-1]==160 and abs(widths[3]-136)<=1
    assert widths[3]<widths[2]<widths[0] and abs(widths[2]-widths[4])<=1
    assert bounds(compose_frame(source,2,{},dict(opts,camera_shrink=False),camera))[0]==460
    fullscreen=compose_frame(source,2,{},dict(opts,camera_fullscreen=True),camera);assert np.array_equal(bounds(fullscreen),[0,0,640,360])
    for width,height,aspect in [(20,10,3),(640,100,.7),(100,640,3)]:
        for position in POSITIONS:
            r=camera_rect(width,height,aspect,dict(camera_size=.8,camera_shape='Rectangle',camera_position=position),2)
            assert r.width()>0 and r.height()>0 and QRectF(0,0,width,height).contains(r),(width,height,position,r)


def test_position_grid_keyboard_and_programmatic_restore():
    app=QApplication.instance() or QApplication([]);grid=PositionGrid();grid.show();app.processEvents()
    assert grid.currentText()=='Bottom Right';seen=[];grid.currentTextChanged.connect(seen.append)
    QTest.keyClick(grid.buttons[8],Qt.Key.Key_Up);assert grid.currentText()=='Center Right'
    QTest.keyClick(grid.buttons[5],Qt.Key.Key_Left);assert grid.currentText()=='Center'
    grid.setCurrentText('Top Center');assert grid.buttons[1].isChecked() and sum(b.isChecked() for b in grid.buttons)==1
    grid.setCurrentText('invalid');assert grid.currentText()=='Top Center' and seen==['Center Right','Center','Top Center'];grid.close()
