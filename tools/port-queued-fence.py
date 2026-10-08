"""Port factory PICO type-1 queued-buffer replacement behavior.

Factory captures the dropped buffer ID, detaches its slot and calls the producer
listener with Fence::NO_FENCE and flag=true after the consumer frame callback.
Existing AOSP consumer onDisconnect is retained; it does not require a port.
"""
from pathlib import Path
import subprocess

PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
TARGET = PROJECT / 'source/aosp-10/frameworks/native'


def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Expected unique source anchor: ' + old[:120])
    return text.replace(old, new, 1)


def main():
    if subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,UUID', '--target', str(PROJECT)], text=True).split() != ['ext4', 'a00da05f-1eb2-44b6-99f0-9109391f67dc']:
        raise RuntimeError('Expected ext4 source volume')
    if subprocess.check_output(['git', '-C', str(TARGET), 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Preserve existing source changes')
    path = TARGET / 'libs/gui/BufferQueueProducer.cpp'
    text = path.read_text()
    text = replace(text, '    sp<IConsumerListener> frameReplacedListener;', '''    sp<IConsumerListener> frameReplacedListener;
    sp<IProducerListener> droppedBufferListener;
    uint64_t droppedBufferId = 0;''')
    text = replace(text, '''                    // After leaving shared buffer mode, the shared buffer will
                    // still be around.''', '''                    const sp<GraphicBuffer>& dropped = mSlots[last.mSlot].mGraphicBuffer;
                    if (dropped != nullptr &&
                            (dropped->getUsage() & 0xf00000000ULL) == 0x100000000ULL) {
                        droppedBufferId = dropped->getId();
                        droppedBufferListener = mCore->mConnectedProducerListener;
                        mCore->mActiveBuffers.erase(last.mSlot);
                        mCore->mFreeSlots.insert(last.mSlot);
                        mCore->clearBufferSlotLocked(last.mSlot);
                        output->bufferReplaced = true;
                    } else {
                    // After leaving shared buffer mode, the shared buffer will
                    // still be around.''')
    text = replace(text, '''                        output->bufferReplaced = true;
                    }
                }

                // Overwrite the droppable''', '''                        output->bufferReplaced = true;
                    }
                    }
                }

                // Overwrite the droppable''')
    # Indent the preserved ordinary release path inside its new else block.
    begin = text.index('                    // After leaving shared buffer mode, the shared buffer will')
    end = text.index('                    }\n                }\n\n                // Overwrite', begin)
    ordinary = text[begin:end]
    text = text[:begin] + ''.join('    ' + line if line.strip() else line for line in ordinary.splitlines(keepends=True)) + text[end:]
    text = replace(text, '    // PICO keeps the reference through the listener callback, then', '''    // Factory sends this after the consumer frame callback with neither queue
    // nor callback mutex held. The payload is NO_FENCE, not the old acquire fence.
    if (droppedBufferListener != nullptr) {
        droppedBufferListener->onBufferReleasedWithFence(Fence::NO_FENCE,
                                                         droppedBufferId, true);
    }

    // PICO keeps the reference through the listener callback, then''')
    path.write_text(text)
    print('Applied PICO queued replacement fence callback')


if __name__ == '__main__':
    main()
