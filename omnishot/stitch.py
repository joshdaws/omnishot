"""Conservative overlap stitching. Reject uncertain matches rather than lose rows."""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class Match:
    shift: int
    confidence: float
    error: float


def match_translation(previous: np.ndarray, current: np.ndarray) -> Match:
    """Find vertical displacement using several independent textured strip anchors.

    Inputs are RGB. Static sidebars and scrollbar edges are excluded from anchors.
    Positive displacement means forward/down. Match consensus prevents a single
    animated area or repeated line from deciding the entire stitch.
    """
    if previous.shape != current.shape:
        raise ValueError("Capture dimensions changed; start a new scrolling capture.")
    h, w = previous.shape[:2]
    if h < 32 or w < 24:
        raise ValueError("Select an area at least 24 × 32 pixels.")
    old = cv2.cvtColor(previous, cv2.COLOR_RGB2GRAY)
    new = cv2.cvtColor(current, cv2.COLOR_RGB2GRAY)
    # Preserve vertical resolution, reduce wide desktop captures to bounded work.
    tw = min(w, 320)
    old = cv2.resize(old, (tw, h), interpolation=cv2.INTER_AREA)
    new = cv2.resize(new, (tw, h), interpolation=cv2.INTER_AREA)
    if np.mean(np.abs(old.astype(float) - new)) < 0.7:
        return Match(0, 1.0, 0.0)
    border = max(3, tw // 12)
    sh = min(56, max(16, h // 10))
    candidates = []
    for anchor_index,f in enumerate((0.12, 0.27, 0.43, 0.60, 0.76, 0.87)):
        y = min(h-sh, int(h*f))
        anchor = new[y:y+sh, border:tw-border]
        if float(anchor.std()) < 4:
            continue
        scores = cv2.matchTemplate(old[:, border:tw-border], anchor, cv2.TM_CCOEFF_NORMED).ravel()
        # Keep several peaks: repeated rows may beat the correct match by a
        # fraction, and newly revealed content must not outvote actual overlap.
        for _ in range(4):
            location=int(np.argmax(scores));score=float(scores[location]);shift=location-y
            if score<.83:break
            if abs(shift)<h-max(sh,h//8):candidates.append((shift,score,anchor_index))
            scores[max(0,location-4):location+5]=-1
    if not candidates:
        return Match(0, 0.0, 255.0)
    same=np.mean(np.abs(old.astype(float)-new),axis=1)<1.2
    top=bottom=0
    for value in same:
        if not value or top>=h//5:break
        top+=1
    for value in same[::-1]:
        if not value or bottom>=h//5:break
        bottom+=1
    evaluated=[]
    for shift in sorted(set(c[0] for c in candidates)):
        group=[c for c in candidates if abs(c[0]-shift)<=1]
        if len({c[2] for c in group})<2:continue
        # Compare textured pixels throughout the real overlap. Median row error
        # treats blank rows as proof and can silently skip repeated paragraphs.
        lo=max(top,top-shift);hi=min(h-bottom,h-bottom-shift)
        if hi-lo<max(48,h//8):continue
        a=old[lo+shift:hi+shift,border:-border].astype(np.float32)
        b=new[lo:hi,border:-border].astype(np.float32)
        detail_a=np.abs(a-cv2.GaussianBlur(a,(5,5),0))
        detail_b=np.abs(b-cv2.GaussianBlur(b,(5,5),0))
        mask=(detail_a>5)|(detail_b>5)
        if np.count_nonzero(mask)<30:continue
        differences=np.abs(a-b)
        error=float(np.mean(differences[mask]))
        confidence=float(np.mean([max(c[1] for c in group if c[2]==idx) for idx in {c[2] for c in group}]))
        evaluated.append(Match(shift,confidence,error))
    if not evaluated:return Match(0,0.0,255.0)
    evaluated.sort(key=lambda match:(match.error,-match.confidence))
    best=evaluated[0]
    # Fully indistinguishable repeated patterns cannot establish a safe shift.
    alternate=next((m for m in evaluated[1:] if abs(m.shift-best.shift)>2),None)
    if alternate and abs(alternate.error-best.error)<.08 and alternate.confidence>.95:
        return Match(best.shift,0.0,best.error)
    return best



class ScrollStitcher:
    def __init__(self, horizontal=False, max_pixels=120_000_000):
        self.horizontal = horizontal
        self.max_pixels = max_pixels
        self.previous = None
        self.image = None
        self.position = 0
        self.origin = 0
        self.accepted = 0

    def push(self, frame: np.ndarray) -> tuple[bool, str]:
        frame = np.ascontiguousarray(frame.transpose(1,0,2) if self.horizontal else frame)
        if self.previous is None:
            if frame.shape[0]*frame.shape[1]>self.max_pixels:raise ValueError("Capture exceeds the 120 megapixel limit.")
            self.image = frame.copy()
            self.previous = frame.copy()
            self.accepted = 1
            return True, "Ready — scroll slowly inside the selected area."
        match = match_translation(self.previous, frame)
        # Repeated labels can correlate well while disagreeing on the unique
        # digits in every row. Accept residual image changes only when the
        # independent template anchors agree very strongly on the movement.
        if match.confidence < .83 or match.error > 16 or (match.error > 4 and match.confidence < .97):
            return False, "Could not align. Scroll back slightly or slow down."
        if abs(match.shift) <= 1:
            return False, "No new content."
        new_position = self.position + match.shift
        bottom = new_position + len(frame)
        image_bottom = self.origin + len(self.image)
        extra_bottom = max(0, bottom-image_bottom)
        extra_top = max(0, self.origin-new_position)
        new_h = len(self.image)+extra_bottom+extra_top
        if new_h*frame.shape[1] > self.max_pixels:
            raise ValueError("Capture reached the 120 megapixel limit. Finish this capture.")
        if extra_bottom or extra_top:
            same = np.mean(np.abs(self.previous.astype(float)-frame), axis=(1,2)) < 1.2
        if extra_bottom:
            # Detect stationary footer rows and replace them before appending.
            footer = 0
            for v in same[::-1]:
                if not v or footer >= len(frame)//5: break
                footer += 1
            cut = min(footer, len(self.image)-1, len(frame)-extra_bottom)
            if cut:
                self.image = np.concatenate((self.image[:-cut], frame[-(extra_bottom+cut):]))
            else:
                self.image = np.concatenate((self.image, frame[-extra_bottom:]))
        if extra_top:
            # Scrolling above the initial viewport must replace its stationary
            # header too; otherwise that header becomes a seam inside the page.
            header = 0
            for value in same:
                if not value or header >= len(frame)//5:break
                header += 1
            cut = min(header, len(self.image)-1, len(frame)-extra_top)
            self.image = np.concatenate((frame[:extra_top+cut], self.image[cut:]))
            self.origin = new_position
        self.position = new_position
        self.previous = frame.copy()
        self.accepted += 1
        return bool(extra_top or extra_bottom), f"{self.output.shape[1]} × {self.output.shape[0]} pixels · {self.accepted} frames"

    @property
    def output(self):
        if self.image is None: return None
        return np.ascontiguousarray(self.image.transpose(1,0,2) if self.horizontal else self.image)
