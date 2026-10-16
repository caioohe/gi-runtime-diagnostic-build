/* Public libc string allocation must share the host broker's ownership.
 * Newlib strdup otherwise calls _malloc_r directly, bypassing --wrap=malloc. */
char *__wrap_strdup(const char *text) {
  size_t length = strlen(text);
  if (length == SIZE_MAX) { errno = ENOMEM; return NULL; }
  char *copy = __wrap_malloc(length + 1);
  if (copy) memcpy(copy, text, length + 1);
  return copy;
}
char *__wrap_strndup(const char *text, size_t limit) {
  size_t length = strnlen(text, limit);
  if (length == SIZE_MAX) { errno = ENOMEM; return NULL; }
  char *copy = __wrap_malloc(length + 1);
  if (copy) { memcpy(copy, text, length); copy[length] = 0; }
  return copy;
}

