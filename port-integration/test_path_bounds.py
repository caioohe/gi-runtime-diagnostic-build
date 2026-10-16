"""Test the actual integrated path-copy C on the host, including OOM.

This is not a test of realpath canonicalization or the Switch filesystem.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

source=(Path(sys.argv[1])/'source/libc_shim.c').read_text()
start=source.index('char *realpath_fake(')
function=source[start:source.index('\n}',start)+2]
harness=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static unsigned alloc_calls;
static int fail_alloc;
static void *test_malloc(size_t n) {
  ++alloc_calls;assert(n==4096);return fail_alloc?NULL:malloc(n);
}
#define malloc test_malloc
'''+function+r'''
#undef malloc
int main(void) {
  char input[5001];memset(input,'X',5000);input[5000]=0;
  struct { char output[4096]; unsigned char guard[8]; } b;
  memset(&b,0x55,sizeof b);
  errno=0;assert(!realpath_fake(NULL,NULL) && errno==EINVAL && alloc_calls==0);
  errno=0;assert(!realpath_fake(input,NULL) && errno==ENAMETOOLONG && alloc_calls==0);
  errno=0;assert(!realpath_fake(input,b.output) && errno==ENAMETOOLONG);
  for(size_t i=0;i<sizeof b;i++) assert(((unsigned char *)&b)[i]==0x55);
  input[4096]=0;errno=0;
  assert(!realpath_fake(input,NULL) && errno==ENAMETOOLONG && alloc_calls==0);
  input[4095]=0;
  char *p=realpath_fake(input,NULL);assert(p && strlen(p)==4095 && !strcmp(p,input));free(p);
  assert(realpath_fake(input,b.output)==b.output && !strcmp(b.output,input));
  for(size_t i=0;i<sizeof b.guard;i++) assert(b.guard[i]==0x55);
  const char *paths[]={"","sdmc:/switch/genshinimpact_nx/assets","/data/user/0/com.miHoYo.GenshinImpact/files","../assets","relative/path"};
  for(size_t i=0;i<sizeof paths/sizeof paths[0];i++) {
    p=realpath_fake(paths[i],NULL);assert(p && !strcmp(p,paths[i]));free(p);
    unsigned before=alloc_calls;
    assert(realpath_fake(paths[i],b.output)==b.output && !strcmp(b.output,paths[i]));
    assert(alloc_calls==before);
  }
  fail_alloc=1;errno=0;
  assert(!realpath_fake("relative/path",NULL) && errno==ENOMEM);
  assert(realpath_fake("relative/path",b.output)==b.output && !strcmp(b.output,"relative/path"));
  puts("PASS path bounds: null, 5000/4096/4095 bytes, destination preservation, five path forms, allocation failure");
}
'''
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(root/'test.c'),'-o',str(root/'test')],check=True)
    subprocess.run([str(root/'test')],check=True,env=os.environ)

