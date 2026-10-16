"""Reduce dynamic retention while preserving sparse and exact Unity geometry."""
from pathlib import Path
import sys
r=Path(sys.argv[1])/'source'
p=r/'config.h';s=p.read_text();a='#define OC_DYNAMIC_SEGMENT_BYTES ((size_t)8 * 1024 * 1024)';assert s.count(a)==1
s=s.replace(a,'/* Dynamic fallback backing only; Unity slab activation stays 8 MiB. */\n#define OC_DYNAMIC_SEGMENT_BYTES ((size_t)1 * 1024 * 1024)');p.write_text(s)
p=r/'libc_shim.c';s=p.read_text()
a='#define OC_DONOR_UNITS_PER_SEGMENT \\\n  (OC_DYNAMIC_SEGMENT_BYTES / OC_HEAP_DONOR_UNIT_BYTES)';assert s.count(a)==1
s=s.replace(a,a+'''
#define OC_DONOR_UNITS_PER_UNITY_SLAB \\
  (UNITY_SLAB_CHUNK_BYTES / OC_HEAP_DONOR_UNIT_BYTES)
/* Preserve existing sparse reservation rounding independently of dynamic maps. */
#define OC_SPARSE_RESERVATION_BYTES ((size_t)8 * 1024 * 1024)
#define OC_SPARSE_RESERVATION_PAGES (OC_SPARSE_RESERVATION_BYTES / MMAP_PAGE)
_Static_assert(UNITY_SLAB_CHUNK_BYTES == (size_t)8 * 1024 * 1024 &&
               UNITY_SLAB_CHUNK_BYTES % OC_HEAP_DONOR_UNIT_BYTES == 0,
               "exact Unity source alignment must remain independent");
_Static_assert(OC_DYNAMIC_SEGMENT_BYTES >= OC_SPARSE_COMMIT_GRANULE_BYTES &&
               OC_DYNAMIC_SEGMENT_BYTES % OC_SPARSE_COMMIT_GRANULE_BYTES == 0 &&
               OC_SPARSE_RESERVATION_BYTES % OC_DYNAMIC_SEGMENT_BYTES == 0 &&
               OC_SPARSE_RESERVATION_BYTES % OC_SPARSE_COMMIT_GRANULE_BYTES == 0,
               "sparse reservations must contain complete backing granules");''')
a='    chunk, UNITY_SLAB_CHUNK_BYTES,\n    OC_DONOR_UNITS_PER_SEGMENT, 1, &source);';assert s.count(a)==1
s=s.replace(a,'    chunk, UNITY_SLAB_CHUNK_BYTES,\n    OC_DONOR_UNITS_PER_UNITY_SLAB, 1, &source);')
a=s.index('static void *oc_alloc_locked(');b=s.index('\nstatic int oc_commit_locked(',a)
s=s[:a]+s[a:b].replace('OC_DYNAMIC_SEGMENT_PAGES','OC_SPARSE_RESERVATION_PAGES')+s[b:]
s=s.replace('8 MiB segments receive physical pages only while live.','1 MiB dynamic segments receive physical pages only while live.')
s=s.replace('Sparse reservations consume complete, currently unmapped 8 MiB segments','Sparse reservations consume complete, currently unmapped dynamic segments')
p.write_text(s)
