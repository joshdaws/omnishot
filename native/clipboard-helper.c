/* Own PNG, editable annotations and file offers after the GUI caller exits.
 * File-only mode never reads the media payload into memory. */
#define _POSIX_C_SOURCE 200809L
#include <wayland-client.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "data-control.h"

static struct zwlr_data_control_manager_v1 *manager;
static struct wl_seat *seat;
static bool stopped;
static unsigned char *png;
static size_t png_size;
static unsigned char *annotations;
static size_t annotations_size;
static const char *annotation_mime="application/x-omnishot-annotations+json";
static char *uri,*gnome;
static void global(void *data,struct wl_registry *r,uint32_t id,const char *name,uint32_t version) {
    (void)data;
    if(!strcmp(name,"zwlr_data_control_manager_v1"))manager=wl_registry_bind(r,id,&zwlr_data_control_manager_v1_interface,version<2?version:2);
    else if(!strcmp(name,"wl_seat")&&!seat)seat=wl_registry_bind(r,id,&wl_seat_interface,1);
}
static void removed(void *data,struct wl_registry *r,uint32_t id){(void)data;(void)r;(void)id;}
static void send_data(void *data,struct zwlr_data_control_source_v1 *source,const char *mime,int32_t fd) {
    (void)data;(void)source;
    const void *bytes=NULL;size_t length=0;
    if(!strcmp(mime,"image/png")){bytes=png;length=png_size;}
    else if(!strcmp(mime,annotation_mime)){bytes=annotations;length=annotations_size;}
    else if(!strcmp(mime,"text/uri-list")){bytes=uri;length=strlen(uri);}
    else if(!strcmp(mime,"x-special/gnome-copied-files")){bytes=gnome;length=strlen(gnome);}
    else if(!strcmp(mime,"application/x-kde-cutselection")){bytes="0";length=1;}
    int flags=fcntl(fd,F_GETFL);if(flags>=0)fcntl(fd,F_SETFL,flags|O_NONBLOCK);
    while(length) {
        struct pollfd p={fd,POLLOUT,0};int result=poll(&p,1,5000);
        if(result<0&&errno==EINTR)continue;
        if(result<=0||!(p.revents&POLLOUT))break;
        ssize_t n=write(fd,bytes,length);
        if(n<0&&(errno==EINTR||errno==EAGAIN))continue;
        if(n<=0)break;
        bytes=(const unsigned char*)bytes+n;length-=n;
    }
    close(fd);
}
static void cancelled(void *data,struct zwlr_data_control_source_v1 *source){(void)data;(void)source;stopped=true;}
static void mime_offered(void *data,struct zwlr_data_control_offer_v1 *offer,const char *mime){(void)data;(void)offer;(void)mime;}
static void offer(void *data,struct zwlr_data_control_device_v1 *device,struct zwlr_data_control_offer_v1 *offer) {
    (void)data;(void)device;static const struct zwlr_data_control_offer_v1_listener listener={mime_offered};zwlr_data_control_offer_v1_add_listener(offer,&listener,NULL);
}
static void selection(void *data,struct zwlr_data_control_device_v1 *device,struct zwlr_data_control_offer_v1 *offer){(void)data;(void)device;if(offer)zwlr_data_control_offer_v1_destroy(offer);}
static void finished(void *data,struct zwlr_data_control_device_v1 *device){(void)data;(void)device;stopped=true;}

static bool read_file(const char *path,unsigned char **bytes,size_t *length,size_t limit) {
    FILE *file=fopen(path,"rb");if(!file)return false;
    struct stat st;
    if(fstat(fileno(file),&st)||!S_ISREG(st.st_mode)||st.st_size<=0||(uintmax_t)st.st_size>limit){fclose(file);return false;}
    *length=(size_t)st.st_size;*bytes=malloc(*length);
    bool ok=*bytes&&fread(*bytes,1,*length,file)==*length;
    fclose(file);return ok;
}

int main(int argc,char **argv) {
    if(argc!=4|| (strcmp(argv[1],"both")&&strcmp(argv[1],"file")&&strcmp(argv[1],"image")&&strcmp(argv[1],"annotations")))return 2;
    signal(SIGPIPE,SIG_IGN);
    bool editable=!strcmp(argv[1],"annotations");
    if(strcmp(argv[1],"file")) {
        if(!read_file(argv[2],&png,&png_size,512L*1024*1024))return 3;
    } else {
        struct stat st;if(stat(argv[2],&st)||!S_ISREG(st.st_mode)||st.st_size<=0)return 3;
    }
    if(editable&&!read_file(argv[3],&annotations,&annotations_size,64L*1000*1000))return 3;
    size_t size=strlen(argv[3])+16;uri=malloc(size);gnome=malloc(size);if(!uri||!gnome)return 3;
    snprintf(uri,size,"%s\r\n",argv[3]);snprintf(gnome,size,"copy\n%s",argv[3]);
    struct wl_display *display=wl_display_connect(NULL);if(!display)return 4;
    struct wl_registry *registry=wl_display_get_registry(display);const struct wl_registry_listener globals={global,removed};
    wl_registry_add_listener(registry,&globals,NULL);
    if(wl_display_roundtrip(display)<0||!manager||!seat){fprintf(stderr,"Clipboard data-control protocol is unavailable\n");return 4;}
    struct zwlr_data_control_source_v1 *source=zwlr_data_control_manager_v1_create_data_source(manager);
    const struct zwlr_data_control_source_v1_listener sources={send_data,cancelled};zwlr_data_control_source_v1_add_listener(source,&sources,NULL);
    if(strcmp(argv[1],"file"))zwlr_data_control_source_v1_offer(source,"image/png");
    if(editable)zwlr_data_control_source_v1_offer(source,annotation_mime);
    if(strcmp(argv[1],"image")&&!editable) {
        zwlr_data_control_source_v1_offer(source,"text/uri-list");zwlr_data_control_source_v1_offer(source,"x-special/gnome-copied-files");zwlr_data_control_source_v1_offer(source,"application/x-kde-cutselection");
    }
    struct zwlr_data_control_device_v1 *device=zwlr_data_control_manager_v1_get_data_device(manager,seat);
    const struct zwlr_data_control_device_v1_listener devices={offer,selection,finished,selection};zwlr_data_control_device_v1_add_listener(device,&devices,NULL);
    zwlr_data_control_device_v1_set_selection(device,source);
    if(wl_display_roundtrip(display)<0)return 4;
    pid_t child=fork();if(child<0)return 5;if(child>0)return 0;
    setsid();int null=open("/dev/null",O_RDWR);if(null>=0){dup2(null,0);dup2(null,1);dup2(null,2);if(null>2)close(null);}
    while(!stopped&&wl_display_dispatch(display)>=0){}
    wl_display_disconnect(display);free(png);free(annotations);free(uri);free(gnome);return 0;
}
