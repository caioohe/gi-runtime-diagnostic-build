"""Check ELF image rounding and final LOAD spans before touching the image."""
from pathlib import Path
import sys
path=Path(sys.argv[1])/'source/so_util.c'
s=path.read_text()
old='''  mod->load_size = ALIGN_MEM(mod->load_size, load_align);
  if (mod->load_size > max_size) { res = -3; goto out; }
'''
new='''  /* Reject empty/overflowing images before rounding or reserving memory. */
  if (!mod->load_size || mod->load_size > SIZE_MAX - (load_align - 1)) {
    res = -3;
    goto out;
  }
  mod->load_size = ALIGN_MEM(mod->load_size, load_align);
  if (mod->load_size > max_size) { res = -3; goto out; }
  for (int i = 0; i < header.e_phnum; ++i) {
    const Elf64_Phdr *p = &mod->prog_hdr[i];
    if (p->p_type == PT_LOAD &&
        (p->p_vaddr > mod->load_size ||
         p->p_memsz > mod->load_size - p->p_vaddr ||
         p->p_filesz > mod->load_size - p->p_vaddr)) {
      res = -3;
      goto out;
    }
  }
'''
assert s.count(old)==1, 'unexpected ELF load sizing; review before patching'
path.write_text(s.replace(old,new))

