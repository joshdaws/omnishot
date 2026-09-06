from pathlib import Path
import pytest
from omnishot import backend


def test_invalid_recordings_do_not_enter_history_or_change_source(tmp_path):
    store=backend.Store(tmp_path/'data')
    for extension in ('.mp4','.mov','.webm','.mkv'):
        source=tmp_path/('broken'+extension);source.write_bytes(b'not video data')
        with pytest.raises(ValueError,match='Could not open recording'):store.import_file(source)
        assert source.read_bytes()==b'not video data' and not store.history()
        assert not list(store.captures.iterdir())


def test_audio_only_rejected_and_valid_video_import_preserved(tmp_path):
    store=backend.Store(tmp_path/'data');audio=tmp_path/'audio.mp4';video=tmp_path/'video.mp4'
    backend.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440','-t','0.2','-c:a','aac',audio])
    with pytest.raises(ValueError,match='no video track'):store.import_file(audio)
    assert not store.history()
    backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=10','-t','0.2','-c:v','libx264','-threads','1',video])
    path=store.import_file(video);assert path.read_bytes()==video.read_bytes() and len(store.history())==1
    assert store.import_file(video)==path and len(store.history())==1
