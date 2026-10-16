"""Actual relocation code: reject malformed later entries before earlier writes."""
from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1]);s=(r/'source/so_util.c').read_text()
code='''#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "so_util.h"
#define DT_ANDROID_RELA 0x60000011
#define DT_ANDROID_RELASZ 0x60000012
#define DT_ANDROID_RELR 0x6fffe000
#define DT_ANDROID_RELRSZ 0x6fffe001
#define RELOCATION_GROUPED_BY_INFO_FLAG 1
#define RELOCATION_GROUPED_BY_OFFSET_DELTA_FLAG 2
#define RELOCATION_GROUPED_BY_ADDEND_FLAG 4
#define RELOCATION_GROUP_HAS_ADDEND_FLAG 8
static jmp_buf failed;
static void fatal_error(const char *fmt,...) { (void)fmt;longjmp(failed,1); }
'''
code+=s[s.index('static Elf64_Xword so_dynamic_tag('):s.index('static uintptr_t so_lookup_export(')]
code+=s[s.index('typedef struct {\n  so_symbol_resolver resolver;\n  void *opaque;\n  char *error;\n  size_t error_cap;\n} PreflightContext;'):s.index('static int resolve_one(')]
code+='''
int main(void) {
 _Alignas(16) unsigned char image[512],before[512];
 Elf64_Ehdr eh={.e_shnum=1}; Elf64_Shdr sh={.sh_type=SHT_RELA,.sh_addr=128,.sh_size=2*sizeof(Elf64_Rela)};
 Elf64_Sym symbols[2]={{0},{.st_shndx=1,.st_value=48}};
 so_module m={.load_base=image,.load_size=sizeof image,.load_virtbase=(void*)0x10000,
 .elf_hdr=&eh,.sec_hdr=&sh,.shstrtab=".rela.dyn",.syms=symbols,.num_syms=2,.dynstrtab="missing",.dynstr_size=8};
 Elf64_Rela *rels=(void*)(image+128);
 for(volatile int kind=0;kind<6;kind++) {
  memset(image,0,sizeof image); sh.sh_size=2*sizeof(Elf64_Rela);
  rels[0]=(Elf64_Rela){.r_offset=16,.r_info=ELF64_R_INFO(0,R_AARCH64_RELATIVE),.r_addend=9};
  rels[1]=(Elf64_Rela){.r_offset=24,.r_info=ELF64_R_INFO(1,R_AARCH64_ABS64),.r_addend=3};
  if(kind==0)rels[1].r_offset=sizeof image-4;
  if(kind==1)rels[1].r_info=ELF64_R_INFO(99,R_AARCH64_ABS64);
  if(kind==2)rels[1].r_info=ELF64_R_INFO(0,999);
  if(kind==3)sh.sh_size++;
  if(kind==4){symbols[1].st_shndx=SHN_UNDEF;symbols[1].st_name=99;}
  if(kind==5){symbols[1].st_shndx=SHN_UNDEF;symbols[1].st_name=0;m.dynstr_size=7;}
  memcpy(before,image,sizeof image);
  if(!setjmp(failed)){so_relocate(&m);assert(!"accepted malformed relocation");}
  assert(!memcmp(before,image,sizeof image));
  symbols[1].st_shndx=1;symbols[1].st_name=0;m.dynstr_size=8;
 }
 memset(image,0,sizeof image);sh.sh_size=2*sizeof(Elf64_Rela);
 rels[0]=(Elf64_Rela){.r_offset=16,.r_info=ELF64_R_INFO(UINT32_MAX,R_AARCH64_RELATIVE),.r_addend=9};
 rels[1]=(Elf64_Rela){.r_offset=24,.r_info=ELF64_R_INFO(1,R_AARCH64_ABS64),.r_addend=3};
 assert(so_relocate(&m)==0);assert(*(uintptr_t*)(image+16)==0x10009);assert(*(uintptr_t*)(image+24)==0x10033);
 /* Undefined imports remain unresolved here, not replaced by the structural callback. */
 symbols[1].st_shndx=SHN_UNDEF;assert(so_relocate(&m)==0);assert(*(uintptr_t*)(image+24)==3);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(r/'source'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual relocation structural rejection before writes; valid/undefined import behavior preserved; host ASan/UBSan only')

