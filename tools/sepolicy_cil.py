"""Small reader for compiled Android CIL policies (checkpolicy -C / secilc input).

Shared by tools/check-sepolicy.py and tools/reconstruct-factory-sepolicy.py.
Only data is read; nothing is executed.
"""
import re
from collections import defaultdict

TOKEN = re.compile(r'"[^"]*"|[()]|[^\s()"]+')
RULES = ('allow', 'auditallow', 'dontaudit', 'neverallow')
XRULES = ('allowx', 'auditallowx', 'dontauditx', 'neverallowx')
TRANSITIONS = ('typetransition', 'typechange', 'typemember')
AUTO_ATTRIBUTE = re.compile(r'^base_typeattr_\d+$')


def parse(text):
    """Return the list of top-level statements as nested lists of strings."""
    stack, top = [], []
    current = top
    for token in TOKEN.findall(re.sub(r';[^\n]*', '', text)):
        if token == '(':
            node = []
            current.append(node)
            stack.append(current)
            current = node
        elif token == ')':
            current = stack.pop()
        else:
            current.append(token)
    if stack:
        raise ValueError('Unbalanced CIL input')
    return top


def dump(node):
    if isinstance(node, list):
        return '(' + ' '.join(dump(item) for item in node) + ')'
    return node


class Policy:
    """Indexed view of a compiled CIL policy (one or more files)."""

    def __init__(self, *texts):
        self.statements = [s for text in texts for s in parse(text)]
        self.types = set()
        self.attributes = set()
        self.members = defaultdict(set)       # attribute -> plain names
        self.expressions = {}                 # attribute -> expression node
        self.expand = {}
        self.aliases = {}
        self.rules = set()
        self.xrules = set()
        self.transitions = set()
        self.genfs = {}
        self.other = set()
        for statement in self.statements:
            self._index(statement)
        self.normalized = {}

    def _index(self, s):
        kind = s[0]
        if kind == 'type':
            self.types.add(s[1])
        elif kind == 'typeattribute':
            self.attributes.add(s[1])
        elif kind == 'typeattributeset':
            name, value = s[1], s[2]
            if value and value[0] in ('and', 'or', 'not', 'xor', 'all'):
                self.expressions[name] = value
            else:
                self.members[name].update(v for v in value if isinstance(v, str))
                for v in value:
                    if isinstance(v, list):
                        self.expressions.setdefault(name, ['or'])
                        self.expressions[name].append(v)
        elif kind == 'expandtypeattribute':
            for name in s[1]:
                self.expand[name] = s[2]
        elif kind == 'typealias':
            self.aliases.setdefault(s[1], None)
        elif kind == 'typealiasactual':
            self.aliases[s[1]] = s[2]
        elif kind in RULES:
            self.rules.add((kind, s[1], s[2], dump(s[3])))
        elif kind in XRULES:
            self.xrules.add((kind, s[1], s[2], dump(s[3])))
        elif kind in TRANSITIONS:
            self.transitions.add((kind,) + tuple(dump(x) for x in s[1:]))
        elif kind == 'genfscon':
            self.genfs[(s[1], s[2].strip('"'))] = context_type(s[3])
        else:
            self.other.add(dump(s))

    def norm(self, name):
        """Name with auto-generated base_typeattr_N replaced by its expression."""
        if not AUTO_ATTRIBUTE.match(name):
            return name
        if name not in self.normalized:
            expression = self.expressions.get(name)
            if expression is None:
                members = sorted(self.members.get(name, ()))
                self.normalized[name] = '{' + ' '.join(members) + '}'
            else:
                self.normalized[name] = self._norm_expr(expression)
        return self.normalized[name]

    def _norm_expr(self, node):
        if isinstance(node, str):
            return self.norm(node)
        if node and node[0] in ('and', 'or', 'not', 'xor', 'all'):
            args = [self._norm_expr(n) for n in node[1:]]
            if node[0] in ('and', 'or', 'xor'):
                args = sorted(args)
            return '(' + ' '.join([node[0]] + args) + ')'
        items = sorted(self._norm_expr(n) for n in node)
        return items[0] if len(items) == 1 else '{' + ' '.join(items) + '}'

    def rule_set(self):
        """Per-permission rule tuples with normalized source/target."""
        out = set()
        for kind, src, tgt, perms in self.rules:
            node = parse(perms)[0]
            cls = node[0]
            plist = node[1] if len(node) > 1 else []
            if isinstance(plist, str):
                plist = [plist]
            for perm in flatten(plist):
                out.add((kind, self.norm(src), self.norm(tgt), cls, perm))
        return out

    def xrule_set(self):
        return {(k, self.norm(s), self.norm(t), p) for k, s, t, p in self.xrules}

    def transition_set(self):
        out = set()
        for item in self.transitions:
            out.add((item[0], self.norm(item[1]), self.norm(item[2])) + item[3:])
        return out

    def membership(self):
        """(type, attribute) pairs for named (non-auto) attributes."""
        pairs = set()
        for attribute, names in self.members.items():
            if AUTO_ATTRIBUTE.match(attribute) or attribute == 'cil_gen_require':
                continue
            for name in names:
                pairs.add((name, attribute))
        return pairs


