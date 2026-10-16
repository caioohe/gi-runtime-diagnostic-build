"""Adapt only build integration for an experimental public Mesa SDK.

Does not modify the upstream runtime, game version, offsets or protections.
The replacement SDK is 26.2.4, not a reproduction of the missing 26.1.5 SDK.
"""
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('port', type=Path)
    parser.add_argument('sdk', type=Path)
    args = parser.parse_args()
    sdk = args.sdk.resolve()
    for relative in ('lib/libvulkan.a', 'lib/libnak_rs.a', 'include/vulkan/vulkan.h', 'lib/pkgconfig/vulkan.pc'):
        if not (sdk / relative).is_file():
            raise SystemExit(f'Missing SDK component: {relative}')
    path = args.port / 'Makefile'
    original = path.read_text()
    start = original.index('# Keep this SDK self-contained.')
    end = original.index('ARCH :=', start)
    replacement = ('# Experimental integration: public Mesa 26.2.4 unified SDK.\n'
                   f'NVK_SWITCH_SDK := {sdk}\n'
                   'NVK_SWITCH_CPPFLAGS := -I$(NVK_SWITCH_SDK)/include -DVK_USE_PLATFORM_VI_NN\n'
                   'NVK_SWITCH_LDFLAGS := -L$(NVK_SWITCH_SDK)/lib\n'
                   'NVK_SWITCH_LIBS := -lEGL -lglapi -lvulkan -lnak_rs -lexpat -lzstd -lz -lnx -lm\n\n')
    updated = original[:start] + replacement + original[end:]
    updated = updated.replace('APP_ICON    := $(TOPDIR)/icon.jpg', 'APP_ICON    :=')
    updated = updated.replace('NROFLAGS := --icon=$(APP_ICON) --nacp=$(OUTPUT).nacp',
                              'NROFLAGS := --nacp=$(OUTPUT).nacp')
    path.write_text(updated)
    print('Experimental build integration only; runtime validation remains pending.')

if __name__ == '__main__':
    main()

