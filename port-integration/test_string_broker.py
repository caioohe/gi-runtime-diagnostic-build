from pathlib import Path
import subprocess,tempfile
source=Path(__file__).with_name('string_broker.c.inc').read_text()
harness=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static int fail;
static size_t requested;
static void *__wrap_malloc(size_t n) { requested=n; if(fail) { errno=ENOMEM; return NULL; } return malloc(n); }
'''+source+r'''
int main(void) {
 char *a=__wrap_strdup("shader-cache"); assert(a && requested==13 && !strcmp(a,"shader-cache")); free(a);
 a=__wrap_strdup(""); assert(a && requested==1 && a[0]==0); free(a);
 a=__wrap_strndup("shader-cache",6); assert(a && requested==7 && !strcmp(a,"shader")); free(a);
 const char exact[3]={'a','b','c'};
 a=__wrap_strndup(exact,3); assert(a && requested==4 && !strcmp(a,"abc")); free(a);
 a=__wrap_strndup(exact,0); assert(a && requested==1 && a[0]==0); free(a);
 a=__wrap_strndup("a",SIZE_MAX); assert(a && requested==2 && !strcmp(a,"a")); free(a);
 fail=1; assert(!__wrap_strdup("cache") && errno==ENOMEM); assert(!__wrap_strndup(exact,3) && errno==ENOMEM);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(harness)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual string broker: empty/bounded/unterminated input, termination, allocation failure')

