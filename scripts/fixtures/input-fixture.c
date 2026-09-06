#define _GNU_SOURCE
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "virtual-keyboard.h"
#include "virtual-pointer.h"
static struct zwp_virtual_keyboard_manager_v1 *keys;static struct zwlr_virtual_pointer_manager_v1 *pointers;static struct wl_seat *seat;
static uint32_t milliseconds(void){struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);return (uint32_t)((uint64_t)now.tv_sec*1000+now.tv_nsec/1000000);}
static void global(void*d,struct wl_registry*r,uint32_t id,const char*n,uint32_t v){if(!strcmp(n,"zwp_virtual_keyboard_manager_v1"))keys=wl_registry_bind(r,id,&zwp_virtual_keyboard_manager_v1_interface,1);if(!strcmp(n,"zwlr_virtual_pointer_manager_v1"))pointers=wl_registry_bind(r,id,&zwlr_virtual_pointer_manager_v1_interface,1);if(!strcmp(n,"wl_seat"))seat=wl_registry_bind(r,id,&wl_seat_interface,1);}
static void removed(void*d,struct wl_registry*r,uint32_t id){}
int main(){struct wl_display*d=wl_display_connect(NULL);if(!d)return 1;struct wl_registry*r=wl_display_get_registry(d);struct wl_registry_listener l={global,removed};wl_registry_add_listener(r,&l,NULL);wl_display_roundtrip(d);if(!keys||!pointers||!seat)return 2;
struct xkb_context*c=xkb_context_new(0);struct xkb_rule_names names={.layout="us"};struct xkb_keymap*k=xkb_keymap_new_from_names(c,&names,0);char*s=xkb_keymap_get_as_string(k,XKB_KEYMAP_FORMAT_TEXT_V1);size_t len=strlen(s)+1;int fd=memfd_create("omnishot-test-keymap",MFD_CLOEXEC);ftruncate(fd,len);write(fd,s,len);
struct zwp_virtual_keyboard_v1*v=zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(keys,seat);zwp_virtual_keyboard_v1_keymap(v,WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1,fd,len);struct zwlr_virtual_pointer_v1*p=zwlr_virtual_pointer_manager_v1_create_virtual_pointer(pointers,seat);wl_display_roundtrip(d);puts("ready");fflush(stdout);
char line[128],cmd[32];int a,b;
while(fgets(line,sizeof(line),stdin)){a=b=0;if(sscanf(line,"%31s %d %d",cmd,&a,&b)<1)continue;
if(!strcmp(cmd,"key")){if(b)zwp_virtual_keyboard_v1_key(v,milliseconds(),29,1);zwp_virtual_keyboard_v1_modifiers(v,b,0,0,0);zwp_virtual_keyboard_v1_key(v,milliseconds(),a,1);zwp_virtual_keyboard_v1_key(v,milliseconds(),a,0);if(b)zwp_virtual_keyboard_v1_key(v,milliseconds(),29,0);zwp_virtual_keyboard_v1_modifiers(v,0,0,0,0);}
else if(!strcmp(cmd,"click")){zwlr_virtual_pointer_v1_button(p,milliseconds(),a,WL_POINTER_BUTTON_STATE_PRESSED);zwlr_virtual_pointer_v1_frame(p);zwlr_virtual_pointer_v1_button(p,milliseconds(),a,WL_POINTER_BUTTON_STATE_RELEASED);zwlr_virtual_pointer_v1_frame(p);}
else if(!strcmp(cmd,"button")){zwlr_virtual_pointer_v1_button(p,milliseconds(),a,b?WL_POINTER_BUTTON_STATE_PRESSED:WL_POINTER_BUTTON_STATE_RELEASED);zwlr_virtual_pointer_v1_frame(p);}
else if(!strcmp(cmd,"mods")){zwp_virtual_keyboard_v1_modifiers(v,a,0,0,0);}
else if(!strcmp(cmd,"key-state")){zwp_virtual_keyboard_v1_key(v,milliseconds(),a,b?WL_KEYBOARD_KEY_STATE_PRESSED:WL_KEYBOARD_KEY_STATE_RELEASED);}
else if(!strcmp(cmd,"move")){zwlr_virtual_pointer_v1_motion(p,milliseconds(),wl_fixed_from_int(a),wl_fixed_from_int(b));zwlr_virtual_pointer_v1_frame(p);}
wl_display_roundtrip(d);}
zwp_virtual_keyboard_v1_destroy(v);zwlr_virtual_pointer_v1_destroy(p);wl_display_flush(d);wl_display_disconnect(d);close(fd);free(s);xkb_keymap_unref(k);xkb_context_unref(c);return 0;}
