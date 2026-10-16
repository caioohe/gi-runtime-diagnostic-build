"""Execute the actual patched C growth function with a simulated kernel budget.

This tests allocation policy on a computer, not Horizon mappings or gameplay.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

source = (Path(sys.argv[1]) / 'source/libc_shim.c').read_text()
start = source.index('static int oc_donor_grow_locked(')
end = source.index('\nstatic void oc_donor_try_shrink_locked(', start)
function = source[start:end]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#ifndef DONOR_BATCH_MIB
#define DONOR_BATCH_MIB 256u
#endif
#define OC_HEAP_DONOR_GROW_BYTES (DONOR_BATCH_MIB * 1024u * 1024u)
#define OC_HEAP_DONOR_UNIT_BYTES (64u * 1024u)
#define R_FAILED(x) ((x) != 0)
static size_t oc_donor_active_units, oc_donor_unit_capacity;
static uint32_t oc_donor_last_resize_result;
static size_t budget, calls, targets[2];
static int postcondition_failure;
static size_t oc_donor_heap_quantum_units(void) { return 32; }
static int oc_donor_resize_locked(size_t n) {
  assert(calls < 2); targets[calls++] = n;
  assert(n % 32 == 0 && n > oc_donor_active_units);
  if (postcondition_failure) { oc_donor_last_resize_result = 0; return 0; }
  if (n > budget) { oc_donor_last_resize_result = 1; return 0; }
  oc_donor_last_resize_result = 0; oc_donor_active_units = n; return 1;
}
'''
harness += function
harness += r'''
static void reset(size_t capacity, size_t limit) {
  oc_donor_active_units = 1024; oc_donor_unit_capacity = capacity;
  budget = limit; calls = 0; postcondition_failure = 0;
  oc_donor_last_resize_result = 0;
}
int main(void) {
  reset(8192,8192); assert(oc_donor_grow_locked(128));
  assert(calls==1 && targets[0]==1024+OC_HEAP_DONOR_GROW_BYTES/OC_HEAP_DONOR_UNIT_BYTES);
  reset(8192,1280); assert(oc_donor_grow_locked(128));
  assert(calls==2 && targets[1]==1152 && oc_donor_active_units==1152);
  reset(8192,1088); assert(oc_donor_grow_locked(33));
  assert(calls==2 && targets[1]==1088);
  reset(8192,1056); assert(!oc_donor_grow_locked(128));
  assert(calls==2 && oc_donor_active_units==1024);
  reset(8192,4096); assert(!oc_donor_grow_locked(5000));
  assert(calls==1 && oc_donor_active_units==1024);
  reset(1152,1152); assert(oc_donor_grow_locked(128)); assert(calls==1);
  reset(1024,1024); assert(!oc_donor_grow_locked(1)); assert(calls==0);
  reset(8192,8192); postcondition_failure=1;
  assert(!oc_donor_grow_locked(128)); assert(calls==1);
  reset(8192,1100); assert(!oc_donor_grow_locked(SIZE_MAX)); assert(calls==1);
  /* Repeated lifecycles: successful admission grows capacity without
   * mutating ownership; simulated release permits the next same request. */
  for (unsigned i=0;i<1000;++i) {
    reset(8192,1280); assert(oc_donor_grow_locked(128));
    assert(oc_donor_active_units==1152 && calls==2);
  }
  puts("PASS donor growth: 9 boundary/failure cases and 1000 policy repetitions");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / 'test.c'
    exe = Path(tmp) / 'test'
    c.write_text(harness)
    for batch in (256, 32):
      subprocess.run(['cc', f'-DDONOR_BATCH_MIB={batch}', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    str(c), '-o', str(exe)], check=True)
      subprocess.run([str(exe)], check=True)

