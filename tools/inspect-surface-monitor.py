"""Authenticate SurfaceMonitor exports and record factory function boundaries.

Behavior is qualified separately with real methods and local Binder services.
The unresolved factory prefix and full graphics object ABI remain open.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
FACTORY = {'lib64': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
           'lib': '09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0'}
REQUIRED = ['_ZN7android14SurfaceMonitorC1Ev', '_ZN7android14SurfaceMonitorD1Ev',
            '_ZN7android14SurfaceMonitor12setFrameItemENS_12MonitorIndexE',
            '_ZN7android14SurfaceMonitor23updateCurrentDisplayFpsEiNS_7String8E',
            '_ZN7android14SurfaceMonitor8addFrameENS_7String8E']


def main():
    result = {'scope': 'SurfaceMonitor authenticated method group',
              'monitor_item_bytes': 48, 'frame_capacity': 120,
              'average_fps_capacity': 10, 'duration_capacity': 60,
              'operation_gap_ns': 300000000, 'unresolved_prefix_bytes': [8, 48],
              'unresolved_prefix_meaning_recovered': False,
              'full_cpp_abi_proven': False, 'real_display_frequency_qualified': False,
              'abis': {}}
    for directory, expected in FACTORY.items():
        factory_data = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system' / directory / 'libgui.so').read_bytes()
        if hashlib.sha256(factory_data).hexdigest() != expected:
            raise RuntimeError('Pinned factory GUI changed')
        factory = p.pointers.ElfPointers(factory_data)
        source_data = p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/system' / directory / 'libgui.so').read_bytes()
        source = p.pointers.ElfPointers(source_data)
        methods = {}
        for name, symbol in factory.symbols.items():
            if name.startswith('_ZN7android14SurfaceMonitor') and symbol.st_size and symbol.st_shndx != 'SHN_UNDEF':
                if name not in source.symbols:
                    raise RuntimeError('Source monitor method is absent: ' + name)
                address = symbol.st_value & ~1
                offset = factory.file_offset(address, symbol.st_size)
                methods[name] = {'factory_address': hex(address), 'factory_function_bytes': symbol.st_size,
                                 'factory_function_sha256': hashlib.sha256(factory_data[offset:offset + symbol.st_size]).hexdigest(),
                                 'source_export_present': True}
        for name in REQUIRED:
            if name not in methods:
                raise RuntimeError('Required monitor entry not authenticated: ' + name)
        abi = 'arm64' if directory == 'lib64' else 'arm'
        result['abis'][abi] = {'factory_sha256': expected,
                              'source_sha256': hashlib.sha256(source_data).hexdigest(),
                              'observed_source_class_bytes': 6680 if abi == 'arm64' else 6640,
                              'methods': methods}
    (ROOT / 'validation/surface-monitor-abi.json').write_text(json.dumps(result, indent=2) + '\n')
    print('All exported SurfaceMonitor methods present on both ABIs; unresolved prefix/full graphics ABI remains open')


if __name__ == '__main__':
    main()
