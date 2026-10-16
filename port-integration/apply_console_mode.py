from pathlib import Path
import sys

root = Path(sys.argv[1])
# Diagnostic only: production configuration retains its original 1 GiB heap.
c = root / 'source/config.h'
t = c.read_text()
a = '#define OC_MANAGED_BYTES    ((size_t)1024 * 1024 * 1024)'
assert t.count(a) == 1
c.write_text(t.replace(a, '#define OC_MANAGED_BYTES    ((size_t)256 * 1024 * 1024)'))
p = root / 'source/libc_shim.c'
s = p.read_text()
growth = 'static int oc_donor_grow_locked(size_t minimum_extra_units) {'
control = 'static size_t memory_diag_growth_bytes = OC_HEAP_DONOR_GROW_BYTES;\nstatic size_t memory_diag_shrink_bytes = OC_HEAP_DONOR_SHRINK_BYTES;\nint nx_memory_diag_set_batch(size_t bytes) {\n  if (bytes != 32u*1024u*1024u && bytes != 256u*1024u*1024u) return 0;\n  mmap_broker_lock();\n  int ok = !oc_donor_used_units && !oc_dynamic_mapped_segments &&\n    g_heap_donor_active_bytes == OC_HEAP_DONOR_INITIAL_BYTES;\n  if (ok) { memory_diag_growth_bytes = bytes; memory_diag_shrink_bytes = bytes; }\n  mmap_broker_unlock();\n  return ok;\n}\n'
assert s.count(growth) == 1
s = s.replace(growth, control + growth)
s = s.replace('OC_HEAP_DONOR_SHRINK_BYTES / OC_HEAP_DONOR_UNIT_BYTES;',
              'memory_diag_shrink_bytes / OC_HEAP_DONOR_UNIT_BYTES;')
s = s.replace('OC_HEAP_DONOR_GROW_BYTES / OC_HEAP_DONOR_UNIT_BYTES;',
              'memory_diag_growth_bytes / OC_HEAP_DONOR_UNIT_BYTES;')
begin = s.index('int nx_alias_memory_arenas_prepare(void) {')
end = s.index('\nint nx_dynamic_arena_prepare(void)', begin)
body = s[begin:end]
body = body.replace('  if (partial_layout) return 0;',
                    '  if (partial_layout) { memory_init_stage = "partial-layout"; return 0; }')
body = body.replace('  const size_t arena_bytes =',
                    '  memory_init_stage = "select-address-space";\n  const size_t arena_bytes =', 1)
body = body.replace('  const size_t arena_pages =',
                    '  memory_init_stage = "validate-layout-geometry";\n  const size_t arena_pages =', 1)
body = body.replace('  uint8_t *used =',
                    '  memory_init_stage = "allocate-primary-metadata";\n  uint8_t *used =', 1)
body = body.replace('  OcVirtualLayout layout;',
                    '  memory_init_stage = "reserve-virtual-layout";\n  OcVirtualLayout layout;', 1)
body = body.replace('  if (!oc_address_range_state(layout.base,',
                    '  memory_init_stage = "verify-unmapped-layout";\n  if (!oc_address_range_state(layout.base,', 1)
body = body.replace('  const int partition_geometry_valid =',
                    '  memory_init_stage = "partition-geometry";\n  const int partition_geometry_valid =', 1)
body = body.replace('  if (published) return 1;',
                    '  if (published) { memory_init_stage = "ready"; return 1; }\n  memory_init_stage = "publish-conflict";')
decl = 'static const char *memory_init_stage = "not-started";\nconst char *nx_memory_init_stage(void) { return memory_init_stage; }\n'
s = s[:begin] + decl + body + s[end:]
p.write_text(s)
p = root / 'source/main.c'
s = p.read_text()
marker = 'int main(int argc, char **argv) {'
assert s.count(marker) == 1
snippet = Path(__file__).with_name('memory_console.c.inc').read_text()
workloads = Path(__file__).with_name('memory_workloads.c.inc').read_text()
snippet = snippet.replace('static int memory_test_main(void) {', workloads + '\nstatic int memory_test_main(void) {')
s = s.replace(marker, snippet + '\n' + marker + '\n  return memory_test_main();\n')
p.write_text(s)
p = root / 'Makefile'
s = p.read_text().replace('TARGET      := genshinimpact_nx', 'TARGET      := gi-wrapper-memory-hub')
s = s.replace('APP_TITLE   := Genshin Impact NX', 'APP_TITLE   := GI Wrapper Memory Hub')
p.write_text(s)

