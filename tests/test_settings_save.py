import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication
from omnishot.backend import Store
from omnishot.editor import Editor
from omnishot.images import load_image
from omnishot.widgets import Settings,QuickOverlay


def test_grouped_settings_cancel_and_typed_roundtrip(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data");before=dict(store.settings)
    dialog=Settings(store,"quickaccess");assert dialog.sections.currentItem().text()=="Quick Access"
    dialog.fields["ask_save_destination"].setChecked(True);dialog.reject();assert store.settings==before
    dialog=Settings(store,"recording");dialog.fields["fps"].setCurrentIndex(dialog.fields["fps"].findData(60))
    dialog.fields["quality"].setCurrentIndex(dialog.fields["quality"].findData("very_high"))
    dialog.fields["output_dir"].setText(str(tmp_path/"saved"));dialog.fields["ask_save_destination"].setChecked(True);dialog.save()
    reopened=Store(tmp_path/"data")
    assert reopened.settings["fps"]==60 and reopened.settings["quality"]=="very_high"
    assert reopened.settings["ask_save_destination"] and reopened.settings["output_dir"]==str(tmp_path/"saved")


def test_action_matrix_preserves_legacy_choices_and_allows_none(tmp_path):
    from omnishot.backend import capture_actions
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data")
    store.settings.update(after_capture="copy",after_capture_extra=["save","overlay"],after_recording="edit")
    dialog=Settings(store)
    assert {k for k,v in dialog.action_boxes["capture"].items() if v.isChecked()}=={"copy","save","overlay"}
    for box in dialog.action_boxes["capture"].values():box.setChecked(False)
    for box in dialog.action_boxes["recording"].values():box.setChecked(True)
    dialog.save();restored=Store(tmp_path/"data")
    assert capture_actions(restored.settings)==set()
    assert capture_actions(restored.settings,True)=={"edit","overlay","copy","save"}
    assert not Settings(restored).action_boxes["capture"]["overlay"].isChecked()


def test_auto_save_failure_and_cancelled_drop_preserve_capture(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data")
    path=store.add(image=np.full((80,120,3),255,np.uint8));overlay=QuickOverlay(path,store)
    monkeypatch.setattr("omnishot.widgets.place_window",lambda *args:None)
    monkeypatch.setattr("omnishot.widgets.error",lambda *args:None)
    overlay.show();overlay.drag_started();overlay.drag_finished(False,False);assert overlay.isVisible()
    overlay.drag_finished(True,True);assert overlay.isVisible()
    store.settings["overlay_auto_action"]="save"
    monkeypatch.setattr(overlay,"export_to",lambda:(_ for _ in ()).throw(OSError("disk full")))
    overlay.auto_close();assert overlay.isVisible() and path.exists()
    overlay.drag_finished(True,False);assert not overlay.isVisible() and path.exists()


def test_quick_save_exports_current_edits_without_overwriting(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data");store.settings["output_dir"]=str(tmp_path/"saved")
    path=store.add(image=np.full((80,120,3),255,np.uint8));store.rename(path,"Overview")
    editor=Editor(path,store);editor.rotate();editor.close()
    first=QuickOverlay(path,store);first.save();output=tmp_path/"saved/Overview.png"
    assert output.exists() and load_image(output).width()==80 and load_image(output).height()==120
    original=output.read_bytes();second=QuickOverlay(path,store);second.save()
    assert output.read_bytes()==original and (tmp_path/"saved/Overview (2).png").exists()
