/* ABI declarations checked against the pinned Mesa 606441c NAK API. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include "util.h"
struct nir_shader; struct nak_compiler; struct nak_fs_key;
struct nak_shader_bin; struct nv_device_info; struct nir_shader_compiler_options;
extern void memory_runtime_trace(const char *, ...);
static _Thread_local unsigned nak_host_depth;
int nx_nak_host_active(void) { return nak_host_depth!=0; }
static uintptr_t nak_enter(void) {
  uintptr_t previous=nx_compiler_host_tls_enter();
  ++nak_host_depth;
  return previous;
}
static void nak_leave(uintptr_t previous) {
  --nak_host_depth;
  nx_compiler_host_tls_leave(previous);
}

