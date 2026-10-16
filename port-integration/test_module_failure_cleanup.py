"""Actual integrated failed-load branch with PC service/loader stubs."""
from pathlib import Path
import subprocess
import sys
import tempfile

source=(Path(sys.argv[1])/'source/main.c').read_text()
def function(marker):
    a=source.index(marker)
    return source[a:source.index('\n}',a)+2]
checkpoint=function('static void memory_boot_teardown_checkpoint(')
cleanup=function('static void memory_boot_cleanup_early_services(')
load=function('static int load_game_module(')
a=source.index('  int loaded=load_game_module();')
flow=source[a:source.index('  memory_test_check("supported original image fingerprints"',a)]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#define LIB_GAME "synthetic-unused"
#define ALIGN_MEM(v,a) (((v)+(a)-1)&~((a)-1))
typedef struct { size_t load_size; } so_module;
static so_module game_mod;
static uint8_t image[32768];
static void *heap_so_base;
static size_t heap_so_limit;
static int load_result,imports,continued,checks,socket_started,nifm_started,g_net_on;
static int auth_live,sdl_live,audio_live;
static uintptr_t current_tp=1,memory_boot_host_tp=1;
static char order[16],records[16][96],stopping;
static unsigned calls,count;
static jmp_buf escape;
static uintptr_t read_thread_pointer(void) { return current_tp; }
static void write_thread_pointer(uintptr_t p) { current_tp=p; }
static void memory_runtime_trace(const char *fmt,const char *stage) {
  assert(current_tp==1 && count<16);snprintf(records[count++],96,fmt,stage);
}
static void operation(char name,const char *stage) {
  assert(current_tp==1 && calls<15);
  char expected[96];snprintf(expected,sizeof expected,"BOOT %s-begin",stage);
  assert(count && !strcmp(records[count-1],expected));
  order[calls++]=name;order[calls]=0;
  if(stopping==name) longjmp(escape,1);
}
static int so_load(so_module *m,const char *name,void *base,size_t limit) {
  assert(m==&game_mod && !strcmp(name,LIB_GAME) && base==image && limit==sizeof image);
  m->load_size=4096;return load_result;
}
static void resolve_module_imports(so_module *m) {
  assert(m==&game_mod && !load_result);++imports;
}
static void memory_test_check(const char *name,int ok) {
  (void)name;assert(ok==(load_result==0));++checks;
}
static void opensles_shutdown(void) {
  assert(audio_live && sdl_live);operation('O',"load-failure-opensles");audio_live=0;
}
static void SDL_Quit(void) {
  assert(sdl_live && !audio_live && auth_live);operation('S',"init-failure-SDL");sdl_live=0;
}
static void combo_auth_shutdown(void) {
  assert(auth_live && !sdl_live && socket_started);operation('A',"init-failure-auth");auth_live=0;
}
static void socketExit(void) {
  assert(socket_started && g_net_on && !auth_live);operation('K',"init-failure-sockets");
}
static void nifmExit(void) {
  assert(nifm_started && !socket_started && !g_net_on);operation('N',"init-failure-nifm");
}
'''+load+'\n'+checkpoint+'\n'+cleanup+'\nstatic void run_flow(void) {\n'+flow+r'''
  ++continued;
}
static void reset(int result,int nf) {
  heap_so_base=image;heap_so_limit=sizeof image;load_result=result;
  imports=continued=checks=calls=count=stopping=0;order[0]=0;
  socket_started=g_net_on=auth_live=sdl_live=audio_live=1;nifm_started=nf;current_tp=1;
}
int main(void) {
  (void)memory_boot_cleanup_early_services;
  (void)opensles_shutdown;
  for(int nf=0;nf<2;nf++) for(int result=-4;result<=0;result++) {
    reset(result,nf);run_flow();assert(checks==1 && current_tp==1);
    assert(imports==(result==0) && continued==(result==0));
    if(result) {
      assert(heap_so_base==image && heap_so_limit==sizeof image);
      assert(!socket_started && !nifm_started && !g_net_on && !auth_live && !sdl_live && !audio_live);
      assert(!strcmp(order,nf?"OSAKN":"OSAK") && count==2*calls);
    } else {
      assert(heap_so_base==image+16384 && heap_so_limit==16384);
      assert(socket_started && g_net_on && auth_live && sdl_live && audio_live);
      assert(nifm_started==nf && !count && !calls);
    }
  }
  const char stops[]="OSAKN";
  for(unsigned i=0;i<5;i++) {
    reset(-2,1);stopping=stops[i];
    if(!setjmp(escape)) { run_flow();assert(0); }
    assert(calls==i+1 && count==2*i+1 && !imports && !continued);
  }
  puts("PASS module failure: four loader errors/success with two nifm states, heap cursor/imports, service order/flags/TLS and 5 non-return injections");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)

