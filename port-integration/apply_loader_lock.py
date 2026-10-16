"""Synchronize recursive loader ownership without reading another owner's depth."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);p=root/'source/plugin_loader.c';s=p.read_text()
assert 'g_loader_depth && g_loader_owner == self' in s, 'unexpected loader lock; review before patching'
s=s.replace('static Handle g_loader_owner;','static Handle g_loader_owner; /* accessed atomically */')
s=s.replace('  if (g_loader_depth && g_loader_owner == self) {','  if (__atomic_load_n(&g_loader_owner, __ATOMIC_ACQUIRE) == self) {')
s=s.replace('  g_loader_owner = self;\n  g_loader_depth = 1;','  g_loader_depth = 1;\n  __atomic_store_n(&g_loader_owner, self, __ATOMIC_RELEASE);')
s=s.replace('  g_loader_owner = 0;','  __atomic_store_n(&g_loader_owner, 0, __ATOMIC_RELEASE);')
p.write_text(s)
p=root/'source/main.c';s=p.read_text();old='__asm__ volatile("msr s3_3_c13_c0_2, %0" : : "r"(value));';assert s.count(old)==1;p.write_text(s.replace(old,'__asm__ volatile("msr s3_3_c13_c0_2, %0" : : "r"(value) : "memory");'))

