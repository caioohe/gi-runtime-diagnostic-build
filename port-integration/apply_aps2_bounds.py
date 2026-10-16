"""Apply audited APS2 arithmetic checks to the pinned parser only."""
from pathlib import Path
import hashlib, sys
path = Path(sys.argv[1]) / 'source/so_util.c'
source = path.read_text()
start = source.index('typedef struct {\n  const uint8_t *cur;')
end = source.index('static int relocate_one(', start)
original = source[start:end]
assert hashlib.sha256(original.encode()).hexdigest() == 'ef6fff0cba585e1556245f9e10cf3b928b9c8efe56839fe2f395a8815def5c14', 'unexpected APS2 parser; review before patching'
replacement = Path(__file__).with_name('aps2_bounds.c.inc').read_text() + '\n'
path.write_text(source[:start] + replacement + source[end:])

