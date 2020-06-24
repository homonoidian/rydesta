import re

from .error import RyError
from .reader import RyNode, ReaderError

from pathlib import Path
from operator import itemgetter
from textwrap import indent, dedent
from fractions import Fraction
from linecache import getline


###- CLASSES -##############

class HasType:
  pass


class _DeathError(Exception):
  """This exception is raised when something has gone/was done wrong
     in the interpreter."""

  __slots__ = 'state', 'reason'

  def __init__(self, state, reason):
    self.state = state
    self.reason = reason


class _ReturnException(Exception):
  __Slots__ = 'value',

  def __init__(self, value):
    self.value = value


class _Box:
  """A box is a lightweight wrapper around a Python value made to change only
     its __repr__. It may also carry some meta-information."""

  __slots__ = 'value',

  def __init__(self, value):
    self.value = value


class RyTypeType(HasType, _Box):
  """The root of the type hierarchy."""
  type = 'type'

  def __repr__(self):
    return f'[type {self.value}]'


class RyVariations(HasType):
  """A list of functions with a common name."""

  __slots__ = 'name', 'variations', 'quoting', 'naked'

  type = 'variations'

  def __init__(self, name, initial, quoting=False, naked=False):
    self.name = name
    self.naked = naked
    self.quoting = quoting
    self.variations = [initial]

  def add(self, variation):
    """Add a new variation and re-sort the variations by their signature."""
    self.variations.append(variation)
    self.variations.sort(key=lambda x: x.signature, reverse=True)

  def __repr__(self):
    return f'[function "{self.name}" with {len(self.variations)} variation(s)]'


class RyFunction(HasType):
  """A particular function."""

  __slots__ = 'state', 'signature', 'name', 'params', 'arity', 'body', 'head'

  type = 'function'

  def __init__(self, state, signature, name, params, body, line):
    self.name = name
    self.body = body
    self.state = state
    self.arity = len(params)
    self.params = params
    self.head = getline(state.filename, line) or state.reader.source.splitlines()[line - 1]
    self.signature = signature

  def _help_rmprefix(self, string, prefix):
    if string.startswith(prefix):
      return string[len(prefix):]
    return string[:]

  def _help_rmsuffix(self, string, suffix):
    if string.endswith(suffix):
      return string[:-len(suffix)]
    return string[:]

  def dump(self):
    """Return the name of the function plus the parameters of the function
       as the user had written them."""
    excerpt = self.head
    excerpt = dedent(self._help_rmprefix(excerpt, 'for'))
    excerpt = self._help_rmsuffix(excerpt, '{')
    params = excerpt.split('->')[0].strip()
    if self.name == params: # zero-arity
      return self.name
    return f'{self.name}: {params} -> ...'

  def __repr__(self):
    return f'[{self.dump()}]'


class RyObject(HasType):
  """A box to enclose the (uninstantiated) objects."""

  __slots__ = 'name', 'props', 'block', 'state'

  type = 'object'

  def __init__(self, name, props, block, state):
    self.name = name
    self.props = props
    self.block = block
    self.state = state

  def __repr__(self):
    return f'[object {self.name}]'


class RyRouteable(HasType):
  """Anything that can be dottted (e.g., `a.b.c`) is routeable; in the "e.g.",
     both `a` and `b` are routeables."""

  __slots__ = 'name', 'env', 'extractable'

  type = 'routeable'

  def __init__(self, name, env, *, extractable=[]):
    self.name = name
    self.env = env
    self.extractable = extractable or [*self.env.keys()]

  def __repr__(self):
    return f'[routeable "{self.name}"]'


class RyExcerpt(HasType):
  type = 'excerpt'

  def __init__(self, state, node):
    # Excerpts are somewhat-ly closures, too.
    self.state = state.copy()
    self.node = node

  def __repr__(self):
    return f'[excerpt {self.node}]'


class RyBuiltin(HasType, _Box):
  """A container for a Python function."""

  type = 'builtin'

  def __repr__(self):
    if doc := self.value.__doc__:
      return f'[builtin: {doc[0].lower() + doc[1:]}]'
    return f'[builtin]'


class RyBool(HasType, _Box):
  type = 'bool'

  def __repr__(self):
    return 'true' if self.value else 'false'


class RyVec(HasType, _Box):
  type = 'vec'

  def __repr__(self):
    return f'[{" ".join(str(item) for item in self.value)}]'


