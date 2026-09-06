#define _GNU_SOURCE
#include <gsr/plugin.h>
#include <wayland-client.h>
#include <GLES3/gl3.h>
#include <EGL/egl.h>
#include <sys/mman.h>
#include <poll.h>
#include <signal.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "screencopy.h"
typedef struct Capture Capture;
struct Output {struct wl_output *output;char name[128];uint32_t id;};
struct Capture {
 struct wl_display *display;struct wl_registry *registry;struct wl_shm *shm;struct zwlr_screencopy_manager_v1 *manager;
 struct Output outputs[32];int count;struct wl_output *output;struct zwlr_screencopy_frame_v1 *frame;struct wl_buffer *buffer;
 uint32_t w,h,stride,format,flags,texture_flags,texture_format,bw,bh,bs,bformat;void *pixels;size_t bytes;int ready,failed,has_texture;
 int x,y,rw,rh,cursor;GLuint program,texture,vao;GLint swap_uniform,flip_uniform;
};
static void geometry(void*d,struct wl_output*o,int32_t x,int32_t y,int32_t w,int32_t h,int32_t sub,const char*make,const char*model,int32_t transform){}
static void mode(void*d,struct wl_output*o,uint32_t f,int32_t w,int32_t h,int32_t rate){}
static void output_done(void*d,struct wl_output*o){}
static void scale(void*d,struct wl_output*o,int32_t s){}
static void name(void*d,struct wl_output*o,const char*n){snprintf(((struct Output*)d)->name,128,"%s",n);}
static void description(void*d,struct wl_output*o,const char*n){}
static const struct wl_output_listener output_listener={geometry,mode,output_done,scale,name,description};
static void global(void*d,struct wl_registry*r,uint32_t id,const char*n,uint32_t v){
 Capture*c=d;
 if(!strcmp(n,"wl_shm"))c->shm=wl_registry_bind(r,id,&wl_shm_interface,1);
 if(!strcmp(n,"zwlr_screencopy_manager_v1")&&v>=3)c->manager=wl_registry_bind(r,id,&zwlr_screencopy_manager_v1_interface,3);
 if(!strcmp(n,"wl_output")&&v>=4&&c->count<32){struct Output*o=&c->outputs[c->count++];o->id=id;o->output=wl_registry_bind(r,id,&wl_output_interface,4);wl_output_add_listener(o->output,&output_listener,o);}
}
static void removed(void*d,struct wl_registry*r,uint32_t id){Capture*c=d;for(int i=0;i<c->count;i++)if(c->outputs[i].id==id&&c->outputs[i].output==c->output)c->failed=1;}
static const struct wl_registry_listener registry_listener={global,removed};
static void frame_buffer(void*d,struct zwlr_screencopy_frame_v1*f,uint32_t fmt,uint32_t w,uint32_t h,uint32_t stride){Capture*c=d;c->w=w;c->h=h;c->stride=stride;c->format=fmt;}
static void frame_flags(void*d,struct zwlr_screencopy_frame_v1*f,uint32_t flags){((Capture*)d)->flags=flags;}
static void ready(void*d,struct zwlr_screencopy_frame_v1*f,uint32_t hi,uint32_t lo,uint32_t ns){((Capture*)d)->ready=1;}
static void failed(void*d,struct zwlr_screencopy_frame_v1*f){((Capture*)d)->failed=1;}
static void damage(void*d,struct zwlr_screencopy_frame_v1*f,uint32_t x,uint32_t y,uint32_t w,uint32_t h){}
static void dmabuf(void*d,struct zwlr_screencopy_frame_v1*f,uint32_t fmt,uint32_t w,uint32_t h){}
static void buffer_done(void*d,struct zwlr_screencopy_frame_v1*f){
 Capture*c=d;
 if(!c->w||!c->h||c->w>30000||c->h>30000||c->stride<c->w*4||(uint64_t)c->stride*c->h>512000000){c->failed=1;return;}
 if(c->format!=WL_SHM_FORMAT_ARGB8888&&c->format!=WL_SHM_FORMAT_XRGB8888&&c->format!=WL_SHM_FORMAT_ABGR8888&&c->format!=WL_SHM_FORMAT_XBGR8888){c->failed=1;return;}
 if(!c->buffer||c->w!=c->bw||c->h!=c->bh||c->stride!=c->bs||c->format!=c->bformat){
  if(c->buffer)wl_buffer_destroy(c->buffer);if(c->pixels)munmap(c->pixels,c->bytes);c->buffer=NULL;c->pixels=NULL;
  c->bytes=(size_t)c->stride*c->h;int fd=memfd_create("omnishot-clean-capture",MFD_CLOEXEC);
  if(fd<0){c->failed=1;return;}if(ftruncate(fd,c->bytes)<0){close(fd);c->failed=1;return;}
  c->pixels=mmap(NULL,c->bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
  if(c->pixels==MAP_FAILED){c->pixels=NULL;close(fd);c->failed=1;return;}
  struct wl_shm_pool*pool=wl_shm_create_pool(c->shm,fd,c->bytes);c->buffer=wl_shm_pool_create_buffer(pool,0,c->w,c->h,c->stride,c->format);wl_shm_pool_destroy(pool);close(fd);
  c->bw=c->w;c->bh=c->h;c->bs=c->stride;c->bformat=c->format;c->has_texture=0;
 }
 zwlr_screencopy_frame_v1_copy(f,c->buffer);
}
static const struct zwlr_screencopy_frame_v1_listener frame_listener={frame_buffer,frame_flags,ready,failed,damage,dmabuf,buffer_done};
static void request(Capture*c){
 if(c->frame)zwlr_screencopy_frame_v1_destroy(c->frame);c->ready=0;c->flags=0;
 c->frame=c->rw?zwlr_screencopy_manager_v1_capture_output_region(c->manager,c->cursor,c->output,c->x,c->y,c->rw,c->rh):zwlr_screencopy_manager_v1_capture_output(c->manager,c->cursor,c->output);
 zwlr_screencopy_frame_v1_add_listener(c->frame,&frame_listener,c);wl_display_flush(c->display);
}
static void pump(Capture*c,int timeout){
 if(wl_display_dispatch_pending(c->display)<0){c->failed=1;return;}
 wl_display_flush(c->display);struct pollfd fd={wl_display_get_fd(c->display),POLLIN,0};
 if(poll(&fd,1,timeout)>0){if(fd.revents&(POLLHUP|POLLERR))c->failed=1;else if(fd.revents&POLLIN&&wl_display_dispatch(c->display)<0)c->failed=1;}
}
static void synced(void*d,struct wl_callback*cb,uint32_t serial){*(int*)d=1;}
static const struct wl_callback_listener sync_listener={synced};
static int roundtrip(Capture*c){
 int done=0;struct wl_callback*cb=wl_display_sync(c->display);if(!cb)return -1;
 wl_callback_add_listener(cb,&sync_listener,&done);
 for(int i=0;i<200&&!done&&!c->failed;i++)pump(c,10);
 wl_callback_destroy(cb);return done&&!c->failed?0:-1;
}
static GLuint shader(GLenum kind,const char*source){GLuint id=glCreateShader(kind);glShaderSource(id,1,&source,NULL);glCompileShader(id);GLint ok=0;glGetShaderiv(id,GL_COMPILE_STATUS,&ok);if(!ok){char log[1024];glGetShaderInfoLog(id,sizeof(log),NULL,log);fprintf(stderr,"OmniShot shader: %s\n",log);glDeleteShader(id);return 0;}return id;}
static void draw(const gsr_plugin_draw_params*p,void*d){
 Capture*c=d;for(int i=0;i<4&&!c->ready&&!c->failed;i++)pump(c,0);
 GLint program,vao,active,texture,row,alignment,unpack;glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING,&unpack);glBindBuffer(GL_PIXEL_UNPACK_BUFFER,0);glGetIntegerv(GL_CURRENT_PROGRAM,&program);glGetIntegerv(GL_VERTEX_ARRAY_BINDING,&vao);glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&texture);glGetIntegerv(GL_UNPACK_ROW_LENGTH,&row);glGetIntegerv(GL_UNPACK_ALIGNMENT,&alignment);
 GLboolean blend=glIsEnabled(GL_BLEND),scissor=glIsEnabled(GL_SCISSOR_TEST);glDisable(GL_BLEND);glDisable(GL_SCISSOR_TEST);glBindTexture(GL_TEXTURE_2D,c->texture);
 if(c->ready&&!c->failed){
  glPixelStorei(GL_UNPACK_ROW_LENGTH,c->stride/4);glPixelStorei(GL_UNPACK_ALIGNMENT,4);
  if(!c->has_texture)glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,c->w,c->h,0,GL_RGBA,GL_UNSIGNED_BYTE,c->pixels);
  else glTexSubImage2D(GL_TEXTURE_2D,0,0,0,c->w,c->h,GL_RGBA,GL_UNSIGNED_BYTE,c->pixels);
  c->has_texture=1;c->texture_flags=c->flags;c->texture_format=c->format;
 }
 if(c->has_texture&&!c->failed){
  glUseProgram(c->program);glUniform1i(c->swap_uniform,c->texture_format==WL_SHM_FORMAT_ARGB8888||c->texture_format==WL_SHM_FORMAT_XRGB8888);glUniform1i(c->flip_uniform,c->texture_flags&1);glBindVertexArray(c->vao);glDrawArrays(GL_TRIANGLES,0,3);
 }else{GLfloat clear[4];glGetFloatv(GL_COLOR_CLEAR_VALUE,clear);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);glClearColor(clear[0],clear[1],clear[2],clear[3]);}
 glBindBuffer(GL_PIXEL_UNPACK_BUFFER,unpack);glPixelStorei(GL_UNPACK_ROW_LENGTH,row);glPixelStorei(GL_UNPACK_ALIGNMENT,alignment);glBindTexture(GL_TEXTURE_2D,texture);glActiveTexture(active);glBindVertexArray(vao);glUseProgram(program);if(blend)glEnable(GL_BLEND);if(scissor)glEnable(GL_SCISSOR_TEST);
 if(c->failed){fprintf(stderr,"OmniShot clean capture disconnected; stopping recording\n");raise(SIGINT);}else if(c->ready)request(c);
}
static bool is_damaged(void*d){return true;}
static void destroy_capture(void*d){
 Capture*c=d;if(!c)return;
 if(c->program)glDeleteProgram(c->program);if(c->vao)glDeleteVertexArrays(1,&c->vao);if(c->texture)glDeleteTextures(1,&c->texture);
 if(c->frame)zwlr_screencopy_frame_v1_destroy(c->frame);if(c->buffer)wl_buffer_destroy(c->buffer);if(c->pixels)munmap(c->pixels,c->bytes);if(c->manager)zwlr_screencopy_manager_v1_destroy(c->manager);if(c->shm)wl_shm_destroy(c->shm);
 for(int i=0;i<c->count;i++)wl_output_release(c->outputs[i].output);
 if(c->registry)wl_registry_destroy(c->registry);if(c->display)wl_display_disconnect(c->display);free(c);
}
static Capture* create_capture(const char*output,const char*geometry){
 Capture*c=calloc(1,sizeof(*c));if(!c)return NULL;
 c->cursor=getenv("OMNISHOT_CAPTURE_CURSOR")&&!strcmp(getenv("OMNISHOT_CAPTURE_CURSOR"),"1");
 if(!output)goto fail;
 if(geometry&&(sscanf(geometry,"%d,%d %dx%d",&c->x,&c->y,&c->rw,&c->rh)!=4||c->rw<1||c->rh<1))goto fail;
 c->display=wl_display_connect(getenv("OMNISHOT_CAPTURE_SOCKET"));if(!c->display)goto fail;
 c->registry=wl_display_get_registry(c->display);wl_registry_add_listener(c->registry,&registry_listener,c);
 if(roundtrip(c)<0||roundtrip(c)<0)goto fail;
 for(int i=0;i<c->count;i++)if(!strcmp(output,c->outputs[i].name))c->output=c->outputs[i].output;
 if(!c->output||!c->shm||!c->manager)goto fail;
 GLuint vs=shader(GL_VERTEX_SHADER,"#version 300 es\nout vec2 uv;void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=p;gl_Position=vec4(p*2.-1.,0.,1.);}");
 GLuint fs=shader(GL_FRAGMENT_SHADER,"#version 300 es\nprecision highp float;uniform sampler2D image;uniform bool swap_color;uniform bool flip;in vec2 uv;out vec4 color;void main(){vec4 s=texture(image,vec2(uv.x,flip?1.-uv.y:uv.y));color=vec4(swap_color?s.bgr:s.rgb,1.);}");
 if(!vs||!fs){if(vs)glDeleteShader(vs);if(fs)glDeleteShader(fs);goto fail;}
 c->program=glCreateProgram();glAttachShader(c->program,vs);glAttachShader(c->program,fs);glLinkProgram(c->program);glDeleteShader(vs);glDeleteShader(fs);GLint linked=0;glGetProgramiv(c->program,GL_LINK_STATUS,&linked);if(!linked)goto fail;
 c->swap_uniform=glGetUniformLocation(c->program,"swap_color");c->flip_uniform=glGetUniformLocation(c->program,"flip");glGenVertexArrays(1,&c->vao);glGenTextures(1,&c->texture);
 GLint bound;glGetIntegerv(GL_TEXTURE_BINDING_2D,&bound);glBindTexture(GL_TEXTURE_2D,c->texture);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);glBindTexture(GL_TEXTURE_2D,bound);
 request(c);for(int i=0;i<200&&!c->ready&&!c->failed;i++)pump(c,10);if(!c->ready||c->failed)goto fail;
 return c;
 fail:fprintf(stderr,"OmniShot could not initialize clean capture\n");destroy_capture(c);return NULL;
}

