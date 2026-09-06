"""Verify independent Wayland clipboard consumers and durable file snapshots."""
import io
import json
from pathlib import Path
import sys
from urllib.parse import unquote,urlparse
import numpy as np
from PIL import Image
from omnishot import backend

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);store=backend.Store(out/"data")
source=store.add(image=np.full((60,100,3),(15,130,220),np.uint8))
try:
    backend.copy_image(source,store,name="Clipboard example.png")
    types=backend.run(["wl-paste","--list-types"]).decode().splitlines()
    assert "image/png" in types and "text/uri-list" in types and "x-special/gnome-copied-files" in types,types
    uri=backend.run(["wl-paste","--type","text/uri-list","--no-newline"]).decode().strip()
    snapshot=Path(unquote(urlparse(uri).path));assert snapshot.name=="Clipboard example.png" and snapshot.exists()
    gnome=backend.run(["wl-paste","--type","x-special/gnome-copied-files","--no-newline"]).decode();assert gnome=="copy\n"+uri
    store.remove(source)
    image=Image.open(io.BytesIO(backend.run(["wl-paste","--type","image/png","--no-newline"])))
    assert image.size==(100,60) and image.getpixel((50,30))==(15,130,220) and snapshot.exists()
    store.settings["clipboard_mode"]="file";backend.copy_image(snapshot,store,name="File-only.png")
    types=backend.run(["wl-paste","--list-types"]).decode().splitlines();assert "text/uri-list" in types and "image/png" not in types
    store.settings["clipboard_mode"]="image";backend.copy_image(snapshot,store)
    types=backend.run(["wl-paste","--list-types"]).decode().splitlines();assert "image/png" in types and "text/uri-list" not in types
    Image.open(io.BytesIO(backend.run(["wl-paste","--type","image/png","--no-newline"]))).save(out/"clipboard.png")
    report=dict(file_and_image=True,file_only=True,image_only=True,snapshot_survives_history_deletion=True,gnome_file_copy_representation=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:backend.run(["wl-copy","--clear"])
