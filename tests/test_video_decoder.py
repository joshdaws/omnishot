from omnishot import video_decoder


def test_intel_preview_policy_preserves_explicit_override_and_other_vendors(monkeypatch,tmp_path):
    device=tmp_path/'vendor';device.write_text('0x8086\n')
    class Devices:
        def __init__(self,*args):pass
        def glob(self,*args):return [device]
    monkeypatch.setattr(video_decoder,'Path',Devices)
    monkeypatch.delenv('QT_FFMPEG_DECODING_HW_DEVICE_TYPES',raising=False)
    video_decoder.configure_preview_decoder();assert video_decoder.os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES']==','
    monkeypatch.setenv('QT_FFMPEG_DECODING_HW_DEVICE_TYPES','vaapi');video_decoder.configure_preview_decoder();assert video_decoder.os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES']=='vaapi'
    monkeypatch.delenv('QT_FFMPEG_DECODING_HW_DEVICE_TYPES');device.write_text('0x1002\n');video_decoder.configure_preview_decoder();assert 'QT_FFMPEG_DECODING_HW_DEVICE_TYPES' not in video_decoder.os.environ
