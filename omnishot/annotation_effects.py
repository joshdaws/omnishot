"""Stable annotation effects; secure blur never samples the concealed interior."""
import math
import numpy as np
from PIL import Image,ImageFilter
from PySide6.QtCore import Qt,QRect
from PySide6.QtGui import QImage,QPainter,QRegion,QTransform


def rgba(image):
    image=image.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4).copy()


def as_image(array):
    array=np.ascontiguousarray(array,dtype=np.uint8)
    return QImage(array.data,array.shape[1],array.shape[0],array.strides[0],QImage.Format.Format_RGBA8888).copy()


def secure_texture(boundary,width,height,strength,seed):
    """Accept only outside samples, never the original region being hidden.

    The opaque replacement uses a surrounding color and independent, smooth
    noise. Identical surroundings and seed give identical output regardless of
    the contents behind the mask. Editable projects still retain their source.
    """
    pixels=boundary.reshape(-1,4).astype(np.float32);alpha=pixels[:,3:4]/255
    weight=float(alpha.sum())
    color=(pixels[:,:3]*alpha).sum(axis=0)/weight if weight else np.array([216,220,228],np.float32)
    rng=np.random.default_rng(int(seed));spacing=max(8,int(strength)*2)
    noise=rng.normal(0,16,(max(2,math.ceil(height/spacing)),max(2,math.ceil(width/spacing)))).clip(-36,36)
    # Resize a tiny independent texture; no information from the masked image
    # enters this interpolation or the subsequent blur.
    texture=Image.fromarray((noise+128).astype(np.uint8)).resize((width,height),Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(max(2,strength/3)))
    values=np.asarray(texture,dtype=np.float32)-128
    result=np.empty((height,width,4),np.uint8);result[:,:,:3]=np.clip(color+values[:,:,None],0,255);result[:,:,3]=255
    return as_image(result)


def render_effect(base,transform,props):
    width=max(1,math.ceil(props.get('w',100)));height=max(1,math.ceil(props.get('h',40)))
    kind=props['kind'];strength=max(2,int(props.get('strength',18)));seed=props.get('effect_seed',0)
    secure=kind=='blur' and props.get('blur_mode','Smooth')=='Secure'
    pad=8 if secure else 0
    raw=QImage(width+pad*2,height+pad*2,QImage.Format.Format_ARGB32_Premultiplied);raw.fill(Qt.GlobalColor.transparent)
    painter=QPainter(raw)
    if secure:
        # The unpainted guard band also excludes fractional edge sampling.
        interior=QRect(pad-3,pad-3,width+6,height+6)
        painter.setClipRegion(QRegion(raw.rect()).subtracted(QRegion(interior)))
    inverse,valid=transform.inverted()
    if valid:
        placement=inverse*QTransform.fromTranslate(pad,pad)
        painter.setWorldTransform(placement);painter.drawImage(0,0,base)
    painter.end()
    if secure:
        sampled=rgba(raw)
        boundary=np.concatenate((sampled[:pad-3].reshape(-1,4),sampled[-(pad-3):].reshape(-1,4),sampled[pad-3:-(pad-3),:pad-3].reshape(-1,4),sampled[pad-3:-(pad-3),-(pad-3):].reshape(-1,4)))
        return secure_texture(boundary,width,height,strength,seed)
    if kind=='pixelate':
        factor=max(5,strength);small=raw.scaled(max(1,width//factor),max(1,height//factor))
        if props.get('pixelate_mode','Classic')=='Randomized':
            values=rgba(small);rng=np.random.default_rng(int(seed));flat=values.reshape(-1,4).copy()
            # Random placement and color perturbation are stable for this object,
            # preventing flicker or a different pattern on export/reopening.
            rng.shuffle(flat);flat[:,:3]=np.clip(flat[:,:3].astype(float)+rng.normal(0,12,(len(flat),3)),0,255)
            small=as_image(flat.reshape(values.shape))
        return small.scaled(width,height)
    return as_image(np.asarray(Image.fromarray(rgba(raw)).filter(ImageFilter.GaussianBlur(strength))))
