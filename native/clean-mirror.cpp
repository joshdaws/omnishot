#include <hyprland/src/includes.hpp>
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/render/ElementRenderer.hpp>
#include <hyprland/src/render/pass/SurfacePassElement.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <stdexcept>
#include <charconv>
#include <lua.hpp>
#include <sys/syscall.h>
#include <unistd.h>
#include <poll.h>
#include <hyprland/src/pointer/PointerManager.hpp>
static HANDLE handle;
static CFunctionHook *surfaceHook, *opaqueHook, *copyHook, *textureHook, *cursorHook;
// A pidfd prevents accidental reuse of an exited application's PID. Only the
// registered application's recording control surfaces are removed from capture.
static pid_t owner = 0;
static int ownerFD = -1;
static pid_t selectorOwner = 0;
static int selectorFD = -1;
static pid_t cursorOwner = 0;
static int cursorFD = -1;
static bool alive(int descriptor) {
    if (descriptor < 0) return false;
    pollfd fd{descriptor, POLLIN, 0};
    return poll(&fd, 1, 0) == 0;
}
static bool active() { return alive(ownerFD) || alive(selectorFD) || alive(cursorFD); }
static bool own(CSurfacePassElement* element) {
    auto w=element->m_data.pWindow;
    if (!w || (w->m_class!="omnishot" && w->m_class!="org.omarchy.OmniShot")) return false;
    return (alive(ownerFD) && w->getPID()==owner && (w->m_title=="OmniShot Recording Controls" || w->m_title=="OmniShot Camera Preview" || w->m_title.starts_with("OmniShot Recording Dim ")))
        || (alive(selectorFD) && w->getPID()==selectorOwner && w->m_title.starts_with("OmniShot Selection — "));
}
static void draw(Render::IElementRenderer* renderer, WP<CSurfacePassElement> element, const CRegion& damage) {
    auto fb=g_pHyprRenderer->m_renderData.currentFB;
    bool exclude=element && own(element.get()) && fb && fb->getMirrorTexture();
    GLboolean mask[4]={GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE};
    if(exclude) { glGetBooleani_v(GL_COLOR_WRITEMASK,1,mask); glColorMaski(1,GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE); }
    reinterpret_cast<void(*)(Render::IElementRenderer*,WP<CSurfacePassElement>,const CRegion&)>(surfaceHook->m_original)(renderer,element,damage);
    if(exclude) glColorMaski(1,mask[0],mask[1],mask[2],mask[3]);
}
static CRegion opaque(CSurfacePassElement* element) {
    if(own(element)) return {};
    return reinterpret_cast<CRegion(*)(CSurfacePassElement*)>(opaqueHook->m_original)(element);
}
static void drawTexture(Render::IElementRenderer* renderer, WP<CTexPassElement> element, const CRegion& damage) {
    auto fb=g_pHyprRenderer->m_renderData.currentFB;
    bool cursor=active() && element && fb && fb->getMirrorTexture() && element->m_data.tex==Pointer::mgr()->getCurrentCursorTexture();
    GLboolean mask[4]={GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE};
    if(cursor) {glGetBooleani_v(GL_COLOR_WRITEMASK,1,mask);glColorMaski(1,GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);}
    reinterpret_cast<void(*)(Render::IElementRenderer*,WP<CTexPassElement>,const CRegion&)>(textureHook->m_original)(renderer,element,damage);
    if(cursor)glColorMaski(1,mask[0],mask[1],mask[2],mask[3]);
}
static void cursor(Pointer::CPointerManager* manager, PHLMONITOR monitor, const Time::steady_tp& now, CRegion& damage, std::optional<Vector2D> position, bool screencopy, bool force) {
    reinterpret_cast<void(*)(Pointer::CPointerManager*,PHLMONITOR,const Time::steady_tp&,CRegion&,std::optional<Vector2D>,bool,bool)>(cursorHook->m_original)(manager,monitor,now,damage,position,screencopy,force||(active() && screencopy));
}
static bool needsCopy(Monitor::CMonitor* monitor) {
    return active() || reinterpret_cast<bool(*)(Monitor::CMonitor*)>(copyHook->m_original)(monitor);
}
static SDispatchResult registration(std::string args, pid_t& registeredOwner = owner, int& registeredFD = ownerFD) {
    int pid = 0;
    auto result = std::from_chars(args.data(), args.data()+args.size(), pid);
    if (result.ec != std::errc{} || result.ptr != args.data()+args.size() || pid < 0)
        return {.success=false, .error="Expected an application PID, or 0 to disable"};
    if (pid && alive(registeredFD) && registeredOwner != pid)
        return {.success=false, .error="Another OmniShot recording is using clean capture"};
    int fd = pid ? syscall(SYS_pidfd_open, pid, 0) : -1;
    if (pid && fd < 0) return {.success=false, .error="Recording application is unavailable"};
    if (registeredFD >= 0) close(registeredFD);
    registeredFD = fd; registeredOwner = pid;
    return {};
}
static CFunctionHook* hook(const char* name,void* replacement) {
    std::string full=name; auto matches=HyprlandAPI::findFunctionsByName(handle,full.substr(full.rfind("::")+2,full.find("(")==std::string::npos?std::string::npos:full.find("(")-full.rfind("::")-2));
    std::erase_if(matches,[&](const auto& match){return !match.demangled.contains(full);});
    if(matches.size()!=1) throw std::runtime_error(std::string("Ambiguous hook: ")+name+" count="+std::to_string(matches.size()));
    auto result=HyprlandAPI::createFunctionHook(handle,matches[0].address,replacement);
    if(!result || !result->hook()) throw std::runtime_error(std::string("Could not hook ")+name);
    return result;
}
APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    if(std::string(__hyprland_api_get_hash())!=std::string(__hyprland_api_get_client_hash())) throw std::runtime_error("OmniShot compositor ABI mismatch");
    handle=h;
    surfaceHook=hook("IElementRenderer::preDrawSurface",reinterpret_cast<void*>(draw));
    opaqueHook=hook("CSurfacePassElement::opaqueRegion",reinterpret_cast<void*>(opaque));
    copyHook=hook("CMonitor::needsUnmodifiedCopy",reinterpret_cast<void*>(needsCopy));
    textureHook=hook("IElementRenderer::drawTex(",reinterpret_cast<void*>(drawTexture));
    cursorHook=hook("CPointerManager::renderSoftwareCursorsFor",reinterpret_cast<void*>(cursor));
    if (!HyprlandAPI::addLuaFunction(handle, "omnishot", "clean_capture", [](lua_State* L) -> int {
        auto result = registration(std::to_string(luaL_checkinteger(L, 1)));
        if (!result.success) return luaL_error(L, "%s", result.error.c_str());
        lua_pushboolean(L, true); return 1;
    }))
        throw std::runtime_error("Could not register OmniShot capture dispatcher");
    if (!HyprlandAPI::addLuaFunction(handle, "omnishot", "selection_capture", [](lua_State* L) -> int {
        auto result = registration(std::to_string(luaL_checkinteger(L, 1)), selectorOwner, selectorFD);
        if (!result.success) return luaL_error(L, "%s", result.error.c_str());
        lua_pushboolean(L, true); return 1;
    }) || !HyprlandAPI::addLuaFunction(handle, "omnishot", "cursor_capture", [](lua_State* L) -> int {
        auto result = registration(std::to_string(luaL_checkinteger(L, 1)), cursorOwner, cursorFD);
        if (!result.success) return luaL_error(L, "%s", result.error.c_str());
        lua_pushboolean(L, true); return 1;
    }) || !HyprlandAPI::addLuaFunction(handle, "omnishot", "capture_active", [](lua_State* L) -> int {
        lua_pushboolean(L, active()); return 1;
    })) throw std::runtime_error("Could not register OmniShot selection capture");
    return {"omnishot-clean-mirror","Clean recording, selection and scrolling capture","OmniShot","0.5.0"};
}

APICALL EXPORT void PLUGIN_EXIT() { if (ownerFD >= 0) close(ownerFD); ownerFD = -1; owner = 0; if (selectorFD >= 0) close(selectorFD); selectorFD = -1; selectorOwner = 0; if (cursorFD >= 0) close(cursorFD); cursorFD = -1; cursorOwner = 0; }
