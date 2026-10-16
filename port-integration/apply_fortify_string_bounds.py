"""Bound fortified string scans before copying or raising the existing failure."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'source/genshin_compat.c';s=p.read_text()
old='  if (strlen(dst) + strlen(src) + 1 > dst_size) fortify_fail();'
assert s.count(old)==1
s=s.replace(old,'''  const size_t used = strnlen(dst, dst_size);
  if (used == dst_size || strnlen(src, dst_size - used) == dst_size - used)
    fortify_fail();''')
old='  if (strlen(src) + 1 > dst_size) fortify_fail();'
assert s.count(old)==1
s=s.replace(old,'  if (strnlen(src, dst_size) == dst_size) fortify_fail();')
p.write_text(s)

