char *realpath_fake(const char *path, char *resolved) {
  /* Preserve this shim's virtual-path copy semantics and 4096-byte limit. */
  if (!path) { errno = EINVAL; return NULL; }
  const size_t length = strnlen(path, 0x1000);
  if (length == 0x1000) { errno = ENAMETOOLONG; return NULL; }
  if (!resolved) {
    resolved = malloc(0x1000);
    if (!resolved) { errno = ENOMEM; return NULL; }
  }
  memcpy(resolved, path, length + 1);
  return resolved;
}

