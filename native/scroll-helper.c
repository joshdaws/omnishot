/* Small, unprivileged Wayland scroll injector. Protocol copyright in adjacent XML. */
#include <wayland-client.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "virtual-pointer.h"
static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data, struct wl_registry *r, uint32_t id, const char *name, uint32_t v) {
    (void)data;
    if (!strcmp(name,"zwlr_virtual_pointer_manager_v1"))
        manager=wl_registry_bind(r,id,&zwlr_virtual_pointer_manager_v1_interface,v<2?v:2);
}
static void removed(void *d, struct wl_registry *r, uint32_t id) {(void)d;(void)r;(void)id;}
int main(int argc,char **argv) {
    if(argc!=3) {fputs("usage: scroll-helper vertical|horizontal steps\n",stderr);return 2;}
    int click=!strcmp(argv[1],"click");
    if(!click && strcmp(argv[1],"horizontal") && strcmp(argv[1],"vertical")) return 2;
    int axis=!strcmp(argv[1],"horizontal")?1:0;
    char *end; long steps=strtol(argv[2],&end,10);
    if(*end || (click ? (steps<272 || steps>274) : (!steps || steps>20 || steps< -20))) return 2;
    struct wl_display *d=wl_display_connect(NULL);
    if(!d) {fputs("No Wayland display\n",stderr);return 1;}
    struct wl_registry *r=wl_display_get_registry(d);
    const struct wl_registry_listener listener={global,removed};
    wl_registry_add_listener(r,&listener,NULL);wl_display_roundtrip(d);
    if(!manager) {fputs("Compositor does not support virtual pointer scrolling\n",stderr);return 1;}
    struct zwlr_virtual_pointer_v1 *p=zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager,NULL);
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
    uint32_t ms=(uint32_t)(t.tv_sec*1000+t.tv_nsec/1000000);
    if(click) {
        zwlr_virtual_pointer_v1_button(p,ms,(uint32_t)steps,WL_POINTER_BUTTON_STATE_PRESSED);
        zwlr_virtual_pointer_v1_frame(p);wl_display_roundtrip(d);
        zwlr_virtual_pointer_v1_button(p,ms+1,(uint32_t)steps,WL_POINTER_BUTTON_STATE_RELEASED);
    } else {
        zwlr_virtual_pointer_v1_axis_source(p,WL_POINTER_AXIS_SOURCE_WHEEL);
        zwlr_virtual_pointer_v1_axis_discrete(p,ms,axis,wl_fixed_from_int(15*(int)steps),(int)steps);
    }
    zwlr_virtual_pointer_v1_frame(p);wl_display_roundtrip(d);
    zwlr_virtual_pointer_v1_destroy(p);
    zwlr_virtual_pointer_manager_v1_destroy(manager);wl_registry_destroy(r);
    wl_display_flush(d);wl_display_disconnect(d);return 0;
}
