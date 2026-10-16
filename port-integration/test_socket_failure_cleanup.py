"""Exercise the integrated pre-auth socket failure path with host stubs."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = (Path(sys.argv[1]) / 'source/main.c').read_text()
start = source.index('static void memory_boot_teardown_checkpoint(')
checkpoint = source[start:source.index('\n}', start) + 2]
start = source.index('  nifm_started=R_SUCCEEDED(nifmInitialize(')
end = source.index('  network_configure_long_stream_receive_window(', start)
flow = source[start:end]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
typedef unsigned Result;
typedef struct { unsigned num_bsd_sessions; } SocketInitConfig;
#define R_SUCCEEDED(r) ((r)==0)
#define NifmServiceType_User 1
#define NETWORK_BSD_SESSION_COUNT 16u
static int nifm_started, socket_started, g_net_on, continued;
static int nifm_fails, sockets_fail, exit_calls, stopping, count;
static uintptr_t memory_boot_host_tp=1, current_tp=1;
static char records[2][96];
static jmp_buf escape;
static uintptr_t read_thread_pointer(void) { return current_tp; }
static void write_thread_pointer(uintptr_t tp) { current_tp=tp; }
static void memory_runtime_trace(const char *format, const char *stage) {
  assert(current_tp==1 && count<2);
  snprintf(records[count++],96,format,stage);
}
static void memory_test_report(const char *format, Result rc) { (void)format;(void)rc; }
static void memory_test_check(const char *name, int ok) {
  (void)name;assert(ok==!sockets_fail && current_tp==1);
}
static Result nifmInitialize(int type) { assert(type==1 && current_tp==1);return nifm_fails; }
static const SocketInitConfig *socketGetDefaultInitConfig(void) {
  static const SocketInitConfig c={3};return &c;
}
static Result socketInitialize(const SocketInitConfig *c) {
  assert(c->num_bsd_sessions==16 && current_tp==1);return sockets_fail;
}
static void nifmExit(void) {
  assert(nifm_started && !socket_started && !g_net_on && current_tp==1);
  ++exit_calls;
  assert(count==1 && !strcmp(records[0],"BOOT socket-failure-nifmExit-begin"));
  if(stopping) longjmp(escape,1);
}
'''+checkpoint+'\nstatic void run_flow(void) {\n'+flow+r'''
  ++continued;
}
static void reset(int nf, int sf) {
  nifm_started=socket_started=g_net_on=continued=exit_calls=count=stopping=0;
  nifm_fails=nf;sockets_fail=sf;current_tp=1;
}
int main(void) {
  (void)memory_boot_teardown_checkpoint;
  (void)nifmExit;
  for(int nf=0;nf<2;nf++) for(int sf=0;sf<2;sf++) {
    reset(nf,sf);run_flow();
    assert(continued==!sf && socket_started==!sf && g_net_on==!sf);
    assert(nifm_started==(!nf && !sf) && exit_calls==(!nf && sf));
    assert(count==2*exit_calls && current_tp==1);
    if(exit_calls) assert(!strcmp(records[1],"BOOT socket-failure-nifmExit-returned"));
  }
  reset(0,1);stopping=1;
  if(!setjmp(escape)) { run_flow();assert(0); }
  assert(exit_calls==1 && count==1 && nifm_started && !continued);
  puts("PASS socket failure: four acquisition combinations, flags, TLS, early return and non-return checkpoint");
}
'''
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    (root/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
    subprocess.run([str(root/'test')],check=True)

