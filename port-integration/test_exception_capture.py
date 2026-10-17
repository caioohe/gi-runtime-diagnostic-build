"""Actual capture module: I/O failures, first-fault publication and stop fence."""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1]);source=(root/'source/exception_capture.c').read_text();template=Path(__file__).with_name('exception_capture.c.inc').read_text();assert template in source
assert not any(x in source for x in ['fopen(', 'fprintf(', 'malloc(', 'calloc(', 'snprintf(', 'fflush('])
obs=(root/'source/shutdown_observer.c').read_text();assert 'nx_exception_capture_stop();' in obs and 'nx_exception_capture_poll();' in obs
main=(root/'source/main.c').read_text();assert main.index('nx_exception_capture_prepare();')<main.index('nx_shutdown_observer_start();')
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdarg.h>
#include <sched.h>
typedef uint8_t u8;typedef uint64_t u64;typedef int Result;
typedef pthread_mutex_t Mutex;typedef struct{int session,own_handle;}Service;typedef struct{Service s;}FsFile;typedef struct{int handle;}FsFileSystem;
typedef struct{uint64_t x;}Reg;
typedef struct{uint32_t error_desc,pstate,esr,afsr0,afsr1;Reg pc,lr,sp,fp,far,cpu_gprs[29];}ThreadExceptionDump;
#define R_SUCCEEDED(x) ((x)==0)
#define MAKERESULT(a,b) ((a)+(b))
#define Module_Libnx 100
#define LibnxError_NotInitialized 1
#define FsWriteOption_Flush 1
#define FsOpenMode_Write 2
static uintptr_t g_il2cpp_base=0x10000000,g_il2cpp_size=0x161e0000;
static FsFileSystem filesystem={1};static int no_fs,create_error,open_error,clone_error,write_error,short_write,reenter;
static unsigned opens,closes,writes,traces,creates,raw_closes,owned_original;
static unsigned char disk[4096];
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;
static int block_write,write_entered,release_write;
static atomic_int stop_entered,stop_done;
static _Thread_local int fault_thread;
static void _start(void){}
static void mutexLock(Mutex*m){assert(!pthread_mutex_lock(m));}
static int mutexTryLock(Mutex*m){return pthread_mutex_trylock(m)==0;}
static void mutexUnlock(Mutex*m){assert(!pthread_mutex_unlock(m));}
static uint64_t armGetSystemTick(void){return 0x12345678;}
static int threadExceptionIsAArch64(ThreadExceptionDump*c){(void)c;return 1;}
static void memory_runtime_trace(const char*f,...){assert(!fault_thread&&strstr(f,"EXCEPTION prepare"));++traces;}
static FsFileSystem*fsdevGetDeviceFileSystem(const char*n){assert(!fault_thread&&!strcmp(n,"sdmc"));return no_fs?NULL:&filesystem;}
static Result fsFsCreateFile(FsFileSystem*f,const char*p,int64_t size,unsigned opt){assert(!fault_thread&&f==&filesystem&&strstr(p,"exception-0000000012345678.bin")&&size==4096&&!opt);++creates;if(!create_error)memset(disk,0,sizeof disk);return create_error;}
static Result fsFsOpenFile(FsFileSystem*f,const char*p,unsigned mode,FsFile*out){assert(!fault_thread&&f==&filesystem&&p&&mode==2);++opens;out->s.session=5;out->s.own_handle=owned_original;return open_error;}
static Result serviceClone(Service*s,Service*out){assert(!fault_thread&&s->session==5);out->session=6;out->own_handle=1;return clone_error;}
static Result svcCloseHandle(int h){assert(!fault_thread&&h==5);++raw_closes;return 0;}
static void fsFileClose(FsFile*f){assert(f->s.session==5||f->s.session==6);++closes;}
void __libnx_exception_handler(ThreadExceptionDump*);
static Result fsFileWrite(FsFile*f,int64_t off,const void*buf,uint64_t n,unsigned opt){
 assert(f->s.session==6&&!off&&n==456&&opt==1);++writes;
 if(reenter){reenter=0;ThreadExceptionDump nested={0};nested.pc.x=0xdead;__libnx_exception_handler(&nested);}
 pthread_mutex_lock(&gate);
 if(block_write){write_entered=1;pthread_cond_broadcast(&changed);while(!release_write)pthread_cond_wait(&changed,&gate);}
 pthread_mutex_unlock(&gate);
 if(short_write){memcpy(disk,buf,37);return 44;}
 if(write_error)return write_error;
 memcpy(disk,buf,n);return 0;
}
'''+source+r'''
static ThreadExceptionDump ctx(uint64_t pc){ThreadExceptionDump c={0};c.error_desc=0x101;c.esr=0x92000045;c.pc.x=pc;c.lr.x=0x222;c.sp.x=0x333;c.fp.x=0x444;c.far.x=0x555;for(unsigned i=0;i<29;i++)c.cpu_gprs[i].x=0x1000+i;return c;}
static void reset(void){
 assert(!exception_open);
 memset(&exception_record,0,sizeof exception_record);exception_claim=exception_sealed=exception_persisted=0;
 exception_started=exception_stopped=0;exception_run_tick=0;exception_last_write_result=0;
 no_fs=create_error=open_error=clone_error=write_error=short_write=reenter=0;opens=closes=writes=traces=creates=raw_closes=owned_original=0;
 block_write=write_entered=release_write=0;stop_entered=stop_done=0;memset(disk,0xcc,sizeof disk);
}
static int disk_valid(void){NxExceptionRecord r;memcpy(&r,disk,sizeof r);return r.magic==EX_MAGIC&&r.end==EX_END&&r.version==1&&r.bytes==456&&r.checksum==exception_checksum(&r);}
static void check(uint64_t pc){assert(exception_sealed&&exception_record.pc==pc&&exception_record.esr==0x92000045&&exception_record.regs[28]==0x101c&&exception_record.checksum==exception_checksum(&exception_record));}
static void fault(ThreadExceptionDump*c){fault_thread=1;__libnx_exception_handler(c);fault_thread=0;}
static void*worker(void*p){fault(p);return NULL;}
static void*stopper(void*p){(void)p;stop_entered=1;nx_exception_capture_stop();stop_done=1;return NULL;}
int main(int argc,char**argv){
 assert(!pthread_mutex_init(&exception_io_lock,NULL));
 for(unsigned test=0;test<5;test++){
  reset();if(test==1)no_fs=1;if(test==2)create_error=7;if(test==3)open_error=8;if(test==4)clone_error=9;
  nx_exception_capture_prepare();nx_exception_capture_prepare();assert(traces==1);
  ThreadExceptionDump c=ctx(0x111);fault(&c);check(0x111);
  if(!test)assert(exception_persisted&&disk_valid());else assert(!exception_persisted);
  nx_exception_capture_stop();nx_exception_capture_stop();unsigned w=writes;nx_exception_capture_poll();assert(writes==w&&closes==((test==0||test==4)?1:0));
 }
 reset();nx_exception_capture_stop();nx_exception_capture_prepare();assert(!creates&&!traces);
 reset();write_error=9;nx_exception_capture_prepare();assert(closes==1&&!exception_open);ThreadExceptionDump c=ctx(0x111);fault(&c);check(0x111);assert(!exception_persisted);nx_exception_capture_stop();
 reset();owned_original=1;nx_exception_capture_prepare();assert(raw_closes==1&&!closes);fault(&c);assert(exception_persisted);nx_exception_capture_stop();assert(closes==1);
 /* Failed write retains sealed original; observer poll can retry. */
 reset();nx_exception_capture_prepare();assert(disk_valid());write_error=10;fault(&c);check(0x111);assert(!exception_persisted&&exception_last_write_result==10);
 ThreadExceptionDump other=ctx(0x999);fault(&other);check(0x111);write_error=0;nx_exception_capture_poll();assert(exception_persisted&&disk_valid());nx_exception_capture_stop();
 /* A torn overwrite is rejected; retry restores a coherent record. */
 reset();nx_exception_capture_prepare();short_write=1;fault(&c);check(0x111);assert(!disk_valid());short_write=0;nx_exception_capture_poll();assert(disk_valid());nx_exception_capture_stop();
 /* Reentry inside write cannot overwrite first context or recurse into I/O. */
 reset();nx_exception_capture_prepare();reenter=1;fault(&c);check(0x111);assert(writes==2);nx_exception_capture_stop();
 /* Busy I/O lock keeps a memory copy, then a later poll persists it. */
 reset();nx_exception_capture_prepare();mutexLock(&exception_io_lock);fault(&c);check(0x111);assert(!exception_persisted);mutexUnlock(&exception_io_lock);nx_exception_capture_poll();assert(exception_persisted);nx_exception_capture_stop();
 /* Two simultaneous exceptions: only one immutable coherent payload wins. */
 reset();nx_exception_capture_prepare();pthread_t a,b;assert(!pthread_create(&a,NULL,worker,&c));assert(!pthread_create(&b,NULL,worker,&other));assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));assert(exception_record.pc==0x111||exception_record.pc==0x999);check(exception_record.pc);nx_exception_capture_poll();assert(disk_valid());nx_exception_capture_stop();
 /* Stop waits for active IPC, closes once; no operation after fence. */
 reset();nx_exception_capture_prepare();block_write=1;assert(!pthread_create(&a,NULL,worker,&c));
 pthread_mutex_lock(&gate);while(!write_entered)pthread_cond_wait(&changed,&gate);pthread_mutex_unlock(&gate);
 assert(!pthread_create(&b,NULL,stopper,NULL));while(!stop_entered)sched_yield();assert(!stop_done&&!closes);
 pthread_mutex_lock(&gate);release_write=1;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);
 assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));assert(closes==1&&stop_done);
 unsigned w=writes;nx_exception_capture_poll();fault(&other);assert(writes==w&&closes==1);
 /* Null input does not claim, and stopping before a fault still retains RAM. */
 reset();fault(NULL);assert(!exception_claim);nx_exception_capture_stop();fault(&c);check(0x111);assert(!writes);
 if(argc>1){reset();nx_exception_capture_prepare();fault(&c);FILE*f=fopen(argv[1],"wb");assert(f&&fwrite(disk,1,sizeof disk,f)==sizeof disk);assert(!fclose(f));nx_exception_capture_stop();}
 puts("PASS exception capture: open/create/session-clone/write/flush-equivalent failure, torn record/retry, reentry, first winner, stop overlap and immutable original context");return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td)
 for name in ['switch.h','config.h','libc_shim.h','exception_capture.h']:(p/name).write_text('')
 (p/'test.c').write_text(code)
 subprocess.run(['gcc','-std=c11','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-pie','-no-pie','-I'+td,str(p/'test.c'),'-o',str(p/'test')],check=True)
 record=Path(sys.argv[2]) if len(sys.argv)>2 else p/'record.bin'
 subprocess.run([str(p/'test'),str(record)],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
 import importlib.util
 spec=importlib.util.spec_from_file_location('exception_decoder',Path(__file__).parents[1]/'tools/decode_exception_record.py');decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
 data=record.read_bytes();decoded=decoder.decode(data);assert decoded['pc']==0x111 and decoded['x28']==0x101c and decoded['context_present']==1
 for corrupt in [data[:100],data[:24]+bytes([data[24]^1])+data[25:],bytes(len(data))]:
  try:decoder.decode(corrupt)
  except ValueError:pass
  else:raise AssertionError('decoder accepted bad/truncated record')
 print('PASS decoder: actual capture bytes, truncation, corruption and invalid magic')
