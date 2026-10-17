"""Replace fallible stdio-first fault capture with a preopened fixed record."""
from pathlib import Path
import os,sys
r=Path(sys.argv[1])/'source';here=Path(__file__).parent
p=r/'exception_capture.c';s=p.read_text();assert 'FILE *file = fopen(GAME_HOME "/fatal.txt", "ab");' in s
build=os.environ.get('GITHUB_SHA','local-unversioned');assert len(build)<48 and (all(c in '0123456789abcdef-' for c in build) or build=='local-unversioned')
p.write_text('#define EXCEPTION_BUILD "'+build+'"\n'+(here/'exception_capture.c.inc').read_text())
(r/'exception_capture.h').write_text('''#pragma once
void nx_exception_capture_prepare(void);
void nx_exception_capture_poll(void);
void nx_exception_capture_stop(void);
''')
p=r/'main.c';s=p.read_text();s='#include "exception_capture.h"\n'+s;a='  nx_shutdown_observer_start();';assert s.count(a)==1;s=s.replace(a,'  nx_exception_capture_prepare();\n'+a);p.write_text(s)
p=r/'shutdown_observer.c';s=p.read_text();s='#include "exception_capture.h"\n'+s;a='    NxMemorySample mem;';assert s.count(a)==1;s=s.replace(a,'    nx_exception_capture_poll();\n'+a)
# Close/fence dedicated handle inside existing observer stop, before unmount.
a='  observer_stopped=1;';assert s.count(a)==1;s=s.replace(a,a+'\n  nx_exception_capture_stop();');p.write_text(s)
