"""Host fault injection in actual integrated pre-guest control flow and auth C."""
from pathlib import Path
import subprocess
import sys
import tempfile

root=Path(sys.argv[1])
source=(root/'source/main.c').read_text()
auth=(root/'source/combo_auth.c').read_text()
def function(text, marker):
    start=text.index(marker)
    return text[start:text.index('\n}',start)+2]
checkpoint=function(source,'static void memory_boot_teardown_checkpoint(')
cleanup=function(source,'static void memory_boot_cleanup_early_services(')
auth_init=function(auth,'int combo_auth_init(void)')
auth_shutdown=function(auth,'void combo_auth_shutdown(void)')
start=source.index('  int auth_result=combo_auth_init();')
flow=source[start:source.index('  (void)opensles_initialize();',start)]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
typedef int CURLcode;
typedef unsigned Result;
#define CURL_GLOBAL_DEFAULT 3
#define CURLE_OK 0
#define R_FAILED(r) ((r)!=0)
#define COMBO_AUTH_SESSION_UNCHECKED 0
#define SDL_INIT_AUDIO 1
#define SDL_INIT_GAMECONTROLLER 2
static int g_initialized,g_spl_initialized,g_curl_code,g_service_result;
static int g_session_checked,g_session_replay_pending,g_session_state;
static char g_lifecycle_id[40],g_asterisk_name[8],g_connection_ui_message[8];
static int socket_started,nifm_started,g_net_on,continued,auth_attempts,sdl_attempts;
static unsigned memory_test_failed;
static int curl_fails,spl_fails,sdl_fails,sdl_partial,curl_live,spl_live,sdl_live;
static uintptr_t current_tp=1,memory_boot_host_tp=1;
static char order[16],records[16][96];static unsigned calls,count;
static char stopping;static jmp_buf escape;
static void operation(char name,const char *stage) {
  assert(current_tp==1 && calls<15);
  order[calls++]=name;order[calls]=0;
  char expected[96];snprintf(expected,sizeof expected,"BOOT init-failure-%s-begin",stage);
  assert(count && !strcmp(records[count-1],expected));
  if(stopping==name) longjmp(escape,1);
}
static uintptr_t read_thread_pointer(void) { return current_tp; }
static void write_thread_pointer(uintptr_t tp) { current_tp=tp; }
static void memory_runtime_trace(const char *fmt,const char *stage) {
  assert(current_tp==1 && count<16);snprintf(records[count++],96,fmt,stage);
}
static CURLcode curl_global_init(int flags) {
  assert(flags==3 && current_tp==1 && !curl_live);++auth_attempts;
  if(curl_fails) return 1;
  curl_live=1;return 0;
}
static void curl_global_cleanup(void) { assert(curl_live);curl_live=0; }
static Result splInitialize(void) {
  assert(curl_live && !spl_live);
  if(spl_fails) return 1;
  spl_live=1;return 0;
}
static void splExit(void) { assert(spl_live);spl_live=0; }
static void randomGet(void *p,size_t n) { memset(p,0,n); }
static void erase_bytes(void *p,size_t n) { memset(p,0,n); }
static void erase_attempt_secrets(void) {
  assert(g_initialized && curl_live && spl_live && socket_started);
  operation('A',"auth");
}
static void socketExit(void) {
  assert(socket_started && g_net_on && !curl_live && !spl_live && !sdl_live);
  operation('K',"sockets");
}
static void nifmExit(void) {
  assert(nifm_started && !socket_started && !g_net_on);operation('N',"nifm");
}
static void SDL_SetMainReady(void) { assert(g_initialized && current_tp==1); }
static int SDL_Init(unsigned flags) {
  assert(flags==3 && g_initialized && current_tp==1);++sdl_attempts;
  sdl_live=!sdl_fails || sdl_partial;return sdl_fails?-1:0;
}
static void SDL_Quit(void) {
  assert(sdl_attempts==1 && g_initialized && socket_started);
  operation('S',"SDL");sdl_live=0;
}
static void initialize_network_state(void) { assert(socket_started);g_net_on=1; }
static int android_native_update_mode(void) { assert(current_tp==1);return 0; }
static void memory_test_check(const char *name,int ok) { (void)name;if(!ok) ++memory_test_failed; }
'''+auth_init+'\n'+auth_shutdown+'\n'+checkpoint+'\n'+cleanup+'\nstatic void run_flow(void) {\n'+flow+r'''
  ++continued;
}
static void reset(int nf,int cf,int pf,int sf,int partial) {
  g_initialized=g_spl_initialized=curl_live=spl_live=sdl_live=0;
  g_session_checked=g_session_replay_pending=g_session_state=0;
  socket_started=g_net_on=1;nifm_started=nf;
  curl_fails=cf;spl_fails=pf;sdl_fails=sf;sdl_partial=partial;
  continued=auth_attempts=sdl_attempts=memory_test_failed=calls=count=stopping=0;
  order[0]=0;current_tp=1;
}
int main(void) {
  (void)memory_boot_cleanup_early_services;
  for(int nf=0;nf<2;nf++) for(int mode=0;mode<5;mode++) {
    reset(nf,mode==0,mode==1,mode==2||mode==3,mode==3);
    run_flow();
    int success=mode==4,auth_ok=mode>=2;
    assert(auth_attempts==1 && sdl_attempts==auth_ok && continued==success);
    assert(current_tp==1 && socket_started==success && g_net_on==success);
    assert(nifm_started==(nf&&success));
    assert(g_initialized==success && g_spl_initialized==success);
    assert(curl_live==success && spl_live==success && sdl_live==success);
    assert(memory_test_failed==!success);
    assert(!strcmp(order,success?"":auth_ok?(nf?"SAKN":"SAK"):(nf?"KN":"K")));
    assert(count==2*calls);
  }
  /* A cumulative diagnostic failure after successful auth still releases it. */
  reset(1,0,0,0,0);memory_test_failed=1;run_flow();
  assert(!strcmp(order,"AKN") && !continued && !sdl_attempts && !g_initialized);
  const char stops[]="SAKN";
  for(unsigned i=0;i<4;i++) {
    reset(1,0,0,1,1);stopping=stops[i];
    if(!setjmp(escape)) { run_flow();assert(0); }
    assert(calls==i+1 && count==2*i+1 && !continued && current_tp==1);
  }
  puts("PASS early services: 10 auth/SDL/nifm cases, cumulative failure, inverse cleanup order, flags/TLS and 4 non-return injections");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)

