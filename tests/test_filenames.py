from datetime import datetime,timezone
import numpy as np
from omnishot.backend import Store
from omnishot.filenames import format_name


def test_filename_tokens_utc_and_literal_percent():
    stamp=datetime(2026,9,5,14,7,9,tzinfo=timezone.utc).timestamp()
    result=format_name("%y-%m-%d %H.%M.%S %p %t %a %r %i %%",created=stamp,utc=True,context={"title":"Notes","app":"Editor"},sequence=42,random_token="abcdef")
    assert result=="2026-09-05 14.07.09 PM Notes Editor abcdef 42 %"


def test_filename_cannot_escape_folder_and_limits_unicode_bytes():
    result=format_name("../%t",context={"title":"../../秘密:<>?*"*100})
    assert "/" not in result and ":" not in result and len(result.encode())<=230
    assert format_name("..") == "OmniShot"
    assert format_name("Part: 1?",remove_illegal=False)=="Part: 1?"


def test_sequence_persists_without_changing_history_identity(tmp_path):
    store=Store(tmp_path/"data");store.settings["filename_format"]="Demo %i"
    first=store.add(image=np.zeros((20,30,3),np.uint8));store.name_capture(first)
    store=Store(tmp_path/"data");second=store.add(image=np.zeros((20,30,3),np.uint8));store.name_capture(second)
    assert store.display_name(first)=="Demo 1.png" and store.display_name(second)=="Demo 2.png"
    assert first.exists() and second.exists() and first!=second
    store.settings["filename_format"]="Literal %%i";store.name_capture(second)
    assert store.settings["filename_counter"]==2 and store.display_name(second)=="Literal %i.png"


def test_scale_suffix_follows_capture_density_and_scaling(tmp_path):
    store=Store(tmp_path/'data');store.settings['filename_format']='Capture'
    for ratio,suffix in [(1,''),(1.6,'@1.6x'),(2,'@2x')]:
        path=store.add(image=np.zeros((20,30,3),np.uint8))
        metadata=store.metadata(path);metadata['pixel_ratio']=ratio;store.atomic_json(path.with_suffix('.json'),metadata)
        store.name_capture(path)
        assert store.display_name(path)==f'Capture{suffix}.png'
        store.set_pixel_ratio(path,1)
        assert store.display_name(path)=='Capture.png'
    store.rename(path,'My manual @2x');store.set_pixel_ratio(path,1)
    assert store.display_name(path)=='My manual @2x.png'
    store.settings['filename_scale_suffix']=False
    store.set_pixel_ratio(path,2);store.name_capture(path)
    assert store.display_name(path)=='Capture.png'
    store.save_settings();assert Store(store.root).settings['filename_scale_suffix'] is False
