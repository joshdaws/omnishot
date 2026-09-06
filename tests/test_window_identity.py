import pytest
from omnishot import backend


def setup_capture(monkeypatch,clients):
    calls=[]
    monkeypatch.setattr(backend,'capture_monitors',lambda:None)
    monkeypatch.setattr(backend,'hypr',lambda command:clients)
    def run(args,**kwargs):
        calls.append(args)
        return b'P7\nWIDTH 1\nHEIGHT 1\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n'+bytes([12,34,56,255])
    monkeypatch.setattr(backend,'run',run)
    return calls


def test_duplicate_titles_use_selected_address_and_allow_renaming(monkeypatch):
    first=dict(address='0x112345678',stableId='1',title='Same',**{'class':'same'})
    second=dict(first,address='0x212345679',stableId='2')
    calls=setup_capture(monkeypatch,[first,second])
    stale=dict(second,title='Old title')
    assert backend.grab_window(stale,True).tolist()==[[[12,34,56,255]]]
    assert calls[0][1:]==[0x12345679,1]


@pytest.mark.parametrize('clients',[
    [],
    [dict(address='0x212345678',stableId='2')],
    [dict(address='0x112345678',stableId='reused')],
    [dict(address='0x112345678',stableId='1'),dict(address='0x212345678',stableId='2')],
])
def test_closed_reused_and_colliding_handles_do_not_capture(monkeypatch,clients):
    calls=setup_capture(monkeypatch,clients)
    with pytest.raises(RuntimeError):backend.grab_window(dict(address='0x112345678',stableId='1'))
    assert not calls


@pytest.mark.parametrize('address',[None,'not an address','0x123;other',''])
def test_invalid_window_identity_never_invokes_helper(monkeypatch,address):
    calls=setup_capture(monkeypatch,[])
    with pytest.raises(RuntimeError):backend.grab_window(dict(address=address))
    assert not calls


def test_window_replaced_during_capture_is_not_returned(monkeypatch):
    client=dict(address='0x112345678',stableId='1');calls=setup_capture(monkeypatch,[client]);run=backend.run
    def replaced(*args,**kwargs):
        data=run(*args,**kwargs);client['stableId']='2';return data
    monkeypatch.setattr(backend,'run',replaced)
    with pytest.raises(RuntimeError,match='during capture'):backend.grab_window(dict(client))
    assert len(calls)==1
