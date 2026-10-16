"""Execute the actual integrated APS2 parser with synthetic streams on the host."""
from pathlib import Path
import os, subprocess, sys, tempfile
s=(Path(sys.argv[1])/'source/so_util.c').read_text()
parser=s[s.index('typedef struct {\n  const uint8_t *cur;'):s.index('static int relocate_one(')]
def sleb(n):
    out=[]
    while True:
        b=n&127; n >>= 7
        done=(n==0 and not b&64) or (n==-1 and b&64)
        out.append(b if done else b|128)
        if done:return bytes(out)
def stream(nums):return b'APS2'+b''.join(sleb(n) for n in nums)
hi=(1<<63)-1; lo=-(1<<63)
cases=[
 ('addend-overflow',[2,0,2,11,0,0,hi,1],-2,[(0,0,hi)]),
 ('addend-underflow',[2,0,2,11,0,0,lo,-1],-2,[(0,0,lo)]),
 ('valid-boundaries',[3,0,3,11,8,7,hi,lo,1],1,[(8,7,hi),(16,7,-1),(24,7,0)]),
 ('valid-grouped',[2,0,2,15,8,9,-4],1,[(8,9,-4),(16,9,-8)]),
 ('valid-negative-offset',[2,24,2,1,5,-8,-8],1,[(16,5,0),(8,5,0)]),
 ('offset-underflow',[1,0,1,3,-1,0],-2,[]),
 ('offset-int64-min',[1,0,1,3,lo,0],-2,[]),
 ('offset-large-sum',[1,hi,1,3,hi,0],-2,[]),
 ('valid-negative-initial',[1,-8,1,3,16,0],1,[(8,0,0)]),
 ('zero-relocations',[0,0],1,[]),
 ('truncated',[1,0,1,11,0,0],-2,[]),
 ('group-too-large',[1,0,2,3,0,0],-2,[]),
 ('callback-error',[1,0,1,3,8,0],-1,[(8,0,0)]),
]
code='''#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#include <elf.h>
#define DT_ANDROID_RELA 0x60000011
#define DT_ANDROID_RELASZ 0x60000012
#define RELOCATION_GROUPED_BY_INFO_FLAG 1
#define RELOCATION_GROUPED_BY_OFFSET_DELTA_FLAG 2
#define RELOCATION_GROUPED_BY_ADDEND_FLAG 4
#define RELOCATION_GROUP_HAS_ADDEND_FLAG 8
typedef struct { void *load_base; size_t load_size; } so_module;
static size_t packed_length, packed_offset=8, calls;
static int callback_error;
static Elf64_Rela received[8];
static Elf64_Xword so_dynamic_tag(so_module *m, Elf64_Sxword t) {
 (void)m; return t==DT_ANDROID_RELA ? packed_offset : packed_length;
}
static int accept(so_module *m,const Elf64_Rela *r,void *o) {
 (void)m;(void)o; assert(calls<8); received[calls++]=*r;return callback_error;
}
'''+parser+'\nint main(void){ unsigned char b[256]; so_module m={b,sizeof b};\n'
def add_case(data,result,expected,extra=''):
    global code
    code+='{ unsigned char p[]={'+','.join(map(str,data))+'}; memset(b,0,sizeof b); memcpy(b+packed_offset,p,sizeof p); packed_length=sizeof p; calls=0; callback_error=0; m.load_size=sizeof b; '+extra+f' assert(so_iterate_android_rela(&m,accept,0)=={result}); assert(calls=={len(expected)});'
    for i,(off,info,add) in enumerate(expected):
        literal='INT64_MIN' if add==lo else str(add)+'LL'
        code+=f'assert(received[{i}].r_offset=={off}ULL && received[{i}].r_info=={info}ULL && received[{i}].r_addend=={literal});'
    code+='}\n'
for name,nums,result,expected in cases:
    add_case(stream(nums),result,expected,'callback_error=1;' if name=='callback-error' else '')
for tenth in [1,0x7e,0x80,0xff]:
    add_case(b'APS2'+bytes([0x80]*9+[tenth]),-2,[])
# Directly exercise the real decoder at both signed endpoints and malformed encodings.
for n in [hi,lo,0,127,-128]:
    data=sleb(n); literal='INT64_MIN' if n==lo else str(n)+'LL'
    code+='{uint8_t p[]={'+','.join(map(str,data))+f'}}; SlebReader r={{p,p+sizeof p,0}};assert(sleb128_read(&r)=={literal} && !r.failed && r.cur==r.end);}}\n'
# Tiny mapped span is rejected by packed-span validation before any callback.
add_case(stream([1,0,1,3,0,0]),-2,[],'m.load_size=7; packed_offset=8;')
code+='return 0;}\n'
with tempfile.TemporaryDirectory() as td:
    p=Path(td); (p/'test.c').write_text(code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('APS2 actual-parser synthetic positive/negative fixtures passed (ASan/UBSan; no hardware).')

