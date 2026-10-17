/* Fixed first-exception record. No stdio/heap/guest callbacks on fault path.
 * Direct FS IPC can still block/fail; this is best-effort, not crash-safe I/O. */
#include <stdint.h>
#include <stddef.h>
#include <switch.h>
#include "config.h"
#include "libc_shim.h"
#include "exception_capture.h"
#define NX_EXCEPTION_STACK_BYTES 0x8000u
__attribute__((aligned(16))) u8 __nx_exception_stack[NX_EXCEPTION_STACK_BYTES];
u64 __nx_exception_stack_size=sizeof(__nx_exception_stack);
extern void _start(void);
extern void memory_runtime_trace(const char *,...);
#define EX_MAGIC UINT64_C(0x31304358454947)
#define EX_END UINT64_C(0x31444e4558434947)
typedef struct {
  uint64_t magic,version,bytes,context_present,run_tick,crash_tick;
  uint64_t host_base,guest_base,guest_size,error_desc,pstate,esr,afsr0,afsr1,aarch64;
  uint64_t pc,lr,sp,fp,far,regs[29];
  char build[48];
  uint64_t checksum,end;
} NxExceptionRecord;
_Static_assert(sizeof(NxExceptionRecord)==456,"update decoder for record layout change");
static NxExceptionRecord exception_record;
static unsigned exception_claim,exception_sealed,exception_persisted;
static uint64_t exception_run_tick;
static Mutex exception_io_lock;
static FsFile exception_file;
static unsigned exception_started,exception_stopped,exception_open;
static uint32_t exception_last_write_result;
static char exception_path[128];
static __attribute__((noinline,noclone)) uint64_t exception_checksum(const NxExceptionRecord *r) {
  const unsigned char *p=(const unsigned char *)r;
  uint64_t value=UINT64_C(14695981039346656037);
  for(size_t i=0;i<offsetof(NxExceptionRecord,checksum);i++) {
    value^=p[i];value*=UINT64_C(1099511628211);
  }
  return value;
}
static __attribute__((noinline,noclone)) void exception_header(NxExceptionRecord *r) {
  r->magic=EX_MAGIC;r->version=1;r->bytes=sizeof(*r);r->end=EX_END;
  r->run_tick=exception_run_tick;
  const char *build=EXCEPTION_BUILD;
  for(size_t i=0;i<sizeof(r->build);i++) {
    r->build[i]=*build;
    if(*build)++build;
  }
}
/* Caller has already sealed the immutable payload before requesting I/O.
 * Stop and persistence share only this process-owned mutex. Fault side tries
 * once; it never waits for an observer or teardown holding this mutex. */
