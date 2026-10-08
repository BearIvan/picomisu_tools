"""Apply the observed PICO ConsumerBase ABI and fallback frame notification.

Run against the existing Picomisu native checkout. Member names are local;
the binary contract is a function pointer and int after mMutex, plus a virtual
latch getter before releaseBufferLocked. Factory ignores the callback result.
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native', type=Path)
    args = parser.parse_args()
    header = args.native / 'libs/gui/include/gui/ConsumerBase.h'
    source = args.native / 'libs/gui/ConsumerBase.cpp'
    h, s = header.read_text(), source.read_text()
    replacements = [
        ('    int getLatchAcquireSlotLocked();', '    virtual int getLatchAcquireSlotLocked();'),
        ('    mutable Mutex mMutex;\n',
         '    mutable Mutex mMutex;\n\n'
         '    // PICO fallback used when the weak FrameAvailableListener cannot be promoted.\n'
         '    // Keep after mMutex: factory clients access these fields by offset.\n'
         '    void (*mPicoFrameCallback)(int) = nullptr;\n'
         '    int mPicoFrameCallbackArgument = -1;\n'),
    ]
    for old, new in replacements:
        if h.count(old) != 1:
            raise RuntimeError('Unexpected header input: ' + old)
        h = h.replace(old, new)
    for method in ('onFrameAvailable', 'onFrameReplaced'):
        old = '        listener->' + method + '(item);\n    }'
        new = ('        listener->' + method + '(item);\n'
               '    } else if (mPicoFrameCallback != nullptr && mPicoFrameCallbackArgument != -1) {\n'
               '        mPicoFrameCallback(mPicoFrameCallbackArgument);\n    }')
        if s.count(old) != 1:
            raise RuntimeError('Unexpected callback input: ' + method)
        s = s.replace(old, new)
    header.write_text(h)
    source.write_text(s)


if __name__ == '__main__':
    main()
