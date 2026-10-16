/* Observe the real libnx exit path without replacing it or forcing shutdown. */
#include <errno.h>
#include <switch.h>
#include "guest_termination.h"
extern void memory_runtime_trace(const char *, ...);
extern void nx_guest_thread_observer_counters(unsigned long long *, unsigned long long *);
static _Thread_local unsigned host_exit_depth;
static _Thread_local int host_exit_storage_live=1;
static void host_exit_checkpoint(const char *stage) {
  if (!host_exit_depth) return;
  int saved=errno;
  nx_guest_termination_set_stage(stage);
  if(host_exit_storage_live) memory_runtime_trace("HOST exit stage=%s",stage);
  errno=saved;
}
extern void __real___libnx_exit(int) __attribute__((noreturn));
__attribute__((noreturn)) void __wrap___libnx_exit(int status) {
  int saved=errno;
  ++host_exit_depth;
  unsigned long long created=0,reaped=0;
  nx_guest_thread_observer_counters(&created,&reaped);
  memory_runtime_trace("HOST exit begin status=%d applet_type=%d is_nso=%d exit_callback=%d created=%llu reaped=%llu; counters are not live-thread proof",status,(int)appletGetAppletType(),envIsNso(),envGetExitFuncPtr()!=NULL,created,reaped);
  errno=saved;
  host_exit_checkpoint("host-libnx-exit-begin");
  __real___libnx_exit(status);
}
#define TRACE_HOST_EXIT(name,label) \
  extern void __real_##name(void); \
  void __wrap_##name(void) { \
    host_exit_checkpoint("host-" label "-begin"); \
    __real_##name(); \
    host_exit_checkpoint("host-" label "-returned"); \
  }
TRACE_HOST_EXIT(__nx_win_exit,"window-exit")
extern Result __real_fsdevUnmountAll(void);
Result __wrap_fsdevUnmountAll(void) {
  host_exit_checkpoint("host-observer-stop-begin");
  nx_shutdown_observer_stop();
  host_exit_checkpoint("host-observer-stop-returned");
  host_exit_checkpoint("host-filesystem-unmount-begin");
  if(host_exit_depth) host_exit_storage_live=0;
  Result rc=__real_fsdevUnmountAll();
  host_exit_checkpoint("host-filesystem-unmount-returned");
  return rc;
}
_Static_assert(__builtin_types_compatible_p(__typeof__(&fsdevUnmountAll), __typeof__(&__wrap_fsdevUnmountAll)), "fsdevUnmountAll wrapper ABI must match SDK");
TRACE_HOST_EXIT(fsExit,"filesystem-exit")
TRACE_HOST_EXIT(timeExit,"time-exit")
TRACE_HOST_EXIT(hidExit,"hid-exit")
TRACE_HOST_EXIT(appletExit,"applet-exit")
TRACE_HOST_EXIT(smExit,"service-manager-exit")

