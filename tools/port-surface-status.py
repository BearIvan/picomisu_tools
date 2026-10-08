"""Apply the experimental PICO Surface VR-status bridge to a clean AOSP 10 base."""
import argparse
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unexpected AOSP source; refusing ambiguous patch')
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frameworks_base', type=Path)
    args = parser.parse_args()
    java = args.frameworks_base / 'core/java/android/view/Surface.java'
    jni = args.frameworks_base / 'core/jni/android_view_Surface.cpp'
    java_text, jni_text = java.read_text(), jni.read_text()
    if 'nativeSetPvrStatus' in java_text or 'nativeSetPvrStatus' in jni_text:
        raise RuntimeError('VR status bridge already present; inspect existing changes')
    java_text = replace_once(java_text,
        '    private static native int nativeSetScalingMode(long nativeObject, int scalingMode);',
        '    private static native void nativeSetPvrStatus(long nativeObject, int status);\n'
        '    private static native int nativeSetScalingMode(long nativeObject, int scalingMode);')
    java_text = replace_once(java_text, '    void forceScopedDisconnect() {', '''    /**
     * Pass a PICO VR status value to the producer without changing its interpretation.
     * Requires the PICO QUERY transport and a producer implementing query 10000.
     * @hide
     */
    @UnsupportedAppUsage
    public void setPvrStatus(int status) {
        synchronized (mLock) {
            checkNotReleasedLocked();
            nativeSetPvrStatus(mNativeObject, status);
        }
    }

    void forceScopedDisconnect() {''')
    jni_text = replace_once(jni_text,
        'static jint nativeSetScalingMode(JNIEnv *env, jclass clazz, jlong nativeObject, jint scalingMode) {',
        '''static void nativeSetPvrStatus(JNIEnv*, jclass, jlong nativeObject, jint status) {
    Surface* surface = reinterpret_cast<Surface*>(nativeObject);
    sp<IGraphicBufferProducer> producer = surface->getIGraphicBufferProducer();
    // PICO 5.13.7 uses query 10000 as an input operation. Its JNI entry has
    // signature (JI)V and ignores the returned status and output value.
    constexpr int kPicoQuerySetPvrStatus = 10000;
    int value = status;
    producer->query(kPicoQuerySetPvrStatus, &value);
}

static jint nativeSetScalingMode(JNIEnv *env, jclass clazz, jlong nativeObject, jint scalingMode) {''')
    jni_text = replace_once(jni_text,
        '    {"nativeSetScalingMode", "(JI)I", (void*)nativeSetScalingMode },',
        '    {"nativeSetPvrStatus", "(JI)V", (void*)nativeSetPvrStatus },\n'
        '    {"nativeSetScalingMode", "(JI)I", (void*)nativeSetScalingMode },')
    java.write_text(java_text)
    jni.write_text(jni_text)


if __name__ == '__main__':
    main()
