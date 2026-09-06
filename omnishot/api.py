"""Local URL commands compatible with CleanShot's non-cloud capture actions."""
from urllib.parse import urlparse,parse_qs
ALIASES={"all-in-one":"select","capture-area":"area","capture-fullscreen":"fullscreen","capture-window":"window","capture-previous-area":"previous","scrolling-capture":"scroll","open-annotate":"open","open-from-clipboard":"clipboard","capture-text":"ocr","open-history":"history","restore-recently-closed":"restore","open-settings":"settings","record-screen":"record","self-timer":"timer","add-quick-access-overlay":"overlay"}


def parse_url(value):
    url=urlparse(value)
    if url.scheme not in ("omnishot","cleanshot"):raise ValueError("Unsupported URL scheme")
    query=parse_qs(url.query);args={"command":ALIASES.get(url.netloc,url.netloc),"via_url":True}
    for source,target in [("filepath","path"),("action","action"),("tab","tab")]:
        if source in query:args[target]=query[source][0]
    if args.get("action") not in (None,"overlay","copy","save","annotate","pin"):raise ValueError("Unsupported after-capture action; cloud uploads are excluded")
    for field in ("start","autoscroll","linebreaks"):
        if field in query:
            value=query[field][0].lower()
            if value not in ("true","false"):raise ValueError(f"{field} must be true or false")
            args[field]=value=="true"
    coordinates={}
    for field in ("x","y","width","height","display"):
        if field in query:
            number=int(query[field][0])
            if abs(number)>1_000_000:raise ValueError("Capture coordinates are out of range")
            coordinates[field]=number
    if coordinates:args["url_coordinates"]=coordinates
    return args


def url_geometry(coordinates,monitors,cursor):
    from .clean_capture import monitor_bounds
    index=coordinates.get("display")
    if index is not None:
        if not 1<=index<=len(monitors):raise ValueError("That display is not connected")
        monitor=monitors[index-1]
    else:
        def contains(m):
            x,y,w,h=monitor_bounds(m)
            return x<=cursor["x"]<x+w and y<=cursor["y"]<y+h
        monitor=next((m for m in monitors if contains(m)),monitors[0])
    _,_,mw,mh=monitor_bounds(monitor)
    width,height=coordinates.get("width",min(640,mw)),coordinates.get("height",min(400,mh))
    x,y=coordinates.get("x",0),coordinates.get("y",0)
    if width<2 or height<2 or x<0 or y<0 or x+width>mw or y+height>mh:raise ValueError("The requested area is outside the display")
    # Public URL coordinates use a lower-left origin; native CLI geometry uses
    # Hyprland's upper-left origin, in logical pixels.
    return monitor["x"]+x,monitor["y"]+mh-y-height,width,height
