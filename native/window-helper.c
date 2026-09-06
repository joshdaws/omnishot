/* Capture an isolated Hyprland toplevel into a PAM RGBA stream.
 * Protocol notices are retained in the adjacent XML files. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include "toplevel-export.h"
#include "foreign-toplevel.h"
static struct wl_shm *shm;
static struct hyprland_toplevel_export_manager_v1 *exporter;
static struct zwlr_foreign_toplevel_manager_v1 *foreign;
struct top { struct zwlr_foreign_toplevel_handle_v1 *handle; char *title,*app; int closed; struct top *next; };
static struct top *tops;
static int done,failed;
static uint32_t width,height,stride,format,flags;
static void *pixels;
static struct wl_buffer *buffer;
static void title(void *d,struct zwlr_foreign_toplevel_handle_v1 *h,const char *s) {(void)h;struct top *t=d;free(t->title);t->title=strdup(s);}
static void appid(void *d,struct zwlr_foreign_toplevel_handle_v1 *h,const char *s) {(void)h;struct top *t=d;free(t->app);t->app=strdup(s);}
static void output(void *d,struct zwlr_foreign_toplevel_handle_v1 *h,struct wl_output *o) {(void)d;(void)h;(void)o;}
static void state(void *d,struct zwlr_foreign_toplevel_handle_v1 *h,struct wl_array *a) {(void)d;(void)h;(void)a;}
static void topdone(void *d,struct zwlr_foreign_toplevel_handle_v1 *h) {(void)d;(void)h;}
static void closed(void *d,struct zwlr_foreign_toplevel_handle_v1 *h) {(void)h;((struct top*)d)->closed=1;}
static void parent(void *d,struct zwlr_foreign_toplevel_handle_v1 *h,struct zwlr_foreign_toplevel_handle_v1 *p) {(void)d;(void)h;(void)p;}
static const struct zwlr_foreign_toplevel_handle_v1_listener top_listener={title,appid,output,output,state,topdone,closed,parent};
static void toplevel(void *d,struct zwlr_foreign_toplevel_manager_v1 *m,struct zwlr_foreign_toplevel_handle_v1 *h) {
 (void)d;(void)m;struct top *t=calloc(1,sizeof(*t));t->handle=h;t->next=tops;tops=t;zwlr_foreign_toplevel_handle_v1_add_listener(h,&top_listener,t);
}
static void finished(void *d,struct zwlr_foreign_toplevel_manager_v1 *m) {(void)d;(void)m;}
static const struct zwlr_foreign_toplevel_manager_v1_listener manager_listener={toplevel,finished};
static void global(void *d,struct wl_registry *r,uint32_t id,const char *name,uint32_t v) {
 (void)d;
 if(!strcmp(name,"wl_shm"))shm=wl_registry_bind(r,id,&wl_shm_interface,1);
 if(!strcmp(name,"hyprland_toplevel_export_manager_v1") && v>=2)exporter=wl_registry_bind(r,id,&hyprland_toplevel_export_manager_v1_interface,2);
 if(!strcmp(name,"zwlr_foreign_toplevel_manager_v1")) {
  foreign=wl_registry_bind(r,id,&zwlr_foreign_toplevel_manager_v1_interface,v<3?v:3);
  zwlr_foreign_toplevel_manager_v1_add_listener(foreign,&manager_listener,NULL);
 }
}
static void removed(void *d,struct wl_registry *r,uint32_t id) {(void)d;(void)r;(void)id;}
static void frame_buffer(void *d,struct hyprland_toplevel_export_frame_v1 *f,uint32_t fmt,uint32_t w,uint32_t h,uint32_t s) {
 (void)d;(void)f;format=fmt;width=w;height=h;stride=s;
}
static void damage(void *d,struct hyprland_toplevel_export_frame_v1 *f,uint32_t x,uint32_t y,uint32_t w,uint32_t h) {(void)d;(void)f;(void)x;(void)y;(void)w;(void)h;}
static void frame_flags(void *d,struct hyprland_toplevel_export_frame_v1 *f,uint32_t v) {(void)d;(void)f;flags=v;}
static void ready(void *d,struct hyprland_toplevel_export_frame_v1 *f,uint32_t hi,uint32_t lo,uint32_t ns) {(void)d;(void)f;(void)hi;(void)lo;(void)ns;done=1;}
static void fail(void *d,struct hyprland_toplevel_export_frame_v1 *f) {(void)d;(void)f;failed=done=1;}
static void dmabuf(void *d,struct hyprland_toplevel_export_frame_v1 *f,uint32_t fmt,uint32_t w,uint32_t h) {(void)d;(void)f;(void)fmt;(void)w;(void)h;}
static void buffer_done(void *d,struct hyprland_toplevel_export_frame_v1 *f) {
 (void)d;
 if(!width || !height || width>30000 || height>30000 || stride<width*4 || (uint64_t)stride*height>512000000) {failed=done=1;return;}
 if(format!=WL_SHM_FORMAT_ARGB8888 && format!=WL_SHM_FORMAT_XRGB8888 && format!=WL_SHM_FORMAT_ABGR8888 && format!=WL_SHM_FORMAT_XBGR8888) {fprintf(stderr,"Unsupported window pixel format: %u\n",format);failed=done=1;return;}
 int fd=memfd_create("omnishot-window",MFD_CLOEXEC);size_t size=(size_t)stride*height;
 if(fd<0 || ftruncate(fd,size)<0) {failed=done=1;if(fd>=0)close(fd);return;}
 pixels=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
 if(pixels==MAP_FAILED) {pixels=NULL;close(fd);failed=done=1;return;}
 struct wl_shm_pool *pool=wl_shm_create_pool(shm,fd,size);
 buffer=wl_shm_pool_create_buffer(pool,0,width,height,stride,format);wl_shm_pool_destroy(pool);close(fd);
 hyprland_toplevel_export_frame_v1_copy(f,buffer,1);
}
static const struct hyprland_toplevel_export_frame_v1_listener frame_listener={frame_buffer,damage,frame_flags,ready,fail,dmabuf,buffer_done};
int main(int argc,char **argv) {
 if(argc!=3 && argc!=4) {fputs("usage: window-helper handle cursor(0|1)\n",stderr);return 2;}
 uint32_t target=0;
 if(argc==3) {
  char *end;errno=0;unsigned long long value=strtoull(argv[1],&end,10);
  if(errno || !argv[1][0] || argv[1][0]=='-' || *end || value>UINT32_MAX) {fputs("Invalid window handle\n",stderr);return 2;}
  target=(uint32_t)value;
 }
 if(strcmp(argv[argc-1],"0") && strcmp(argv[argc-1],"1")) {fputs("Invalid cursor flag\n",stderr);return 2;}
 alarm(10);struct wl_display *display=wl_display_connect(NULL);if(!display)return 1;
 struct wl_registry *registry=wl_display_get_registry(display);const struct wl_registry_listener listener={global,removed};wl_registry_add_listener(registry,&listener,NULL);
 wl_display_roundtrip(display);wl_display_roundtrip(display);wl_display_roundtrip(display);
 if(!shm || !exporter || (argc==4 && !foreign)) {fputs("Isolated window capture protocol unavailable\n",stderr);return 1;}
 struct hyprland_toplevel_export_frame_v1 *frame;
 if(argc==3)frame=hyprland_toplevel_export_manager_v1_capture_toplevel(exporter,atoi(argv[2]),target);
 else {
 /* Keep the old invocation usable while an installed resident is upgrading. */
 struct top *chosen=NULL;
 for(struct top *t=tops;t;t=t->next)if(!t->closed && t->title && t->app && !strcmp(t->title,argv[2]) && !strcmp(t->app,argv[1])) {
  if(chosen) {fputs("Multiple windows have this title. Rename or close the duplicate before isolated capture.\n",stderr);return 1;}chosen=t;
 }
 if(!chosen) {fputs("Window closed or is unavailable for capture\n",stderr);return 1;}
 frame=hyprland_toplevel_export_manager_v1_capture_toplevel_with_wlr_toplevel_handle(exporter,atoi(argv[3]),chosen->handle);
 }
 hyprland_toplevel_export_frame_v1_add_listener(frame,&frame_listener,NULL);
 while(!done && wl_display_dispatch(display)>=0) {}
 if(!done || failed || !pixels) {fputs("Isolated window capture failed\n",stderr);return 1;}
 printf("P7\nWIDTH %u\nHEIGHT %u\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n",width,height);
 int alpha=format==WL_SHM_FORMAT_ARGB8888 || format==WL_SHM_FORMAT_ABGR8888;
 int bgr=format==WL_SHM_FORMAT_ABGR8888 || format==WL_SHM_FORMAT_XBGR8888;
 for(uint32_t y=0;y<height;y++) {
  uint32_t sy=(flags&1)?height-1-y:y;uint32_t *row=(uint32_t*)((char*)pixels+(size_t)sy*stride);
  for(uint32_t x=0;x<width;x++) {
   uint32_t v=row[x],a=alpha?v>>24:255;uint8_t rgba[4]={(v>>(bgr?0:16))&255,(v>>8)&255,(v>>(bgr?16:0))&255,a};
   if(a && a<255)for(int c=0;c<3;c++)rgba[c]=(uint8_t)(((unsigned)rgba[c]*255/a)>255?255:(unsigned)rgba[c]*255/a);
   fwrite(rgba,1,4,stdout);
  }
 }
 hyprland_toplevel_export_frame_v1_destroy(frame);wl_buffer_destroy(buffer);munmap(pixels,(size_t)stride*height);wl_display_disconnect(display);return ferror(stdout)?1:0;
}
