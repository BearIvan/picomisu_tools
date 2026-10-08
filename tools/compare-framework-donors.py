"""Check open-source framework donors for PICO API candidates that consumers need.

Reads validation/api-consumers.json and, for every `needed` and
`needed_by_preserved_factory_component` candidate, looks for the same DEX
descriptor in pinned donor trees:

* Java sources are parsed into declarations (types, fields, methods) and every
  parameter/return/field type is resolved to a DEX descriptor through the
  file's package, imports, nested and inherited member types and a class index
  of the whole donor tree; constructors of inner classes and enums receive the
  implicit leading parameters that javac emits.
* AIDL interfaces are expanded into the classes and methods that the AIDL
  compiler generates (I, I$Stub, I$Stub$Proxy, I$Default).
* JAR/AAR files of the PICO SDK repositories are read as class files, which
  give exact descriptors for definitions and for client call sites.

Quality `exact` means the whole descriptor matches; `name-only` means the class
simple name or member name matches but the descriptor differs or could not be
resolved. Donor sources are read from separate bare blobless Git caches on the
research volume; the script never fetches and never changes working trees.
"""
import argparse
import collections
import hashlib
import importlib.util
import io
import json
from multiprocessing import Pool
from pathlib import Path
import pickle
import re
import signal
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
CACHE = PROJECT / 'analysis/framework-reference'
VOLUME = ['ext4', 'a00da05f-1eb2-44b6-99f0-9109391f67dc']
DECISIONS = ('needed', 'needed_by_preserved_factory_component')
SUPPLEMENTARY = 'not_needed'

CAF_BASE = 'https://git.codelinaro.org/clo/la/platform/frameworks/base.git'
CAF_BT = 'https://git.codelinaro.org/clo/la/platform/system/bt.git'
AOSP_BASE = 'https://android.googlesource.com/platform/frameworks/base'
AOSP_BT = 'https://android.googlesource.com/platform/system/bt'
SMT_BASE = 'https://github.com/SmartisanTech/android_frameworks_base.git'
CAF_TAG = 'refs/tags/LA.UM.8.12.c3-64900-sm8250.0'
# Each donor: components (checkout path, bare cache, local ref, upstream ref, remote).
# system/bt carries android.bluetooth AIDL (IBluetooth*) on Android 10-12.
DONORS = [
    {'name': 'qualcomm_q', 'family': 'qualcomm', 'components': [
        ('frameworks/base', 'caf-base.git', 'refs/research/qualcomm-q-64900', CAF_TAG, CAF_BASE),
        ('system/bt', 'caf-bt.git', 'refs/research/qualcomm-q-64900', CAF_TAG, CAF_BT)],
     'aliases': [('frameworks/base', 'caf-base.git', 'refs/research/qualcomm-q-77400',
                  'refs/tags/LA.UM.8.12.c3-77400-sm8250.0')]},
    {'name': 'aosp_11_r48', 'family': 'aosp', 'components': [
        ('frameworks/base', 'aosp-base.git', 'refs/research/aosp-11-r48', 'refs/tags/android-11.0.0_r48', AOSP_BASE),
        ('system/bt', 'aosp-bt.git', 'refs/research/aosp-11-r48', 'refs/tags/android-11.0.0_r48', AOSP_BT)]},
    {'name': 'aosp_12.1_r27', 'family': 'aosp', 'components': [
        ('frameworks/base', 'aosp-base.git', 'refs/research/aosp-12.1-r27', 'refs/tags/android-12.1.0_r27', AOSP_BASE),
        ('system/bt', 'aosp-bt.git', 'refs/research/aosp-12.1-r27', 'refs/tags/android-12.1.0_r27', AOSP_BT)]},
    {'name': 'smartisan_m', 'family': 'smartisan', 'components': [
        ('frameworks/base', 'smartisan-base.git', 'refs/research/smartisan-m', 'refs/heads/smartisan-m', SMT_BASE)]},
    {'name': 'smartisan_m_onestep', 'family': 'smartisan', 'components': [
        ('frameworks/base', 'smartisan-base.git', 'refs/research/smartisan-m-onestep',
         'refs/heads/smartisan-m-onestep_bigboom', SMT_BASE)]},
    # Control, not a donor: the AOSP baseline tag. A hit here means the candidate is not new API.
    {'name': 'aosp_10_r47_control', 'family': 'control', 'components': [
        ('frameworks/base', 'aosp-base.git', 'refs/research/aosp-10-r47', 'refs/tags/android-10.0.0_r47', AOSP_BASE),
        ('system/bt', 'aosp-bt.git', 'refs/research/aosp-10-r47', 'refs/tags/android-10.0.0_r47', AOSP_BT)]},
]
AV_SOURCE = ('aosp_av_12.1_r27', 'aosp-av.git', 'refs/research/aosp-12.1-r27', 'refs/tags/android-12.1.0_r27',
             'https://android.googlesource.com/platform/frameworks/av')
AV_MARKERS = {
    'AudioSystem::getSpatializer': r'\bgetSpatializer\s*\(',
    'AudioSystem::canBeSpatialized': r'\bcanBeSpatialized\s*\(',
    'ISpatializer': r'\binterface\s+ISpatializer\b',
    'Spatializer (audiopolicy)': r'\bclass\s+Spatializer\b',
    'track state callback': r'(?i)trackstate',
    'VR metadata type': r'(?i)\bvr_?type\b',
}
PICO_SDK_DIR = 'pico-sdk'
SKIP_PATH = re.compile(r'(^|/)(tests?|testing|benchmarks?)/')

PRIMS = {'void': 'V', 'boolean': 'Z', 'byte': 'B', 'char': 'C', 'short': 'S', 'int': 'I',
         'long': 'J', 'float': 'F', 'double': 'D'}
MODIFIERS = {'public', 'protected', 'private', 'static', 'final', 'abstract', 'native', 'synchronized',
             'transient', 'volatile', 'strictfp', 'default', 'sealed', 'non-sealed'}
