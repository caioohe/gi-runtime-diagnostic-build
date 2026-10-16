from pathlib import Path
import os, subprocess, sys, tempfile
root=Path(sys.argv[1]);s=(root/'source/unity_input.c').read_text();jni=(root/'source/jni_fake.c').read_text()
for branch in ['if (input_owns_recv(ref)) return input_retain(ref);','if (input_owns_recv(ref)) { input_release(ref); return; }','input_recycle(recv); return;']:assert branch in jni
code=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <stdlib.h>
static int fail_alloc,live;
static void *event_malloc(size_t n){if(fail_alloc)return NULL;void *p=malloc(n);if(p)__atomic_add_fetch(&live,1,__ATOMIC_RELAXED);return p;}
static void event_free(void *p){__atomic_sub_fetch(&live,1,__ATOMIC_RELAXED);free(p);}
#define malloc event_malloc
#define free event_free
'''+s+r'''
#undef malloc
#undef free
static void *retain_worker(void *e){for(int i=0;i<10000;++i){assert(input_retain(e));input_release(e);}return NULL;}
static void *producer(void *arg){int key=(int)(intptr_t)arg;void *e=unity_keyevent(0,key);for(int i=0;i<10000;++i){void *d=unity_motionevent_obtain(e);assert(((UEvent*)d)->keycode==key);input_release(d);}return NULL;}
int main(void){
 void *copies[64];for(int i=0;i<64;++i)copies[i]=unity_motionevent_obtain(unity_keyevent(0,100+i));
 for(int i=0;i<64;++i){assert(((UEvent*)copies[i])->keycode==100+i);input_recycle(copies[i]);assert(((UEvent*)copies[i])->keycode==100+i);}
 pthread_t t[4];for(int i=0;i<4;++i)assert(!pthread_create(&t[i],NULL,retain_worker,copies[0]));
 for(int i=0;i<4;++i)assert(!pthread_join(t[i],NULL));
 assert(input_retain(copies[0]));input_release(copies[0]);assert(((UEvent*)copies[0])->keycode==100);
 for(int i=0;i<64;++i)input_release(copies[i]);assert(!live);
 fail_alloc=1;assert(!unity_motionevent_obtain(unity_keyevent(0,7)));fail_alloc=0;
 for(int i=0;i<4;++i)assert(!pthread_create(&t[i],NULL,producer,(void*)(intptr_t)(200+i)));
 for(int i=0;i<4;++i)assert(!pthread_join(t[i],NULL));assert(!live);
 void *borrowed=unity_keyevent(0,1);assert(input_retain(borrowed));input_release(borrowed);assert(((UEvent*)borrowed)->keycode==1);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-O1','-g','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(root/'source'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS input: 64 retained copies, recycle, allocation failure, balanced roots, concurrent retain/release and per-thread producers')

