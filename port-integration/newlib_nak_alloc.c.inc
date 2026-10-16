/* Newlib internals bypass public malloc wrapping. Only NAK scope may borrow.
 * Primary calls remain reentrant; sparse pointers never go into newlib. */
#include <sys/reent.h>
extern int nx_nak_host_active(void);
void *__real__malloc_r(struct _reent *, size_t);
void *__real__realloc_r(struct _reent *, void *, size_t);
void __real__free_r(struct _reent *, void *);
void *__real__calloc_r(struct _reent *,size_t,size_t);
void *__real__memalign_r(struct _reent *,size_t,size_t);
static _Thread_local unsigned nak_newlib_depth;
void *__wrap__malloc_r(struct _reent *r,size_t size) {
  int before=r->_errno;
  int eligible=nx_nak_host_active() && !nak_newlib_depth;
  ++nak_newlib_depth;
  void *p=__real__malloc_r(r,size);
  --nak_newlib_depth;
  if(p || !size || !eligible) return p;
  int failed=r->_errno;
  int caller_errno=errno;
  p=host_pool_fallback(size,_Alignof(max_align_t),0);
  errno=caller_errno;
  r->_errno=p?before:failed;
  return p;
}
void __wrap__free_r(struct _reent *r,void *p) {
  if(p && nx_sparse_pool_contains_address(p)) { __wrap_free(p); return; }
  __real__free_r(r,p);
}
void *__wrap__realloc_r(struct _reent *r,void *p,size_t size) {
  if(p && nx_sparse_pool_contains_address(p)) {
    int caller_errno=errno, before=r->_errno;
    /* Bridge current-thread errno back to the explicitly supplied reent. */
    void *q=__wrap_realloc(p,size);
    int failed=errno;
    errno=caller_errno;
    r->_errno=(!q && size)?failed:before;
    return q;
  }
  if(!p) return __wrap__malloc_r(r,size);
  int before=r->_errno;
  int eligible=nx_nak_host_active() && !nak_newlib_depth;
  ++nak_newlib_depth;
  void *q=__real__realloc_r(r,p,size);
  --nak_newlib_depth;
  if(q || !size || !eligible) return q;
  int failed=r->_errno;
  size_t old=__real_malloc_usable_size(p);
  int caller_errno=errno;
  q=host_pool_fallback(size,_Alignof(max_align_t),0);
  if(q) { memcpy(q,p,old<size?old:size); __real__free_r(r,p); }
  errno=caller_errno;
  r->_errno=q?before:failed;
  return q;
}

void *__wrap__calloc_r(struct _reent *r,size_t count,size_t size) {
  int before=r->_errno;
  int eligible=nx_nak_host_active() && !nak_newlib_depth;
  ++nak_newlib_depth;
  void *p=__real__calloc_r(r,count,size);
  --nak_newlib_depth;
  if(p || !count || !size || !eligible) return p;
  int failed=r->_errno;
  if(count>SIZE_MAX/size) { r->_errno=ENOMEM; return NULL; }
  int caller_errno=errno;
  p=host_pool_fallback(count*size,_Alignof(max_align_t),1);
  errno=caller_errno;
  r->_errno=p?before:failed;
  return p;
}
void *__wrap__memalign_r(struct _reent *r,size_t alignment,size_t size) {
  /* Public memalign wrapper may fall back only AFTER newlib returns. */
  ++nak_newlib_depth;
  void *p=__real__memalign_r(r,alignment,size);
  --nak_newlib_depth;
  return p;
}