class RyNum(HasType, _Box):
  """A box for a Rydesta number. The value passed to the initializer
     must be a Fraction; otherwise, everything will break apart."""

  type = 'num'

  def __repr__(self):
    value = self.value.numerator
    try:
      value /= self.value.denominator
      return str(int(value) if value.is_integer() else value)
    except OverflowError:
      value //= self.value.denominator
      return str(value)


class RyStr(HasType, _Box):
  type = 'str'

  def __repr__(self):
    return f'"{self.value}"'


class RyState:
  """A vehicle to carry values on an inter-node highway."""

  __slots__ = 'filename', 'reader', 'line', 'env'

  def __init__(self, filename, reader, env={}, line=1):
    self.filename = filename
    self.reader = reader
    self.line = line
    self.env = env

  def copy(self):
    """Make a copy of the state."""
    return RyState(self.filename, self.reader, self.env.copy(), self.line)

  def __repr__(self):
    return f'[frozen state for "{self.filename}"]'


###- HELPERS -##############

def _just_of(nodes, *types):
  """Given a list of RyNodes, return the same list but with the nodes *not*
     of the `types` excluded."""
  return [node for node in nodes if node.type in types]


def _die(state, reason='generic death'):
  """Raise DeathError of the given reason."""
  raise _DeathError(state, reason)


def _sign(pattern):
  """A signature of a pattern is a unique number, which, as a general rule,
     increases with the conciseness of the pattern: the more concise one
     is, the larger its signature."""
  # XXX signatures of different kinds still overlap?
  if type(pattern) is list:
    return sum((_sign(item) for item in pattern))
  elif pattern.type == 'P_Compare':
    return 2**24
  elif pattern.type == 'P_Guard':
    return 2**21
  elif pattern.type == 'P_Extract':
    return sum(map(_sign, pattern.fields), 2**18) * (len(pattern.fields) + 1)
  elif pattern.type == 'P_Unpack':
    return sum(map(_sign, pattern.members), 2**15) * (len(pattern.members) + 1)
  elif pattern.type in ('P_Identifier', 'P_Discard'):
    return 2**12
  elif pattern.type in ('P_NamedMulti', 'P_NamedMany'):
    return 2**9
  elif pattern.type in ('P_DiscardMulti', 'P_DiscardMany'):
    return 2**6
  else:
    return 0


###- INTERPRETER -##############
### Pattern Engine ##############

