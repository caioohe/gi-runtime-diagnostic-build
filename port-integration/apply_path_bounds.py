"""Bound the existing virtual-path copy and handle allocation failure."""
from pathlib import Path
import sys

root=Path(sys.argv[1])
path=root/'source/libc_shim.c'
source=path.read_text()
original='''char *realpath_fake(const char *path, char *resolved) {
  if (!path) return NULL;          /* POSIX: realpath(NULL,..) is an error, not a crash */
  if (!resolved) resolved = malloc(0x1000);
  strcpy(resolved, path);
  return resolved;
}'''
assert source.count(original)==1, 'unexpected realpath shim; review before patching'
replacement=Path(__file__).with_name('path_bounds.c.inc').read_text().rstrip()
path.write_text(source.replace(original,replacement))

