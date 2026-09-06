/* Observe Wayland's definitive dnd_finished/cancelled events for our own drags.
 * Hyprland 0.56 can omit wl_data_source.action, leaving QDrag::exec() at Ignore
 * even after dnd_finished. No compositor, target application or event is changed.
 * Preload into OmniShot only; arm immediately around its QDrag::exec(). */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>

struct observer {
    struct wl_proxy *proxy;
    const struct wl_data_source_listener *original;
    void *data;
    unsigned long token;
    struct observer *next;
};
static struct observer *observers;
static unsigned long generation,finished;
static bool armed;
/* Qt's Wayland proxies and these entry points run on the GUI thread. */
unsigned long omnishot_drag_begin(void) { armed=true; return ++generation; }
int omnishot_drag_end(unsigned long token) {
    armed=false;
    for(struct observer **p=&observers;*p;) {
        if((*p)->token==token){struct observer *old=*p;*p=old->next;free(old);}else p=&(*p)->next;
    }
    return finished==token;
}
static struct observer *lookup(struct wl_data_source *source) {
    for (struct observer *o=observers;o;o=o->next) if (o->proxy==(struct wl_proxy*)source) return o;
    return NULL;
}
static void target(void *data,struct wl_data_source *s,const char *mime) {
    struct observer *o=lookup(s); if(o&&o->original->target)o->original->target(o->data,s,mime);
}
static void send_data(void *data,struct wl_data_source *s,const char *mime,int32_t fd) {
    struct observer *o=lookup(s); if(o&&o->original->send)o->original->send(o->data,s,mime,fd);
}
static void cancelled(void *data,struct wl_data_source *s) {
    struct observer *o=lookup(s); if(o&&o->original->cancelled)o->original->cancelled(o->data,s);
}
static void dropped(void *data,struct wl_data_source *s) {
    struct observer *o=lookup(s); if(o&&o->original->dnd_drop_performed)o->original->dnd_drop_performed(o->data,s);
}
static void complete(void *data,struct wl_data_source *s) {
    struct observer *o=lookup(s); if(!o)return; finished=o->token;
    if(o->original->dnd_finished)o->original->dnd_finished(o->data,s);
}
static void action(void *data,struct wl_data_source *s,uint32_t value) {
    struct observer *o=lookup(s); if(o&&o->original->action)o->original->action(o->data,s,value);
}
static const struct wl_data_source_listener listener={target,send_data,cancelled,dropped,complete,action};

int wl_proxy_add_listener(struct wl_proxy *proxy,void (**implementation)(void),void *data) {
    static int (*original)(struct wl_proxy*,void (**)(void),void*);
    if(!original)original=dlsym(RTLD_NEXT,"wl_proxy_add_listener");
    if(armed&&!strcmp(wl_proxy_get_class(proxy),"wl_data_source")&&wl_proxy_get_version(proxy)>=3) {
        struct observer *o=calloc(1,sizeof(*o));
        if(o) {
            o->proxy=proxy;o->original=(const struct wl_data_source_listener*)implementation;o->data=data;o->token=generation;
            int result=original(proxy,(void (**)(void))&listener,data);
            if(result==0){o->next=observers;observers=o;armed=false;}else free(o);
            return result;
        }
    }
    return original(proxy,implementation,data);
}
