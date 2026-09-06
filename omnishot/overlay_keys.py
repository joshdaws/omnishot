"""Temporary hover shortcuts without stealing focus from the active app."""
import json
import os
import uuid
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication
from . import backend

ACTIONS = {"CTRL + C":"copy", "CTRL + S":"save", "CTRL + W":"close",
           "CTRL + E":"annotate", "CTRL + P":"pin", "SPACE":"preview", "ESCAPE":"close"}


def available_actions(bindings, actions=ACTIONS):
    # Hyprland 0.56's handle.remove() removes every binding with the same
    # modifiers and key, including other submaps. Never install over one.
    occupied={(b.get("modmask",0),b.get("key","").casefold()) for b in bindings}
    return {key:action for key,action in actions.items()
            if (4 if key.startswith("CTRL + ") else 0,key.split(" + ")[-1].casefold()) not in occupied}


class OverlayKeys(QObject):
    activated = Signal(str)
    actions=ACTIONS
    namespace="overlay"
    require_hover=True
    description="OmniShot hovered preview"

    def target_title(self):return self.parent().windowTitle()

    def lua(self,code):
        return code.replace("omnishot_overlay_",f"omnishot_{self.namespace}_")

    def __init__(self, parent):
        super().__init__(parent);self.token=uuid.uuid4().hex;self.active=False;self.error=None
        self.timer=QTimer(self);self.timer.setInterval(60);self.timer.timeout.connect(self.poll)

    def start(self):
        if self.active or QApplication.platformName()!="wayland":return
        try:
            backend.run(["hyprctl","eval",self.lua("if omnishot_overlay_keys then omnishot_overlay_keys.stop() end")],timeout=2)
            actions=available_actions(backend.hypr("binds"),self.actions)
        except Exception as exc:self.error=str(exc);return
        if not actions:return
        title=json.dumps(self.target_title())
        script='''
if omnishot_overlay_keys then omnishot_overlay_keys.stop() end
local s={bindings={},queue={},lease=os.time(),token="TOKEN"}
omnishot_overlay_keys=s
function s.stop()
  for _,b in ipairs(s.bindings) do b:remove() end
  s.bindings={}
  if omnishot_overlay_watch then omnishot_overlay_watch:set_enabled(false) end
  if omnishot_overlay_keys==s then omnishot_overlay_keys=nil end
end
function s.hovered()
  local p=hl.get_cursor_pos()
  for _,w in ipairs(hl.get_windows({mapped=true,title=TITLE})) do
    if w.pid==PID and w.visible then
      local a,z=w.at,w.size
      if not REQUIRE_HOVER or (p.x>=a.x and p.y>=a.y and p.x<a.x+z.x and p.y<a.y+z.y) then return true end
    end
  end
  return false
end
function s.action(action)
  for _,b in ipairs(s.bindings) do b:set_enabled(false) end
  if not s.hovered() then s.expired=true;return {pass_event=true} end
  if #s.queue==0 then table.insert(s.queue,action) end
end
'''.replace("TOKEN",self.token).replace("TITLE",title).replace("PID",str(os.getpid())).replace("REQUIRE_HOVER","true" if self.require_hover else "false")
        for key,action in actions.items():
            script+=f'table.insert(s.bindings,hl.bind("{key}",function() return s.action("{action}") end,{{description="{self.description}: {action}"}}))\n'
        script+='''if not omnishot_overlay_watch then
  omnishot_overlay_watch=hl.timer(function()
    local current=omnishot_overlay_keys
    if current then
      if current.expired or os.time()-current.lease>2 or not current.hovered() then current.stop() end
    else omnishot_overlay_watch:set_enabled(false) end
  end,{timeout=100,type="repeat"})
else omnishot_overlay_watch:set_enabled(true) end
'''
        try:backend.run(["hyprctl","eval",self.lua(script)],timeout=2)
        except Exception as exc:
            self.error=str(exc);self.active=True;self.stop();return
        self.active=True;self.timer.start()

    def stop(self):
        self.timer.stop()
        if not self.active:return
        self.active=False
        try:backend.run(["hyprctl","eval",self.lua(f'if omnishot_overlay_keys and omnishot_overlay_keys.token=="{self.token}" then omnishot_overlay_keys.stop() end')],timeout=2)
        except Exception:pass

    def should_rearm(self):
        from shiboken6 import isValid
        parent=self.parent()
        return bool(parent and isValid(parent) and parent.isVisible()
                    and (not self.require_hover or parent.underMouse())
                    and not any(getattr(parent,key,False) for key in ('collapsed','dragging','copying','quicklook')))

    def poll(self):
        try:
            reply=backend.run(["hyprctl","repl",self.lua(f'local s=omnishot_overlay_keys; if not s then return "inactive" end; if s.token~="{self.token}" then return "replaced" end; s.lease=os.time(); return s.queue[1] or ""')],timeout=1).decode().strip()
        except Exception:self.stop();return
        if reply in ('inactive','replaced'):
            self.active=False;self.timer.stop()
            # Hyprland reloads Lua after plugin load/unload and theme changes.
            # Recover a lost lease, but never replace a newer window's lease.
            if reply=='inactive' and self.should_rearm():self.start()
        elif reply in self.actions.values():self.stop();self.activated.emit(reply)


class ScrollKeys(OverlayKeys):
    """Capture-scoped keys, including while a foreign app has keyboard focus."""
    actions={"ESCAPE":"cancel","RETURN":"accept"}
    namespace="scroll"
    require_hover=False
    description="OmniShot scrolling capture"

    def target_title(self):return self.parent().visuals.guides[0].windowTitle()

    def should_rearm(self):
        parent=self.parent()
        return not parent.closed and any(guide.isVisible() for guide in parent.visuals.guides)