def _visit_pattern(S, pattern, value):
  """Given a pattern and a value for it to try to match on, return a tuple of
     (status, payload), where, if status is False, payload is an error message;
     or, if status is True, an empty string, meaning a successful match."""
  if pattern.type == 'P_Identifier':
    S.env[pattern.name] = value
  elif pattern.type == 'P_Compare':
    comparee = _visit_node(S, pattern.value)
    if comparee.value != value.value:
      return False, f'expected {comparee}, found {value}'
  elif pattern.type == 'P_Guard':
    S.env[pattern.param] = value
    result = _visit_node(S, pattern.guard)
    if not (isinstance(result, RyBool) and result.value):
      return False, f'vetoed by the guard of "{pattern.param}"'
  elif pattern.type == 'P_Extract':
    if not (obj := S.env.get(pattern.obj, False)):
      _die(S, f'entity "{pattern.obj}" does not exist')
    elif not isinstance(obj, RyObject):
      if isinstance(obj, _Box) and isinstance(value, _Box):
        lval, rval = obj.value, value.value
        # XXX only RyBools require need with `is`, I guess.
        if isinstance(obj, RyBool) or isinstance(value, RyBool):
          if lval is rval:
            return True, ''
        elif lval == rval:
          return True, ''
      return False, f'expected {obj}, found {value}'
    if not isinstance(value, RyRouteable):
      return False, f'type {value.type} is not an object'
    elif obj.name != value.name:
      return False, f'bogus object: expected "{obj.name}", got "{value.name}"'
    for extractable, field in zip(value.extractable, pattern.fields):
      status, payload = _visit_pattern(S, field, extractable)
      if not status:
        return False, f'extraction for "{obj.name}" failed on field for "{prop}": {payload}'
  elif pattern.type == 'P_Unpack':
    if not isinstance(value, (RyVec, RyStr)):
      return False, f'right-hand side must be a vector or a string, got {value}'
    # If the value is string, return substrings. If vector, return sub-vectors.
    is_str = isinstance(value, RyStr)
    myself = 'string' if is_str else 'vector'
    multis = len(_just_of(pattern.members, 'P_DiscardMulti', 'P_NamedMulti'))
    manys = len(_just_of(pattern.members, 'P_DiscardMany', 'P_NamedMany'))
    if len(pattern.members) != len(value.value) and not (multis or manys):
      return False, f'got pattern of length {len(pattern.members)}, but {myself} ' \
                    f'is of length {len(value.value)}: {value}'
    # TODO: does this 'formula' really work? it seems it doesnt!
    if multis + manys > 2 and (multis + manys) * 1.5 > len(pattern.members):
      _die(S, 'several multi-item captures must be delimited')
    v_off, m_off = 0, 0
    while members := pattern.members[m_off:]:
      member = pattern.members[m_off]
      values = value.value[v_off:]
      named, multi = 'Named' in member.type, 'Multi' in member.type
      name = member.name if named else f'<{"plus" if multi else "star"}>'
      # Assume we'll capture everything up to the vector's end.
      captured = len(values) - len(members[1:])
      if member.type.startswith(('P_DiscardM', 'P_NamedM')):
        # Detect a separator (which has to directly follow the grouping).
        # Valid separators are patterns that capture exactly one value: comparison,
        # object extraction, or a guarding expression.
        if len(members) > 1 and members[1].type in ('P_Compare', 'P_Guard', 'P_Extract'):
          # Iterate over the values left until we meet the specified separator.
          for index, item in enumerate(values):
            status, _ = _visit_pattern(S, members[1], RyStr(item) if is_str else item)
            if status is True:
              captured = index
              # For v_off, we jump over the delimiter ('consuming' it).
              # For m_off, we jump over the pattern of the delimiter.
              v_off += 1
              m_off += 1
              break
            elif index == len(values) - 1:
              return False, f'reached the end of the {myself} searching for the delimiter of "{name}": {value}'
        if not captured and multi:
          return False, f'"{name}" required at least one item to match, got none: {value}'
        if named:
          S.env[member.name] = (RyStr if is_str else RyVec)(values[:captured])
        v_off += captured
      elif captured < 0:
        return False, f'the given {myself} is too small to be captured by {name}'
      else: # if it's not DiscardM... or NamedM...
        item = value.value[v_off]
        status, payload = _visit_pattern(S, member, RyStr(item) if is_str else item)
        if not status:
          return False, f'unpack failed on member no. {m_off + 1}, for item no. {v_off + 1}; {payload}'
        v_off += 1
      m_off += 1
  elif pattern.type == 'P_Discard':
    pass
  return True, ''


### Visitor ##############

