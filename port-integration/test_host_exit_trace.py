from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1]);s=(r/'source/host_exit_trace.c').read_text();s=s.replace('#include <switch.h>','').replace('#include "guest_termination.h"','')
code='''#include <assert.h>
#include <stdarg.h>
#include <setjmp.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
typedef unsigned Result;
Result fsdevUnmountAll(void);
static jmp_buf finished;static int steps,logs,stages,status_seen;static int calls[7];
static const char *stage;
static void nx_guest_termination_set_stage(const char*s){stage=s;++stages;}
static void memory_runtime_trace(const char*f,...){(void)f;++logs;errno=99;}
static void nx_shutdown_observer_stop(void){}
static void nx_guest_thread_observer_counters(unsigned long long*a,unsigned long long*b){*a=22;*b=4;}
static int appletGetAppletType(void){return 2;}
static int envIsNso(void){return 0;}
static void dummy(void){}
static void (*envGetExitFuncPtr(void))(void){return dummy;}
'''+s+'\n'
names=['__nx_win_exit','fsdevUnmountAll','fsExit','timeExit','hidExit','appletExit','smExit']
for i,n in enumerate(names):
 ret='Result' if n=='fsdevUnmountAll' else 'void'
 tail='return 0x12345;' if ret=='Result' else ''
 code+=f'{ret} __real_{n}(void){{++calls[{i}];if(host_exit_depth)assert(steps++=={i});errno=12;{tail}}}\n'
code+='void __real___libnx_exit(int n){status_seen=n;assert(errno==42);'+''.join('assert(__wrap_fsdevUnmountAll()==0x12345);' if n=='fsdevUnmountAll' else '__wrap_'+n+'();' for n in names)+'longjmp(finished,1); }\n'
code+='''int main(void){
 errno=42;
 __wrap_fsExit();assert(calls[2]==1&&errno==12&&logs==0&&stages==0);
 calls[2]=0;errno=42;
 if(!setjmp(finished))__wrap___libnx_exit(7);
 assert(status_seen==7&&steps==7&&logs==7&&stages==17&&errno==12);
 for(int i=0;i<7;i++)assert(calls[i]==1);
 assert(stage!=NULL);return 0;
}'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual host exit wrappers: inactive forwarding, ordered cleanup checkpoints, unchanged status and errno; host stubs, no Horizon exit')

