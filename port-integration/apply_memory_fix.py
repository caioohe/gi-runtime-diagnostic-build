"""Apply a narrowly scoped donor growth fix to the pinned upstream wrapper."""
from pathlib import Path
import sys

OLD = '''  if (target <= oc_donor_active_units) return 0;
  return oc_donor_resize_locked(target);
}'''
NEW = '''  if (target <= oc_donor_active_units) return 0;
  if (oc_donor_resize_locked(target)) return 1;

  /* A speculative 256 MiB batch can exceed physical admission even when
   * the requested allocation fits. Retry only a failed kernel resize,
   * never a successful resize whose postcondition/rollback was rejected. */
  if (!R_FAILED(__atomic_load_n(&oc_donor_last_resize_result,
                               __ATOMIC_RELAXED)))
    return 0;
  if (minimum_extra_units > oc_donor_unit_capacity - oc_donor_active_units)
    return 0;
  size_t minimum_target = oc_donor_active_units + minimum_extra_units;
  if (minimum_target > SIZE_MAX - (quantum_units - 1u)) return 0;
  minimum_target = (minimum_target + quantum_units - 1u) &
                   ~(quantum_units - 1u);
  if (minimum_target > oc_donor_unit_capacity ||
      minimum_target <= oc_donor_active_units || minimum_target >= target)
    return 0;
  return oc_donor_resize_locked(minimum_target);
}'''

def apply(root):
    path = Path(root) / 'source/libc_shim.c'
    source = path.read_text()
    if source.count(OLD) != 1:
        raise SystemExit('Pinned donor growth block changed; refusing to patch.')
    path.write_text(source.replace(OLD, NEW))
    config = Path(root) / 'source/config.h'
    text = config.read_text()
    old = '#define OC_HEAP_DONOR_GROW_BYTES    ((size_t)256 * 1024 * 1024)'
    if text.count(old) != 1:
        raise SystemExit('Pinned donor configuration changed.')
    config.write_text(text.replace(old, '#define OC_HEAP_DONOR_GROW_BYTES    ((size_t)32 * 1024 * 1024)'))

if __name__ == '__main__':
    apply(sys.argv[1])

