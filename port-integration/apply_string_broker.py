from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'source/memory_broker.c'
s=p.read_text()
assert 'char *__wrap_strdup' not in s
p.write_text(s+'\n'+Path(__file__).with_name('string_broker.c.inc').read_text())
p=root/'Makefile';s=p.read_text()
needle='-Wl,--wrap=malloc -Wl,--wrap=calloc -Wl,--wrap=realloc'
assert s.count(needle)==1
p.write_text(s.replace(needle,needle+' -Wl,--wrap=strdup -Wl,--wrap=strndup'))

