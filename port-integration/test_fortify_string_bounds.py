"""Actual fortified functions reject unterminated spans before OOB reads/writes."""
from pathlib import Path
import os,subprocess,sys,tempfile
s=(Path(sys.argv[1])/'source/genshin_compat.c').read_text()
def extract(name):
 start=s.index('char *'+name+'(');end=s.index('\n}',start)+2;return s[start:end]
code='''#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <string.h>
static jmp_buf failed;
static void fortify_fail(void) { longjmp(failed,1); }
'''+extract('nx_strcat_chk')+'\n'+extract('nx_strcpy_chk')+'''
int main(void) {
 static char dst[4],src[4],before[4];
 memcpy(dst,"a",2);assert(nx_strcat_chk(dst,"bc",4)==dst);assert(!strcmp(dst,"abc"));
 assert(nx_strcpy_chk(dst,"abc",4)==dst);assert(!strcmp(dst,"abc"));
 memset(dst,'d',4);memcpy(before,dst,4);
 if(!setjmp(failed)){nx_strcat_chk(dst,"",4);assert(0);}assert(!memcmp(dst,before,4));
 memset(src,'s',4);memcpy(dst,"",1);memcpy(before,dst,4);
 if(!setjmp(failed)){nx_strcpy_chk(dst,src,4);assert(0);}assert(!memcmp(dst,before,4));
 memcpy(dst,"ab",3);memcpy(before,dst,4);
 if(!setjmp(failed)){nx_strcat_chk(dst,"cd",4);assert(0);}assert(!memcmp(dst,before,4));
 if(!setjmp(failed)){nx_strcpy_chk(dst,"",0);assert(0);}
 return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual fortified string bounds, success/failure/unchanged buffers; host ASan/UBSan only')

