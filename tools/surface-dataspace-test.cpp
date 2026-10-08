// Copyright 2026 Picomisu contributors
// SPDX-License-Identifier: Apache-2.0
#include <gui/BufferQueueCore.h>
#include <gui/BufferQueueProducer.h>
#include <gui/Surface.h>
#include <ui/GraphicBuffer.h>
#include <gtest/gtest.h>
#include <cstdarg>
#include <vector>

namespace android {
namespace {
class RecordingSurface : public Surface {
public:
    explicit RecordingSurface(const sp<IGraphicBufferProducer>& producer) : Surface(producer) {
        Surface::setBuffersDataSpace(ui::Dataspace::V0_SRGB);
        ANativeWindow* window = this;
        window->perform = performHook;
        window->queueBuffer = queueHook;
    }
    int failureStep = 0;
    std::vector<int> calls;
    int step(int number) {
        calls.push_back(number);
        return number == failureStep ? -100 - number : OK;
    }
    int setBuffersDataSpace(ui::Dataspace value) override {
        int result = step(calls.size() == 1 ? 2 : 5);
        return result == OK ? Surface::setBuffersDataSpace(value) : result;
    }
    int attachBuffer(ANativeWindowBuffer* buffer) override {
        EXPECT_NE(nullptr, buffer);
        return step(3);
    }
    int disconnect(int api, IGraphicBufferProducer::DisconnectMode mode) override {
        EXPECT_EQ(NATIVE_WINDOW_API_CPU, api);
        EXPECT_EQ(IGraphicBufferProducer::DisconnectMode::Api, mode);
        return step(6);
    }
    static int performHook(ANativeWindow* window, int operation, ...) {
        va_list args;
        va_start(args, operation);
        int api = va_arg(args, int);
        va_end(args);
        EXPECT_EQ(NATIVE_WINDOW_API_CONNECT, operation);
        EXPECT_EQ(NATIVE_WINDOW_API_CPU, api);
        return static_cast<RecordingSurface*>(window)->step(1);
    }
    static int queueHook(ANativeWindow* window, ANativeWindowBuffer* buffer, int fd) {
        auto self = static_cast<RecordingSurface*>(window);
        EXPECT_NE(nullptr, buffer);
        EXPECT_EQ(-1, fd);
        EXPECT_EQ(ui::Dataspace::DISPLAY_P3, self->getBuffersDataSpace());
        return self->step(4);
    }
};

sp<RecordingSurface> makeSurface() {
    sp<BufferQueueCore> core = new BufferQueueCore;
    return new RecordingSurface(new BufferQueueProducer(core));
}
}

TEST(PicoSurfaceDataspace, SuccessRestoresDataspaceAndDisconnects) {
    sp<RecordingSurface> surface = makeSurface();
    sp<GraphicBuffer> buffer = new GraphicBuffer;
    EXPECT_EQ(OK, Surface::attachAndQueueBufferWithDataspace(surface.get(), buffer,
                                                            ui::Dataspace::DISPLAY_P3));
    EXPECT_EQ((std::vector<int>{1, 2, 3, 4, 5, 6}), surface->calls);
    EXPECT_EQ(ui::Dataspace::V0_SRGB, surface->getBuffersDataSpace());
}

TEST(PicoSurfaceDataspace, NullBufferReturnsBadValueBeforeAccessingSurface) {
    EXPECT_EQ(BAD_VALUE, Surface::attachAndQueueBufferWithDataspace(nullptr, nullptr,
                                                                   ui::Dataspace::DISPLAY_P3));
}

TEST(PicoSurfaceDataspace, EveryFailureReturnsImmediatelyLikeFactory) {
    for (int failing = 1; failing <= 6; ++failing) {
        SCOPED_TRACE(failing);
        sp<RecordingSurface> surface = makeSurface();
        sp<GraphicBuffer> buffer = new GraphicBuffer;
        surface->failureStep = failing;
        EXPECT_EQ(-100 - failing, Surface::attachAndQueueBufferWithDataspace(
                surface.get(), buffer, ui::Dataspace::DISPLAY_P3));
        std::vector<int> expected;
        for (int step = 1; step <= failing; ++step) expected.push_back(step);
        EXPECT_EQ(expected, surface->calls);
        EXPECT_EQ(failing <= 2 || failing == 6 ? ui::Dataspace::V0_SRGB : ui::Dataspace::DISPLAY_P3,
                  surface->getBuffersDataSpace());
    }
}
} // namespace android
