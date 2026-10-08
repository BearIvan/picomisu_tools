"""Add the verified PICO producer status store to the experimental native tree."""
import argparse
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unexpected source; refusing ambiguous patch')
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frameworks_native', type=Path)
    args = parser.parse_args()
    gui = args.frameworks_native / 'libs/gui'
    replacements = {
        gui / 'include/gui/BufferQueueCore.h': (
            '    const uint64_t mUniqueId;\n',
            '''    const uint64_t mUniqueId;

    // PICO producer QUERY 10000 stores a signed VR status value. Guarded by
    // mMutex. This is distinct from the consumer's private transaction 10000.
    // The downstream VR frame handling is not yet ported.
    int32_t mPicoVrStatus;
'''),
        gui / 'BufferQueueCore.cpp': (
            '    mUniqueId(getUniqueId())\n',
            '    mUniqueId(getUniqueId()),\n    mPicoVrStatus(0)\n'),
        gui / 'BufferQueueProducer.cpp': (
            '    int value;\n    switch (what) {\n',
            '''    int value;
    switch (what) {
        case 10000: // PICO QUERY_SET_PVR_STATUS: an input/output query.
            value = *outValue;
            mCore->mPicoVrStatus = value;
            break;
'''),
    }
    changed = {}
    for path, (old, new) in replacements.items():
        text = path.read_text()
        if 'mPicoVrStatus' in text:
            raise RuntimeError('Status store already exists: ' + str(path))
        changed[path] = replace_once(text, old, new)
    header = gui / 'include/gui/BufferQueueCore.h'
    changed[header] = replace_once(changed[header],
        '    friend class BufferQueueConsumer;\n',
        '    friend class BufferQueueConsumer;\n    friend class PicoBufferQueueStatusTest;\n')
    for path, text in changed.items():
        path.write_text(text)


if __name__ == '__main__':
    main()
