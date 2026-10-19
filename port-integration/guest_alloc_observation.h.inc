#pragma once
#include <stdint.h>
#include <stddef.h>
#define NX_ALLOC_OBSERVATION_WORDS 18
void nx_guest_alloc_attempt(void);
void nx_guest_alloc_primary_failed(void);
void nx_guest_alloc_failed(size_t,size_t,uintptr_t,int,int);
void nx_guest_alloc_bind(uintptr_t,size_t);
void nx_guest_alloc_sample(void);
void nx_guest_alloc_snapshot(uint64_t out[NX_ALLOC_OBSERVATION_WORDS]);
