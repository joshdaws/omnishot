"""Offline OCR with local language packs and script detection."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request

LANGUAGES={"eng":"English","spa":"Spanish","fra":"French","deu":"German","ita":"Italian","por":"Portuguese","nld":"Dutch","dan":"Danish","swe":"Swedish","nor":"Norwegian","fin":"Finnish","isl":"Icelandic","pol":"Polish","ces":"Czech","slk":"Slovak","hun":"Hungarian","ron":"Romanian","tur":"Turkish","vie":"Vietnamese","ind":"Indonesian","msa":"Malay","cat":"Catalan","hrv":"Croatian","slv":"Slovenian","ell":"Greek","rus":"Russian","ukr":"Ukrainian","bul":"Bulgarian","ara":"Arabic","heb":"Hebrew","hin":"Hindi","chi_sim":"Chinese (simplified)","chi_tra":"Chinese (traditional)","jpn":"Japanese","kor":"Korean","tha":"Thai"}
SCRIPTS={"Latin":"Latin","Cyrillic":"Cyrillic","Greek":"Greek","Arabic":"Arabic","Hebrew":"Hebrew","Devanagari":"Devanagari","Han":"HanS","Japanese":"Japanese","Hangul":"Hangul","Thai":"Thai"}
MODEL_VERSION="4.1.0"


def model_dir():
    return Path(os.environ.get("XDG_DATA_HOME",Path.home()/".local/share"))/"omnishot"/"tessdata"


def install_models(progress=None):
    root=model_dir();root.mkdir(parents=True,exist_ok=True)
    names=list(LANGUAGES)+["osd"]+["script/"+s for s in SCRIPTS.values()]
    def fetch(name):
        path=root/(name+".traineddata");path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists() or path.stat().st_size==32_000_000:
            url=f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{MODEL_VERSION}/{name}.traineddata"
            with urllib.request.urlopen(url,timeout=60) as response:
                data=response.read(200_000_001)
                expected=int(response.headers.get("Content-Length",len(data)))
            if len(data)>200_000_000 or len(data)!=expected:raise RuntimeError(f"Incomplete language model download: {name}")
            if len(data)<1000:raise RuntimeError(f"Invalid language model: {name}")
            temp=path.with_suffix(".download");temp.write_bytes(data);temp.replace(path)
        return name,hashlib.sha256(path.read_bytes()).hexdigest()
    hashes={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for name,digest in pool.map(fetch,names):
            hashes[name]=digest
            if progress:progress(len(hashes),len(names))
    (root/"manifest.json").write_text(json.dumps({"source":"tesseract-ocr/tessdata_fast","version":MODEL_VERSION,"sha256":hashes},indent=2))
    return len(LANGUAGES)


def recognize(path,languages="auto",linebreaks=True):
    from .backend import run
    root=model_dir();local=(root/"eng.traineddata").exists();extra=["--tessdata-dir",str(root)] if local else []
    if languages=="auto":
        script="Latin"
        try:
            report=run(["tesseract",str(path),"stdout",*extra,"-l","osd","--psm","0"],timeout=20).decode()
            match=re.search(r"^Script:\s*(\S+)",report,re.MULTILINE)
            if match:script=match.group(1)
        except RuntimeError:pass # Short selections often have too few characters for OSD.
        model="script/"+SCRIPTS.get(script,"Latin")
        languages=model if local and (root/(model+".traineddata")).exists() else "eng"
    elif not re.fullmatch(r"[A-Za-z_]+(?:\+[A-Za-z_]+)*",languages):
        raise ValueError("Choose Auto or language codes such as eng+spa")
    value=run(["tesseract",str(path),"stdout",*extra,"-l",languages,"--psm","3"],timeout=90).decode().strip()
    if not value:
        value=run(["tesseract",str(path),"stdout",*extra,"-l",languages,"--psm","11"],timeout=90).decode().strip()
    return value if linebreaks else " ".join(value.split())


if __name__=="__main__":
    print(f"Installed {install_models()} OCR languages for offline use.")
