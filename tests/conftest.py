"""Shared fixtures for tests that stub compositor calls."""
import os

import pytest

# Decode test clips in software. Hardware decoders need large contiguous
# buffers (Apple AVD asks for 4 MB blocks); under memory pressure those
# allocations fail repeatedly and a full run can stall the desktop. Set before
# any test imports QtMultimedia, which reads this once.
os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES'] = ','


@pytest.fixture
def native_capture_files(tmp_path, monkeypatch):
    # Lifecycle tests mock backend.run; their file checks should not depend on
    # an installed compositor SDK or binaries from a developer's working tree.
    from omnishot import clean_capture
    directory = tmp_path / 'native'
    directory.mkdir()
    for name in ('clean-mirror.so', 'clean-capture.so'):
        (directory / name).write_bytes(b'unit-test placeholder; never loaded')
    monkeypatch.setattr(clean_capture, 'NATIVE', directory)
    return directory


@pytest.fixture
def no_compositor(monkeypatch):
    from omnishot import backend
    monkeypatch.setattr(backend, 'hypr', lambda query: [])
