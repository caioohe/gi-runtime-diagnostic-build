"""Actual pre-finalization discard and integrated fingerprint error branch."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root=Path(sys.argv[1])
main=(root/'source/main.c').read_text()
loader=(root/'source/so_util.c').read_text()
def function(text,marker):
    a=text.index(marker)
    return text[a:text.index('\n}',a)+2]
functions='\n'.join(function(main,m) for m in [
    'static void memory_boot_teardown_checkpoint(',
    'static void memory_boot_cleanup_early_services(',
    'static void memory_boot_discard_pre_slab_failure('])
a=main.index('  memory_test_check("supported original image fingerprints"')
flow=main[a:main.index('  void *slab=NULL;',a)]
discard=function(loader,'void so_discard_unfinalized(')
is_loaded=function(loader,'int so_is_loaded_module(')
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include "so_util.h"
typedef struct { int alive; } VirtmemReservation;
static so_module game_mod,left,right,*so_list;
static VirtmemReservation reservation;
static unsigned char image[32768];
static void *heap_so_base;
static size_t heap_so_limit;
static int socket_started,nifm_started,g_net_on,audio_live,sdl_live,auth_live;
static int memory_test_failed,fingerprint_ok,continued,reports,locked,freed;
static uintptr_t current_tp=1,memory_boot_host_tp=1;
static char order[16],records[16][96],stopping;
static unsigned calls,count;
static jmp_buf escape;
static void operation(char name,const char *stage) {
  assert(current_tp==1 && calls<15);
  char expected[96];snprintf(expected,sizeof expected,"BOOT %s-begin",stage);
  assert(count && !strcmp(records[count-1],expected));
  order[calls++]=name;order[calls]=0;
  if(stopping==name) longjmp(escape,1);
}
static void virtmemLock(void) { assert(!locked);locked=1; }
static void virtmemUnlock(void) { assert(locked);locked=0; }
static void virtmemRemoveReservation(VirtmemReservation *r) {
  assert(locked && r==&reservation && r->alive);
  operation('D',"pre-slab-failure-discard");r->alive=0;
}
static void test_free(void *p) {
  assert(p==game_mod.so_base && p && !reservation.alive && !locked);
  ++freed;free(p);
}
#define free test_free
'''+is_loaded+'\n'+discard+r'''
#undef free
static uintptr_t read_thread_pointer(void) { return current_tp; }
static void write_thread_pointer(uintptr_t tp) { current_tp=tp; }
static void memory_runtime_trace(const char *fmt,const char *stage) {
  assert(current_tp==1 && count<16);snprintf(records[count++],96,fmt,stage);
}
static void memory_test_report(const char *fmt) { (void)fmt;++reports; }
static int supported_game_image(void) { return fingerprint_ok; }
static void memory_test_check(const char *name,int ok) { (void)name;if(!ok) memory_test_failed=1; }
static void opensles_shutdown(void) {
  assert(freed==1 && !so_is_loaded_module(&game_mod) && heap_so_base==image && heap_so_limit==sizeof image);
  assert(audio_live && sdl_live);operation('O',"pre-slab-failure-opensles");audio_live=0;
}
static void SDL_Quit(void) { assert(!audio_live && sdl_live);operation('S',"init-failure-SDL");sdl_live=0; }
static void combo_auth_shutdown(void) { assert(!sdl_live && auth_live);operation('A',"init-failure-auth");auth_live=0; }
static void socketExit(void) { assert(!auth_live && socket_started);operation('K',"init-failure-sockets"); }
static void nifmExit(void) { assert(!socket_started && !g_net_on && nifm_started);operation('N',"init-failure-nifm"); }
'''+functions+'\nstatic void run_flow(void *module_heap_base,size_t module_heap_limit) {\n'+flow+r'''
  ++continued;
}
static void reset(int position,int nf,int valid) {
  memset(&game_mod,0,sizeof game_mod);memset(&left,0,sizeof left);memset(&right,0,sizeof right);
  game_mod.so_base=malloc(64);assert(game_mod.so_base);
  game_mod.load_memrv=&reservation;game_mod.load_base=image;game_mod.load_size=4096;
  if(position==0) { so_list=&game_mod;game_mod.next=&right; }
  if(position==1) { so_list=&left;left.next=&game_mod;game_mod.next=&right; }
  if(position==2) { so_list=&left;left.next=&right;right.next=&game_mod; }
  reservation.alive=1;heap_so_base=image+16384;heap_so_limit=16384;
  socket_started=g_net_on=audio_live=sdl_live=auth_live=1;nifm_started=nf;
  fingerprint_ok=valid;memory_test_failed=continued=reports=locked=freed=calls=count=stopping=0;
  order[0]=0;current_tp=1;
}
int main(void) {
  (void)memory_boot_discard_pre_slab_failure;
  for(int position=0;position<3;position++) for(int nf=0;nf<2;nf++) {
    reset(position,nf,0);run_flow(image,sizeof image);
    so_module zero={0};
    assert(!memcmp(&game_mod,&zero,sizeof zero) && !so_is_loaded_module(&game_mod));
    assert(!reservation.alive && freed==1 && !locked && !continued && memory_test_failed);
    assert(!socket_started && !g_net_on && !nifm_started && !audio_live && !sdl_live && !auth_live);
    assert(!strcmp(order,nf?"DOSAKN":"DOSAK") && count==2*calls);
    assert(position==0?so_list==&right:so_list==&left);
    if(position==1) assert(left.next==&right);
    if(position==2) assert(left.next==&right && !right.next);
  }
  reset(1,1,1);run_flow(image,sizeof image);
  assert(continued && !memory_test_failed && !calls && so_is_loaded_module(&game_mod));
  assert(reservation.alive && !freed && heap_so_base==image+16384 && heap_so_limit==16384);
  free(game_mod.so_base);
  for(int guard=0;guard<2;guard++) {
    reset(1,1,0);
    if(guard==0) game_mod.finalized=1;else so_list=&right;
    run_flow(image,sizeof image);
    assert(reports==1 && !calls && !continued && !freed && reservation.alive);
    assert(socket_started && g_net_on && audio_live && sdl_live && auth_live);
    free(game_mod.so_base);
  }
  const char stops[]="DOSAKN";
  for(unsigned i=0;i<6;i++) {
    reset(1,1,0);stopping=stops[i];
    if(!setjmp(escape)) { run_flow(image,sizeof image);assert(0); }
    assert(calls==i+1 && count==2*i+1 && !continued);
    if(!freed) free(game_mod.so_base);
  }
  puts("PASS fingerprint: actual discard at 3 list positions x 2 nifm states, success, lifecycle guards, cursor/metadata/reservation and 6 non-return injections");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'source'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True,env=os.environ)

