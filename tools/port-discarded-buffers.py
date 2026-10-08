"""Port the connected QPR3 discarded-buffer notification group.

Uses a pinned public donor and preserves existing Picomisu native changes.
Does not include the unrelated damage merge or attach-with-dataspace changes.
"""
import difflib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
CACHE = PROJECT / 'analysis/qualcomm-reference/native.git'
TARGET = PROJECT / 'source/aosp-10/frameworks/native'
BASE = '013eb744f289c70e6d3fe180500d9a414ac55539'
DONOR = '71e1890b755f126274e8225875050c7b785006e4'
FILES = ['IProducerListener.cpp', 'include/gui/IProducerListener.h',
         'BufferQueueCore.cpp', 'include/gui/BufferQueueCore.h',
         'BufferQueueProducer.cpp', 'BufferQueueConsumer.cpp',
         'Surface.cpp', 'include/gui/Surface.h']


def source(commit, path):
    return subprocess.check_output(['git', '-C', str(CACHE), 'show', commit + ':' + path], text=True)


def function(text, name):
    match = re.search(re.escape(name) + r'\s*\(', text)
    if not match:
        raise RuntimeError('Missing expected function: ' + name)
    start = text.rfind('\n', 0, match.start()) + 1
    brace = text.index('{', match.end())
    depth = 0
    for end in range(brace, len(text)):
        if text[end] == '{':
            depth += 1
        elif text[end] == '}':
            depth -= 1
            if depth == 0:
                return text[start:end + 1]
    raise RuntimeError('Unbalanced donor function')


def main():
    mounted = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,UUID', '--target', str(PROJECT)], text=True).split()
    if mounted != ['ext4', 'a00da05f-1eb2-44b6-99f0-9109391f67dc']:
        raise RuntimeError('Expected ext4 source volume')
    if subprocess.check_output(['git', '-C', str(TARGET), 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Preserve existing uncommitted source changes')
    patches = []
    for filename in FILES:
        path = 'libs/gui/' + filename
        old, new = source(BASE, path), source(DONOR, path)
        if filename == 'Surface.cpp':
            new = new.replace(function(new, 'Surface::attachAndQueueBufferWithDataspace'),
                              function(old, 'Surface::attachAndQueueBuffer'), 1)
        elif filename == 'include/gui/Surface.h':
            new, count = re.subn(r'    static status_t attachAndQueueBufferWithDataspace\([^;]+;',
                                '    static status_t attachAndQueueBuffer(Surface* surface, sp<GraphicBuffer> buffer);',
                                new)
            if count != 1:
                raise RuntimeError('Unexpected donor Surface declaration')
        elif filename == 'BufferQueueProducer.cpp':
            unrelated = '''                // Make sure to merge the damage rect from the frame we're about
                // to drop into the new frame's damage rect.
                if (last.mSurfaceDamage.bounds() == Rect::INVALID_RECT ||
                    item.mSurfaceDamage.bounds() == Rect::INVALID_RECT) {
                    item.mSurfaceDamage = Region::INVALID_REGION;
                } else {
                    item.mSurfaceDamage |= last.mSurfaceDamage;
                }

'''
            if new.count(unrelated) != 1:
                raise RuntimeError('Unexpected donor queueBuffer damage change')
            new = new.replace(unrelated, '', 1)
        patch = ''.join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                           fromfile='a/' + path, tofile='b/' + path))
        if patch:
            patches.append('diff --git a/' + path + ' b/' + path + '\n' + patch)
    patch = ''.join(patches)
    subprocess.run(['git', '-C', str(TARGET), 'apply', '--check', '-'], input=patch, text=True, check=True)
    subprocess.run(['git', '-C', str(TARGET), 'apply', '-'], input=patch, text=True, check=True)
    (ROOT / 'patches/0005-qpr3-discarded-buffer-notifications.patch').write_text(patch)
    print('Applied pinned QPR3 notification group to eight source files')


if __name__ == '__main__':
    main()
