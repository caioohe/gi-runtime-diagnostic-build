/* Diagnostic observations only. No allocation, I/O, locks or retry loops. */
#include "guest_alloc_observation.h"
static uint64_t calls,primary_failures,final_failures;
static unsigned first_state;
static uint64_t first[5];
static uintptr_t module_base;static size_t module_size;
static uint64_t cache[8],cache_seq;
void nx_guest_alloc_attempt(void){__atomic_fetch_add(&calls,1,__ATOMIC_RELAXED);}
void nx_guest_alloc_primary_failed(void){__atomic_fetch_add(&primary_failures,1,__ATOMIC_RELAXED);}
void nx_guest_alloc_failed(size_t size,size_t align,uintptr_t caller,int primary_error,int final_error){
 __atomic_fetch_add(&final_failures,1,__ATOMIC_RELAXED);
 unsigned expected=0;
 if(!__atomic_compare_exchange_n(&first_state,&expected,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED))return;
 first[0]=size;first[1]=align;first[2]=caller;first[3]=(uint32_t)primary_error;first[4]=(uint32_t)final_error;
 __atomic_store_n(&first_state,2,__ATOMIC_RELEASE);
}
/* Single normal startup/render thread owns bind/sample. No exception-side
 * reads of guest pointers. Bind is called only after supported-image checks. */
void nx_guest_alloc_bind(uintptr_t base,size_t bytes){module_base=base;module_size=bytes;}
static int in_rw(uintptr_t p,size_t bytes){
 if(!module_base||module_size<0x161def10u||module_base>UINTPTR_MAX-module_size)return 0;
 const uintptr_t lo=module_base+0x1587ad80u,hi=module_base+0x161def10u;
 return p>=lo&&p<=hi&&bytes<=hi-p;
}
void nx_guest_alloc_sample(void){
 uint64_t data[8]={0};
 if(module_base&&module_base<=UINTPTR_MAX-0x15fd51b0u&&in_rw(module_base+0x15fd51b0u,8)){
  uintptr_t manager=__atomic_load_n((uintptr_t *)(module_base+0x15fd51b0u),__ATOMIC_RELAXED);
  data[1]=manager;
  if(!(manager&7u)&&in_rw(manager,0x2930u)){
   data[0]=1;
   data[2]=__atomic_load_n((unsigned char *)(manager+0xc4du),__ATOMIC_RELAXED)|
    ((uint64_t)__atomic_load_n((unsigned char *)(manager+0xc4eu),__ATOMIC_RELAXED)<<8)|
    ((uint64_t)__atomic_load_n((unsigned char *)(manager+0xc4fu),__ATOMIC_RELAXED)<<16);
   data[3]=__atomic_load_n((uintptr_t *)(manager+0xc60u),__ATOMIC_RELAXED);
   data[4]=__atomic_load_n((uintptr_t *)(manager+0xc70u),__ATOMIC_RELAXED);
   data[5]=__atomic_load_n((uintptr_t *)(manager+0x1ec8u),__ATOMIC_RELAXED);
   data[6]=__atomic_load_n((unsigned char *)(module_base+0x15fd5200u),__ATOMIC_RELAXED);
  }
 }
 uint64_t seq=__atomic_load_n(&cache_seq,__ATOMIC_RELAXED);
 __atomic_store_n(&cache_seq,seq+1,__ATOMIC_SEQ_CST);
 for(unsigned i=0;i<8;i++)__atomic_store_n(&cache[i],data[i],__ATOMIC_SEQ_CST);
 __atomic_store_n(&cache_seq,seq+2,__ATOMIC_SEQ_CST);
}
void nx_guest_alloc_snapshot(uint64_t out[NX_ALLOC_OBSERVATION_WORDS]){
 for(unsigned i=0;i<NX_ALLOC_OBSERVATION_WORDS;i++)out[i]=0;
 out[0]=1;out[1]=__atomic_load_n(&calls,__ATOMIC_RELAXED);
 out[2]=__atomic_load_n(&primary_failures,__ATOMIC_RELAXED);out[3]=__atomic_load_n(&final_failures,__ATOMIC_RELAXED);
 unsigned state=__atomic_load_n(&first_state,__ATOMIC_ACQUIRE);out[4]=state;
 if(state==2)for(unsigned i=0;i<5;i++)out[5+i]=first[i];
 uint64_t before=__atomic_load_n(&cache_seq,__ATOMIC_SEQ_CST);
 if(!(before&1u)){
  for(unsigned i=0;i<8;i++)out[10+i]=__atomic_load_n(&cache[i],__ATOMIC_SEQ_CST);
  uint64_t after=__atomic_load_n(&cache_seq,__ATOMIC_SEQ_CST);
  if(before!=after)for(unsigned i=10;i<NX_ALLOC_OBSERVATION_WORDS;i++)out[i]=0;
 }
 /* Cache generation occupies the reserved final word; validity is word10.
  * A valid sample is a prior normal boundary, not the instantaneous fault. */
 out[17]=before;
}