__attribute__((noinline,noclone)) void nx_exception_capture_poll(void) {
  if(!__atomic_load_n(&exception_sealed,__ATOMIC_ACQUIRE) ||
     __atomic_load_n(&exception_persisted,__ATOMIC_ACQUIRE))return;
  if(!mutexTryLock(&exception_io_lock))return;
  if(!exception_stopped&&exception_open&&
     !__atomic_load_n(&exception_persisted,__ATOMIC_RELAXED)) {
    Result rc=fsFileWrite(&exception_file,0,&exception_record,
                          sizeof(exception_record),FsWriteOption_Flush);
    __atomic_store_n(&exception_last_write_result,rc,__ATOMIC_RELAXED);
    if(R_SUCCEEDED(rc))__atomic_store_n(&exception_persisted,1,__ATOMIC_RELEASE);
  }
  mutexUnlock(&exception_io_lock);
}
void nx_exception_capture_stop(void) {
  /* Normal teardown may wait for an in-flight SD IPC, like observer stop.
   * This fence is required before filesystem teardown; no guest join. */
  mutexLock(&exception_io_lock);
  exception_stopped=1;
  if(exception_open){exception_open=0;fsFileClose(&exception_file);}
  mutexUnlock(&exception_io_lock);
}
void nx_exception_capture_prepare(void) {
  mutexLock(&exception_io_lock);
  if(exception_started||exception_stopped){mutexUnlock(&exception_io_lock);return;}
  exception_started=1;exception_run_tick=armGetSystemTick();
  /* Build the relative path without stdio; used on the sdmc filesystem. */
  const char prefix[]="/switch/genshinimpact_nx/exception-";
  size_t at=0;
  for(size_t i=0;i<sizeof(prefix)-1;i++)exception_path[at++]=prefix[i];
  for(unsigned i=0;i<16;i++)exception_path[at++]="0123456789abcdef"[(exception_run_tick>>(60-i*4))&15];
  const char suffix[]=".bin";
  for(size_t i=0;i<sizeof(suffix);i++)exception_path[at++]=suffix[i];
  FsFileSystem *fs=fsdevGetDeviceFileSystem("sdmc");
  Result rc=MAKERESULT(Module_Libnx,LibnxError_NotInitialized);
  if(fs) {
    /* Do not open/reuse an old file on name collision or create failure. */
    rc=fsFsCreateFile(fs,exception_path,4096,0);
    if(R_SUCCEEDED(rc))rc=fsFsOpenFile(fs,exception_path,FsOpenMode_Write,&exception_file);
    if(R_SUCCEEDED(rc)) {
      /* A cloned domain session retains this object ID on an owned handle.
       * Transfer ownership without closing the original child object: closing
       * it here would invalidate the very object used by the clone. Separate
       * session means fsFileWrite bypasses libnx's shared FS session manager. */
      Service dedicated;
      rc=serviceClone(&exception_file.s,&dedicated);
      if(R_SUCCEEDED(rc)) {
        /* A non-domain/owned original also has a session handle to release.
         * Close only that handle, never the shared domain object ID. */
        if(exception_file.s.own_handle)svcCloseHandle(exception_file.s.session);
        exception_file.s=dedicated;
      }
      else fsFileClose(&exception_file);
    }
    if(R_SUCCEEDED(rc)) {
      NxExceptionRecord armed={0};exception_header(&armed);
      armed.checksum=exception_checksum(&armed);
      rc=fsFileWrite(&exception_file,0,&armed,sizeof(armed),FsWriteOption_Flush);
      if(R_SUCCEEDED(rc))exception_open=1;
      else fsFileClose(&exception_file);
    }
  }
  mutexUnlock(&exception_io_lock);
  memory_runtime_trace("EXCEPTION prepare rc=0x%x path=sdmc:%s; fixed record, direct FS IPC remains fallible",rc,exception_path);
}
__attribute__((noinline,noclone)) void __libnx_exception_handler(ThreadExceptionDump *context) {
  if(!context)return;
  unsigned expected=0;
  if(!__atomic_compare_exchange_n(&exception_claim,&expected,1,0,
                                  __ATOMIC_ACQUIRE,__ATOMIC_RELAXED))return;
  /* First exception wins. Publish before ANY persistence/formatting attempt.
   * Nested faults cannot overwrite this payload or recursively attempt I/O. */
  NxExceptionRecord *r=&exception_record;
  exception_header(r);r->context_present=1;r->crash_tick=armGetSystemTick();
  r->host_base=(uintptr_t)&_start;r->guest_base=g_il2cpp_base;r->guest_size=g_il2cpp_size;
  r->error_desc=context->error_desc;r->pstate=context->pstate;r->esr=context->esr;
  r->afsr0=context->afsr0;r->afsr1=context->afsr1;r->aarch64=threadExceptionIsAArch64(context)?1:0;
  r->pc=context->pc.x;r->lr=context->lr.x;r->sp=context->sp.x;
  r->fp=context->fp.x;r->far=context->far.x;
  for(unsigned i=0;i<29;i++)r->regs[i]=context->cpu_gprs[i].x;
  r->checksum=exception_checksum(r);
  __atomic_store_n(&exception_sealed,1,__ATOMIC_RELEASE);
  nx_exception_capture_poll();
  /* Return to the original libnx fatal path. No recovery or fault suppression. */
}
