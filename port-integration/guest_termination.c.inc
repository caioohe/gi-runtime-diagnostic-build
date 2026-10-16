/* Observe termination imports, then forward with this thread's host TLS.
 * This does not unload guest code or invoke guest thread destructors. */
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include "util.h"
#include "guest_termination.h"
extern void memory_runtime_trace(const char *, ...);
static const char *termination_stage = "not-recorded";
static _Thread_local int termination_tracing;
void nx_guest_termination_set_stage(const char *stage) {
  __atomic_store_n(&termination_stage, stage, __ATOMIC_RELEASE);
}
static __attribute__((noinline)) void termination_record(const char *kind, int status, void *caller) {
  int restored = restore_bionic_tls();
  if (termination_tracing) return;
  termination_tracing = 1;
  memory_runtime_trace("GUEST termination kind=%s status=%d caller=%p tls_restored=%d stage=%s", kind, status, caller, restored,
    __atomic_load_n(&termination_stage, __ATOMIC_ACQUIRE));
  termination_tracing = 0;
}
__attribute__((noinline,noreturn)) void nx_guest_exit(int status) {
  termination_record("exit", status, __builtin_return_address(0));
  exit(status);
}
__attribute__((noinline,noreturn)) void nx_guest_immediate_exit(int status) {
  termination_record("_exit", status, __builtin_return_address(0));
  _exit(status);
}
__attribute__((noinline,noreturn)) void nx_guest_abort(void) {
  termination_record("abort", 0, __builtin_return_address(0));
  abort();
}

/* Reasons passed here are static host literals. Never dereference guest
 * assertion strings on a fatal path. Publish before fallible trace I/O. */
__attribute__((noinline)) void nx_guest_fatal_begin(const char *reason, int detail, void *caller) {
  termination_record(reason, detail, caller);
}
__attribute__((noinline,noreturn)) void nx_guest_fatal(const char *reason, int detail, void *caller) {
  nx_guest_fatal_begin(reason, detail, caller);
  abort();
}