typedef struct {
 Capture* captures[32];
 int count,width,height,x[32],y[32],w[32],h[32];
} Scene;

static void draw_scene(const gsr_plugin_draw_params*p,void*d){
 Scene*s=d;
 if(!s->width){draw(p,s->captures[0]);return;}
 GLint viewport[4];glGetIntegerv(GL_VIEWPORT,viewport);
 GLboolean scissor=glIsEnabled(GL_SCISSOR_TEST);glDisable(GL_SCISSOR_TEST);
 GLfloat clear[4];glGetFloatv(GL_COLOR_CLEAR_VALUE,clear);
 glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);glClearColor(clear[0],clear[1],clear[2],clear[3]);
 for(int i=0;i<s->count;i++){
  // GSR's plugin framebuffer has its image origin at the bottom-left; the
  // final color conversion flips it. Keep logical top-to-bottom coordinates.
  int x=(int)(((int64_t)s->x[i]*p->width+s->width/2)/s->width);
  int y=(int)(((int64_t)s->y[i]*p->height+s->height/2)/s->height);
  int right=(int)(((int64_t)(s->x[i]+s->w[i])*p->width+s->width/2)/s->width);
  int bottom=(int)(((int64_t)(s->y[i]+s->h[i])*p->height+s->height/2)/s->height);
  glViewport(x,y,right-x,bottom-y);draw(p,s->captures[i]);
 }
 glViewport(viewport[0],viewport[1],viewport[2],viewport[3]);
 if(scissor)glEnable(GL_SCISSOR_TEST);
}

