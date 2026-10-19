"""Add bounded guest memalign observations; preserve allocator decisions/errno."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);r=root/'source';here=Path(__file__).parent
for name in ['guest_alloc_observation.c','guest_alloc_observation.h']:
 (r/name).write_text((here/(name+'.inc')).read_text())
p=r/'imports.c';s=p.read_text();s='#include "guest_alloc_observation.h"\n'+s
start=s.index('static void *nx_guest_memalign(');end=s.index('\nstatic int nx_guest_posix_memalign',start)
b=s[start:end]
a='  const int caller_errno = errno;';assert b.count(a)==1;b=b.replace(a,a+'\n  nx_guest_alloc_attempt();')
a='  const int allocator_errno = errno;';assert b.count(a)==1;b=b.replace(a,a+'\n  nx_guest_alloc_primary_failed();')
a='  errno = allocator_errno;\n  return NULL;';assert b.count(a)==1;b=b.replace(a,'  nx_guest_alloc_failed(size, alignment, (uintptr_t)__builtin_extract_return_addr(__builtin_return_address(0)), allocator_errno, errno);\n'+a)
s=s[:start]+b+s[end:];p.write_text(s)
p=r/'main.c';s=p.read_text();s='#include "guest_alloc_observation.h"\n'+s
a='  g_il2cpp_base=(uintptr_t)game_mod.load_virtbase; g_il2cpp_size=game_mod.load_size;';assert s.count(a)==1;s=s.replace(a,a+'\n  nx_guest_alloc_bind((uintptr_t)game_mod.load_virtbase,game_mod.load_size);\n  nx_guest_alloc_sample();')
a='render(fake_env,fake_unityplayer_thiz)';assert s.count(a)==2
s=s.replace(a,'(nx_guest_alloc_sample(), render(fake_env,fake_unityplayer_thiz))');p.write_text(s)
