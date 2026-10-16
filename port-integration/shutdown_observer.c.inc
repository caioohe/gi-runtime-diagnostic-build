/* Process-owned host observer. Its FILE is fenced before filesystem unmount. */
#include <stdio.h>
#include <errno.h>
#include <switch.h>
#include "guest_termination.h"
#include "imports.h"
extern void memory_runtime_trace(const char *, ...);
static Thread observer_thread;
static Mutex observer_io_lock;
static int observer_started, observer_stopped;
static FILE *observer_file;
static void observer_close_locked(void) {
  FILE *f=observer_file;
  observer_file=NULL;
  if(f) fclose(f);
}
void nx_shutdown_observer_stop(void) {
  /* Wait only for this observer's current stdio operation, never a guest lock.
   * No join is needed: after this fence the sleeping thread performs no I/O. */
  int saved=errno;
  mutexLock(&observer_io_lock);
  observer_stopped=1;
  observer_close_locked();
  mutexUnlock(&observer_io_lock);
  errno=saved;
}
static void observer_main(void *unused) {
  (void)unused;
  mutexLock(&observer_io_lock);
  if(observer_stopped) { mutexUnlock(&observer_io_lock); return; }
  observer_file=fopen("sdmc:/switch/genshinimpact_nx/shutdown-observer.txt","wb");
  if(!observer_file) { mutexUnlock(&observer_io_lock); return; }
  int header=fprintf(observer_file,"OBSERVER build=%s tick=%llu interval_ns=1000000000 max_samples=300; synchronous I/O, approximate lifecycle counters\n",OBSERVER_BUILD,(unsigned long long)armGetSystemTick());
  if(header<0 || fflush(observer_file)!=0) {
    observer_close_locked(); mutexUnlock(&observer_io_lock); return;
  }
  mutexUnlock(&observer_io_lock);
  for(unsigned i=0;i<300;i++) {
    mutexLock(&observer_io_lock);
    if(observer_stopped || !observer_file) { mutexUnlock(&observer_io_lock); return; }
    unsigned long long created=0,reaped=0;
    nx_guest_thread_observer_counters(&created,&reaped);
    NxPthreadStorageDiagnostics storage;
    nx_pthread_storage_get_diagnostics(&storage);
    int n=fprintf(observer_file,"sample=%u tick=%llu phase=%s termination=%s created=%llu reaped=%llu pthread_lock=0x%x\n",i,(unsigned long long)armGetSystemTick(),nx_guest_termination_stage(),nx_guest_termination_kind(),created,reaped,storage.lock_word);
    if(n<0 || fflush(observer_file)!=0) {
      observer_close_locked(); mutexUnlock(&observer_io_lock); return;
    }
    mutexUnlock(&observer_io_lock);
    svcSleepThread(1000000000LL);
  }
  mutexLock(&observer_io_lock);
  observer_close_locked();
  mutexUnlock(&observer_io_lock);
}
void nx_shutdown_observer_start(void) {
  mutexLock(&observer_io_lock);
  if(observer_started || observer_stopped) { mutexUnlock(&observer_io_lock); return; }
  observer_started=1;
  Result rc=threadCreate(&observer_thread,observer_main,NULL,NULL,0x10000,0x3b,-2);
  if(R_SUCCEEDED(rc)) {
    rc=threadStart(&observer_thread);
    if(R_FAILED(rc)) threadClose(&observer_thread);
  }
  if(!observer_stopped) memory_runtime_trace("OBSERVER start rc=0x%x; process-owned native thread, no watchdog",rc);
  mutexUnlock(&observer_io_lock);
}
