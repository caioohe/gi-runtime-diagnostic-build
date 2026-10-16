"""Actual commit/release: retention comparison and transactional map failure."""
from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1])/'source';s=(r/'libc_shim.c').read_text();cfg=(r/'config.h').read_text()
assert '#define OC_DYNAMIC_SEGMENT_BYTES ((size_t)1 * 1024 * 1024)' in cfg
assert '#define OC_MANAGED_BYTES    ((size_t)256 * 1024 * 1024)' in cfg
assert 'chunk, UNITY_SLAB_CHUNK_BYTES,\n    OC_DONOR_UNITS_PER_UNITY_SLAB, 1, &source)' in s
reserve=s[s.index('static void *oc_alloc_locked('):s.index('static int oc_commit_locked(')]
assert 'OC_SPARSE_RESERVATION_PAGES' in reserve and 'OC_DYNAMIC_SEGMENT_PAGES' not in reserve
assert '#define OC_SPARSE_RESERVATION_BYTES ((size_t)8 * 1024 * 1024)' in s
assert '(UNITY_SLAB_CHUNK_BYTES / OC_HEAP_DONOR_UNIT_BYTES)' in s

def function(prefix):
 a=s.index(prefix);return s[a:s.index('\n}',a)+2]
functions=function('static int oc_dynamic_commit_segments_locked(')+'\n'+function('static void oc_dynamic_release_segments_locked(')
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MMAP_PAGE 4096u
#define OC_DYNAMIC_SEGMENT_BYTES ((size_t)SEG_MIB*1024u*1024u)
#define OC_DYNAMIC_SEGMENT_PAGES (OC_DYNAMIC_SEGMENT_BYTES/MMAP_PAGE)
#define OC_DYNAMIC_MAX_SEGMENTS (64u/SEG_MIB)
#define OC_HEAP_DONOR_UNIT_BYTES 65536u
#define OC_DONOR_UNITS_PER_SEGMENT (OC_DYNAMIC_SEGMENT_BYTES/OC_HEAP_DONOR_UNIT_BYTES)
#define R_FAILED(x) ((x)!=0)
typedef unsigned Result;
static unsigned char arena[64u*1024u*1024u];
static unsigned char *oc_dynamic_base=arena;
static size_t oc_dynamic_pages=sizeof(arena)/MMAP_PAGE;
static uint8_t oc_dynamic_segment_mapped[OC_DYNAMIC_MAX_SEGMENTS];
static uint32_t oc_dynamic_segment_sources[OC_DYNAMIC_MAX_SEGMENTS];
static uint32_t oc_dynamic_segment_live_pages[OC_DYNAMIC_MAX_SEGMENTS];
static uint64_t oc_dynamic_mapped_segments,oc_peak_dynamic_mapped_segments;
static unsigned calls,fail_at,backed,unmaps;
static uint8_t real_maps[OC_DYNAMIC_MAX_SEGMENTS];
static void oc_update_peak(uint64_t *p,uint64_t n){if(n>*p)*p=n;}
static void fatal_error(const char *f,...){(void)f;abort();}
static Result oc_backing_map_locked(void *p,size_t n,size_t align,int high,uint32_t *out){
 size_t i=((unsigned char*)p-arena)/OC_DYNAMIC_SEGMENT_BYTES;
 assert(i<OC_DYNAMIC_MAX_SEGMENTS&&n==OC_DYNAMIC_SEGMENT_BYTES&&align==OC_DONOR_UNITS_PER_SEGMENT&&high==1&&!real_maps[i]);
 if(++calls==fail_at)return 1;
 real_maps[i]=1;++backed;*out=(uint32_t)i+1;return 0;
}
static Result oc_backing_unmap_locked(void *p,size_t n,uint32_t source){
 size_t i=((unsigned char*)p-arena)/OC_DYNAMIC_SEGMENT_BYTES;
 assert(i<OC_DYNAMIC_MAX_SEGMENTS&&n==OC_DYNAMIC_SEGMENT_BYTES&&source==i+1&&real_maps[i]);
 real_maps[i]=0;--backed;++unmaps;return 0;
}
'''+functions+r'''
static void reset(void){
 memset(oc_dynamic_segment_mapped,0,sizeof oc_dynamic_segment_mapped);memset(oc_dynamic_segment_sources,0,sizeof oc_dynamic_segment_sources);memset(oc_dynamic_segment_live_pages,0,sizeof oc_dynamic_segment_live_pages);memset(real_maps,0,sizeof real_maps);
 oc_dynamic_mapped_segments=oc_peak_dynamic_mapped_segments=0;calls=fail_at=backed=unmaps=0;
}
int main(void){
 reset();
 /* Same 16384 distinct page allocations and lifetimes for both configurations. */
 for(size_t p=0;p<oc_dynamic_pages;++p)assert(oc_dynamic_commit_segments_locked(p,1));
 assert(backed==OC_DYNAMIC_MAX_SEGMENTS);
 for(size_t p=0;p<oc_dynamic_pages;++p)if(p%2048)oc_dynamic_release_segments_locked(p,1);
 size_t retained=(size_t)backed*OC_DYNAMIC_SEGMENT_BYTES;
 assert(retained==(size_t)SEG_MIB*8u*1024u*1024u);
 printf("dynamic=%u MiB; identical survivors=8 pages; retained=%zu MiB; maps=%u\n",SEG_MIB,retained/(1024u*1024u),calls);
 for(size_t p=0;p<oc_dynamic_pages;p+=2048)oc_dynamic_release_segments_locked(p,1);
 assert(!backed&&!oc_dynamic_mapped_segments);
 /* Failure at each new map rolls back only this transaction, not pre-existing data. */
 for(unsigned fail=1;fail<=3;++fail){
  reset();assert(oc_dynamic_commit_segments_locked(0,1));calls=0;fail_at=fail;
  assert(!oc_dynamic_commit_segments_locked(OC_DYNAMIC_SEGMENT_PAGES-1,OC_DYNAMIC_SEGMENT_PAGES*2+2));
  assert(backed==1&&oc_dynamic_mapped_segments==1&&real_maps[0]&&oc_dynamic_segment_mapped[0]&&oc_dynamic_segment_live_pages[0]==1);
  for(size_t i=1;i<OC_DYNAMIC_MAX_SEGMENTS;++i)assert(!oc_dynamic_segment_mapped[i]&&!oc_dynamic_segment_sources[i]&&!oc_dynamic_segment_live_pages[i]&&!real_maps[i]);
  fail_at=0;assert(oc_dynamic_commit_segments_locked(OC_DYNAMIC_SEGMENT_PAGES-1,OC_DYNAMIC_SEGMENT_PAGES*2+2));
  oc_dynamic_release_segments_locked(OC_DYNAMIC_SEGMENT_PAGES-1,OC_DYNAMIC_SEGMENT_PAGES*2+2);
  assert(backed==1&&oc_dynamic_segment_live_pages[0]==1);oc_dynamic_release_segments_locked(0,1);assert(!backed);
 }
 reset();assert(!oc_dynamic_commit_segments_locked(0,0));assert(!oc_dynamic_commit_segments_locked(oc_dynamic_pages,1));assert(!oc_dynamic_commit_segments_locked(oc_dynamic_pages-1,2));assert(!calls);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'probe.c').write_text(code)
 for mib in [8,1]:
  subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DSEG_MIB='+str(mib),str(p/'probe.c'),'-o',str(p/'probe')],check=True)
  subprocess.run([str(p/'probe')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual dynamic commit/release: same-lifetime comparison, cross-boundary rollback/retry preserving existing pages, invalid bounds; host map stubs only')
