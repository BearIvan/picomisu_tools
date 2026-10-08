"""Check AVB templates and filesystem metadata before building the actual image."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('pico_image_builder', Path(__file__).with_name('build-vr-image.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def main():
    builder.pico.guard_volume()
    _, root, descriptors, _ = builder.image_data(builder.STOCK / 'vbmeta.img')
    chains = {item.partition_name: item.rollback_index_location for item in descriptors
              if isinstance(item, builder.avb.AvbChainPartitionDescriptor)}
    if chains != {'recovery': 1, 'vbmeta_system': 2} or root.flags != 0:
        raise RuntimeError('Unexpected factory AVB chain or flags')
    root_blob = builder.vbmeta_blob([item for item in descriptors
                                   if not isinstance(item, builder.avb.AvbChainPartitionDescriptor)])
    _, child, child_descriptors, _ = builder.image_data(builder.STOCK / 'vbmeta_system.img')
    preserved = [item for item in child_descriptors
                 if (isinstance(item, builder.avb.AvbHashtreeDescriptor) and item.partition_name == 'product')
                 or (isinstance(item, builder.avb.AvbPropertyDescriptor) and item.key.startswith('com.android.build.product.'))]
    if not any(isinstance(item, builder.avb.AvbHashtreeDescriptor) for item in preserved):
        raise RuntimeError('Missing factory product hashtree')
    product_blob = builder.vbmeta_blob(preserved)
    maximum = int(builder.avb_command('add_hashtree_footer', '--partition_size', '5704732672',
                                      '--hash_algorithm', 'sha256', '--do_not_generate_fec',
                                      '--calc_max_image_size').strip())
    report = {'passed': True, 'chain_locations': chains, 'stock_root_flags': root.flags,
              'stock_system_rollback_index': child.rollback_index,
              'unsigned_root_template_bytes': len(root_blob), 'unsigned_product_template_bytes': len(product_blob),
              'maximum_filesystem_bytes_without_fec': maximum,
              'development_key_exists': builder.KEY.is_file(),
              'production_key_used': False, 'headset_modified': False}
    (builder.pico.REPORTS / 'image-preflight.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
