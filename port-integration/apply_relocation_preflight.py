"""Validate relocation structure on every mutation path; retain import policy."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'source/so_util.c'
s=p.read_text()
anchor='int so_relocate(so_module *mod) {\n'
assert s.count(anchor)==1
s=s.replace(anchor,'''/* This callback checks structure only. No returned address is installed;
 * actual host/guest import resolution remains in so_resolve/imports. */
static uintptr_t relocation_structure_only(const char *name, void *opaque) {
  (void)name; (void)opaque;
  return 1;
}

int so_relocate(so_module *mod) {
  char error[256];
  if (so_preflight_imports(mod, relocation_structure_only, NULL,
                           error, sizeof(error)) != 0) {
    fatal_error("Error: invalid relocation structure: %s", error);
    return -1;
  }
''')
s=s.replace('  Elf64_Sym *sym = &mod->syms[ELF64_R_SYM(rel->r_info)];\n  switch (ELF64_R_TYPE(rel->r_info)) {','''  const unsigned type = ELF64_R_TYPE(rel->r_info);
  /* NONE/RELATIVE do not use a symbol index or symbol pointer. */
  Elf64_Sym *sym = (type == R_AARCH64_ABS64 ||
                    type == R_AARCH64_GLOB_DAT || type == R_AARCH64_JUMP_SLOT)
    ? &mod->syms[ELF64_R_SYM(rel->r_info)] : NULL;
  switch (type) {''',1)
s=s.replace('for (int j = 0; j < mod->sec_hdr[i].sh_size / sizeof(Elf64_Rela); j++)', 'for (size_t j = 0; j < mod->sec_hdr[i].sh_size / sizeof(Elf64_Rela); j++)')
p.write_text(s)

