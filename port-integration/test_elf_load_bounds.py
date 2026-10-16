"""Run the actual so_load with tiny synthetic ELF files and host reservation stubs."""
from pathlib import Path
import os, subprocess, sys, tempfile
root=Path(sys.argv[1]);s=(root/'source/so_util.c').read_text()
a=s.index('int so_load('); loader=s[a:s.index('static Elf64_Xword so_dynamic_tag(',a)]
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "so_util.h"
static so_module *so_list;
static int finds,adds,removes,locked;
static void virtmemLock(void){assert(!locked);locked=1;}
static void virtmemUnlock(void){assert(locked);locked=0;}
static void *virtmemFindCodeMemory(size_t size,size_t align){
 assert(locked && size && !(size&(align-1)));++finds;return (void*)0x100000;
}
static void *virtmemAddReservation(void *base,size_t size){
 assert(locked && base && size);++adds;return (void*)0x200000;
}
static void virtmemRemoveReservation(void *r){assert(locked && r);++removes;}
'''+loader+r'''
static void fixture(const char *path,uint64_t vaddr,uint64_t memsz,uint64_t align,
                    int no_load,uint64_t filesz){
 unsigned char image[512]={0};
 Elf64_Ehdr h={0};memcpy(h.e_ident,ELFMAG,SELFMAG);h.e_ident[EI_CLASS]=ELFCLASS64;
 h.e_machine=EM_AARCH64;h.e_phentsize=sizeof(Elf64_Phdr);h.e_shentsize=sizeof(Elf64_Shdr);
 h.e_phnum=1;h.e_shnum=3;h.e_shstrndx=2;h.e_phoff=64;h.e_shoff=120;
 memcpy(image,&h,sizeof h);
 Elf64_Phdr p={0};p.p_type=no_load?PT_NULL:PT_LOAD;p.p_vaddr=vaddr;p.p_memsz=memsz;p.p_align=align;p.p_filesz=filesz;
 memcpy(image+64,&p,sizeof p);
 Elf64_Shdr sh[3]={{0}};
 sh[0].sh_name=1;sh[0].sh_addr=320;sh[0].sh_size=sizeof(Elf64_Sym);
 sh[1].sh_name=9;sh[1].sh_addr=360;sh[1].sh_size=1;
 sh[2].sh_offset=400;sh[2].sh_size=18;
 memcpy(image+120,sh,sizeof sh);memcpy(image+400,"\0.dynsym\0.dynstr\0x\0",18);
 FILE *f=fopen(path,"wb");assert(f);assert(fwrite(image,1,sizeof image,f)==sizeof image);assert(!fclose(f));
}
static void check(const char *path,void *base,uint64_t vaddr,uint64_t memsz,
                  uint64_t align,int no_load,uint64_t filesz,size_t limit,
                  int expect,size_t expected_size){
 fixture(path,vaddr,memsz,align,no_load,filesz);
 so_module m;finds=adds=removes=locked=0;so_list=NULL;memset(base,0xa5,131072);
 int result=so_load(&m,path,base,limit);
 if(expect){
  assert(result==0 && m.load_size==expected_size && finds==1 && adds==1 && !removes);
  assert(so_list==&m && m.so_base && m.load_memrv);
  assert(!memcmp(base,ELFMAG,SELFMAG));
  assert(((unsigned char*)base)[512]==0 && ((unsigned char*)base)[expected_size-1]==0);
  assert(((unsigned char*)base)[expected_size]==0xa5);
  free(m.so_base);
 }else{
  assert(result<0 && !finds && !adds && !removes && !m.so_base && !m.load_memrv && !so_list);
  for(size_t i=0;i<131072;++i)assert(((unsigned char*)base)[i]==0xa5);
 }
 assert(!locked);
}
int main(int argc,char **argv){
 assert(argc==2);void *base=aligned_alloc(65536,131072);assert(base);
 check(argv[1],base,0,0x1234,4096,0,512,131072,1,8192);
 check(argv[1],base,0,0x1234,8192,0,512,8192,1,8192);
 check(argv[1],base,0,8192,8192,0,512,8192,1,8192);
 check(argv[1],base,0,0x1234,65536,0,512,131072,1,65536);
 /* Preserve the existing fallback for a non-power-of-two alignment. */
 check(argv[1],base,0,0x1234,6000,0,512,131072,1,8192);
 check(argv[1],base,0,SIZE_MAX-7,4096,0,0,4096,0,0);
 check(argv[1],base,0,SIZE_MAX,4096,0,0,4096,0,0);
 check(argv[1],base,SIZE_MAX-7,16,4096,0,0,4096,0,0);
 check(argv[1],base,0,0,4096,0,0,4096,0,0);
 check(argv[1],base,0,8192,4096,1,0,8192,0,0);
 check(argv[1],base,0,8193,4096,0,512,8192,0,0);
 check(argv[1],base,0,511,4096,0,512,8192,0,0);
 check(argv[1],base,0,SIZE_MAX/2+2,UINT64_C(1)<<63,0,0,4096,0,0);
 free(base);return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(root/'source'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'fixture.elf')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS actual so_load: synthetic valid ELF alignments and invalid image sizes/spans; ASan/UBSan, host stubs only')

