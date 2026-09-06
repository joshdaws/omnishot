import pytest
from PySide6.QtCore import QPointF
from omnishot.annotation_resize import resize_rect


@pytest.mark.parametrize('edge',['lt','t','rt','r','rb','b','lb','l'])
@pytest.mark.parametrize('point',[QPointF(-40,-30),QPointF(180,120),QPointF(30,20),QPointF(120,80)])
def test_proportional_handles_preserve_ratio_and_opposite_anchor(edge,point):
    r=resize_rect(120,80,edge,point,True)
    assert r.width()>=8 and r.height()>=8 and r.width()/r.height()==pytest.approx(1.5)
    if 'l' in edge:assert 120==pytest.approx(r.right() if point.x()<=120 else r.left())
    if 'r' in edge:assert 0==pytest.approx(r.left() if point.x()>=0 else r.right())
    if 't' in edge:assert 80==pytest.approx(r.bottom() if point.y()<=80 else r.top())
    if 'b' in edge:assert 0==pytest.approx(r.top() if point.y()>=0 else r.bottom())
    if edge in ('t','b'):assert r.center().x()==pytest.approx(60)
    if edge in ('l','r'):assert r.center().y()==pytest.approx(40)


def test_shift_vertical_edge_changes_size_instead_of_translating():
    assert resize_rect(120,80,'t',QPointF(60,-40),True).getRect()==(-30,-40,180,120)
    assert resize_rect(120,80,'b',QPointF(60,120),True).getRect()==(-30,0,180,120)
    assert resize_rect(120,80,'t',QPointF(60,-40)).getRect()==(0,-40,120,120)
