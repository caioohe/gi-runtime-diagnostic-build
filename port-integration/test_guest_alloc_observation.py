"""Exercise actual observed memalign wrapper and snapshot code with host stubs."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(sys.argv[1]);r=root/'source';source=(r/'imports.c').read_text();a=source.index('static void *nx_guest_memalign(');b=source.index('\nstatic int nx_guest_posix_memalign',a);wrapper=source[a:b]
assert source.index('#define _GNU_SOURCE')<source.index('#include "guest_alloc_observation.h"'), 'Observation header must follow feature macros'
main=(r/'main.c').read_text();assert main.count('nx_guest_alloc_sample(), render(')==2
assert main.index('supported original image fingerprints')<main.index('nx_guest_alloc_bind(')
code=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <sys/mman.h>
#include <stdio.h>
#include "guest_alloc_observation.h"
static unsigned primary_ok,fallback_ok;
static void *nx_primary_memalign(size_t a,size_t n){assert(a==16&&n==1440);if(primary_ok)return (void*)0x1230;errno=12;return NULL;}
static void *nx_sparse_pool_spill_alloc_aligned(size_t n,size_t a){assert(a==16&&n==1440);if(fallback_ok)return (void*)0x4560;errno=34;return NULL;}
''' + (r/'guest_alloc_observation.c').read_text() + wrapper + r'''
static void *failer(void *p){uintptr_t n=(uintptr_t)p;for(unsigned i=0;i<10000;i++)nx_guest_alloc_failed(n,16,n+100,12,34);return NULL;}
static void *sampler(void *p){(void)p;for(unsigned i=0;i<10000;i++)nx_guest_alloc_sample();return NULL;}
int main(void){
 uint64_t out[18];primary_ok=1;errno=7;assert(nx_guest_memalign(16,1440)==(void*)0x1230&&errno==7);
 primary_ok=0;fallback_ok=1;errno=7;assert(nx_guest_memalign(16,1440)==(void*)0x4560&&errno==7);
 fallback_ok=0;errno=7;assert(!nx_guest_memalign(16,1440)&&errno==12);
 nx_guest_alloc_snapshot(out);assert(out[0]==1&&out[1]==3&&out[2]==2&&out[3]==1&&out[4]==2);
 assert(out[5]==1440&&out[6]==16&&out[7]&&out[8]==12&&out[9]==34);
 nx_guest_alloc_failed(999,32,888,1,2);nx_guest_alloc_snapshot(out);assert(out[5]==1440&&out[3]==2);
 first_state=1;nx_guest_alloc_snapshot(out);assert(out[4]==1&&!out[5]&&!out[9]);first_state=0;
 pthread_t a,b;assert(!pthread_create(&a,NULL,failer,(void*)111));assert(!pthread_create(&b,NULL,failer,(void*)222));
 for(unsigned i=0;i<10000;i++){nx_guest_alloc_snapshot(out);if(out[4]==2)assert((out[5]==111||out[5]==222)&&out[7]==out[5]+100&&out[8]==12&&out[9]==34);}
 assert(!pthread_join(a,NULL)&&!pthread_join(b,NULL));nx_guest_alloc_snapshot(out);assert(out[3]==20002);
 nx_guest_alloc_bind(0,0);nx_guest_alloc_sample();nx_guest_alloc_snapshot(out);assert(!out[10]);
 nx_guest_alloc_bind(UINTPTR_MAX-16,0x161e0000);nx_guest_alloc_sample();nx_guest_alloc_snapshot(out);assert(!out[10]);
 unsigned char *base=mmap(NULL,0x161e0000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(base!=MAP_FAILED);
 uintptr_t manager=(uintptr_t)base+0x15fd12c0;
 __atomic_store_n((uintptr_t *)(base+0x15fd51b0),manager,__ATOMIC_RELAXED);
 *(unsigned char *)(manager+0xc4d)=1;*(unsigned char *)(manager+0xc4e)=1;*(unsigned char *)(manager+0xc4f)=0;
 *(uintptr_t *)(manager+0xc60)=0x100;*(uintptr_t *)(manager+0xc70)=0x200;*(uintptr_t *)(manager+0x1ec8)=0x300;base[0x15fd5200]=1;
 nx_guest_alloc_bind((uintptr_t)base,0x161e0000);nx_guest_alloc_sample();nx_guest_alloc_snapshot(out);
 assert(out[10]==1&&out[11]==manager&&out[12]==0x101&&out[13]==0x100&&out[14]==0x200&&out[15]==0x300&&out[16]==1&&!(out[17]&1));
 assert(!pthread_create(&a,NULL,sampler,NULL));for(unsigned i=0;i<10000;i++){nx_guest_alloc_snapshot(out);if(out[10])assert(out[11]==manager&&out[12]==0x101&&out[15]==0x300);}
 assert(!pthread_join(a,NULL));cache_seq|=1;nx_guest_alloc_snapshot(out);assert(!out[10]&&!out[11]);cache_seq++;
 /* Foreign, unaligned and boundary-crossing pointers are recorded but not followed. */
 for(unsigned i=0;i<3;i++){*(uintptr_t *)(base+0x15fd51b0)=i==0?1:i==1?manager+1:(uintptr_t)base+0x161def08;nx_guest_alloc_sample();nx_guest_alloc_snapshot(out);assert(!out[10]);}
 assert(!munmap(base,0x161e0000));nx_guest_alloc_bind(0,0);nx_guest_alloc_sample();
 puts("PASS actual guest memalign outcome/errno, first failure publication, races, cached manager bounds and no-wait snapshots");
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'guest_alloc_observation.h').write_text((r/'guest_alloc_observation.h').read_text());(p/'test.c').write_text(code)
 subprocess.run(['gcc','-std=c11','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-pie','-no-pie','-I'+td,str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
