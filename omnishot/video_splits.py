"""Source-frame clip boundaries, independent of playback navigation."""
import math


def clean_splits(values):
    if not isinstance(values,list):return []
    return sorted({float(v) for v in values if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<v<86400})


def clips(start,end,cuts,splits):
    from .studio import kept_segments
    result=[]
    for a,b in kept_segments(start,end,cuts):
        edges=[a]+[s for s in splits if a<s<b]+[b]
        result.extend(zip(edges,edges[1:]))
    return result


def trim_clip(start,end,cuts,splits,bounds,edge,value,fps):
    """Resize one retained source interval without consuming a neighboring clip.

    Use the cuts at gesture start, so reversing a drag restores every frame.
    Split boundaries delimit the source material belonging to a clip. A gap
    inside that region can be restored up to the next retained interval.
    """
    a,b=bounds;frame=1/fps
    neighbors=clips(start,end,cuts,splits)
    lo=max([start]+[s for s in splits if s<=a]+[y for x,y in neighbors if y<=a])
    hi=min([end]+[s for s in splits if s>=b]+[x for x,y in neighbors if x>=b])
    value=round(value*fps)/fps
    if edge=='start':new_a=max(lo,min(b-frame,value));new_b=b
    else:new_a=a;new_b=min(hi,max(a+frame,value))
    if abs(new_a-a)<1e-9 and abs(new_b-b)<1e-9:return [list(c) for c in cuts],(a,b)
    # Union an excluded part, or subtract a restored part, from baseline cuts.
    removed=(a,new_a) if edge=='start' else (new_b,b)
    restored=(new_a,a) if edge=='start' else (b,new_b)
    result=[]
    for x,y in cuts:
        u,v=restored
        if v<=u or y<=u or x>=v:result.append([x,y])
        else:
            if x<u:result.append([x,u])
            if y>v:result.append([v,y])
    if removed[1]>removed[0]:result.append(list(removed))
    merged=[]
    for x,y in sorted(result):
        if merged and x<=merged[-1][1]+1e-9:merged[-1][1]=max(y,merged[-1][1])
        else:merged.append([x,y])
    return merged,(new_a,new_b)