JAVA_LANG = set('''String Object Integer Long Boolean Byte Short Character Float Double Number CharSequence
Runnable Thread Class ClassLoader Throwable Exception RuntimeException Error IllegalArgumentException
IllegalStateException Iterable Comparable Void StringBuilder StringBuffer Enum Math StrictMath System
AutoCloseable Cloneable Process ProcessBuilder Runtime ThreadLocal InheritableThreadLocal InterruptedException
SecurityException UnsupportedOperationException NullPointerException IndexOutOfBoundsException
ArrayIndexOutOfBoundsException StringIndexOutOfBoundsException ClassCastException NumberFormatException
CloneNotSupportedException ClassNotFoundException NoSuchMethodException NoSuchFieldException
ReflectiveOperationException IllegalAccessException InstantiationException ArithmeticException
Override Deprecated SuppressWarnings FunctionalInterface SafeVarargs StackTraceElement ThreadGroup Package
Appendable Readable OutOfMemoryError AssertionError StackOverflowError LinkageError VirtualMachineError
NoClassDefFoundError UnsatisfiedLinkError ExceptionInInitializerError IllegalMonitorStateException
NegativeArraySizeException ArrayStoreException TypeNotPresentException EnumConstantNotPresentException
SecurityManager Compiler'''.split())
JDK_PACKAGES = {
    'java.util': '''List ArrayList LinkedList Map HashMap LinkedHashMap TreeMap SortedMap NavigableMap Set HashSet
LinkedHashSet TreeSet SortedSet NavigableSet Collection Collections Iterator ListIterator Arrays Queue Deque
ArrayDeque PriorityQueue Stack Vector Hashtable Enumeration Properties Random UUID Date Calendar Locale
Objects Optional OptionalInt OptionalLong OptionalDouble Comparator BitSet Timer TimerTask Scanner
StringJoiner Map.Entry EventListener EventObject Observable Observer WeakHashMap IdentityHashMap
AbstractList AbstractMap AbstractSet AbstractCollection Spliterator TimeZone Currency Formatter
ConcurrentModificationException NoSuchElementException MissingResourceException ResourceBundle
IllformedLocaleException InputMismatchException EnumMap EnumSet GregorianCalendar SimpleTimeZone
Base64 StringTokenizer RandomAccess PrimitiveIterator DoubleSummaryStatistics IntSummaryStatistics
LongSummaryStatistics'''.split(),
    'java.util.concurrent': '''Executor ExecutorService Executors ScheduledExecutorService Future
CompletableFuture ConcurrentHashMap ConcurrentMap CountDownLatch TimeUnit Callable ThreadPoolExecutor
LinkedBlockingQueue BlockingQueue CopyOnWriteArrayList CopyOnWriteArraySet Semaphore TimeoutException
ExecutionException ThreadFactory ScheduledFuture CancellationException ArrayBlockingQueue
ConcurrentLinkedQueue ConcurrentLinkedDeque CyclicBarrier FutureTask RejectedExecutionException
ScheduledThreadPoolExecutor Delayed LinkedBlockingDeque BlockingDeque CompletionStage ForkJoinPool
ConcurrentSkipListMap ConcurrentSkipListSet PriorityBlockingQueue SynchronousQueue Phaser Exchanger
DelayQueue CompletionService ExecutorCompletionService RunnableFuture'''.split(),
    'java.util.concurrent.atomic': '''AtomicBoolean AtomicInteger AtomicLong AtomicReference
AtomicIntegerArray AtomicLongArray AtomicReferenceArray'''.split(),
    'java.util.concurrent.locks': 'Lock ReentrantLock ReadWriteLock ReentrantReadWriteLock Condition'.split(),
    'java.util.function': '''Function BiFunction Consumer BiConsumer Supplier Predicate BiPredicate
UnaryOperator BinaryOperator IntFunction IntConsumer IntPredicate IntSupplier ToIntFunction
LongConsumer LongFunction ToLongFunction BooleanSupplier DoubleSupplier IntUnaryOperator
ObjIntConsumer'''.split(),
    'java.util.regex': 'Pattern Matcher PatternSyntaxException'.split(),
    'java.io': '''File FileDescriptor FileInputStream FileOutputStream InputStream OutputStream Reader Writer
PrintWriter PrintStream BufferedReader BufferedWriter BufferedInputStream BufferedOutputStream
IOException FileNotFoundException Closeable Serializable DataInputStream DataOutputStream
ByteArrayInputStream ByteArrayOutputStream InputStreamReader OutputStreamWriter StringWriter
StringReader FileReader FileWriter RandomAccessFile EOFException UnsupportedEncodingException
ObjectInputStream ObjectOutputStream FilenameFilter FileFilter Flushable CharArrayWriter
UncheckedIOException InterruptedIOException'''.split(),
    'java.net': '''InetAddress Inet4Address Inet6Address URI URL Socket ServerSocket InetSocketAddress
SocketAddress URLConnection HttpURLConnection UnknownHostException SocketException DatagramSocket
DatagramPacket NetworkInterface URISyntaxException MalformedURLException Proxy
SocketTimeoutException'''.split(),
    'java.nio': 'ByteBuffer ByteOrder CharBuffer IntBuffer FloatBuffer ShortBuffer LongBuffer Buffer'.split(),
    'java.nio.charset': 'Charset StandardCharsets'.split(),
    'java.lang.reflect': 'Method Field Constructor InvocationTargetException Modifier Array Proxy Type'.split(),
    'java.lang.annotation': 'Retention RetentionPolicy Target ElementType Documented Inherited Annotation'.split(),
    'java.lang.ref': 'WeakReference SoftReference Reference ReferenceQueue PhantomReference'.split(),
    'java.text': 'SimpleDateFormat DateFormat NumberFormat DecimalFormat ParseException Collator'.split(),
    'java.security': 'MessageDigest NoSuchAlgorithmException PublicKey PrivateKey KeyStore SecureRandom'.split(),
    'java.time': 'Duration Instant LocalDate LocalDateTime LocalTime ZoneId ZonedDateTime Clock'.split(),
}
AIDL_BUILTINS = {'List': 'java/util/List', 'Map': 'java/util/Map', 'String': 'java/lang/String',
                 'CharSequence': 'java/lang/CharSequence', 'IBinder': 'android/os/IBinder',
                 'FileDescriptor': 'java/io/FileDescriptor',
                 'ParcelFileDescriptor': 'android/os/ParcelFileDescriptor'}

TOKEN = re.compile(r'''
    (?P<ws>\s+)
  | (?P<lc>//[^\n]*)
  | (?P<bc>/\*.*?\*/)
  | (?P<tb>""".*?""")
  | (?P<str>"(?:\\.|[^"\\\n])*")
  | (?P<chr>'(?:\\.|[^'\\\n])+')
  | (?P<id>[A-Za-z_$][\w$]*)
  | (?P<num>\d[\w.]*)
  | (?P<sym>\.\.\.|::|->|.)
''', re.S | re.X)


def tokenize(text):
    tokens, positions = [], []
    for match in TOKEN.finditer(text):
        kind = match.lastgroup
        if kind in ('ws', 'lc', 'bc'):
            continue
        tokens.append('"' if kind in ('tb', 'str', 'chr') else ('0' if kind == 'num' else match.group()))
        positions.append(match.start())
    return tokens, positions


