import cv2
import numpy as np
import pytest
from omnishot.stitch import ScrollStitcher, match_translation


def page(h=3200,w=600):
    rng = np.random.default_rng(12)
    a = np.full((h,w,3),245,np.uint8)
    for y in range(0,h,37):
        cv2.putText(a,f"Row {y:04d}: unique text {rng.integers(100000)}",(20,y+25),
                    cv2.FONT_HERSHEY_SIMPLEX,.6,(30,40,55),1,cv2.LINE_AA)
        cv2.rectangle(a,(w-80,y+3),(w-30,y+30),tuple(int(x) for x in rng.integers(50,220,3)),-1)
    return a


def test_exact_vertical_forward_reverse():
    source = page()
    stitch = ScrollStitcher()
    for y in [0,180,360,180,360,540,720,900,1000]: stitch.push(source[y:y+600])
    assert np.array_equal(stitch.output,source[:1600])


def test_horizontal():
    source = page().transpose(1,0,2).copy()
    stitch = ScrollStitcher(horizontal=True)
    for x in [0,180,360,540]: stitch.push(source[:,x:x+600])
    assert np.array_equal(stitch.output,source[:,:1140])


def test_duplicates_do_not_grow():
    source=page()[:600]
    stitch=ScrollStitcher()
    stitch.push(source)
    for _ in range(10): assert not stitch.push(source)[0]
    assert np.array_equal(stitch.output,source)


def test_unrelated_frame_rejected():
    stitch=ScrollStitcher()
    stitch.push(page()[:600])
    noise=np.random.default_rng(44).integers(0,255,(600,600,3),dtype=np.uint8)
    assert not stitch.push(noise)[0]
    assert stitch.output.shape==(600,600,3)


def test_sticky_header_and_footer():
    source=page()
    stitch=ScrollStitcher()
    for y in [0,170,340,510]:
        frame=source[y:y+600].copy()
        frame[:45]=[80,70,110]
        frame[-30:]=[130,150,170]
        stitch.push(frame)
    assert stitch.output.shape[0]==1110
    assert np.array_equal(stitch.output[45:-30],source[45:1080])


@pytest.mark.parametrize('horizontal',[False,True])
def test_reverse_past_start_keeps_only_one_fixed_leading_edge(horizontal):
    source=page();stitch=ScrollStitcher(horizontal=horizontal)
    for position in [510,340,510,340,340,170,0]:
        frame=source[position:position+600].copy()
        frame[:45]=[80,70,110];frame[-30:]=[130,150,170]
        stitch.push(frame.transpose(1,0,2) if horizontal else frame)
    expected=source[:1110].copy();expected[:45]=[80,70,110];expected[-30:]=[130,150,170]
    if horizontal:expected=expected.transpose(1,0,2)
    assert np.array_equal(stitch.output,expected)


def test_limits_and_resize():
    stitch=ScrollStitcher(max_pixels=600*700)
    source=page()
    stitch.push(source[:600])
    with pytest.raises(ValueError): stitch.push(source[200:800])
    with pytest.raises(ValueError): stitch.push(source[:500])


def test_repeated_browser_rows_choose_real_overlap():
    from PIL import Image
    from pathlib import Path
    fixtures=Path(__file__).parent/"fixtures"
    before=np.array(Image.open(fixtures/"browser-overlap-before.png").convert("RGB"))
    after=np.array(Image.open(fixtures/"browser-overlap-after.png").convert("RGB"))
    # At 1.45 browser scale, 500 CSS pixels are 725 image pixels. The old
    # majority vote selected -29 and silently omitted four complete rows.
    assert match_translation(before,after).shift==725
    stitch=ScrollStitcher();stitch.push(before);assert stitch.push(after)[0]
    assert stitch.output.shape[:2]==(2323,1000)


def test_large_native_jump_with_repeated_rows_is_rejected_without_changing_state():
    from PIL import Image
    from pathlib import Path
    fixtures=Path(__file__).parent/'fixtures'
    before=np.array(Image.open(fixtures/'scroll-jump-before.png').convert('RGB'))
    after=np.array(Image.open(fixtures/'scroll-jump-after.png').convert('RGB'))
    # The native page moved up 480 logical pixels (768 captured pixels).
    # Repeated row labels previously matched a +192-pixel downward movement.
    stitch=ScrollStitcher();stitch.push(before)
    changed,message=stitch.push(after)
    assert not changed and 'Could not align' in message
    assert stitch.position==0 and stitch.origin==0 and stitch.accepted==1
    assert np.array_equal(stitch.output,before) and np.array_equal(stitch.previous,before)


@pytest.mark.parametrize('change',['brightness','noise'])
def test_valid_motion_with_minor_frame_changes_is_still_accepted(change):
    source=page();before=source[:600];after=source[170:770].copy()
    if change=='brightness':after=np.clip(after.astype(int)+12,0,255).astype(np.uint8)
    else:after=np.clip(after.astype(int)+np.random.default_rng(4).normal(0,5,after.shape),0,255).astype(np.uint8)
    stitch=ScrollStitcher();stitch.push(before)
    assert stitch.push(after)[0] and stitch.position==170
    assert np.array_equal(stitch.output[:600],before) and np.array_equal(stitch.output[600:],after[-170:])
