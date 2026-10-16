typedef struct {
  const uint8_t *cur;
  const uint8_t *end;
  int failed;
} SlebReader;

static int64_t sleb128_read(SlebReader *r) {
  uint64_t value = 0;
  unsigned shift = 0;
  uint8_t byte = 0;
  do {
    if (r->cur >= r->end || shift >= 64) {
      r->failed = 1;
      return 0;
    }
    byte = *r->cur++;
    /* The tenth byte has one value bit and seven sign/continuation bits. */
    if (shift == 63 && byte != 0x00 && byte != 0x7f) {
      r->failed = 1;
      return 0;
    }
    value |= (uint64_t)(byte & 0x7f) << shift;
    shift += 7;
  } while (byte & 0x80);
  if (shift < 64 && (byte & 0x40))
    value |= (~0ULL) << shift;
  return (int64_t)value;
}

typedef int (*packed_rela_callback)(so_module *, const Elf64_Rela *, void *);

static int so_iterate_android_rela(so_module *mod, packed_rela_callback cb, void *opaque) {
  const Elf64_Xword packed_off = so_dynamic_tag(mod, DT_ANDROID_RELA);
  const Elf64_Xword packed_size = so_dynamic_tag(mod, DT_ANDROID_RELASZ);
  if (!packed_off || !packed_size)
    return 0;
  if (packed_off > mod->load_size || packed_size > mod->load_size - packed_off)
    return -2;

  SlebReader rd = {
    .cur = (const uint8_t *)mod->load_base + packed_off,
    .end = (const uint8_t *)mod->load_base + packed_off + packed_size,
    .failed = 0,
  };
  if ((size_t)(rd.end - rd.cur) < 4 || memcmp(rd.cur, "APS2", 4) != 0)
    return -2;
  rd.cur += 4;

  const int64_t relocation_count_signed = sleb128_read(&rd);
  if (rd.failed || relocation_count_signed < 0)
    return -2;
  const uint64_t relocation_count = (uint64_t)relocation_count_signed;
  uint64_t emitted = 0;
  Elf64_Rela rela = {0};
  int64_t offset = sleb128_read(&rd);
  rela.r_offset = (Elf64_Addr)offset;

  while (!rd.failed && emitted < relocation_count) {
    const int64_t group_size_signed = sleb128_read(&rd);
    const int64_t group_flags_signed = sleb128_read(&rd);
    if (rd.failed || group_size_signed <= 0 || group_flags_signed < 0 ||
        (uint64_t)group_size_signed > relocation_count - emitted) {
      rd.failed = 1;
      break;
    }
    const uint64_t group_size = (uint64_t)group_size_signed;
    const uint64_t flags = (uint64_t)group_flags_signed;
    const int64_t group_offset_delta =
      (flags & RELOCATION_GROUPED_BY_OFFSET_DELTA_FLAG) ? sleb128_read(&rd) : 0;
    const int64_t group_info =
      (flags & RELOCATION_GROUPED_BY_INFO_FLAG) ? sleb128_read(&rd) : 0;
    const int64_t group_addend_delta =
      ((flags & RELOCATION_GROUP_HAS_ADDEND_FLAG) &&
       (flags & RELOCATION_GROUPED_BY_ADDEND_FLAG)) ? sleb128_read(&rd) : 0;

    for (uint64_t i = 0; !rd.failed && i < group_size; i++, emitted++) {
      const int64_t off_delta = (flags & RELOCATION_GROUPED_BY_OFFSET_DELTA_FLAG)
        ? group_offset_delta : sleb128_read(&rd);
      int64_t next_offset;
      if (rd.failed || __builtin_add_overflow(offset, off_delta, &next_offset) ||
          next_offset < 0) {
        rd.failed = 1;
        break;
      }
      offset = next_offset;
      rela.r_offset = (Elf64_Addr)offset;
      rela.r_info = (Elf64_Xword)((flags & RELOCATION_GROUPED_BY_INFO_FLAG)
        ? group_info : sleb128_read(&rd));
      if (flags & RELOCATION_GROUP_HAS_ADDEND_FLAG) {
        const int64_t addend_delta = (flags & RELOCATION_GROUPED_BY_ADDEND_FLAG)
          ? group_addend_delta : sleb128_read(&rd);
        Elf64_Sxword next_addend;
        if (rd.failed || __builtin_add_overflow(rela.r_addend, addend_delta,
                                               &next_addend)) {
          rd.failed = 1;
          break;
        }
        rela.r_addend = next_addend;
      } else {
        rela.r_addend = 0;
      }
      if (rd.failed || mod->load_size < sizeof(uintptr_t) ||
          rela.r_offset > mod->load_size - sizeof(uintptr_t)) {
        rd.failed = 1;
        break;
      }
      if (cb(mod, &rela, opaque) != 0)
        return -1;
    }
  }

  if (rd.failed || emitted != relocation_count || rd.cur != rd.end)
    return -2;
  return 1;
}