class Parser:
    """Declaration-level Java/AIDL parser; method bodies and initializers are skipped."""

    def __init__(self, text):
        self.t, self.pos = tokenize(text)
        self.newlines = [i for i, ch in enumerate(text) if ch == '\n']
        self.n = len(self.t)

    def line(self, index):
        import bisect
        return bisect.bisect_right(self.newlines, self.pos[min(index, self.n - 1)] if self.n else 0) + 1

    def at(self, i):
        return self.t[i] if i < self.n else ''

    def skip_balanced(self, i, open_, close):
        depth = 0
        while i < self.n:
            tok = self.t[i]
            if tok == open_:
                depth += 1
            elif tok == close:
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return i

    def skip_annotation(self, i):
        i += 1  # '@'
        i += 1
        while self.at(i) == '.' and self.at(i + 1) not in ('', 'interface'):
            i += 2
        if self.at(i) == '(':
            i = self.skip_balanced(i, '(', ')')
        return i

    def skip_angle(self, i):
        depth = 0
        while i < self.n:
            tok = self.t[i]
            if tok == '<':
                depth += 1
            elif tok == '>':
                depth -= 1
                if depth == 0:
                    return i + 1
            elif tok in ('{', '}', ';', '(') and depth:
                return i  # not a type argument list
            i += 1
        return i

    def parse_type(self, i):
        """Return ((parts, dims), next index) or (None, i)."""
        while self.at(i) == '@' and self.at(i + 1) != 'interface':
            i = self.skip_annotation(i)
        while self.at(i) == 'final':
            i += 1
        tok = self.at(i)
        if not tok or not (tok[0].isalpha() or tok[0] in '_$'):
            return None, i
        parts = [tok]
        i += 1
        while True:
            if self.at(i) == '<':
                i = self.skip_angle(i)
            if self.at(i) == '.' and self.at(i + 1) == '@':
                i += 1
                while self.at(i) == '@':
                    i = self.skip_annotation(i)
                parts.append(self.at(i))
                i += 1
                continue
            if self.at(i) == '.' and self.at(i + 1)[:1].isalpha() or (self.at(i) == '.' and self.at(i + 1)[:1] in '_$' and self.at(i + 1)):
                parts.append(self.at(i + 1))
                i += 2
                continue
            break
        dims = 0
        while True:
            while self.at(i) == '@':
                i = self.skip_annotation(i)
            if self.at(i) == '[' and self.at(i + 1) == ']':
                dims += 1
                i += 2
            else:
                break
        return (parts, dims), i

    def parse_type_params(self, i):
        params = {}
        end = self.skip_angle(i)
        j = i + 1
        while j < end - 1:
            while self.at(j) == '@':
                j = self.skip_annotation(j)
            name = self.at(j)
            j += 1
            bound = None
            if self.at(j) == 'extends':
                bound, j = self.parse_type(j + 1)
            params[name] = bound
            depth = 0
            while j < end - 1:
                tok = self.at(j)
                if tok == '<':
                    depth += 1
                elif tok == '>':
                    depth -= 1
                elif tok == ',' and depth == 0:
                    j += 1
                    break
                j += 1
        return params, end

    def parse_java(self):
        out = {'package': '', 'imports': [], 'types': []}
        i = 0
        while i < self.n:
            tok = self.t[i]
            if tok == 'package':
                j = i + 1
                parts = []
                while self.at(j) != ';' and j < self.n:
                    if self.at(j) != '.':
                        parts.append(self.at(j))
                    j += 1
                out['package'] = '.'.join(parts)
                i = j + 1
            elif tok == 'import':
                j = i + 1
                static = self.at(j) == 'static'
                if static:
                    j += 1
                parts = []
                while self.at(j) != ';' and j < self.n:
                    if self.at(j) != '.':
                        parts.append(self.at(j))
                    j += 1
                if not static:
                    out['imports'].append('.'.join(parts))
                else:
                    out['imports'].append('static:' + '.'.join(parts))
                i = j + 1
            elif tok in ('class', 'interface', 'enum', 'record') or (tok == '@' and self.at(i + 1) == 'interface'):
                i = self.parse_type_decl(i, [], None, False, out['types'])
            elif tok == '@':
                i = self.skip_annotation(i)
            else:
                i += 1
        return out

    def parse_type_decl(self, i, modifiers, outer, outer_is_interface, sink):
        line = self.line(i)
        if self.at(i) == '@':
            kind = 'annotation'
            i += 2
        else:
            kind = self.at(i)
            i += 1
        name = self.at(i)
        i += 1
        decl = {'name': name, 'outer': outer, 'kind': kind, 'modifiers': sorted(modifiers), 'line': line,
                'type_params': {}, 'supers': [], 'fields': [], 'methods': [],
                'static': kind != 'class' or 'static' in modifiers or outer is None or outer_is_interface}
        if self.at(i) == '<':
            decl['type_params'], i = self.parse_type_params(i)
        if kind == 'record' and self.at(i) == '(':
            i = self.skip_balanced(i, '(', ')')
        while i < self.n and self.at(i) != '{':
            if self.at(i) in ('extends', 'implements', ','):
                sup, i = self.parse_type(i + 1)
                if sup:
                    decl['supers'].append(sup)
            else:
                i += 1
        sink.append(decl)
        return self.parse_body(i, decl, sink)

    def parse_body(self, i, decl, sink):
        i += 1  # '{'
        rel = decl['name'] if decl['outer'] is None else decl['outer'] + '$' + decl['name']
        is_interface = decl['kind'] in ('interface', 'annotation')
        if decl['kind'] == 'enum':
            while i < self.n and self.at(i) not in (';', '}'):
                while self.at(i) == '@':
                    i = self.skip_annotation(i)
                tok = self.at(i)
                if tok and (tok[0].isalpha() or tok[0] in '_$'):
                    decl['fields'].append({'name': tok, 'type': ([rel.replace('$', '.')], 0), 'self_enum': True,
                                           'modifiers': ['public', 'static', 'final'], 'line': self.line(i)})
                    i += 1
                if self.at(i) == '(':
                    i = self.skip_balanced(i, '(', ')')
                if self.at(i) == '{':
                    i = self.skip_balanced(i, '{', '}')
                if self.at(i) == ',':
                    i += 1
                elif self.at(i) not in (';', '}'):
                    i += 1
            if self.at(i) == ';':
                i += 1
        while i < self.n:
            tok = self.t[i]
            if tok == '}':
                return i + 1
            if tok == ';':
                i += 1
                continue
            modifiers = []
            start = i
            while True:
                tok = self.at(i)
                if tok in MODIFIERS or (tok == 'non' and self.at(i + 1) == '-'):
                    if tok == 'non':
                        i += 2
                        tok = 'non-sealed'
                    modifiers.append(tok)
                    i += 1
                elif tok == '@' and self.at(i + 1) != 'interface':
                    i = self.skip_annotation(i)
                else:
                    break
            tok = self.at(i)
            if tok == '{':
                i = self.skip_balanced(i, '{', '}')
                continue
            if tok in ('class', 'interface', 'enum', 'record') or (tok == '@' and self.at(i + 1) == 'interface'):
                if tok == 'record' and self.at(i + 2) not in ('(', '<'):
                    pass  # field or method whose type is named record
                else:
                    i = self.parse_type_decl(i, modifiers, rel, is_interface, sink)
                    continue
            type_params = {}
            if tok == '<':
                type_params, i = self.parse_type_params(i)
            line = self.line(i)
            if self.at(i) == decl['name'] and self.at(i + 1) == '(':
                name, ret = '<init>', None
                i += 1
            else:
                ret, j = self.parse_type(i)
                if ret is None:
                    i = max(i + 1, start + 1)
                    continue
                i = j
                name = self.at(i)
                if not name or not (name[0].isalpha() or name[0] in '_$'):
                    i += 1
                    continue
                i += 1
            if self.at(i) == '(':
                params, i = self.parse_params(i)
                while self.at(i) == '[' and self.at(i + 1) == ']':
                    ret = (ret[0], ret[1] + 1)
                    i += 2
                while i < self.n and self.at(i) not in ('{', ';', 'default', '}'):
                    i += 1
                if self.at(i) == '{':
                    i = self.skip_balanced(i, '{', '}')
                elif self.at(i) == 'default':
                    while i < self.n and self.at(i) != ';':
                        if self.at(i) in ('{', '('):
                            i = self.skip_balanced(i, self.at(i), '}' if self.at(i) == '{' else ')')
                        else:
                            i += 1
                if is_interface and 'private' not in modifiers:
                    modifiers = modifiers + ['public']
                decl['methods'].append({'name': name, 'type_params': type_params, 'params': params,
                                        'ret': ret, 'modifiers': sorted(set(modifiers)), 'line': line})
                continue
            # field declarators
            while True:
                dims = 0
                while self.at(i) == '[' and self.at(i + 1) == ']':
                    dims += 1
                    i += 2
                field_mods = modifiers + (['public', 'static', 'final'] if is_interface else [])
                decl['fields'].append({'name': name, 'type': (ret[0], ret[1] + dims),
                                       'modifiers': sorted(set(field_mods)), 'line': line})
                if self.at(i) == '=':
                    i += 1
                    while i < self.n and self.at(i) not in (',', ';', '}'):
                        if self.at(i) in ('(', '[', '{'):
                            pair = {'(': ')', '[': ']', '{': '}'}[self.at(i)]
                            i = self.skip_balanced(i, self.at(i), pair)
                        else:
                            i += 1
                if self.at(i) == ',':
                    nxt = self.at(i + 1)
                    if nxt and (nxt[0].isalpha() or nxt[0] in '_$') and self.at(i + 2) in ('=', ',', ';', '['):
                        name = nxt
                        i += 2
                        continue
                    while i < self.n and self.at(i) not in (';', '}'):
                        if self.at(i) in ('(', '[', '{'):
                            pair = {'(': ')', '[': ']', '{': '}'}[self.at(i)]
                            i = self.skip_balanced(i, self.at(i), pair)
                        else:
                            i += 1
                if self.at(i) == ';':
                    i += 1
                break
        return i

    def parse_params(self, i):
        end = self.skip_balanced(i, '(', ')')
        params = []
        j = i + 1
        while j < end - 1:
            while self.at(j) in ('final', 'in', 'out', 'inout') or self.at(j) == '@':
                j = self.skip_annotation(j) if self.at(j) == '@' else j + 1
            ptype, j = self.parse_type(j)
            if ptype is None:
                break
            dims = ptype[1]
            if self.at(j) == '...':
                dims += 1
                j += 1
            name = self.at(j)
            j += 1
            while self.at(j) == '[' and self.at(j + 1) == ']':
                dims += 1
                j += 2
            if name != 'this':
                params.append((ptype[0], dims))
            depth = 0
            while j < end - 1:
                tok = self.at(j)
                if tok in ('(', '<', '['):
                    depth += 1
                elif tok in (')', '>', ']'):
                    depth -= 1
                elif tok == ',' and depth <= 0:
                    j += 1
                    break
                j += 1
        return params, end

    def parse_aidl(self):
        out = {'package': '', 'imports': [], 'types': [], 'aidl': True}
        i = 0
        while i < self.n:
            tok = self.t[i]
            if tok in ('package', 'import'):
                j = i + 1
                parts = []
                while self.at(j) != ';' and j < self.n:
                    if self.at(j) != '.':
                        parts.append(self.at(j))
                    j += 1
                if tok == 'package':
                    out['package'] = '.'.join(parts)
                else:
                    out['imports'].append('.'.join(parts))
                i = j + 1
            elif tok == '@':
                i = self.skip_annotation(i)
            elif tok == 'interface':
                line = self.line(i)
                name = self.at(i + 1)
                decl = {'name': name, 'outer': None, 'kind': 'interface', 'aidl': 'interface',
                        'modifiers': ['public'], 'line': line, 'type_params': {}, 'supers': [],
                        'fields': [], 'methods': [], 'static': True}
                i += 2
                while i < self.n and self.at(i) != '{':
                    i += 1
                i += 1
                while i < self.n and self.at(i) != '}':
                    while self.at(i) in ('oneway',) or self.at(i) == '@':
                        i = self.skip_annotation(i) if self.at(i) == '@' else i + 1
                    if self.at(i) == ';':
                        i += 1
                        continue
                    if self.at(i) == 'const':
                        ctype, i = self.parse_type(i + 1)
                        decl['fields'].append({'name': self.at(i), 'type': ctype, 'line': self.line(i),
                                               'modifiers': ['final', 'public', 'static']})
                        while i < self.n and self.at(i) != ';':
                            i += 1
                        continue
                    if self.at(i) in ('parcelable', 'interface', 'enum', 'union'):
                        i = self.skip_balanced(i, '{', '}')
                        continue
                    line = self.line(i)
                    ret, i = self.parse_type(i)
                    if ret is None:
                        i += 1
                        continue
                    name = self.at(i)
                    i += 1
                    if self.at(i) != '(':
                        continue
                    params, i = self.parse_params(i)
                    while i < self.n and self.at(i) not in (';', '}'):
                        i += 1
                    decl['methods'].append({'name': name, 'type_params': {}, 'params': params, 'ret': ret,
                                            'modifiers': ['abstract', 'public'], 'line': line})
                out['types'].append(decl)
                i += 1
            elif tok == 'parcelable' and self.at(i + 2) in ('{', '<'):
                j = i + 2
                if self.at(j) == '<':
                    j = self.skip_angle(j)
                if self.at(j) != '{':
                    i = j
                    continue
                line = self.line(i)
                name = self.at(i + 1)
                decl = {'name': name, 'outer': None, 'kind': 'class', 'aidl': 'parcelable',
                        'modifiers': ['public'], 'line': line, 'type_params': {}, 'supers': [],
                        'fields': [], 'methods': [], 'static': True}
                end = self.skip_balanced(j, '{', '}')
                j += 1
                while j < end - 1:
                    while self.at(j) == '@':
                        j = self.skip_annotation(j)
                    ftype, j = self.parse_type(j)
                    if ftype is None:
                        j += 1
                        continue
                    decl['fields'].append({'name': self.at(j), 'type': ftype, 'line': self.line(j),
                                           'modifiers': ['public']})
                    while j < end - 1 and self.at(j) != ';':
                        j += 1
                    j += 1
                out['types'].append(decl)
                i = end
            else:
                i += 1
        return out


