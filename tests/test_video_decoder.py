from omnishot import video_decoder

VARIABLE='QT_FFMPEG_DECODING_HW_DEVICE_TYPES'


def gpu(monkeypatch,tmp_path,vendor):
    # Asahi's platform GPU exposes no PCI vendor file at all.
    devices=[]
    if vendor:
        device=tmp_path/'vendor';device.write_text(vendor+'\n');devices.append(device)
    class Devices:
        def __init__(self,*args):pass
        def glob(self,*args):return devices
    monkeypatch.setattr(video_decoder,'Path',Devices)


def test_software_decoding_is_the_default_on_every_gpu(monkeypatch,tmp_path):
    monkeypatch.setattr(video_decoder,'EXPLICIT',None)
    for vendor in ('0x8086','0x1002',None):
        gpu(monkeypatch,tmp_path,vendor);monkeypatch.delenv(VARIABLE,raising=False)
        video_decoder.configure_preview_decoder({});assert video_decoder.os.environ[VARIABLE]==','


def test_setting_enables_hardware_decoding_except_on_intel(monkeypatch,tmp_path):
    monkeypatch.setattr(video_decoder,'EXPLICIT',None);enabled={'hardware_video_decoding':True}
    for vendor in ('0x1002',None):
        gpu(monkeypatch,tmp_path,vendor);monkeypatch.setenv(VARIABLE,',')
        assert video_decoder.hardware_decoding_supported()
        video_decoder.configure_preview_decoder(enabled);assert VARIABLE not in video_decoder.os.environ
    gpu(monkeypatch,tmp_path,'0x8086');assert not video_decoder.hardware_decoding_supported()
    video_decoder.configure_preview_decoder(enabled);assert video_decoder.os.environ[VARIABLE]==','


def test_value_set_before_startup_stays_authoritative(monkeypatch,tmp_path):
    gpu(monkeypatch,tmp_path,None);monkeypatch.setattr(video_decoder,'EXPLICIT','vaapi');monkeypatch.setenv(VARIABLE,'vaapi')
    video_decoder.configure_preview_decoder({});assert video_decoder.os.environ[VARIABLE]=='vaapi'
    monkeypatch.setattr(video_decoder,'EXPLICIT','');monkeypatch.delenv(VARIABLE)
    video_decoder.configure_preview_decoder({'hardware_video_decoding':True});assert VARIABLE not in video_decoder.os.environ
