from omnishot.shortcuts import replace_section,MARKER,END,key_to_lua
from PySide6.QtGui import QKeySequence
import pytest


def test_binding_replacement_preserves_other_user_lines():
    original='-- Personal bindings\no.bind("SUPER + T", "Terminal", "foot")\n'+MARKER+'\nhl.unbind("PRINT")\no.bind("PRINT", "OmniShot capture", "omnishot menu")\n-- My additional customization\no.bind("SUPER + Y", "Other", "app")\n'
    block=MARKER+'\nhl.unbind("CTRL + PRINT")\no.bind("CTRL + PRINT", "OmniShot capture", "omnishot menu")\n'+END+'\n'
    updated=replace_section(original,block)
    assert '-- My additional customization\no.bind("SUPER + Y", "Other", "app")' in updated
    assert updated.count('o.bind("PRINT"')==0
    assert replace_section(updated,block)==updated
    assert updated.startswith('-- Personal bindings\no.bind("SUPER + T"')


def test_shortcut_mapping_requires_a_safe_combination():
    assert key_to_lua(QKeySequence("Meta+Shift+Print"))=="SUPER + SHIFT + PRINT"
    assert key_to_lua(QKeySequence("Ctrl+F8"))=="CTRL + F8"
    with pytest.raises(ValueError):key_to_lua(QKeySequence("A"))


def test_pin_shortcut_conflicts_are_rejected_before_global_bindings_change(tmp_path):
    from omnishot.annotation_shortcuts import validate_pin
    from omnishot.shortcuts import write_shortcuts
    from omnishot.backend import Store
    for key in ('Ctrl+P','S','Ctrl+Left','Ctrl+Shift+S','Ctrl+K, Ctrl+P'):
        with pytest.raises(ValueError):validate_pin(key,{})
    validate_pin('Ctrl+Alt+P',{});validate_pin('J',{});validate_pin('',{'menu':'Print'})
    store=Store(tmp_path/'data');store.settings['annotation_pin_shortcut']='Ctrl+Alt+P';store.save_settings();before=store.settings_path.read_bytes()
    with pytest.raises(ValueError,match='global OmniShot'):write_shortcuts({'menu':'Ctrl+Alt+P'},store)
    assert store.settings_path.read_bytes()==before and not (store.root/'config-backups').exists()