def parse_blob(item):
    oid, path, data = item
    text = data.decode('utf-8', 'replace')

    def expired(*_):
        raise TimeoutError('parser time limit')
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(30)
    try:
        parser = Parser(text)
        parsed = parser.parse_aidl() if path.endswith('.aidl') else parser.parse_java()
    except (IndexError, RecursionError, TypeError, TimeoutError) as error:
        parsed = {'package': '', 'imports': [], 'types': [], 'error': repr(error)}
    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
    return oid, parsed


# ---------------------------------------------------------------- git helpers

def git(repo, *args, data=False):
    out = subprocess.check_output(['git', '-C', str(repo), *args])
    return out if data else out.decode()


def read_blobs(repo, oids):
    """Yield (oid, bytes) for blobs; callers pass only objects present in the cache.

    GIT_NO_LAZY_FETCH (git >= 2.44) is an extra guard; with older git the
    missing_objects() filter is what prevents promisor fetches.
    """
    proc = subprocess.Popen(['git', '-C', str(repo), 'cat-file', '--batch'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, env={'GIT_NO_LAZY_FETCH': '1', 'PATH': '/usr/bin:/bin'})
    import threading
    def feed():
        for oid in oids:
            proc.stdin.write((oid + '\n').encode())
        proc.stdin.close()
    threading.Thread(target=feed, daemon=True).start()
    for oid in oids:
        header = proc.stdout.readline().decode().split()
        if len(header) < 3 or header[1] == 'missing':
            yield oid, None
            continue
        size = int(header[2])
        body = proc.stdout.read(size)
        proc.stdout.read(1)
        yield oid, body
    proc.wait()


def missing_objects(repo, commit):
    out = subprocess.run(['git', '-C', str(repo), 'rev-list', '--objects', '--missing=print', commit],
                         capture_output=True, text=True, check=True).stdout
    return {line[1:] for line in out.splitlines() if line.startswith('?')}


def tree_files(repo, commit, pattern):
    rows = []
    for line in git(repo, 'ls-tree', '-r', '-z', commit).split('\0'):
        if not line:
            continue
        meta, path = line.split('\t', 1)
        mode, kind, oid = meta.split()
        if kind == 'blob' and re.search(pattern, path):
            rows.append((oid, path))
    return rows


# ---------------------------------------------------------------- donor index

class Donor:
    def __init__(self, name):
        self.name = name
        self.types = {}          # binary name -> list of (decl, path, fileinfo)
        self.by_canonical = {}   # dotted canonical name -> binary name
        self.package_types = collections.defaultdict(set)
        self.simple = collections.defaultdict(set)  # last binary segment -> binaries
        self.parse_errors = []
        self.revisions = {}
        self.memo = {}

    def revision_of(self, path):
        for checkout, commit in self.revisions.items():
            if path.startswith(checkout + '/'):
                return commit
        return None

    def add_file(self, path, parsed):
        if parsed.get('error'):
            self.parse_errors.append(path)
        pkg = parsed['package']
        prefix = pkg.replace('.', '/') + '/' if pkg else ''
        info = {'package': pkg, 'imports': parsed['imports'], 'path': path, 'aidl': parsed.get('aidl', False)}
        for decl in parsed['types']:
            rel = decl['name'] if decl['outer'] is None else decl['outer'] + '$' + decl['name']
            self._register(prefix + rel, dict(decl, rel=rel), path, info)
            if decl.get('aidl') == 'interface':
                iface = prefix + rel
                for suffix, kind in (('$Stub', 'class'), ('$Stub$Proxy', 'class'), ('$Default', 'class')):
                    gen = dict(decl, rel=rel + suffix, kind=kind, generated_from=iface, fields=[],
                               methods=[dict(m, modifiers=['public']) for m in decl['methods']],
                               supers=[])
                    if suffix == '$Stub':
                        gen['methods'] = gen['methods'] + [
                            {'name': 'asInterface', 'type_params': {}, 'params': [(['android', 'os', 'IBinder'], 0)],
                             'ret': ([*pkg.split('.'), rel] if pkg else [rel], 0), 'modifiers': ['public', 'static'],
                             'line': decl['line']}]
                    self._register(prefix + rel + suffix, gen, path, info)

    def _register(self, binary, decl, path, info):
        self.types.setdefault(binary, []).append((decl, path, info))
        self.by_canonical.setdefault(binary.replace('/', '.').replace('$', '.'), binary)
        self.simple[binary.rsplit('/', 1)[-1]].add(binary)
        if '$' not in binary.rsplit('/', 1)[-1]:
            self.package_types[info['package']].add(binary.rsplit('/', 1)[-1])

    # -- type resolution
    def binary_of_qualified(self, dotted):
        if dotted in self.by_canonical:
            return self.by_canonical[dotted]
        parts = dotted.split('.')
        for k, part in enumerate(parts):
            if part[:1].isupper() and not re.fullmatch(r'V\d+_\d+', part):  # HIDL packages: ...V1_0
                return '/'.join(parts[:k + 1]) + ''.join('$' + p for p in parts[k + 1:])
        return None

    def member_type(self, owner_binary, simple, seen=None):
        """Nested type `simple` declared in owner or inherited from its supertypes."""
        seen = seen or set()
        if owner_binary in seen or len(seen) > 12:
            return None
        seen.add(owner_binary)
        candidate = owner_binary + '$' + simple
        if candidate in self.types:
            return candidate
        for decl, path, info in self.types.get(owner_binary, [])[:1]:
            outer_binary = owner_binary.rsplit('$', 1)[0] if decl['outer'] else None
            for sup in decl['supers']:
                sup_binary = self.resolve_name(sup[0], info, outer_binary, {}, seen_types=seen)
                if sup_binary:
                    found = self.member_type(sup_binary, simple, seen)
                    if found:
                        return found
        return None

    def resolve_name(self, parts, info, owner, type_params, seen_types=None):
        key = (tuple(parts), info['path'], owner, tuple(sorted(type_params)))
        if key in self.memo:
            return self.memo[key]
        result = self._resolve_name(parts, info, owner, type_params, seen_types)
        self.memo[key] = result
        return result

    def _resolve_name(self, parts, info, owner, type_params, seen_types):
        first = parts[0]
        base = None
        if first in type_params:
            return None if len(parts) == 1 else None
        # enclosing classes, innermost first, including inherited member types
        chain = []
        cur = owner
        while cur:
            chain.append(cur)
            cur = cur.rsplit('$', 1)[0] if '$' in cur.rsplit('/', 1)[-1] else None
        for enclosing in chain:
            if enclosing.rsplit('/', 1)[-1].split('$')[-1] == first:
                base = enclosing
                break
            found = self.member_type(enclosing, first, set(seen_types or ()))
            if found:
                base = found
                break
        if base is None:
            for imp in info['imports']:
                if not imp.startswith('static:') and not imp.endswith('.*') and imp.rsplit('.', 1)[-1] == first:
                    base = self.binary_of_qualified(imp)
                    break
        if base is None and first in self.package_types.get(info['package'], ()):
            base = (info['package'].replace('.', '/') + '/' if info['package'] else '') + first
        if base is None:
            for imp in info['imports']:
                if imp.endswith('.*') and not imp.startswith('static:'):
                    pkg = imp[:-2]
                    if first in self.package_types.get(pkg, ()):
                        base = pkg.replace('.', '/') + '/' + first
                        break
                    outer = self.by_canonical.get(pkg)
                    if outer and outer + '$' + first in self.types:
                        base = outer + '$' + first
                        break
                    if first in JDK_PACKAGES.get(pkg, ()):
                        base = pkg.replace('.', '/') + '/' + first
                        break
        if base is None and info.get('aidl') and first in AIDL_BUILTINS:
            base = AIDL_BUILTINS[first]
        if base is None and first in JAVA_LANG:
            base = 'java/lang/' + first
        if base is None and len(parts) > 1 and first[:1].islower():
            return self.binary_of_qualified('.'.join(parts))
        if base is None:
            return None
        for part in parts[1:]:
            nested = self.member_type(base, part) if base in self.types else None
            base = nested or base + '$' + part
        return base

    def descriptor(self, typ, info, owner, type_params):
        parts, dims = typ
        if len(parts) == 1 and parts[0] in PRIMS:
            return '[' * dims + PRIMS[parts[0]]
        if len(parts) == 1 and parts[0] in type_params:
            bound = type_params[parts[0]]
            if bound is None:
                return '[' * dims + 'Ljava/lang/Object;'
            inner = self.descriptor(bound, info, owner, {k: v for k, v in type_params.items() if k != parts[0]})
            return None if inner is None else '[' * dims + inner
        binary = self.resolve_name(parts, info, owner, type_params)
        return None if binary is None else '[' * dims + 'L' + binary + ';'

    def scope_type_params(self, binary, decl):
        params = dict(decl.get('type_params', {}))
        cur = binary
        while '$' in cur.rsplit('/', 1)[-1] and not decl.get('static', True):
            cur = cur.rsplit('$', 1)[0]
            for outer_decl, _, _ in self.types.get(cur, [])[:1]:
                for k, v in outer_decl.get('type_params', {}).items():
                    params.setdefault(k, v)
                decl = outer_decl
        return params

    def method_descriptors(self, binary, decl, info):
        """Yield (method, descriptor or None, unresolved simple names)."""
        scope = self.scope_type_params(binary, decl)
        owner = binary
        for method in decl['methods']:
            tparams = dict(scope)
            tparams.update(method['type_params'])
            descs = []
            unresolved = []
            if method['name'] == '<init>':
                if decl['kind'] == 'enum':
                    descs += ['Ljava/lang/String;', 'I']
                elif decl['kind'] == 'class' and not decl['static'] and decl['outer']:
                    descs.append('L' + binary.rsplit('$', 1)[0] + ';')
            for ptype in method['params']:
                desc = self.descriptor(ptype, info, owner, tparams)
                descs.append(desc)
                if desc is None:
                    unresolved.append('.'.join(ptype[0]))
            ret = 'V' if method['ret'] is None else self.descriptor(method['ret'], info, owner, tparams)
            if ret is None:
                unresolved.append('.'.join(method['ret'][0]))
            full = None if unresolved else '(' + ''.join(descs) + ')' + ret
            yield method, full, unresolved, descs, ret
        has_ctor = any(m['name'] == '<init>' for m in decl['methods'])
        if not has_ctor and decl['kind'] in ('class', 'enum') and not decl.get('aidl') and not decl.get('generated_from'):
            lead = ''
            if decl['kind'] == 'enum':
                lead = 'Ljava/lang/String;I'
            elif not decl['static'] and decl['outer']:
                lead = 'L' + binary.rsplit('$', 1)[0] + ';'
            yield ({'name': '<init>', 'modifiers': ['implicit'], 'line': decl['line'], 'params': []},
                   '(' + lead + ')V', [], [], 'V')

    def field_descriptor(self, binary, decl, info, field):
        scope = self.scope_type_params(binary, decl)
        if field.get('self_enum'):
            return 'L' + binary + ';'
        return self.descriptor(field['type'], info, binary, scope)

    def supertypes(self, binary):
        out = []
        for decl, path, info in self.types.get(binary, [])[:1]:
            outer = binary.rsplit('$', 1)[0] if decl['outer'] else None
            for sup in decl['supers']:
                resolved = self.resolve_name(sup[0], info, outer, decl.get('type_params', {}))
                if resolved:
                    out.append(resolved)
        return out


# ---------------------------------------------------------------- class files (PICO SDK)

def parse_class_file(data):
    import struct
    if data[:4] != b'\xca\xfe\xba\xbe':
        return None
    pos = 8
    count = struct.unpack('>H', data[pos:pos + 2])[0]
    pos += 2
    cp = [None] * count
    i = 1
    while i < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            length = struct.unpack('>H', data[pos:pos + 2])[0]
            cp[i] = ('utf8', data[pos + 2:pos + 2 + length].decode('utf-8', 'replace'))
            pos += 2 + length
        elif tag in (3, 4):
            pos += 4
        elif tag in (5, 6):
            pos += 8
            i += 1
        elif tag in (7, 8, 16, 19, 20):
            cp[i] = ('class' if tag == 7 else 'other', struct.unpack('>H', data[pos:pos + 2])[0])
            pos += 2
        elif tag in (9, 10, 11, 12, 17, 18):
            a, b = struct.unpack('>HH', data[pos:pos + 4])
            cp[i] = ({9: 'field', 10: 'method', 11: 'imethod', 12: 'nat'}.get(tag, 'other'), a, b)
            pos += 4
        elif tag == 15:
            pos += 3
        else:
            return None
        i += 1

    def utf(k):
        return cp[k][1]

    def cls(k):
        return utf(cp[k][1])
    access, this_class, super_class = struct.unpack('>HHH', data[pos:pos + 6])
    pos += 6
    icount = struct.unpack('>H', data[pos:pos + 2])[0]
    pos += 2 + 2 * icount
    members = {'field': [], 'method': []}
    for kind in ('field', 'method'):
        n = struct.unpack('>H', data[pos:pos + 2])[0]
        pos += 2
        for _ in range(n):
            acc, name_i, desc_i, attrs = struct.unpack('>HHHH', data[pos:pos + 8])
            pos += 8
            for _ in range(attrs):
                length = struct.unpack('>I', data[pos + 2:pos + 6])[0]
                pos += 6 + length
            members[kind].append((utf(name_i), utf(desc_i), acc))
    refs = set()
    for entry in cp:
        if entry and entry[0] in ('field', 'method', 'imethod'):
            owner = cls(entry[1])
            nat = cp[entry[2]]
            name, desc = utf(nat[1]), utf(nat[2])
            refs.add('L%s;->%s%s%s' % (owner, name, ':' if entry[0] == 'field' else '', desc))
        elif entry and entry[0] == 'class':
            name = utf(entry[1])
            refs.add(name if name.startswith('[') else 'L%s;' % name)
    return {'name': cls(this_class), 'fields': members['field'], 'methods': members['method'], 'refs': refs}


def iter_archive_classes(data, label):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return
    for entry in archive.namelist():
        if entry.endswith('.class'):
            parsed = parse_class_file(archive.read(entry))
            if parsed:
                yield label + '!' + entry, parsed
        elif entry.endswith(('.jar', '.aar')):
            yield from iter_archive_classes(archive.read(entry), label + '!' + entry)


# ---------------------------------------------------------------- matching

def split_candidate(name):
    if '->' not in name:
        return name[1:-1], None, None
    owner, member = name.split('->', 1)
    owner = owner[1:-1]
    if '(' in member:
        return owner, member[:member.index('(')], member[member.index('('):]
    field, desc = member.split(':', 1)
    return owner, field, ':' + desc


def simple_of(binary):
    return binary.rsplit('/', 1)[-1]


def match_in_donor(donor, cand, compiler_generated):
    owner, member, desc = split_candidate(cand['name'])
    results = []
    if member is None:
        entries = donor.types.get(owner, [])
        if entries:
            decl, path, info = entries[0]
            if compiler_generated:
                return [{'quality': 'name-only', 'path': path, 'line': decl['line'],
                         'detail': 'compiler-generated class; donor declares the same binary name'}]
            return [{'quality': 'exact', 'path': path, 'line': decl['line'],
                     'detail': ('generated by AIDL from ' + path) if decl.get('generated_from') or info['aidl'] else None}]
        if compiler_generated:
            lambda_owner = re.match(r'(.*/)-\$\$Lambda\$([^$]+)\$', owner)
            outer = lambda_owner.group(1) + lambda_owner.group(2) if lambda_owner else re.sub(r'(\$\d+)+$', '', owner)
            if outer != owner and outer in donor.types:
                decl, path, info = donor.types[outer][0]
                return [{'quality': 'name-only', 'path': path, 'line': decl['line'],
                         'detail': 'compiler-generated class; enclosing class ' + outer + ' present'}]
        others = sorted(b for b in donor.simple.get(simple_of(owner), ()) if b != owner)
        for other in others[:3]:
            decl, path, info = donor.types[other][0]
            results.append({'quality': 'name-only', 'path': path, 'line': decl['line'],
                            'detail': 'same simple name as L' + other + ';'})
        return results
    queue = [(owner, None)]
    seen = set()
    name_hits = []
    while queue:
        binary, via = queue.pop(0)
        if binary in seen or len(seen) > 40:
            continue
        seen.add(binary)
        for decl, path, info in donor.types.get(binary, []):
            if desc.startswith(':'):
                for field in decl['fields']:
                    if field['name'] != member:
                        continue
                    fdesc = donor.field_descriptor(binary, decl, info, field)
                    hit = {'path': path, 'line': field['line'], 'modifiers': field['modifiers'],
                           'donor_descriptor': fdesc}
                    if via:
                        hit['declared_in'] = 'L' + binary + ';'
                    if fdesc == desc[1:]:
                        return [dict(hit, quality='exact')]
                    name_hits.append(dict(hit, quality='name-only'))
            else:
                for method, full, unresolved, descs, ret in donor.method_descriptors(binary, decl, info):
                    if method['name'] != member:
                        continue
                    hit = {'path': path, 'line': method['line'], 'modifiers': method['modifiers'],
                           'donor_descriptor': full}
                    if via:
                        hit['declared_in'] = 'L' + binary + ';'
                    if full == desc:
                        return [dict(hit, quality='exact')]
                    if unresolved:
                        hit['unresolved_types'] = unresolved
                        hit['partial_descriptor'] = '(' + ''.join(d or '?' for d in descs) + ')' + (ret or '?')
                    name_hits.append(dict(hit, quality='name-only'))
        if member not in ('<init>', '<clinit>'):
            for sup in donor.supertypes(binary):
                queue.append((sup, binary))
    if not name_hits and owner not in donor.types:
        for other in sorted(b for b in donor.simple.get(simple_of(owner), ()) if b != owner)[:3]:
            for decl, path, info in donor.types[other][:1]:
                names = [f['name'] for f in decl['fields']] if desc.startswith(':') else [m['name'] for m in decl['methods']]
                if member in names:
                    name_hits.append({'quality': 'name-only', 'path': path,
                                      'detail': 'member in same-named class L' + other + ';'})
    return name_hits[:3]


def match_in_sdk(sdk, cand, compiler_generated):
    owner, member, desc = split_candidate(cand['name'])
    hits = []
    name = cand['name']
    for path, parsed in sdk['classes']:
        if member is None:
            if parsed['name'] == owner:
                hits.append({'quality': 'name-only' if compiler_generated else 'exact', 'path': path,
                             'evidence': 'class definition'})
        elif parsed['name'] == owner:
            members = parsed['fields'] if desc.startswith(':') else parsed['methods']
            for mname, mdesc, acc in members:
                if mname == member:
                    exact = (':' + mdesc if desc.startswith(':') else mdesc) == desc
                    hits.append({'quality': 'exact' if exact else 'name-only', 'path': path,
                                 'evidence': 'member definition', 'donor_descriptor': mdesc})
        if name in parsed['refs'] and parsed['name'] != owner:
            hits.append({'quality': 'exact', 'path': path, 'evidence': 'client reference from L' + parsed['name'] + ';'})
    hits.sort(key=lambda h: h['quality'] != 'exact')
    return hits[:3]


# ---------------------------------------------------------------- main

def check_volume():
    mounted = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,UUID', '--target', str(PROJECT)], text=True).split()
    if mounted != VOLUME:
        raise RuntimeError('Expected ext4 research volume')


def load_parsed(repo_path, files, workers):
    cache_file = CACHE / ('parsed-' + repo_path.name.replace('.git', '') + '.pickle')
    cache = pickle.loads(cache_file.read_bytes()) if cache_file.exists() else {}
    todo = sorted({oid for oid, _ in files if oid not in cache})
    paths = {oid: path for oid, path in files}
    if todo:
        items = [(oid, paths[oid], body) for oid, body in read_blobs(repo_path, todo) if body is not None]
        with Pool(workers) as pool:
            for oid, parsed in pool.imap_unordered(parse_blob, items, chunksize=64):
                cache[oid] = parsed
        cache_file.write_bytes(pickle.dumps(cache, protocol=pickle.HIGHEST_PROTOCOL))
    return cache


def build_donor(spec, workers):
    donor = Donor(spec['name'])
    components = []
    for checkout, repo, ref, upstream, remote in spec['components']:
        repo_path = CACHE / repo
        row = {'component': checkout, 'repository': remote, 'upstream_ref': upstream, 'cache': repo, 'local_ref': ref}
        try:
            commit = git(repo_path, 'rev-parse', '--verify', '-q', ref + '^{commit}').strip()
        except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
            components.append(dict(row, status='not_fetched'))
            continue
        files = [(oid, path) for oid, path in tree_files(repo_path, commit, r'\.(java|aidl)$')
                 if not SKIP_PATH.search(path)]
        missing = missing_objects(repo_path, commit)
        present = [(oid, path) for oid, path in files if oid not in missing]
        parsed = load_parsed(repo_path, present, workers)
        errors = len(donor.parse_errors)
        for oid, path in present:
            if oid in parsed:
                donor.add_file(checkout + '/' + path, parsed[oid])
        donor.revisions[checkout] = commit
        components.append(dict(row, status='ok', commit=commit,
                               commit_date=git(repo_path, 'log', '-1', '--format=%cI', commit).strip(),
                               source_files=len(files),
                               source_files_read=sum(1 for oid, _ in present if oid in parsed),
                               source_files_missing_from_cache=len(files) - len(present),
                               parse_errors=len(donor.parse_errors) - errors))
    aliases = []
    for checkout, repo, ref, upstream in spec.get('aliases', []):
        try:
            commit = git(CACHE / repo, 'rev-parse', '--verify', '-q', ref + '^{commit}').strip()
        except subprocess.CalledProcessError:
            commit = None
        aliases.append({'component': checkout, 'upstream_ref': upstream, 'commit': commit,
                        'same_commit_as_donor': commit == donor.revisions.get(checkout)})
    meta = {'components': components, 'aliases': aliases, 'types_indexed': len(donor.types),
            'status': 'ok' if all(c['status'] == 'ok' for c in components) else
                      ('partial' if donor.types else 'not_fetched')}
    return donor, meta


def build_sdk(workers):
    base = CACHE / PICO_SDK_DIR
    repos = []
    classes = []
    java_donor = Donor('pico_sdk_sources')
    for repo_path in sorted(base.glob('*.git')) if base.exists() else []:
        full = repo_path.name[:-4].replace('_', '/', 1)
        entry = {'repository': 'https://github.com/' + full, 'cache': str(repo_path.relative_to(CACHE))}
        try:
            commit = git(repo_path, 'rev-parse', 'refs/research/head^{commit}').strip()
        except subprocess.CalledProcessError:
            entry['status'] = 'fetch_failed'
            repos.append(entry)
            continue
        entry['commit'] = commit
        files = tree_files(repo_path, commit, r'\.(java|aidl|jar|aar|kt)$')
        missing = missing_objects(repo_path, commit)
        entry['files'] = collections.Counter(Path(p).suffix for _, p in files)
        entry['files_missing_from_cache'] = sum(1 for oid, _ in files if oid in missing)
        archives = [(oid, p) for oid, p in files if p.endswith(('.jar', '.aar')) and oid not in missing]
        for oid, body in read_blobs(repo_path, [oid for oid, _ in archives]):
            if body is None:
                continue
            path = next(p for o, p in archives if o == oid)
            for label, parsed in iter_archive_classes(body, full + ':' + path):
                classes.append((label, parsed))
        sources = [(oid, p) for oid, p in files if p.endswith(('.java', '.aidl')) and oid not in missing]
        parsed = load_parsed(repo_path, sources, workers) if sources else {}
        for oid, path in sources:
            if oid in parsed:
                java_donor.add_file(full + ':' + path, parsed[oid])
        entry['class_files'] = sum(1 for label, _ in classes if label.startswith(full + ':'))
        entry['status'] = 'ok'
        repos.append(entry)
    for entry in repos:
        if 'files' in entry:
            entry['files'] = dict(entry['files'])
    return {'repos': repos, 'classes': classes, 'java': java_donor}


def av_markers():
    name, repo, ref, upstream, remote = AV_SOURCE
    repo_path = CACHE / repo
    try:
        commit = git(repo_path, 'rev-parse', ref + '^{commit}').strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {'name': name, 'status': 'not_fetched', 'remote': remote, 'upstream_ref': upstream}
    files = tree_files(repo_path, commit, r'\.(h|cpp|aidl|java)$')
    missing = missing_objects(repo_path, commit)
    present = [(oid, p) for oid, p in files if oid not in missing]
    found = {key: [] for key in AV_MARKERS}
    paths = collections.defaultdict(list)
    for oid, path in present:
        paths[oid].append(path)
    for oid, body in read_blobs(repo_path, sorted(paths)):
        if body is None:
            continue
        text = body.decode('utf-8', 'replace')
        for key, pattern in AV_MARKERS.items():
            if re.search(pattern, text):
                found[key].extend(paths[oid])
    return {'name': name, 'status': 'ok', 'remote': remote, 'upstream_ref': upstream, 'commit': commit,
            'files_read': len(present),
            'markers': {k: sorted(v)[:8] for k, v in found.items()},
            'note': 'text markers only; supplementary context for spatial audio candidates, not counted as coverage'}


FACTORY_JARS = {'framework.jar': 'analysis/stock-5.13.7-system/root/system/framework/framework.jar',
                'services.jar': 'analysis/stock-5.13.7-system/root/system/framework/services.jar'}


def factory_api():
    """Declared DEX API of factory framework.jar/services.jar (reuses tools/compare-framework-api.py)."""
    spec = importlib.util.spec_from_file_location('pico_framework_api', ROOT / 'tools/compare-framework-api.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = {}
    for name, rel in FACTORY_JARS.items():
        path = PROJECT / rel
        if path.exists():
            out[name] = {'path': rel, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'classes': module.jar_api(path)}
    return out


def parser_fidelity(donor, factory):
    """Self-check: how many factory DEX members of classes shared with a donor the parser reproduces.

    Factory classes carry PICO changes, so 100% is not expected; low agreement would expose
    descriptor-resolution defects. Compiler-generated members (access$, lambda$, synthetic) are skipped.
    """
    checked = reproduced = 0
    misses = []
    for jar in factory.values():
        for clazz, record in jar['classes'].items():
            binary = clazz[1:-1]
            if binary not in donor.types or re.search(r'\$\d', binary):
                continue
            decl, path, info = donor.types[binary][0]
            if decl.get('generated_from') or info['aidl']:
                continue
            ours = {m['name'] + full for m, full, *_ in donor.method_descriptors(binary, decl, info) if full}
            ours |= {f['name'] + ':' + (donor.field_descriptor(binary, decl, info, f) or '?') for f in decl['fields']}
            for member, flags in list(record['methods'].items()) + list(record['fields'].items()):
                if flags & 0x1000 or member.startswith(('access$', 'lambda$', '<clinit>', '$')) or '$' in member.split('(')[0].split(':')[0]:
                    continue
                name = member.split('(')[0].split(':')[0]
                if not any(o.split('(')[0].split(':')[0] == name for o in ours):
                    continue  # member absent from donor by name: an API difference, not a parser check
                checked += 1
                if member in ours:
                    reproduced += 1
                elif len(misses) < 25:
                    misses.append(clazz + '->' + member)
    return {'donor': donor.name, 'members_checked': checked, 'reproduced': reproduced,
            'share': round(reproduced / checked, 4) if checked else None, 'sample_mismatches': misses}


def aidl_crosscheck(candidates, sdk, factory_jars):
    """Compare PICO AIDL interfaces declared in factory framework.jar with SDK copies and SDK call sites."""
    if 'framework.jar' not in factory_jars:
        return {'status': 'factory_framework_missing'}
    jar = factory_jars['framework.jar']
    factory = jar['classes']
    names = {c['name'] for c in candidates}
    interfaces = sorted(n[1:-1] for n in names
                        if n[:-1] + '$Stub;' in names and re.match(r'L(com/pvr|com/pico|com/pxr)/', n))
    defined = collections.defaultdict(dict)
    calls = collections.defaultdict(lambda: collections.defaultdict(set))
    for label, parsed in sdk['classes']:
        repo = label.split(':', 1)[0]
        if parsed['name'] in interfaces:
            for mname, mdesc, acc in parsed['methods']:
                defined[parsed['name']].setdefault(mname + mdesc, set()).add(repo)
        for ref in parsed['refs']:
            if '->' in ref and '(' in ref and '->asBinder()' not in ref:
                owner = ref[1:ref.index(';')]
                if owner in interfaces and not parsed['name'].startswith(owner):
                    calls[owner][ref.split('->', 1)[1]].add(repo)
    rows = []
    for iface in interfaces:
        record = factory.get('L' + iface + ';', {'methods': {}})
        fmethods = set(record['methods'])
        sdk_methods = set(defined.get(iface, {}))
        called = calls.get(iface, {})
        rows.append({
            'interface': 'L' + iface + ';',
            'factory_class_found': 'L' + iface + ';' in factory,
            'factory_methods': len(fmethods),
            'sdk_copy_methods': len(sdk_methods),
            'sdk_copy_repository_count': len({r for v in defined.get(iface, {}).values() for r in v}),
            'sdk_copy_repositories_sample': sorted({r for v in defined.get(iface, {}).values() for r in v})[:5],
            'common_methods': len(fmethods & sdk_methods),
            'sdk_copy_only': sorted(sdk_methods - fmethods)[:40],
            'factory_only_count': len(fmethods - sdk_methods) if sdk_methods else None,
            'sdk_client_calls': {sig: {'in_factory': sig in fmethods, 'repository_count': len(repos),
                                       'repositories_sample': sorted(repos)[:3]}
                                 for sig, repos in sorted(called.items())},
        })
    return {'status': 'ok', 'factory_jar': jar['path'], 'factory_jar_sha256': jar['sha256'],
            'note': 'method name+descriptor sets only; transaction codes and parcel layout are not compared',
            'interfaces': rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()
    check_volume()
    consumers_path = ROOT / 'validation/api-consumers.json'
    consumers_bytes = consumers_path.read_bytes()
    consumers = json.loads(consumers_bytes)
    candidates = [c for c in consumers['candidates'] if c['decision'] in DECISIONS]
    # not_needed candidates are matched too, for a supplementary summary only (no per-candidate rows)
    extra = [c for c in consumers['candidates'] if c['decision'] == SUPPLEMENTARY]

    donors, sources, control = [], [], None
    for spec in DONORS:
        donor, meta = build_donor(spec, args.workers)
        row = dict({'name': spec['name'], 'family': spec['family']}, **meta)
        sources.append(row)
        if meta['status'] == 'not_fetched':
            print(spec['name'] + ': not available')
            continue
        if spec['family'] == 'control':
            control = donor
        else:
            donors.append((donor, row))
        print('%s: %s types, %s' % (spec['name'], meta['types_indexed'],
                                    ', '.join('%s %s' % (c['component'], c.get('commit', c['status'])[:12])
                                              for c in meta['components'])))
    sdk = build_sdk(args.workers)
    sdk_row = {'name': 'pico_sdk', 'family': 'pico_sdk',
               'status': 'ok' if any(r.get('status') == 'ok' for r in sdk['repos']) else 'not_fetched',
               'repositories': sdk['repos'], 'class_files': len(sdk['classes']),
               'java_types_indexed': len(sdk['java'].types)}
    sources.append(sdk_row)
    print('pico_sdk: %d repos, %d class files, %d source types' % (len(sdk['repos']), len(sdk['classes']),
                                                                   len(sdk['java'].types)))
    sdk_commits = {r['repository'].rsplit('github.com/', 1)[-1]: r.get('commit') for r in sdk['repos']}

    rank = {'exact': 2, 'name-only': 1, 'none': 0}
    out_candidates = []
    for cand in candidates + extra:
        generated = bool(cand.get('compiler_generated'))
        owner = split_candidate(cand['name'])[0]
        matches = []
        for donor, row in donors:
            for hit in match_in_donor(donor, cand, generated):
                matches.append(dict({'donor': donor.name, 'revision': donor.revision_of(hit['path'])}, **hit))
        for hit in match_in_sdk(sdk, cand, generated):
            matches.append(dict({'donor': 'pico_sdk', 'revision': sdk_commits.get(hit['path'].split(':', 1)[0])}, **hit))
        for hit in match_in_donor(sdk['java'], cand, generated):
            matches.append(dict({'donor': 'pico_sdk', 'revision': sdk_commits.get(hit['path'].split(':', 1)[0]),
                                 'evidence': 'source definition'}, **hit))
        best = max((m['quality'] for m in matches), key=rank.get, default='none')
        control_hits = match_in_donor(control, cand, generated) if control else []
        control_quality = max((h['quality'] for h in control_hits), key=rank.get, default='none')
        out_candidates.append({
            'name': cand['name'], 'jar': cand['jar'], 'kind': cand['kind'], 'decision': cand['decision'],
            'group': owner.rsplit('/', 1)[0].replace('/', '.') if '/' in owner else '',
            'vr_related': cand.get('vr_related', False), 'compiler_generated': generated,
            'match_quality': best,
            'aosp_10_r47_control': control_quality,
            'exact_donors': sorted({m['donor'] for m in matches if m['quality'] == 'exact'}),
            'name_only_donors': sorted({m['donor'] for m in matches if m['quality'] == 'name-only'}),
            'matches': matches,
        })

    def tally(rows):
        counter = collections.Counter(r['match_quality'] for r in rows)
        total = len(rows)
        return {'total': total, 'exact': counter['exact'], 'name_only': counter['name-only'], 'none': counter['none'],
                'exact_share': round(counter['exact'] / total, 4) if total else None,
                'any_share': round((counter['exact'] + counter['name-only']) / total, 4) if total else None}
    summary = {}
    for decision in DECISIONS + (SUPPLEMENTARY,):
        rows = [r for r in out_candidates if r['decision'] == decision]
        groups = collections.defaultdict(list)
        for r in rows:
            groups[(r['jar'], r['group'])].append(r)
        by_donor = {}
        for donor_name in [d.name for d, _ in donors] + ['pico_sdk']:
            by_donor[donor_name] = {
                'exact': sum(1 for r in rows if donor_name in r['exact_donors']),
                'name_only_or_better': sum(1 for r in rows if donor_name in r['exact_donors'] or donor_name in r['name_only_donors'])}
        families = {}
        for family in ('qualcomm', 'aosp', 'smartisan', 'pico_sdk'):
            members = [d.name for d, row in donors if row['family'] == family] + (['pico_sdk'] if family == 'pico_sdk' else [])
            families[family] = sum(1 for r in rows if set(members) & set(r['exact_donors']))
        summary[decision] = {
            'overall': tally(rows),
            'exact_and_absent_from_aosp_10_r47': sum(1 for r in rows if r['match_quality'] == 'exact'
                                                     and r['aosp_10_r47_control'] != 'exact'),
            'exact_in_aosp_10_r47_control': sum(1 for r in rows if r['aosp_10_r47_control'] == 'exact'),
            'non_compiler_generated': tally([r for r in rows if not r['compiler_generated']]),
            'by_kind': {k: tally([r for r in rows if r['kind'] == k]) for k in sorted({r['kind'] for r in rows})},
            'by_donor': by_donor, 'exact_by_family': families,
            'groups': [dict({'jar': jar, 'group': group}, **tally(items))
                       for (jar, group), items in sorted(groups.items())],
        }
        if decision == SUPPLEMENTARY:
            summary[decision]['note'] = 'supplementary: not_needed candidates, summary only'
            del summary[decision]['groups']

    factory_jars = factory_api()
    report = {
        'snapshot': consumers.get('snapshot'),
        'api_consumers_sha256': hashlib.sha256(consumers_bytes).hexdigest(),
        'aosp_baseline': consumers.get('aosp_tag'),
        'decisions_covered': list(DECISIONS),
        'candidate_counts': dict(collections.Counter(c['decision'] for c in candidates)),
        'sources': sources,
        'supplementary_native': av_markers(),
        'pico_aidl_crosscheck': aidl_crosscheck(candidates, sdk, factory_jars),
        'parser_fidelity': [parser_fidelity(d, factory_jars) for d in [control] + [d for d, _ in donors] if d],
        'method': ('Java/AIDL declarations parsed from pinned Git blobs and resolved to DEX descriptors '
                   '(package, imports, nested and inherited member types, donor class index, generic erasure, '
                   'implicit inner/enum constructor parameters, AIDL generated classes); PICO SDK JAR/AAR class '
                   'files compared by exact constant-pool descriptors'),
        'quality_definitions': {
            'exact': 'donor declares the same class binary name, or a member with the same name and full descriptor '
                     '(members may be inherited from a donor supertype, see declared_in)',
            'name-only': 'same class simple name in another package, same member name with a different or '
                         'unresolvable descriptor, or a compiler-generated class whose name/enclosing class matches',
            'none': 'no declaration with this name in any checked donor',
        },
        'limitations': [
            'Declaration parser, not a compiler: overloads that differ only by types the donor index cannot '
            'resolve stay name-only (unresolved_types lists them).',
            'Only .java/.aidl files outside tests/ of frameworks/base (+ system/bt for android.bluetooth AIDL) '
            'are read; generated sources and other repositories (frameworks/opt/*, packages/modules/*, '
            'vendor/qcom-opensource, Smartisan closed services) are not part of these donors.',
            'CodeLinaro publishes no LA.QSSI.10.* tags for frameworks/base; LA.UM.8.12.c3 (sm8250, Android 10) '
            'is used, the same family as the native donors.',
            'PICO SDK repositories are pinned to their default-branch head at fetch time; only JAR/AAR class '
            'files and .java/.aidl sources are read.',
            'An exact descriptor match does not prove identical behaviour, Binder transaction codes or '
            'parcel layout.',
            'Compiler-generated classes ($1, lambdas) are never counted as exact.',
            'Kotlin sources in PICO SDK repositories are not parsed.',
        ],
        'summary': summary,
        'control_note': ('aosp_10_r47_control is the pinned AOSP baseline tag, not a donor; an exact hit there means '
                         'the descriptor is already declared in AOSP 10 (typically *_visibility candidates, or '
                         'members the project Source tree lacks for another reason); such candidates are '
                         'excluded from exact_and_absent_from_aosp_10_r47'),
        'candidates': [r for r in out_candidates if r['decision'] in DECISIONS],
        'build_tree_modified': False, 'headset_modified': False,
    }
    (ROOT / 'validation/api-donor-coverage.json').write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    for decision in DECISIONS:
        print(decision, json.dumps(summary[decision]['overall']))
        print('  by donor', json.dumps(summary[decision]['by_donor']))
    for row in report['parser_fidelity']:
        print('parser fidelity', row['donor'], row['reproduced'], '/', row['members_checked'])


if __name__ == '__main__':
    main()
