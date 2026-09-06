"""Shared fixtures for tests that stub compositor calls."""
import pytest


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
