// Copyright 2026 Picomisu contributors
// SPDX-License-Identifier: Apache-2.0
#include <binder/Binder.h>
#include <binder/Parcel.h>
#include <gui/BufferItem.h>
#include <gui/BufferQueueConsumer.h>
#include <gui/BufferQueueCore.h>
#include <gui/BufferQueueProducer.h>
#include <gui/IConsumerListener.h>
#include <gui/IProducerListener.h>
#include <gui/Surface.h>
#include <gtest/gtest.h>
#include <system/window.h>

#include <limits>
#include <vector>

namespace android {
namespace {

constexpr uint32_t kOnBuffersDiscarded = IBinder::FIRST_CALL_TRANSACTION + 2;

class ProducerRelay : public BBinder {
public:
    explicit ProducerRelay(const sp<IBinder>& target) : mTarget(target) {}
    uint32_t lastCode = 0, lastFlags = 0;
protected:
    status_t onTransact(uint32_t code, const Parcel& data, Parcel* reply, uint32_t flags) override {
        lastCode = code;
        lastFlags = flags;
        return mTarget->transact(code, data, reply, flags);
    }
private:
    sp<IBinder> mTarget;
};

class RecordingProducer : public BnProducerListener {
public:
    explicit RecordingProducer(bool releaseNotify = false) : wantsRelease(releaseNotify) {}
    void onBufferReleased() override { ++released; }
    bool needsReleaseNotify() override { return wantsRelease; }
    void onBuffersDiscarded(const std::vector<int32_t>& slots) override {
        ++discarded;
        lastSlots = slots;
    }
    bool wantsRelease;
    int released = 0, discarded = 0;
    std::vector<int32_t> lastSlots;
};

class RecordingSurfaceListener : public SurfaceListener {
public:
    void onBufferReleased() override { ++released; }
    bool needsReleaseNotify() override { return false; }
    void onBuffersDiscarded(const std::vector<sp<GraphicBuffer>>& buffers) override {
        ++discarded;
        lastBuffers = buffers;
    }
    int released = 0, discarded = 0;
    std::vector<sp<GraphicBuffer>> lastBuffers;
};

class TestSurface : public Surface {
public:
    explicit TestSurface(const sp<IGraphicBufferProducer>& producer) : Surface(producer) {}
    using Surface::getAndFlushBuffersFromSlots;
    sp<IProducerListener> proxy() { return mListenerProxy; }
};

class IdleConsumer : public BnConsumerListener {
public:
    void onFrameAvailable(const BufferItem&) override {}
    void onBuffersReleased() override {}
    void onSidebandStreamChanged() override {}
};

class ProducerDiscardTest : public testing::Test {
protected:
    void SetUp() override {
        core = new BufferQueueCore;
        producer = new BufferQueueProducer(core);
        consumer = new BufferQueueConsumer(core);
        ASSERT_EQ(NO_ERROR, consumer->connect(new IdleConsumer, false));
    }
    void queueAndRelease(const sp<GraphicBuffer>& buffer, int* slot) {
        ASSERT_EQ(NO_ERROR, producer->attachBuffer(slot, buffer));
        IGraphicBufferProducer::QueueBufferInput input(0, false, HAL_DATASPACE_UNKNOWN,
                Rect::EMPTY_RECT, NATIVE_WINDOW_SCALING_MODE_FREEZE, 0, Fence::NO_FENCE);
        IGraphicBufferProducer::QueueBufferOutput output;
        ASSERT_EQ(NO_ERROR, producer->queueBuffer(*slot, input, &output));
        BufferItem acquired;
        ASSERT_EQ(NO_ERROR, consumer->acquireBuffer(&acquired, 0));
        ASSERT_EQ(*slot, acquired.mSlot);
        ASSERT_EQ(NO_ERROR, consumer->releaseBuffer(acquired.mSlot, acquired.mFrameNumber,
                  EGL_NO_DISPLAY, EGL_NO_SYNC_KHR, Fence::NO_FENCE));
    }
    void queueSurfaceAndRelease(const sp<TestSurface>& surface,
                                const sp<GraphicBuffer>& buffer, int* slot) {
        ASSERT_EQ(NO_ERROR, surface->attachBuffer(buffer->getNativeBuffer()));
        ANativeWindow* window = surface.get();
        ASSERT_EQ(NO_ERROR, window->queueBuffer(window, buffer->getNativeBuffer(), -1));
        BufferItem acquired;
        ASSERT_EQ(NO_ERROR, consumer->acquireBuffer(&acquired, 0));
        *slot = acquired.mSlot;
        ASSERT_EQ(NO_ERROR, consumer->releaseBuffer(acquired.mSlot, acquired.mFrameNumber,
                  EGL_NO_DISPLAY, EGL_NO_SYNC_KHR, Fence::NO_FENCE));
    }
    sp<BufferQueueCore> core;
    sp<BufferQueueProducer> producer;
    sp<BufferQueueConsumer> consumer;
};

TEST_F(ProducerDiscardTest, BinderCarriesSlotVectorAsOneWayTransaction) {
    sp<RecordingProducer> listener = new RecordingProducer;
    sp<ProducerRelay> relay = new ProducerRelay(IInterface::asBinder(listener));
    sp<IProducerListener> proxy = interface_cast<IProducerListener>(relay);
    std::vector<int32_t> slots{0, 4, -1, std::numeric_limits<int32_t>::max(), 4};
    proxy->onBuffersDiscarded(slots);
    ASSERT_EQ(1, listener->discarded);
    EXPECT_EQ(slots, listener->lastSlots);
    EXPECT_EQ(kOnBuffersDiscarded, relay->lastCode);
    EXPECT_NE(0u, relay->lastFlags & IBinder::FLAG_ONEWAY);
}

TEST_F(ProducerDiscardTest, BinderPreservesOldCallbacksAndAcceptsEmptyVector) {
    sp<RecordingProducer> listener = new RecordingProducer(true);
    sp<ProducerRelay> relay = new ProducerRelay(IInterface::asBinder(listener));
    sp<IProducerListener> proxy = interface_cast<IProducerListener>(relay);
    EXPECT_TRUE(proxy->needsReleaseNotify());
    EXPECT_EQ(IBinder::FIRST_CALL_TRANSACTION + 1, relay->lastCode);
    proxy->onBufferReleased();
    EXPECT_EQ(1, listener->released);
    EXPECT_EQ(IBinder::FIRST_CALL_TRANSACTION, relay->lastCode);
    proxy->onBuffersDiscarded({});
    EXPECT_EQ(1, listener->discarded);
    EXPECT_TRUE(listener->lastSlots.empty());
}

TEST_F(ProducerDiscardTest, BinderRejectsWrongInterface) {
    sp<RecordingProducer> listener = new RecordingProducer;
    Parcel data, reply;
    data.writeInterfaceToken(producer->getInterfaceDescriptor());
    data.writeInt32Vector({1});
    EXPECT_EQ(PERMISSION_DENIED, IInterface::asBinder(listener)->transact(kOnBuffersDiscarded, data, &reply));
    EXPECT_EQ(0, listener->discarded);
}

TEST_F(ProducerDiscardTest, BinderRejectsTruncatedSlotVector) {
    sp<RecordingProducer> listener = new RecordingProducer;
    Parcel data, reply;
    data.writeInterfaceToken(listener->getInterfaceDescriptor());
    data.writeInt32(2);
    data.writeInt32(1);
    EXPECT_NE(NO_ERROR, IInterface::asBinder(listener)->transact(kOnBuffersDiscarded, data, &reply));
    EXPECT_EQ(0, listener->discarded);
}

TEST_F(ProducerDiscardTest, DiscardNotificationWorksWhenReleaseNotificationDisabled) {
    sp<RecordingProducer> listener = new RecordingProducer(false);
    IGraphicBufferProducer::QueueBufferOutput output;
    ASSERT_EQ(NO_ERROR, producer->connect(listener, NATIVE_WINDOW_API_CPU, false, &output));
    sp<GraphicBuffer> buffer = new GraphicBuffer;
    int slot = -1;
    queueAndRelease(buffer, &slot);
    EXPECT_EQ(0, listener->released);
    ASSERT_EQ(NO_ERROR, consumer->discardFreeBuffers());
    ASSERT_EQ(1, listener->discarded);
    EXPECT_EQ(std::vector<int32_t>{slot}, listener->lastSlots);
}

TEST_F(ProducerDiscardTest, ReleaseNotificationStillWorksWhenEnabled) {
    sp<RecordingProducer> listener = new RecordingProducer(true);
    IGraphicBufferProducer::QueueBufferOutput output;
    ASSERT_EQ(NO_ERROR, producer->connect(listener, NATIVE_WINDOW_API_CPU, false, &output));
    sp<GraphicBuffer> buffer = new GraphicBuffer;
    int slot = -1;
    queueAndRelease(buffer, &slot);
    EXPECT_EQ(1, listener->released);
    ASSERT_EQ(NO_ERROR, consumer->discardFreeBuffers());
    EXPECT_EQ(1, listener->discarded);
}

TEST_F(ProducerDiscardTest, EmptyFreeListDoesNotNotify) {
    sp<RecordingProducer> listener = new RecordingProducer;
    IGraphicBufferProducer::QueueBufferOutput output;
    ASSERT_EQ(NO_ERROR, producer->connect(listener, NATIVE_WINDOW_API_CPU, false, &output));
    ASSERT_EQ(NO_ERROR, consumer->discardFreeBuffers());
    EXPECT_EQ(0, listener->discarded);
}

TEST_F(ProducerDiscardTest, SurfaceConvertsSlotsToBuffersAndClearsItsCache) {
    sp<TestSurface> surface = new TestSurface(producer);
    sp<RecordingSurfaceListener> listener = new RecordingSurfaceListener;
    ASSERT_EQ(NO_ERROR, surface->connect(NATIVE_WINDOW_API_CPU, false, listener));
    sp<GraphicBuffer> buffer = new GraphicBuffer;
    int slot = -1;
    queueSurfaceAndRelease(surface, buffer, &slot);
    ASSERT_EQ(NO_ERROR, consumer->discardFreeBuffers());
    ASSERT_EQ(1, listener->discarded);
    ASSERT_EQ(1u, listener->lastBuffers.size());
    EXPECT_EQ(buffer.get(), listener->lastBuffers[0].get());
    EXPECT_EQ(0, listener->released);
    std::vector<sp<GraphicBuffer>> remaining;
    EXPECT_EQ(NO_ERROR, surface->getAndFlushBuffersFromSlots({slot}, &remaining));
    EXPECT_TRUE(remaining.empty());
}

TEST_F(ProducerDiscardTest, SurfaceValidatesAllSlotsBeforeClearingAny) {
    sp<TestSurface> surface = new TestSurface(producer);
    sp<RecordingSurfaceListener> listener = new RecordingSurfaceListener;
    ASSERT_EQ(NO_ERROR, surface->connect(NATIVE_WINDOW_API_CPU, false, listener));
    sp<GraphicBuffer> buffer = new GraphicBuffer;
    int slot = -1;
    queueSurfaceAndRelease(surface, buffer, &slot);
    std::vector<sp<GraphicBuffer>> buffers;
    EXPECT_EQ(BAD_VALUE, surface->getAndFlushBuffersFromSlots({slot, -1}, &buffers));
    EXPECT_TRUE(buffers.empty());
    ASSERT_EQ(NO_ERROR, surface->getAndFlushBuffersFromSlots({slot}, &buffers));
    ASSERT_EQ(1u, buffers.size());
    EXPECT_EQ(buffer.get(), buffers[0].get());
}

TEST_F(ProducerDiscardTest, SurfaceProxyDoesNotNotifyAfterSurfaceIsDestroyed) {
    sp<TestSurface> surface = new TestSurface(producer);
    sp<RecordingSurfaceListener> listener = new RecordingSurfaceListener;
    ASSERT_EQ(NO_ERROR, surface->connect(NATIVE_WINDOW_API_CPU, false, listener));
    sp<IProducerListener> proxy = surface->proxy();
    ASSERT_NE(nullptr, proxy.get());
    surface.clear();
    proxy->onBuffersDiscarded({0});
    EXPECT_EQ(0, listener->discarded);
}

} // namespace
} // namespace android
