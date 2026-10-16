from pathlib import Path
import subprocess, sys, tempfile
root=Path(sys.argv[1]);s=(root/'source/plugin_loader.c').read_text()
a=s.index('static void loader_lock(');b=s.index('static void set_error(',a)
assert '"r"(value) : "memory"' in (root/'source/main.c').read_text()
code=r'''
#include <assert.h>
#include <stdint.h>
#include <pthread.h>
typedef uintptr_t Handle;
static pthread_mutex_t g_loader_lock=PTHREAD_MUTEX_INITIALIZER;
static Handle g_loader_owner;
static unsigned g_loader_depth;
static Handle threadGetCurHandle(void){return (Handle)pthread_self();}
static void mutexLock(pthread_mutex_t *m){assert(!pthread_mutex_lock(m));}
static void mutexUnlock(pthread_mutex_t *m){assert(!pthread_mutex_unlock(m));}
'''+s[a:b]+r'''
static unsigned counter;
static void *worker(void *unused){(void)unused;for(int i=0;i<20000;++i){loader_lock();loader_lock();loader_lock();++counter;loader_unlock();loader_unlock();loader_unlock();}return NULL;}
int main(void){pthread_t t[6];for(int i=0;i<6;++i)assert(!pthread_create(&t[i],NULL,worker,NULL));for(int i=0;i<6;++i)assert(!pthread_join(t[i],NULL));assert(counter==120000 && !g_loader_depth && !g_loader_owner);return 0;}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,timeout=30)
print('PASS actual recursive loader lock: six host threads, 120000 updates, triple recursion; TLS memory clobber present')

