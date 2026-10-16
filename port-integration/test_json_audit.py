"""Exercise complete portable JSON module on bounded hostile synthetic input."""
from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1])
code=r'''#include "json_min.h"
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static void exercise(const char *s,size_t n) {
 JsonMinValue v,w;char out[128];int64_t i;int b;size_t count;
 if(json_min_parse(s,n,&v)!=0)return;
 json_min_string(&v,out,sizeof out);json_min_int64(&v,&i);json_min_bool(&v,&b);
 json_min_object_get(&v,"key",&w);
 if(json_min_array_count(&v,&count)==0) {
  for(size_t k=0;k<count;k++){assert(json_min_array_get(&v,k,&w)==0);json_min_string(&w,out,sizeof out);}
 }
}
int main(void) {
 JsonMinValue v;char out[16];
 const char *u="\"\\uD83D\\uDE00\"";
 assert(json_min_parse(u,strlen(u),&v)==0);assert(json_min_string(&v,out,sizeof out)==0);
 assert(!memcmp(out,"\xf0\x9f\x98\x80\0",5));
 assert(json_min_parse("[1,]",4,&v)!=0);assert(json_min_parse("{\"a\":1}x",8,&v)!=0);
 assert(json_min_parse("\"abcd\"",6,&v)==0);assert(json_min_string(&v,out,4)!=0);
 uint32_t state=0x7a9131u;
 static const char alphabet[]="[]{}\"\\,:0123456789truefalsn uabcdefABCDEF\n\t";
 for(unsigned k=0;k<20000;k++){
  size_t n=k%257;char *s=malloc(n?n:1);assert(s);
  for(size_t j=0;j<n;j++){state=state*1664525u+1013904223u;s[j]=alphabet[state%(sizeof alphabet-1)];}
  exercise(s,n);free(s);
 }
 char nested[512];memset(nested,'[',256);memset(nested+256,']',256);exercise(nested,sizeof nested);
 return 0;
}'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(r/'source'),str(p/'test.c'),str(r/'source/json_min.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS complete JSON module: Unicode/capacity/depth fixtures and 20,000 bounded synthetic inputs; host ASan/UBSan, not exhaustive fuzzing')