def _visit_node(S, node):
  """A recursive, hence slow (and limited by Python's recursion limit), but still
     tail-call-optimizing node interpreter -- the heart of Rydesta. `node` can be
     either a RyNode or a list or RyNodes; `S` is a pre-initialized state. Do not
     use directly -- this function requires some environmental conditions."""
  while True:
    if type(node) in (list, tuple):
      try:
        return [_visit_node(S, x) for x in node]
      except RecursionError:
        _die(S, 'recursion error: recursion too deep :(')
    else:
      S.line = node.line
      if node.type == 'Cases':
        head = _visit_node(S, node.head)
        cases = sorted(node.cases,
          # ValueCases have priority over MatchCases.
          key=lambda x: 2**32 if x.type == 'ValueCase' else _sign(x.cond),
          reverse=True)
        for case in cases:
          if case.type == 'MatchCase':
            # In cases, P_Discard has the highest priority.
            if case.cond.type == 'P_Discard':
              status = True
            else:
              status, _ = _visit_pattern(S, case.cond, head)
          elif case.type == 'ValueCase':
            status = _visit_node(S, case.cond).value == head.value
          if status:
            if not case.body:
              # If the case body is empty, return true.
              return RyBool(True)
            _visit_node(S, case.body[:-1])
            node = case.body[-1]
            break
        if not status:
          return RyBool(False)
        # TCO: continue looping...
      elif node.type == 'Function':
        function = RyFunction(S,
          _sign(node.params),
          node.name, node.params, node.body,
          node.line if not node.params else node.params[0].line)
        variations = S.env.get(node.name, False)
        # Check, first of all, if the function is quoted.
        # --> If it is, make it a parseable infix (with its precedence being
        #     the value of the variable *PREC*), or prefix (when arity = 1).
        # --> Proceed with definition.
        if node.name.startswith('\''):
          name = node.name[1:]
          if function.arity not in (1, 2):
            _die(S,
              'expected either a prefix (arity = 1) or infix (arity = 2), ' \
              f'got arity = {function.arity}')
          if '_' in name:
            S.reader.add_token(name.upper(), r'[ \t]+'.join(name.split('_')))
          elif name[0].isalpha():
            S.reader.add_keyword(name)
          if function.arity == 2:
            S.reader.add_operator(name.upper(), 'left', int(S.env['*PREC*'].value))
          elif function.arity == 1:
            S.reader.add_prefix(name.upper())
        # If the function exists, make this one one of its variations.
        if isinstance(variations, RyVariations):
          if variations.quoting != node.quoting:
            _die(S, f'expected variation `{function}` to be quoting')
          elif variations.naked != node.naked:
            _die(S, f'expected variation `{function}` to be naked')
          variations.add(function)
        else:
          S.env[node.name] = RyVariations(node.name, function,
            quoting = node.quoting,
            naked = node.naked)
        if not node.naked:
          # Make it a closure but with recursion available.
          function.state = function.state.copy()
        return None
      elif node.type == 'If':
        cond = _visit_node(S, node.cond)
        if not (isinstance(cond, RyBool) and cond.value is False):
          if not node.correct:
            # If the body is empty, just return true.
            return RyBool(True)
          _visit_node(S, node.correct[:-1])
          node = node.correct[-1]
        elif node.other:
          _visit_node(S, node.other[:-1])
          node = node.other[-1]
        else:
          # If there is no `else` clause and the condition is false, return false.
          return RyBool(False)
        # TCO: continue looping...
      elif node.type == 'Object':
        S.env[node.name] = (RySecretObject if node.secret else RyObject)(
          node.name,
          node.properties,
          node.block,
          S.copy())
        return None
      elif node.type == 'Ret':
        raise _ReturnException(_visit_node(S, node.value))
      elif node.type == 'Needs':
        from .master import Master
        for modpath in S.env['PATH'].value.split(';'):
          path = Path(modpath) / f'{"_" if node.hidden else ""}{node.module}.ry'
          if path.exists():
            imported = [x.value for x in S.env['MODULES'].value]
            if str(path) in imported:
              return None
            master = Master(path.absolute())
            master.kernel()
            master.load_init()
            master.feed(path.read_text())
            S.reader.merge(master.reader)
            S.env['MODULES'].value.append(RyStr(str(path)))
            if node.expose:
              for entry, value in master.state.env.items():
                # XXX is this right or wrong?
                if entry == 'MODULES':
                  S.env[entry].value += [m for m in value.value if m.value not in imported]
                elif entry not in S.env:
                  S.env[entry] = value
            else:
              name = node.module.split('/')[-1].capitalize()
              S.env[name] = RyRouteable(node.module, master.state.env)
            return None
        _die(S, f'%smodule not found: "{node.module}"' % ('hidden ' if node.hidden else ''))
      elif node.type == 'Assign':
        value = _visit_node(S, node.value)
        status, payload = _visit_pattern(S, node.pattern, value)
        return _die(S, f'match error: {payload}') if not status else value
      elif node.type == 'Call':
        if node.callee.type == 'Request':
          # A bunch of special-form calls (somewhat like LISP's):
          def arity_is(arity):
            if len(node.args) != arity:
              _die(S, f'special-form "{node.callee.name}" receives exactly one argument')
            return True
          if node.callee.name == 'unquote' and arity_is(1):
            quoted = _visit_node(S, node.args[0])
            if not isinstance(quoted, RyExcerpt):
              _die(S, f'cannot unquote a non-excerpt value: {quoted}')
            return _visit_node(quoted.state.copy(), quoted.node)
          elif node.callee.name == 'quote' and arity_is(1):
            return RyExcerpt(S, node.args[0])
        callee = _visit_node(S, node.callee)
        if isinstance(callee, RyVariations):
          args = [(RyExcerpt if callee.quoting else _visit_node)(S, arg) for arg in node.args]
          for idx, variation in enumerate(callee.variations):
            if variation.arity == len(args):
              capsule = variation.state.copy()
              for argno, (param, arg) in enumerate(zip(variation.params, args)):
                status, payload = _visit_pattern(capsule, param, arg)
                if not status:
                  break
              # First condition (the `not in` one) is met when there
              # were no arguments.
              if 'status' not in vars() or status:
                status = True
                break
            elif idx == len(callee.variations) - 1:
              status = False
          if not status:
            variations = '\n'.join(x.dump() for x in callee.variations)
            _die(S,
              f'no variation of "{callee.name}" can handle such {len(args)} argument(s): ' \
              f'{", ".join(map(repr, args))}. Maybe you want one of these:\n{indent(variations, "  ")}')
          # Do not bother doing anything if the function's body is empty.
          if not variation.body:
            return None
          capsule.reader = S.reader
          try:
            _visit_node(capsule, variation.body[:-1])
          except _ReturnException as ret:
            return ret.value
          S = capsule
          last = variation.body[-1]
          node = last.value if last.type == 'Ret' else last
          # TCO: continue looping...
        elif isinstance(callee, RyBuiltin):
          return callee.value(S, *_visit_node(S, node.args))
        else:
          _die(S, f'callee of type {callee.type} is not callable: {callee}')
      elif node.type == 'Instance':
        obj, args = _visit_node(S, [node.callee, node.args])
        if not isinstance(obj, RyObject):
          _die(S, f'value of type {obj.type} is not an object')
        if len(args) != len(obj.props):
          _die(S, f'"{obj.name}" expected {len(obj.props)} properties, got {len(args)}')
        capsule = obj.state.copy()
        # With patterns there is no clear list of parameters an object takes,
        # and .env loses order which we depend on). The only work-around for
        # extraction I could think of is with `extractable`:
        extractable = []
        for idx, (prop, arg) in enumerate(zip(obj.props, args)):
          status, payload = _visit_pattern(capsule, prop, arg)
          if not status:
            _die(S, f'failed to instantiate {obj} on argument no. {idx + 1}: {payload}')
          extractable.append(arg)
        _visit_node(capsule, obj.block)
        return RyRouteable(obj.name, capsule.env, extractable=extractable)
      elif node.type == 'Builtin':
        return RyBuiltin(
          S.env.get(f'#:{node.name}', False) or _die(S, f'builtin "{node.name}" not found'))
      elif node.type == 'Path':
        res = _visit_node(S, node.parent)
        for piece in node.path:
          if res.type != 'routeable':
            _die(S, f'type \'{res.type}\' is not routeable: {res}')
          res = res.env.get(piece) or _die(S, f'no property "{piece}" for {res}')
        return res
      elif node.type == 'Request':
        value = S.env.get(node.name, False)
        if value is False:
          _die(S, f'"{node.name}" is not defined')
        return value
      elif node.type == 'Expect':
        # Evaluate the guard; if it's not false, proceed. If it is, die.
        guard = _visit_node(S, node.guard)
        if isinstance(guard, RyBool) and guard.value == False:
          _die(S, f'expectation false')
        return None
      elif node.type == 'Vector':
        return RyVec(_visit_node(S, node.items))
      elif node.type == 'Number':
        value = node.value
        if 'x' in value:
          value = int(value, 16)
        elif 'o' in value:
          value = int(value, 8)
        elif 'b' in value:
          value = int(value, 2)
        return RyNum(Fraction(value))
      elif node.type == 'String':
        def _format(match):
          name = match.group(1)
          if name not in S.env:
            _die(S, f'interpolation: variable "{name}" is not defined')
          text = S.env.get(name)
          return text.value if isinstance(text, RyStr) else repr(text)
        value = re.sub(r'\$([a-zA-Z][a-zA-Z0-9_\-]*(?<!\-)[!?]?)', _format, node.value)
        return RyStr(bytes(value, 'utf-8').decode('unicode-escape'))
      else:
        raise NotImplementedError(f'internal error: .visit: {node}')


###- ENTRY -##############

def visit(state):
  try:
    last = None
    while node := state.reader.next():
      # Since we don't have any queue and can issue just one node at a time,
      # manual tuple unpacking when multiple nodes have to be issued
      # simultaneously is required.
      if type(node) is tuple:
        for item in node:
          last = _visit_node(state, item)
      else:
        last = _visit_node(state, node)
      state.reader.update_symbol_regex()
    return last
  except ReaderError as error:
    raise RyError(error.reason,
      { 'filename': state.filename,
        'lineno': error.line,
        'kind': 'reader error' })
  except _DeathError as error:
    raise RyError(error.reason,
      { 'filename': error.state.filename,
        'lineno': error.state.line,
        'state': error.state,
        'kind': 'runtime error' })