void gsr_plugin_deinit(void*d){
 Scene*s=d;if(!s)return;
 for(int i=0;i<s->count;i++)destroy_capture(s->captures[i]);
 free(s);
}

bool gsr_plugin_init(const gsr_plugin_init_params*p,gsr_plugin_init_return*ret){
 if(p->graphics_api!=GSR_PLUGIN_GRAPHICS_API_EGL_ES||eglGetCurrentContext()==EGL_NO_CONTEXT)return false;
 Scene*s=calloc(1,sizeof(*s));if(!s)return false;
 const char*layout=getenv("OMNISHOT_CAPTURE_PARTS");char*copy=NULL;
 if(layout){
  copy=strdup(layout);if(!copy)goto fail;
  char*save=NULL;char*line=strtok_r(copy,"\n",&save);int used=0;
  if(!line||sscanf(line,"%d,%d%n",&s->width,&s->height,&used)!=2||line[used]||s->width<2||s->height<2||s->width>30000||s->height>30000)goto fail;
  while((line=strtok_r(NULL,"\n",&save))){
   int i=s->count,rx,ry;char output[128],geometry[128];used=0;
   if(i==32||sscanf(line,"%127[^\t]\t%d,%d %dx%d\t%d,%d%n",output,&rx,&ry,&s->w[i],&s->h[i],&s->x[i],&s->y[i],&used)!=7||line[used])goto fail;
   if(rx<0||ry<0||s->w[i]<1||s->h[i]<1||s->x[i]<0||s->y[i]<0||s->w[i]>s->width||s->h[i]>s->height||s->x[i]>s->width-s->w[i]||s->y[i]>s->height-s->h[i])goto fail;
   snprintf(geometry,sizeof(geometry),"%d,%d %dx%d",rx,ry,s->w[i],s->h[i]);
   s->captures[i]=create_capture(output,geometry);if(!s->captures[i])goto fail;s->count++;
  }
  if(!s->count)goto fail;
 }else{
  s->captures[0]=create_capture(getenv("OMNISHOT_CAPTURE_OUTPUT"),getenv("OMNISHOT_CAPTURE_REGION"));
  if(!s->captures[0])goto fail;s->count=1;
 }
 free(copy);ret->name="OmniShot clean Wayland capture";ret->version=1;ret->userdata=s;ret->draw=draw_scene;ret->is_damaged=is_damaged;ret->clear_damage=NULL;return true;
 fail:free(copy);gsr_plugin_deinit(s);fprintf(stderr,"OmniShot could not initialize recording displays\n");return false;
}
