"""Test actual geometry-failure control flow with host window/console stubs.

No Horizon, GPU, SDK or console rendering is exercised by this test.
"""
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).with_name('boot_init.c.inc').read_text()
helper = source[source.index('static int memory_boot_recover_geometry_console('):source.index('/* Teardown records')]
start = source.index('  write_thread_pointer(memory_boot_host_tp); consoleExit(NULL);')
end = source.index('  memory_boot_checkpoint("nativeRecreateGfxState-begin");', start)
flow = source[start:end]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
typedef struct { int mutex; unsigned slots_configured; } NWindow;
static NWindow window;
static int missing, valid, init_fails, geometry_error;
static int memory_console_active, init_calls, exit_calls, failed_checks, continued;
static uintptr_t memory_boot_host_tp=1, current_tp=1;
static void write_thread_pointer(uintptr_t tp) { current_tp=tp; }
static NWindow *nwindowGetDefault(void) {
  assert(current_tp==memory_boot_host_tp); return missing?NULL:&window;
}
static int nwindowIsValid(NWindow *w) { assert(w==&window); return valid; }
static void mutexLock(int *m) { assert(!*m); *m=1; }
static void mutexUnlock(int *m) { assert(*m); *m=0; }
static void *consoleInit(void *p) {
  (void)p; assert(current_tp==memory_boot_host_tp);
  assert(valid && !missing && !window.slots_configured && !window.mutex);
  ++init_calls; return init_fails?NULL:&window;
}
static void consoleExit(void *p) {
  (void)p; assert(current_tp==memory_boot_host_tp); ++exit_calls;
}
static void memory_test_report(const char *fmt,...) { (void)fmt; }
static void memory_test_check(const char *name,int ok) {
  (void)name; assert(current_tp==memory_boot_host_tp); if(!ok) ++failed_checks;
}
static void memory_boot_checkpoint(const char *stage) { (void)stage; }
static int android_native_apply_window_geometry(void) {
  assert(current_tp==2); return geometry_error;
}
'''+helper+'\nstatic void test_flow(uintptr_t guest_tp) {\n'+flow+r'''
  ++continued;
}
static void run(int error, int absent, int is_valid, unsigned slots,
                int init_failure, int expect_init, int expect_active) {
  geometry_error=error; missing=absent; valid=is_valid;
  window=(NWindow){0,slots}; init_fails=init_failure;
  current_tp=memory_boot_host_tp; memory_console_active=1;
  init_calls=exit_calls=failed_checks=continued=0;
  test_flow(2);
  assert(exit_calls==1 && init_calls==expect_init);
  assert(memory_console_active==expect_active && !window.mutex);
  assert(continued==(error==0) && failed_checks==(error!=0));
  assert(current_tp==(error?memory_boot_host_tp:2));
}
int main(void) {
  run(-5,0,1,0,0,1,1);  /* free valid window: restore diagnostics */
  run(-16,0,1,4,0,0,0); /* buffers owned: avoid console acquisition */
  run(-19,0,0,0,0,0,0); /* invalid window */
  run(-19,1,0,0,0,0,0); /* absent window */
  run(-5,0,1,0,1,1,0);  /* console init failure keeps flag accurate */
  run(0,0,1,0,0,0,0);   /* normal flow continues with console inactive */
  puts("PASS 6 geometry cases: recovery, ownership, invalid/missing window, init failure, normal flow; TLS and early return checked");
}
'''
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'test.c').write_text(harness)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(root / 'test.c'), '-o', str(root / 'test')], check=True)
    subprocess.run([str(root / 'test')], check=True)

