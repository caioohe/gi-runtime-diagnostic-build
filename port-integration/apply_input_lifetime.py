"""Give obtained input events JNI-owned lifetimes instead of a wrapping ring."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);p=root/'source/unity_input.c';s=p.read_text()
s=s.replace('#include <string.h>','#include <string.h>\n#include <stdlib.h>\n#include <stddef.h>')
s=s.replace('uint32_t tag; int kind;','uint32_t tag; uint32_t refs; int kind;').replace('static UEvent g_ev;','static _Thread_local UEvent g_ev;')
s=s.replace('e->tag=UI_TAG; e->kind=', 'e->tag=UI_TAG; e->refs=UINT32_MAX; e->kind=')
a=s.index('/* Keep copies alive');b=s.index('int input_owns_class',a)
s=s[:a]+'''/* Each obtained copy owns one JNI reference; static injection storage is
 * borrowed and per-thread. Payload is immutable after obtain. */
void *unity_motionevent_obtain(void *src){
  const UEvent *s = src;
  if (!s || s->tag!=UI_TAG) return src;
  UEvent *d = malloc(sizeof *d);
  if (!d) return NULL;
  d->tag = s->tag;
  d->refs = 1;
  memcpy(&d->kind, &s->kind, sizeof(*d) - offsetof(UEvent, kind));
  return d;
}
int input_retain(void *obj){
  UEvent *e=obj;
  uint32_t refs=__atomic_load_n(&e->refs,__ATOMIC_ACQUIRE);
  if (refs==UINT32_MAX) return 1;
  while (refs && refs<UINT32_MAX-1) {
    if (__atomic_compare_exchange_n(&e->refs,&refs,refs+1,0,
                                   __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)) return 1;
  }
  return 0;
}
void input_release(void *obj){
  UEvent *e=obj;
  if (__atomic_load_n(&e->refs,__ATOMIC_ACQUIRE)==UINT32_MAX) return;
  if (__atomic_fetch_sub(&e->refs,1,__ATOMIC_ACQ_REL)==1) free(e);
}
/* Android recycle ends application use, not the JNI handle's ownership.
 * Do not pool/reuse backing memory while local/global references still exist. */
void input_recycle(void *obj){ (void)obj; }

'''+s[b:];p.write_text(s)
p=root/'source/unity_input.h';s=p.read_text().replace('int       input_owns_class','int input_retain(void *obj);\nvoid input_release(void *obj);\nvoid input_recycle(void *obj);\n\nint       input_owns_class');p.write_text(s)
p=root/'source/jni_fake.c';s=p.read_text();a='  if (!ref) return 1;';assert s.count(a)==1;s=s.replace(a,a+'\n  if (input_owns_recv(ref)) return input_retain(ref);')
a='static void free_ref(void *ref) {\n  if (!ref)\n    return;';assert s.count(a)==1;s=s.replace(a,a+'\n  if (input_owns_recv(ref)) { input_release(ref); return; }')
a='static void dispatch_void(void *recv, const FakeID *id, va_list va) {';assert s.count(a)==1;s=s.replace(a,a+'\n  if (input_owns_recv(recv) && !strcmp(id->name,"recycle")) { input_recycle(recv); return; }')
s=s.replace('/* Classes, method IDs, interned objects, the static APK signer, and input\n   * event storage are stable outside the local table. */','/* Classes, method IDs, interned objects and the static APK signer are\n   * stable outside the local table. */')
p.write_text(s)

