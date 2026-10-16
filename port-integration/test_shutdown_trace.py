"""Run reconstructed teardown C with host stubs; no Horizon/guest execution."""
from pathlib import Path
import subprocess
import sys
import tempfile

source=(Path(sys.argv[1])/'source/main.c').read_text()
start=source.index('static void (*memory_host_shutdown_trace)')
host=source[start:source.index('\n}',start)+2]
start=source.index('static void memory_boot_teardown_checkpoint(')
checkpoint=source[start:source.index('\n}',start)+2]
start=source.index('  memory_boot_checkpoint("graphics-shutdown-begin");')
flow=source[start:source.index('  memory_boot_checkpoint("graphics-shutdown-finished");',start)]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <setjmp.h>
static uintptr_t memory_boot_host_tp=1,current_tp=2;
static int socket_started,nifm_started,g_net_on,memory_console_active,acquired_sockets,acquired_nifm;
static void *fake_env,*fake_unityplayer_thiz;
static unsigned count,calls,boundaries;
static int expect_trace=1;
static char records[128][96];
static const char *stopping;
static jmp_buf escape;
static const char *order[]={"audio-focus","bridge-focus","nativeFocusChanged","nativePause","combo-bridge","nativeRecreateGfxState","nativeDone","host-vibration","host-opensles","host-auth","host-SDL","host-sockets","host-nifm","consoleInit"};
static uintptr_t read_thread_pointer(void) { return current_tp; }
static void write_thread_pointer(uintptr_t tp) { current_tp=tp; }
static void memory_runtime_trace(const char *fmt,...) {
  assert(current_tp==memory_boot_host_tp && count<128);
  va_list ap; va_start(ap,fmt); vsnprintf(records[count++],96,fmt,ap); va_end(ap);
}
static void memory_boot_checkpoint(const char *s) { (void)s; }
static void call(const char *name,int host) {
  assert(current_tp==(host?1u:2u));
  if(expect_trace && acquired_sockets && acquired_nifm) assert(!strcmp(name,order[calls]));
  ++calls;
  char expected[96]; snprintf(expected,sizeof expected,"BOOT shutdown-%s-begin",name);
  if(expect_trace) assert(count && !strcmp(records[count-1],expected));
  if(stopping && !strcmp(stopping,name)) longjmp(escape,1);
}
static void opensles_set_focus(int f) { assert(!f); call("audio-focus",0); }
static void combo_bridge_set_focus(int f) { assert(!f); call("bridge-focus",0); }
static void focus(void *e,void *o,int f) { (void)e;(void)o;assert(!f);call("nativeFocusChanged",0); }
static int pause(void *e,void *o) { (void)e;(void)o;call("nativePause",0);return 1; }
static void combo_bridge_shutdown(void) { call("combo-bridge",0); }
static void gfx(void *e,void *o,int x,void *s) { (void)e;(void)o;assert(!x&&!s);call("nativeRecreateGfxState",0); }
static void done(void *e,void *o) { (void)e;(void)o;call("nativeDone",0); }
static void android_native_vibration_shutdown(void) { call("host-vibration",1); }
static void opensles_shutdown(void) { call("host-opensles",1); }
static void combo_auth_shutdown(void) { call("host-auth",1); }
static void SDL_Quit(void) { call("host-SDL",1); }
static void socketExit(void) { call("host-sockets",1); }
static void nifmExit(void) { call("host-nifm",1); }
static void *consoleInit(void *s) { (void)s;call("consoleInit",1);return (void *)1; }
static void jni_boundary_begin(const char *s) { (void)s;assert(current_tp==2);++boundaries; }
static void jni_boundary_end(void) { assert(current_tp==2&&boundaries);--boundaries; }
'''+host+'\n'+checkpoint+'\nstatic void run_flow(void) {\n'+flow+r'''
}
static void reset(void) {
  current_tp=2;count=calls=boundaries=0;memory_console_active=0;
  socket_started=nifm_started=g_net_on=acquired_sockets=acquired_nifm=1;memory_host_shutdown_trace=NULL;stopping=NULL;
}
int main(void) {
  reset();run_flow();
  assert(calls==14 && count==30 && !boundaries);
  assert(current_tp==1 && memory_console_active && !memory_host_shutdown_trace);
  for(unsigned i=0;i<14;i++) {
    char begin[96],end[96];
    snprintf(begin,sizeof begin,"BOOT shutdown-%s-begin",order[i]);
    snprintf(end,sizeof end,"BOOT shutdown-%s-returned",order[i]);
    unsigned b=128,e=128;
    for(unsigned j=0;j<count;j++) { if(!strcmp(records[j],begin)) b=j;if(!strcmp(records[j],end)) e=j; }
    assert(b<e && e<count);
  }
  for(unsigned i=0;i<14;i++) {
    reset();stopping=order[i];
    if(!setjmp(escape)) { run_flow();assert(0); }
    char expected[96];snprintf(expected,sizeof expected,"BOOT shutdown-%s-begin",order[i]);
    assert(!strcmp(records[count-1],expected) && calls==i+1);
  }
  for(unsigned flags=0;flags<4;flags++) {
    reset();socket_started=acquired_sockets=flags&1;nifm_started=acquired_nifm=(flags>>1)&1;g_net_on=socket_started;run_flow();
    assert(calls==12+(flags&1)+((flags>>1)&1));
    assert(!socket_started && !nifm_started && !g_net_on);
    assert(!boundaries && !memory_host_shutdown_trace);
  }
  reset();current_tp=1;expect_trace=0;shutdown_host();
  assert(calls==6 && count==0 && !memory_host_shutdown_trace);
  puts("PASS teardown: ordered calls, 14 non-return injections, four service flag combinations, TLS and JNI boundaries");
}
'''
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
    subprocess.run([str(root/'test')],check=True)