def flatten(node):
    if isinstance(node, str):
        yield node
    else:
        for item in node:
            yield from flatten(item)


def context_type(node):
    """Type field of a CIL context (u object_r t ((s0) (s0)))."""
    if isinstance(node, list):
        return node[2]
    return node


def read_contexts(text, kind):
    """Map key -> label for Android contexts files."""
    entries = {}
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if kind == 'file':
            key = ' '.join(fields[:-1])
            entries[key] = fields[-1]
        elif kind == 'seapp':
            entries[' '.join(sorted(fields))] = ''
        elif kind == 'property':
            entries[fields[0]] = ' '.join(fields[1:])
        else:
            entries[fields[0]] = fields[1]
    return entries


def mapping_sets(text):
    """Versioned attribute -> set of plat types from a mapping/NN.0.cil."""
    result = {}
    for s in parse(text):
        if s[0] == 'typeattributeset':
            result[s[1]] = set(v for v in flatten(s[2]))
    return result


def te_name(policy, name):
    """Policy-language spelling of a (possibly auto-generated) CIL type set."""
    if not AUTO_ATTRIBUTE.match(name):
        return name
    expression = policy.expressions.get(name)
    if expression is None:
        return '{ ' + ' '.join(sorted(policy.members.get(name, ()))) + ' }'
    return _te_expr(policy, expression)


def _te_names(policy, node):
    if isinstance(node, str):
        if AUTO_ATTRIBUTE.match(node):
            raise ValueError('Nested auto attribute ' + node)
        return [node]
    if node and node[0] in ('and', 'or', 'not', 'xor', 'all'):
        raise ValueError('Unsupported nested expression ' + dump(node))
    out = []
    for item in node:
        out.extend(_te_names(policy, item))
    return out


def _te_expr(policy, node):
    op = node[0]
    if op == 'all':
        return '*'
    if op == 'not':
        return '~{ ' + ' '.join(sorted(_te_names(policy, node[1]))) + ' }'
    if op == 'and' and len(node) == 3:
        positive = [n for n in node[1:] if not (isinstance(n, list) and n and n[0] == 'not')]
        negative = [n[1] for n in node[1:] if isinstance(n, list) and n and n[0] == 'not']
        if len(positive) == 1 and len(negative) == 1:
            pos = _te_names(policy, positive[0])
            neg = _te_names(policy, negative[0])
            return '{ ' + ' '.join(sorted(pos) + ['-' + n for n in sorted(neg)]) + ' }'
    raise ValueError('Unsupported type expression ' + dump(node))


def expand(policy, name, _cache=None):
    """Set of types a name (type, attribute or auto attribute) stands for."""
    cache = policy.__dict__.setdefault('_expanded', {})
    if name in cache:
        return cache[name]
    if name in policy.types:
        result = {name}
    elif name in policy.expressions:
        result = _expand_expr(policy, policy.expressions[name])
    else:
        result = set()
        for member in policy.members.get(name, ()):
            result |= expand(policy, member)
    cache[name] = result
    return result


def _expand_expr(policy, node):
    if isinstance(node, str):
        return expand(policy, node)
    op = node[0] if node else None
    if op == 'all':
        return set(policy.types)
    if op == 'not':
        return set(policy.types) - _expand_expr(policy, node[1])
    if op == 'and':
        result = _expand_expr(policy, node[1])
        for item in node[2:]:
            result &= _expand_expr(policy, item)
        return result
    if op in ('or', 'xor'):
        result = set()
        for item in node[1:]:
            result |= _expand_expr(policy, item)
        return result
    result = set()
    for item in node:
        result |= _expand_expr(policy, item)
    return result
