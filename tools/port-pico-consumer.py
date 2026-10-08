"""Port the verified PICO consumer marker and callback buffer lifetime."""
import argparse
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unexpected AOSP source; refusing ambiguous patch')
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frameworks_native', type=Path)
    args = parser.parse_args()
    gui = args.frameworks_native / 'libs/gui'
    replacements = {
        'include/gui/BufferQueueCore.h': (
            '    int32_t mPicoVrStatus;\n',
            '''    int32_t mPicoVrStatus;

    // Private consumer transaction 10000 records its id/log flag and marks
    // callbacks that need the GraphicBuffer reference retained. Guarded by mMutex.
    int32_t mPicoConsumerId;
    bool mPicoConsumerLogging;
    bool mHasPicoConsumer;
'''),
        'BufferQueueCore.cpp': (
            '    mPicoVrStatus(0)\n',
            '''    mPicoVrStatus(0),
    mPicoConsumerId(0),
    mPicoConsumerLogging(false),
    mHasPicoConsumer(false)
'''),
        'include/gui/BufferQueueConsumer.h': (
            '    ~BufferQueueConsumer() override;\n',
            '''    ~BufferQueueConsumer() override;

    status_t onTransact(uint32_t code, const Parcel& data, Parcel* reply,
                        uint32_t flags = 0) override;
'''),
        'BufferQueueConsumer.cpp': (
            'BufferQueueConsumer::~BufferQueueConsumer() {}\n',
            '''BufferQueueConsumer::~BufferQueueConsumer() {}

status_t BufferQueueConsumer::onTransact(uint32_t code, const Parcel& data,
                                       Parcel* reply, uint32_t flags) {
    constexpr uint32_t kPicoConsumerConfiguration = 10000;
    if (code != kPicoConsumerConfiguration) {
        return BnGraphicBufferConsumer::onTransact(code, data, reply, flags);
    }
    CHECK_INTERFACE(IGraphicBufferConsumer, data, reply);
    int32_t consumerId, logging;
    if (data.readInt32(&consumerId) != NO_ERROR ||
        data.readInt32(&logging) != NO_ERROR) {
        return BAD_VALUE;
    }
    std::lock_guard<std::mutex> lock(mCore->mMutex);
    mCore->mPicoConsumerId = consumerId;
    mCore->mPicoConsumerLogging = logging == 1;
    mCore->mHasPicoConsumer = true;
    if (mCore->mPicoConsumerLogging) {
        BQ_LOGI("PICO consumer configured: id=%d", consumerId);
    }
    return NO_ERROR;
}
'''),
    }
    changed = {}
    for name, (old, new) in replacements.items():
        path = gui / name
        if 'mHasPicoConsumer' in path.read_text():
            raise RuntimeError('Consumer marker already present: ' + str(path))
        changed[path] = replace_once(path.read_text(), old, new)
    producer = gui / 'BufferQueueProducer.cpp'
    text = producer.read_text()
    text = replace_once(text, '    BufferItem item;\n',
                        '    BufferItem item;\n    bool picoConsumer = false;\n')
    text = replace_once(text, '        callbackTicket = mNextCallbackTicket++;\n',
                        '        callbackTicket = mNextCallbackTicket++;\n'
                        '        picoConsumer = mCore->mHasPicoConsumer;\n')
    text = replace_once(text, '    if (!mConsumerIsSurfaceFlinger) {\n',
                        '    if (!mConsumerIsSurfaceFlinger && !picoConsumer) {\n')
    text = replace_once(text, '    // Update and get FrameEventHistory.\n',
                        '''    // PICO keeps the reference through the listener callback, then
    // releases this local copy before frame timestamp processing.
    if (picoConsumer) {
        item.mGraphicBuffer.clear();
    }

    // Update and get FrameEventHistory.
''')
    changed[producer] = text
    for path, text in changed.items():
        path.write_text(text)


if __name__ == '__main__':
    main()
