"""Inspect exact linked ARM64 original-context publication and dedicated FS path."""
from pathlib import Path
import os,re,subprocess,sys
elf=Path(sys.argv[1]);tool=Path(os.environ['DEVKITPRO'])/'devkitA64/bin/aarch64-none-elf-objdump'
text=subprocess.check_output([str(tool),'-d',str(elf)],text=True)
def body(name):
 m=re.search(r'^\s*[0-9a-f]+ <'+re.escape(name)+r'>:\n(.*?)(?=^\s*[0-9a-f]+ <|\Z)',text,re.M|re.S);assert m,name;return m.group(1)
names=['__libnx_exception_handler','nx_exception_capture_poll','nx_exception_capture_prepare','nx_exception_capture_stop','exception_header','exception_checksum']
blocks={n:body(n) for n in names}
handler=blocks['__libnx_exception_handler'];poll=blocks['nx_exception_capture_poll']
assert 'stlr' in handler and '<nx_exception_capture_poll>' in handler
assert handler.index('stlr')<handler.index('<nx_exception_capture_poll>'),'payload not published before persistence'
assert '<fsFileWrite>' in poll and '<mutexTryLock>' in poll
assert '<mutexLock>' not in poll
for n in ['__libnx_exception_handler','nx_exception_capture_poll','exception_header','exception_checksum']:
 assert not re.search(r'<(?:.*malloc.*|.*calloc.*|.*realloc.*|fopen|fprintf|snprintf|fwrite|fflush|fclose|memory_runtime_trace|mutexLock)>',blocks[n]),n
assert '<fsFsCreateFile>' in blocks['nx_exception_capture_prepare'] and '<fsFsOpenFile>' in blocks['nx_exception_capture_prepare']
assert '<fsFileClose>' in blocks['nx_exception_capture_stop']
stop=body('nx_shutdown_observer_stop');assert '<nx_exception_capture_stop>' in stop
Path('exception-link-audit.txt').write_text('\n'.join('FUNCTION '+n+'\n'+b for n,b in blocks.items()))
print('PASS linked ARM64 exception publication-before-I/O, direct FS and stop fence; not hardware persistence proof')
