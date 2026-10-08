"""Implement the verified PICO producer fence callback and virtual-display listener.

Only edits source; no build, download, device access or firmware installation.
The related consumer fence-readiness path is a separate, still pending port.
"""
from pathlib import Path
import subprocess

PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
TARGET = PROJECT / 'source/aosp-10/frameworks/native'


def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Expected exactly one source anchor: ' + old[:100])
    return text.replace(old, new, 1)


def main():
    mounted = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,UUID', '--target', str(PROJECT)], text=True).split()
    if mounted != ['ext4', 'a00da05f-1eb2-44b6-99f0-9109391f67dc']:
        raise RuntimeError('Expected ext4 source volume')
    if subprocess.check_output(['git', '-C', str(TARGET), 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Preserve existing uncommitted source changes')
    path = TARGET / 'libs/gui/include/gui/IProducerListener.h'
    header = path.read_text()
    header = replace(header, '#include <vector>', '#include <functional>\n#include <vector>')
    header = replace(header, '#include <utils/RefBase.h>', '#include <ui/Fence.h>\n#include <utils/Mutex.h>\n#include <utils/RefBase.h>')
    header = replace(header, '    virtual void onBuffersDiscarded(const std::vector<int32_t>& slots) = 0; // Asynchronous', '''    virtual void onBuffersDiscarded(const std::vector<int32_t>& slots) = 0; // Asynchronous

    // PICO Binder transaction 4 carries a flattened Fence, a buffer ID and a
    // boolean flag. This callback follows onBuffersDiscarded in the vtable.
    virtual void onBufferReleasedWithFence(const sp<Fence>& fence, uint64_t bufferId,
                                          bool flag) = 0; // Asynchronous''')
    header = replace(header, '    virtual void onBuffersDiscarded(const std::vector<int32_t>& slots);', '''    virtual void onBuffersDiscarded(const std::vector<int32_t>& slots);
    virtual void onBufferReleasedWithFence(const sp<Fence>& fence, uint64_t bufferId,
                                          bool flag);''')
    header = replace(header, 'class DummyProducerListener : public BnProducerListener', '''// Factory SurfaceFlinger installs a callback on this producer listener. Keep
// the callback before the mutex: its layout is used by factory inline callers.
class VirtualDisplayProducerListener : public BnProducerListener
{
public:
    VirtualDisplayProducerListener() = default;
    ~VirtualDisplayProducerListener() override;
    void onBufferReleased() override {}
    bool needsReleaseNotify() override { return false; }
    void onBufferReleasedWithFence(const sp<Fence>& fence, uint64_t bufferId,
                                  bool flag) override;
    void setCallback(std::function<int(const sp<Fence>&, uint64_t, bool)> callback);

private:
    std::function<int(const sp<Fence>&, uint64_t, bool)> mCallback;
    Mutex mCallbackMutex;
};

class DummyProducerListener : public BnProducerListener''')
    cpp_path = TARGET / 'libs/gui/IProducerListener.cpp'
    cpp = cpp_path.read_text()
    cpp = replace(cpp, '    ON_BUFFERS_DISCARDED,', '    ON_BUFFERS_DISCARDED,\n    ON_BUFFER_RELEASED_WITH_FENCE,')
    cpp = replace(cpp, '''        remote()->transact(ON_BUFFERS_DISCARDED, data, &reply, IBinder::FLAG_ONEWAY);
    }
};''', '''        remote()->transact(ON_BUFFERS_DISCARDED, data, &reply, IBinder::FLAG_ONEWAY);
    }

    void onBufferReleasedWithFence(const sp<Fence>& fence, uint64_t bufferId,
                                  bool flag) override {
        if (fence == nullptr) {
            ALOGE("IProducerListener: null release fence");
            return;
        }
        Parcel data, reply;
        status_t result = data.writeInterfaceToken(IProducerListener::getInterfaceDescriptor());
        if (result == NO_ERROR) result = data.write(*fence);
        if (result == NO_ERROR) result = data.writeUint64(bufferId);
        if (result == NO_ERROR) result = data.writeBool(flag);
        if (result != NO_ERROR) {
            ALOGE("IProducerListener: failed to write release fence: %d", result);
            return;
        }
        remote()->transact(ON_BUFFER_RELEASED_WITH_FENCE, data, &reply, IBinder::FLAG_ONEWAY);
    }
};''')
    cpp = replace(cpp, '''        return mBase->onBuffersDiscarded(discardedSlots);
    }
};''', '''        return mBase->onBuffersDiscarded(discardedSlots);
    }

    void onBufferReleasedWithFence(const sp<Fence>& fence, uint64_t bufferId,
                                  bool flag) override {
        mBase->onBufferReleasedWithFence(fence, bufferId, flag);
    }
};''')
    cpp = replace(cpp, '''            onBuffersDiscarded(discardedSlots);
            return NO_ERROR;
        }
    }
    return BBinder::onTransact(code, data, reply, flags);''', '''            onBuffersDiscarded(discardedSlots);
            return NO_ERROR;
        }
        case ON_BUFFER_RELEASED_WITH_FENCE: {
            CHECK_INTERFACE(IProducerListener, data, reply);
            sp<Fence> fence = new Fence;
            uint64_t bufferId;
            bool flag;
            status_t result = data.read(*fence);
            if (result == NO_ERROR) result = data.readUint64(&bufferId);
            if (result == NO_ERROR) result = data.readBool(&flag);
            if (result != NO_ERROR) {
                ALOGE("ON_BUFFER_RELEASED_WITH_FENCE: malformed payload: %d", result);
                return result;
            }
            onBufferReleasedWithFence(fence, bufferId, flag);
            return NO_ERROR;
        }
    }
    return BBinder::onTransact(code, data, reply, flags);''')
    cpp = replace(cpp, '} // namespace android', '''void BnProducerListener::onBufferReleasedWithFence(const sp<Fence>& /*fence*/,
                                                 uint64_t /*bufferId*/, bool /*flag*/) {
}

VirtualDisplayProducerListener::~VirtualDisplayProducerListener() = default;

void VirtualDisplayProducerListener::setCallback(
        std::function<int(const sp<Fence>&, uint64_t, bool)> callback) {
    Mutex::Autolock lock(mCallbackMutex);
    mCallback = callback;
}

void VirtualDisplayProducerListener::onBufferReleasedWithFence(
        const sp<Fence>& fence, uint64_t bufferId, bool flag) {
    Mutex::Autolock lock(mCallbackMutex);
    if (mCallback) {
        // Factory ignores the callback's int result; the listener returns void.
        mCallback(fence, bufferId, flag);
    } else {
        ALOGE("VirtualDisplayProducerListener: no release-fence callback");
    }
}

} // namespace android''')
    # Validate all anchors before modifying either source file.
    path.write_text(header)
    cpp_path.write_text(cpp)
    print('Implemented PICO producer fence transport and virtual-display listener')


if __name__ == '__main__':
    main()
