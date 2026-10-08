"""Port the verified local consumer/dequeue fence-ready path from PICO.

The interface has a default local no-op, and no extra Binder transaction.
Factory-style type-1 release detaches the slot and invokes the fence listener.
The separate type-1 queue-replacement callback is still pending.
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
        raise RuntimeError('Preserve uncommitted source changes')
    edits = {}

    def read(relative):
        return (TARGET / 'libs/gui' / relative).read_text()

    slot = read('include/gui/BufferSlot.h')
    slot = replace(slot, '      mNeedsReallocation(false) {', '      mNeedsReallocation(false),\n      mPicoFenceReady(false),\n      mPicoReadyFence(Fence::NO_FENCE) {')
    slot = replace(slot, '    bool mNeedsReallocation;', '''    bool mNeedsReallocation;

    // Local PICO consumer/dequeue handshake, guarded by BufferQueueCore::mMutex.
    bool mPicoFenceReady;
    sp<Fence> mPicoReadyFence;''')
    edits['include/gui/BufferSlot.h'] = slot
    core = read('include/gui/BufferQueueCore.h')
    core = replace(core, '    mutable std::condition_variable mDequeueCondition;', '    mutable std::condition_variable mDequeueCondition;\n    mutable std::condition_variable mPicoFenceCondition;')
    edits['include/gui/BufferQueueCore.h'] = core
    core = read('BufferQueueCore.cpp')
    core = replace(core, '    mDequeueCondition(),', '    mDequeueCondition(),\n    mPicoFenceCondition(),')
    core = replace(core, '    mSlots[slot].mGraphicBuffer.clear();', '''    mSlots[slot].mGraphicBuffer.clear();
    mSlots[slot].mPicoFenceReady = false;
    mSlots[slot].mPicoReadyFence = Fence::NO_FENCE;''')
    edits['BufferQueueCore.cpp'] = core
    consumer = read('include/gui/IGraphicBufferConsumer.h')
    consumer = replace(consumer, '    // Provide backwards source compatibility', '''    // PICO local-only callback. Factory Binder/HIDL proxies use this default
    // no-op; no extra wire transaction is defined for this method.
    virtual status_t notifyFenceReady(const sp<Fence>& /*fence*/, uint64_t /*bufferId*/,
                                     int /*slot*/) { return NO_ERROR; }

    // Provide backwards source compatibility''')
    edits['include/gui/IGraphicBufferConsumer.h'] = consumer
    consumer = read('include/gui/BufferQueueConsumer.h')
    consumer = replace(consumer, '    // Functions required for backwards compatibility.', '''    status_t notifyFenceReady(const sp<Fence>& fence, uint64_t bufferId, int slot) override;

    // Functions required for backwards compatibility.''')
    consumer = replace(consumer, 'private:\n    sp<BufferQueueCore> mCore;', '''private:
    // Caller holds mCore->mMutex. Kept after existing virtual methods.
    virtual status_t detachBufferLocked(int slot);
    sp<BufferQueueCore> mCore;''')
    edits['include/gui/BufferQueueConsumer.h'] = consumer
    consumer = read('BufferQueueConsumer.cpp')
    anchor = '''    std::lock_guard<std::mutex> lock(mCore->mMutex);

    if (mCore->mIsAbandoned) {'''
    start = consumer.index('status_t BufferQueueConsumer::detachBuffer(int slot)')
    end = consumer.index('status_t BufferQueueConsumer::attachBuffer(', start)
    function = consumer[start:end]
    function = replace(function, anchor, '''    std::lock_guard<std::mutex> lock(mCore->mMutex);
    return detachBufferLocked(slot);
}

status_t BufferQueueConsumer::detachBufferLocked(int slot) {
    if (mCore->mIsAbandoned) {''')
    consumer = consumer[:start] + function + consumer[end:]
    start = consumer.index('status_t BufferQueueConsumer::releaseBuffer(int slot, uint64_t frameNumber,')
    end = consumer.index('status_t BufferQueueConsumer::connect(', start)
    function = consumer[start:end]
    function = replace(function, '    sp<IProducerListener> listener;', '''    sp<IProducerListener> listener;
    bool picoDetach = false;
    uint64_t bufferId = 0;
    status_t detachResult = NO_ERROR;''')
    begin = function.index('        mSlots[slot].mEglDisplay = eglDisplay;')
    finish = function.index('    } // Autolock scope', begin)
    ordinary = function[begin:finish]
    specialized = '''        const sp<GraphicBuffer>& buffer = mSlots[slot].mGraphicBuffer;
        if (buffer != nullptr && (buffer->getUsage() & 0xf00000000ULL) == 0x100000000ULL) {
            bufferId = buffer->getId();
            listener = mCore->mConnectedProducerListener;
            detachResult = detachBufferLocked(slot);
            picoDetach = true;
        } else {
'''
    function = function[:begin] + specialized + ''.join('    ' + line if line.strip() else line for line in ordinary.splitlines(keepends=True)) + '        }\n' + function[finish:]
    function = replace(function, '''        listener->onBufferReleased();
    }

    return NO_ERROR;''', '''        if (picoDetach) {
            listener->onBufferReleasedWithFence(releaseFence, bufferId, false);
        } else {
            listener->onBufferReleased();
        }
    }

    return picoDetach ? detachResult : NO_ERROR;''')
    function += '''status_t BufferQueueConsumer::notifyFenceReady(const sp<Fence>& fence,
                                                uint64_t bufferId, int slot) {
    if (slot < 0 || slot >= BufferQueueDefs::NUM_BUFFER_SLOTS || fence == nullptr) {
        return BAD_VALUE;
    }
    std::lock_guard<std::mutex> lock(mCore->mMutex);
    const sp<GraphicBuffer>& buffer = mSlots[slot].mGraphicBuffer;
    if (buffer != nullptr && buffer->getId() == bufferId) {
        mSlots[slot].mPicoReadyFence = fence;
        mSlots[slot].mPicoFenceReady = true;
        mCore->mPicoFenceCondition.notify_all();
    }
    return NO_ERROR;
}

'''
    consumer = consumer[:start] + function + consumer[end:]
    start = consumer.index('status_t BufferQueueConsumer::disconnect(')
    end = consumer.index('\nstatus_t ', start + 1)
    function = consumer[start:end]
    function = replace(function, '    mCore->mDequeueCondition.notify_all();', '    mCore->mDequeueCondition.notify_all();\n    mCore->mPicoFenceCondition.notify_all();')
    consumer = consumer[:start] + function + consumer[end:]
    edits['BufferQueueConsumer.cpp'] = consumer
    producer = read('include/gui/BufferQueueProducer.h')
    producer = replace(producer, '    int getFreeBufferLocked() const;', '    int getFreeBufferLocked() const;\n    void waitForFenceReadyBufferLocked(int slot, sp<Fence>* outFence);')
    producer = replace(producer, '}; // class BufferQueueProducer', '    bool mPicoFenceReadyMode = false;\n}; // class BufferQueueProducer')
    edits['include/gui/BufferQueueProducer.h'] = producer
    producer = read('BufferQueueProducer.cpp')
    producer = replace(producer, '''    int slot = mCore->mFreeBuffers.front();
    mCore->mFreeBuffers.pop_front();
    return slot;''', '''    auto selected = mCore->mFreeBuffers.begin();
    const sp<GraphicBuffer>& buffer = mSlots[*selected].mGraphicBuffer;
    if (mPicoFenceReadyMode && buffer != nullptr &&
            (buffer->getUsage() & 0xf00000000ULL) == 0x200000000ULL &&
            !mSlots[*selected].mPicoFenceReady) {
        auto ready = std::find_if(std::next(selected), mCore->mFreeBuffers.end(),
                [this](int slot) { return mSlots[slot].mPicoFenceReady; });
        if (ready != mCore->mFreeBuffers.end()) selected = ready;
    }
    int slot = *selected;
    mCore->mFreeBuffers.erase(selected);
    return slot;''')
    start = producer.index('status_t BufferQueueProducer::dequeueBuffer(')
    end = producer.index('status_t BufferQueueProducer::detachBuffer(', start)
    function = producer[start:end]
    function = replace(function, '''    } // Autolock scope

    if (returnFlags & BUFFER_NEEDS_REALLOCATION) {''', '''        waitForFenceReadyBufferLocked(found, outFence);
    } // Autolock scope

    if (returnFlags & BUFFER_NEEDS_REALLOCATION) {''')
    helper = '''// Caller owns mCore->mMutex. The factory waits once for 13,880,000 ns.
void BufferQueueProducer::waitForFenceReadyBufferLocked(int slot, sp<Fence>* outFence) {
    if (slot < 0 || slot >= BufferQueueDefs::NUM_BUFFER_SLOTS || outFence == nullptr) return;
    sp<GraphicBuffer> buffer = mSlots[slot].mGraphicBuffer;
    constexpr uint64_t mask = 0xf00000000ULL;
    if (buffer == nullptr || (buffer->getUsage() & mask) != 0x200000000ULL) return;
    mPicoFenceReadyMode = true;
    uint64_t outcome = 0;
    bool timeout = false;
    if (!mSlots[slot].mPicoFenceReady) {
        std::unique_lock<std::mutex> adopted(mCore->mMutex, std::adopt_lock);
        timeout = mCore->mPicoFenceCondition.wait_for(adopted,
                std::chrono::nanoseconds(13'880'000)) == std::cv_status::timeout;
        // Preserve ownership in the caller's existing lock.
        adopted.release();
        buffer = mSlots[slot].mGraphicBuffer;
        if (buffer == nullptr) return;
    }
    if (timeout) {
        outcome = 0x800000000ULL;
    } else {
        if (!mSlots[slot].mPicoFenceReady) outcome = 0x400000000ULL;
        *outFence = mSlots[slot].mPicoReadyFence;
        mSlots[slot].mPicoFenceReady = false;
        mSlots[slot].mPicoReadyFence = Fence::NO_FENCE;
    }
    buffer->usage = (buffer->getUsage() & ~mask) | outcome;
}

'''
    producer = producer[:start] + function + helper + producer[end:]
    start = producer.index('status_t BufferQueueProducer::disconnect(')
    end = producer.index('\nstatus_t ', start + 1)
    function = producer[start:end]
    function = replace(function, '                mCore->mDequeueCondition.notify_all();', '                mCore->mDequeueCondition.notify_all();\n                mCore->mPicoFenceCondition.notify_all();')
    producer = producer[:start] + function + producer[end:]
    edits['BufferQueueProducer.cpp'] = producer
    base = read('include/gui/ConsumerBase.h')
    base = replace(base, '    bool mAbandoned;', '    int mLatchAcquireSlot;\n    bool mAbandoned;')
    base = replace(base, '    // releaseBufferLocked relinquishes', '    // Caller holds mMutex; retains the most recently acquired slot.\n    int getLatchAcquireSlotLocked();\n\n    // releaseBufferLocked relinquishes')
    edits['include/gui/ConsumerBase.h'] = base
    base = read('ConsumerBase.cpp')
    base = replace(base, '        mAbandoned(false),', '        mLatchAcquireSlot(BufferItem::INVALID_BUFFER_SLOT),\n        mAbandoned(false),')
    start = base.index('status_t ConsumerBase::acquireBufferLocked(')
    end = base.index('\nstatus_t ', start + 1)
    function = base[start:end]
    function = replace(function, '    return OK;', '    mLatchAcquireSlot = item->mSlot;\n    return OK;')
    function += '''int ConsumerBase::getLatchAcquireSlotLocked() {
    return mLatchAcquireSlot;
}

'''
    base = base[:start] + function + base[end:]
    edits['ConsumerBase.cpp'] = base
    # No files are written unless every source anchor was validated.
    for relative, text in edits.items():
        (TARGET / 'libs/gui' / relative).write_text(text)
    print('Applied local consumer/dequeue fence-ready group to', len(edits), 'source files')


if __name__ == '__main__':
    main()
