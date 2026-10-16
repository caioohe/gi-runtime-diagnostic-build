from pathlib import Path
import sys
r=Path(sys.argv[1]);here=Path(__file__).parent
(r/'source/host_exit_trace.c').write_text((here/'host_exit_trace.c.inc').read_text())
p=r/'Makefile';s=p.read_text();a='-Wl,--wrap=malloc -Wl,--wrap=calloc';assert s.count(a)==1
names=['__libnx_exit','__nx_win_exit','fsdevUnmountAll','fsExit','timeExit','hidExit','appletExit','smExit']
s=s.replace(a,' '.join('-Wl,--wrap='+n for n in names)+' \\\n            '+a);p.write_text(s)

