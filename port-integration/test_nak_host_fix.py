from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1]);nak=(r/'source/nak_host_tls.c').read_text();alloc=Path(__file__).with_name('newlib_nak_alloc.c.inc').read_text();assert alloc in (r/'source/memory_broker.c').read_text()
def fn(marker):
 s=(r/'source/util.c').read_text();a=s.index(marker);return s[a:s.index('\n}',a)+2]
enter=fn('uintptr_t nx_compiler_host_tls_enter(');leave=fn('void nx_compiler_host_tls_leave(')
code=r'''
#include <assert.h>
#include <pthread.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
struct _reent{int _errno;};
static _Thread_local struct _reent current_reent;
#undef errno
#define errno (current_reent._errno)
static _Thread_local uintptr_t tp,soft_tp;
static uintptr_t read_thread_pointer(void){return tp;}
static void write_thread_pointer(uintptr_t p){tp=p;}
static void *__aarch64_read_tp(void){return (void*)soft_tp;}
static void memory_runtime_trace(const char*f,...){(void)f;assert(tp==soft_tp);}
'''+enter+'\n'+leave+'\n'+nak+r'''
static _Thread_local int fail_malloc,fail_realloc,fail_fallback,primary_calls,fallback_calls,freed,probe_internal;
void *__wrap__malloc_r(struct _reent*,size_t);
static _Thread_local void *pool;
static _Thread_local size_t pool_size;
static void *__real__malloc_r(struct _reent*r,size_t n){++primary_calls;if(fail_malloc){r->_errno=ENOMEM;return NULL;}return malloc(n);}
static void *__real__realloc_r(struct _reent*r,void*p,size_t n){if(probe_internal){void*q=__wrap__malloc_r(r,n);assert(!q);r->_errno=ENOMEM;return NULL;}if(fail_realloc&&n){r->_errno=ENOMEM;return NULL;}return realloc(p,n);}
static void __real__free_r(struct _reent*r,void*p){(void)r;++freed;assert(!p||p!=pool);free(p);}
static size_t __real_malloc_usable_size(void*p){(void)p;return 8;}
static int nx_sparse_pool_contains_address(void*p){return p&&p==pool;}
static void *host_pool_fallback(size_t n,size_t a,int clear){assert(a==_Alignof(max_align_t));errno=EAGAIN;++fallback_calls;if(fail_fallback)return NULL;pool=clear?calloc(1,n):malloc(n);pool_size=n;return pool;}
static void __wrap_free(void*p){assert(p==pool);pool=NULL;free(p);}
static void *__wrap_realloc(void*p,size_t n){assert(p==pool);if(n&&fail_realloc){errno=ENOMEM;return NULL;}if(!n){__wrap_free(p);return NULL;}void*q=realloc(p,n);if(q){pool=q;pool_size=n;}return q;}
static void *__real__calloc_r(struct _reent*r,size_t n,size_t z){if(n&&z>SIZE_MAX/n){r->_errno=ENOMEM;return NULL;}void*p=__wrap__malloc_r(r,n*z);assert(!p||p!=pool);if(p)memset(p,0,n*z);return p;}
static void *__real__memalign_r(struct _reent*r,size_t a,size_t n){(void)a;void*p=__wrap__malloc_r(r,n);assert(!p||p!=pool);return p;}
'''+alloc+r'''
bool __real_nak_should_print_nir(void){assert(tp==soft_tp);return true;}
bool __real_nak_debug_no_ugpr(void){assert(tp==soft_tp);return false;}
struct nak_compiler *__real_nak_compiler_create(const struct nv_device_info*d){assert(tp==soft_tp&&d==(void*)1);return (void*)2;}
void __real_nak_compiler_destroy(struct nak_compiler*n){assert(tp==soft_tp&&n==(void*)2);}
uint64_t __real_nak_debug_flags(const struct nak_compiler*n){assert(tp==soft_tp&&n==(void*)2);return 9;}
const struct nir_shader_compiler_options *__real_nak_nir_options(const struct nak_compiler*n){assert(tp==soft_tp&&n==(void*)2);return (void*)3;}
uint32_t __real_nak_max_warps_per_sm(uint32_t g,const struct nak_compiler*n){assert(tp==soft_tp&&g==7&&n==(void*)2);return 4;}
void __real_nak_shader_bin_destroy(struct nak_shader_bin*b){assert(tp==soft_tp&&b==(void*)4);}
static _Thread_local int null_shader;
struct nak_shader_bin *__real_nak_compile_shader(struct nir_shader*n,bool dump,const struct nak_compiler*k,uint32_t modes,const struct nak_fs_key*key,bool task){assert(tp==soft_tp&&nx_nak_host_active());assert(n==(void*)5&&dump&&k==(void*)2&&modes==123&&key==(void*)6&&task);assert(__wrap_nak_debug_flags(k)==9&&tp==soft_tp);errno=EIO;return null_shader?NULL:(void*)4;}
bool __real_u_memstream_open(struct u_memstream*m,char**b,size_t*z){(void)m;(void)b;(void)z;errno=ENOMEM;return false;}
int __real_u_memstream_flush(struct u_memstream*m){(void)m;errno=EIO;return -1;}
static void *run(void*arg){
 soft_tp=(uintptr_t)arg;tp=soft_tp+100;
 assert(__wrap_nak_should_print_nir()&&!__wrap_nak_debug_no_ugpr());
 assert(__wrap_nak_compiler_create((void*)1)==(void*)2);__wrap_nak_compiler_destroy((void*)2);
 assert(__wrap_nak_nir_options((void*)2)==(void*)3&&__wrap_nak_max_warps_per_sm(7,(void*)2)==4);__wrap_nak_shader_bin_destroy((void*)4);
 for(null_shader=0;null_shader<2;null_shader++){assert(__wrap_nak_compile_shader((void*)5,true,(void*)2,123,(void*)6,true)==(null_shader?NULL:(void*)4));assert(tp==soft_tp+100&&!nx_nak_host_active()&&errno==EIO);}
 /* Memstream failures are recorded before caller unwrap, errno retained. */
 uintptr_t saved=nak_enter();struct u_memstream m;char*b=NULL;size_t z=0;assert(!__wrap_u_memstream_open(&m,&b,&z)&&errno==ENOMEM);assert(__wrap_u_memstream_flush(&m)==-1&&errno==EIO);nak_leave(saved);
 struct _reent rr={42};__wrap__free_r(&rr,NULL);fail_malloc=1;void*p=__wrap__malloc_r(&rr,8);assert(!p&&fallback_calls==0&&rr._errno==ENOMEM);
 saved=nak_enter();rr._errno=42;p=__wrap__malloc_r(&rr,8);assert(p==pool&&rr._errno==42);memset(p,0x5a,8);p=__wrap__realloc_r(&rr,p,16);assert(p==pool&&((unsigned char*)p)[0]==0x5a);nak_leave(saved);
 /* Different explicit reent: failure updates it, leaves caller errno/content. */
 fail_realloc=1;rr._errno=42;errno=EDOM;
 void *failed_pool=__wrap__realloc_r(&rr,p,32);
 assert(!failed_pool&&rr._errno==ENOMEM&&errno==EDOM&&((unsigned char*)p)[0]==0x5a);
 current_reent._errno=42;
 assert(!__wrap__realloc_r(&current_reent,p,32)&&errno==ENOMEM&&((unsigned char*)p)[0]==0x5a);
 fail_realloc=0;rr._errno=42;errno=EDOM;
 p=__wrap__realloc_r(&rr,p,24);assert(p&&rr._errno==42&&errno==EDOM);
 assert(!__wrap__realloc_r(&rr,p,0)&&rr._errno==42);assert(!pool);
 saved=nak_enter();fail_fallback=1;rr._errno=42;assert(!__wrap__malloc_r(&rr,8)&&rr._errno==ENOMEM);fail_fallback=0;fail_malloc=0;
 p=__wrap__malloc_r(&rr,8);memset(p,0x5a,8);fail_realloc=1;rr._errno=42;void*q=__wrap__realloc_r(&rr,p,16);assert(q==pool&&rr._errno==42&&((unsigned char*)q)[7]==0x5a);__wrap__free_r(&rr,q);
 p=malloc(8);memset(p,0x5a,8);fail_fallback=1;q=__wrap__realloc_r(&rr,p,16);assert(!q&&((unsigned char*)p)[7]==0x5a);fail_fallback=0;fail_realloc=0;__wrap__free_r(&rr,p);nak_leave(saved);
 /* Newlib routines must never inspect a sparse pointer's heap header. */
 saved=nak_enter();fail_malloc=1;rr._errno=42;
 q=__wrap__calloc_r(&rr,2,8);assert(q==pool&&rr._errno==42);for(int j=0;j<16;j++)assert(!((unsigned char*)q)[j]);__wrap__free_r(&rr,q);
 assert(!__wrap__memalign_r(&rr,16,8)&&!pool);
 p=malloc(8);memset(p,0x5a,8);probe_internal=1;rr._errno=42;q=__wrap__realloc_r(&rr,p,16);assert(q==pool&&rr._errno==42&&((unsigned char*)q)[7]==0x5a);__wrap__free_r(&rr,q);probe_internal=0;
 int attempts=fallback_calls;assert(!__wrap__calloc_r(&rr,SIZE_MAX,2)&&rr._errno==ENOMEM&&fallback_calls==attempts);
 nak_leave(saved);fail_malloc=0;
 /* Already-host and nested scopes preserve the actual entering TP. */
 tp=soft_tp;saved=nak_enter();uintptr_t nested=nak_enter();nak_leave(nested);assert(tp==soft_tp&&nx_nak_host_active());nak_leave(saved);assert(tp==soft_tp&&!nx_nak_host_active());return NULL;
}
int main(void){run((void*)1);pthread_t t[4];for(uintptr_t i=0;i<4;i++)assert(!pthread_create(&t[i],NULL,run,(void*)(i+2)));for(int i=0;i<4;i++)assert(!pthread_join(t[i],NULL));return 0;}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'sys').mkdir();(p/'sys/reent.h').write_text('');(p/'util.h').write_text('');(p/'test.c').write_text(code)
 subprocess.run(['gcc','-O1','-g','-pthread','-fsanitize=address,undefined','-I'+td,str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual NAK wrappers/scoped newlib allocation: ABI forwarding, 5 threads, nested soft TLS, primary/fallback success/failure, realloc preservation, pool release and errno; host stubs')

