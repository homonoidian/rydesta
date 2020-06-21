import re

from textwrap import indent
from collections import namedtuple

from .error import RyError


Token = namedtuple('Token', 'type value')


class ReaderError(Exception):
  """Reader errors are broad errors raised when the process of reading
     a piece of source ends with a failure."""

  def __init__(self, reason, line):
    self.reason = reason
    self.line = line


class RyNode:
  """Rydesta's node system is not organized in a class-per-node-type way.
     Instead it has just one, generic node class -- this one."""

  def __init__(self, type_, line, **kwargs):
    """Create a node of the given type with the given line number.
       The zero or more of the following keyword arguments are thought of
       as node properties."""
    self.type = type_
    self.line = line
    self.props = kwargs

  def set(self, name, value):
    """Create (or update) a node property."""
    self.props[name] = value

  def __getattr__(self, name):
    return self.props[name]

  def __repr__(self):
    return f'({self.type} {" ".join(f"{k}={v}" for k, v in self.props.items())})'


class Reader:
  """
  This class implements the reader of the Rydesta programming language. It is
  sequential, which means that it emits one top-level node at a time. This allows
  an interpreter that iterates over these nodes to change the parser on-the-fly,
  allowing some extra robustnesses and superpowers.

  Usage:
  >>> reader = Reader()
  >>> reader.update('add 1 2<CR>x = 2')
  >>> reader.next()
  (Call ...)
  >>> reader.next()
  (Assign ...)
  >>> reader.next()
  False
  """

  def __init__(self):
    self.switches = {
      'tokens': {},
      'symbols': {
        '->', '=>', '!', '_',
        '=', '.', ',', '(', ')',
        '[', ']', '{', '}',
        '*', '+'
      },
      'prefixes': set(),
      'keywords': {
        'for', 'expect', 'ret', 'if', 'else', 'case',
        'division', 'needs', 'hidden', 'exposed',
        'new', 'obj', 'secret', 'umbrella'
      },
      'precedence': {}
    }
    self.update_symbol_regex()

  ### Public utility. ##############

  def update_symbol_regex(self):
    """Join the symbols and the user-defined operators together in a valid,
       escaped regex."""
    self._symbol_regex = '|'.join(
      map(re.escape,
        sorted(self.switches['symbols'],
               key=len, reverse=True)))

  def merge(self, other):
    """Merge the switches from this parser with the switches of another one."""
    for switch, value in other.switches.items():
      # Happily, update works for both sets and dicts.
      self.switches[switch].update(value)

  def update(self, source):
    """Reset the reader's progress and and substitute the source."""
    self.pos = 0
    self.line = 1
    self.token = Token('BOL', '')
    self.source = source + '\n\x00'

  def add_prefix(self, prefix):
    """Add a new prefix type. Assume it is in uppercase."""
    self.switches['prefixes'].add(prefix)
    if not prefix[0].isalpha():
      self.switches['symbols'].add(prefix)

  def add_keyword(self, keyword):
    """Add a new keyword. Note that an exact match is performed when lexing."""
    self.switches['keywords'].add(keyword)

  def add_operator(self, op, assoc, prec):
    """Add a new operator type. Assume `op` is in uppercase."""
    self.switches['precedence'].update({op: (assoc, prec)})
    if not op[0].isalpha():
      self.switches['symbols'].add(op)

  def add_token(self, ttype, regex):
    """Add a new token. Note that since these tokens are given the highest
       priority, it is highly hazardous to define some this way. Assume
       the token type is in uppercase."""
    self.switches['tokens'].update({ttype: regex})

  ### Private utility. ##############

  def _pretty_token_type(self, ttype=None):
    """Pretty-format the given token's type (or, if not given one, the type of
       the current token)."""
    # XXX Automate? Tablify?
    token = ttype or self.token.type
    type_ = f'"{token.lower()}"'
    if token == 'NL':
      type_ = 'newline'
    elif token == 'EOF':
      type_ = 'end-of-input'
    elif token == 'BOL':
      type_ = 'beginning-of-line'
    elif token == 'ID':
      type_ = 'identifier'
    elif token == 'BUILTIN':
      type_ = 'builtin literal'
    elif token == 'NUM':
      type_ = 'number literal'
    elif token == 'STR':
      type_ = 'string literal'
    return type_

  ### Lexer. ##############

  def _match(self, pattern):
    """Try to match the working slice of the source against the given pattern.
       If successful, store the matched result in the lexical buffer and increment
       the position counters (pos, lineno). On failure, return False."""
    match = re.match(pattern, self.source[self.pos:])
    if match is not None:
      matched = match.group()
      self.buf = matched
      self.pos += len(matched)
      self.line += matched.count('\n')
      return True
    return False

  def _mk_token(self, type_, *, value=True):
    return Token(type_, self.buf if value else '')

  def _progress(self):
    """Read a full token and return it. Skip whitespaces. Raise ReaderError
       on an uncaptured lexeme."""
    # NOTE that user-defined tokens are given the highest lexical precedence!
    for type_, token in self.switches['tokens'].items():
        if self._match(token):
          return self._mk_token(type_)
    if self._match(r'[a-zA-Z][a-zA-Z0-9_\-]*(?<!\-)\??'):
      if self.buf in self.switches['keywords']:
        return self._mk_token(self.buf.upper())
      return self._mk_token('ID')
    elif self._match(r'\'[a-zA-Z\-]+(?<!\-)' + f'|\'({self._symbol_regex})'):
      return self._mk_token('ID')
    elif self._match(r'#:[a-zA-Z_\-]+(?<!\-)'):
      return self._mk_token('BUILTIN')
    elif self._match(r'0x[0-9A-Fa-f]+|0o[0-7]+|0b[01]+|[0-9]*\.[0-9]+|[1-9][0-9]*|0'):
      return self._mk_token('NUM')
    elif self._match(r'"([^\n"\\]|\\[nrtv\\$"\'0])*"'):
      return self._mk_token('STR')
    elif self._match(self._symbol_regex):
      return self._mk_token(self.buf)
    elif self._match(r'[ \t\r]+|;[^\n]*'):
      return self._progress() # ignore
    elif self._match(r'\n+'):
      return self._mk_token('NL', value=False)
    elif self._match(r'\x00'):
      return self._mk_token('EOF', value=False)
    else:
      raise ReaderError(
        f'uncaptured lexeme "{self.source[self.pos]}"; ' \
        f'last valid token was {self._pretty_token_type()}', self.line)

  ### Common parsing helpers. ##############

  def _die(self, reason='syntax error: invalid syntax', line=None):
    raise ReaderError(reason, line or self.line)

  def _expected(self, what, line=None, *, got=True):
    """Die of generic `expected "...", found "..."` with token type pretty-formatted."""
    reason = f'expected {what}'
    self._die(reason if not got else f'{reason}, found {self._pretty_token_type()}', line)

  def _consume(self, *types):
    """If the current token is of any of the given `types`, progress to
       the next one and return the token that was thus consumed. If not
       of any of the types, or if no types were given at all, return False."""
    if self.token.type in types:
      consumed = self.token
      if self.pos < len(self.source):
        self.token = self._progress()
      return consumed
    return False

  def _kleene_until(self, stopper, unit, *, sep=None, allow_nl=False, chop=True):
    """Call the given unit until an encounter with the stopper token. On success,
    return a list of the results each unit yielded. Return False on any failure.

    When given a separator, expect it to directly follow each unit.
    If `allow_nl` is set to True, ignore the newlines before, between
    and after a unit. If chomp is True (which it is by default), consumes
    the stopper.
    """
    items = []
    while True:
      if chop and self._consume(stopper) or self.token.type == stopper:
        return items
      elif allow_nl and self._consume('NL'):
        continue
      item = unit()
      if (item is False) or sep and self.token.type not in (stopper, sep):
        return False
      if sep:
        self._consume(sep)
      items.append(item)

  def _isolate(self, unit):
    """Call the given unit and return the result, if it is not False.
       If it is, revert the state of the parser to the state before
       the call and return False."""
    #- Save!
    before = self.token, self.pos, self.line
    result = unit()
    if result is not False:
      return result
    #- Restore!
    self.token, self.pos, self.line = before
    return False

  def _any_of(self, *choices):
    """Apply _isolate on each choice until one returns a non-False value; if not
       one of the choices matched, return False."""
    for choice in choices:
      result = self._isolate(choice)
      if result is not False:
        return result
    return False

  ### Parser. ##############

  #| Expressions & values:

  def _value(self):
    # value ::= ID {"." ID} -> Path(parent, [str]path)
    #   | BUILTIN -> Builtin(name)
    #   | STR -> String(value)
    #   | NUM -> Number(value)
    #   | "[" {value} "]" -> Vector([]items)
    #   | "(" infix ")"
    #   / False
    line = self.line
    token = self._consume('ID', 'BUILTIN', 'STR', 'NUM', '(', '[')
    if token is False:
      return False
    if token.type == 'ID':
      path = []
      while self._consume('.'):
        part = self._consume('ID')
        if part is False:
          self._expected('an identifier', line)
        path.append(part.value)
      return RyNode('Path', line, parent=token.value, path=path)
    elif token.type == 'BUILTIN':
      return RyNode('Builtin', line, name=token.value[2:]) # cut the "#:" part
    elif token.type == 'STR':
      return RyNode('String', line, value=token.value[1:-1]) # cut the quotes
    elif token.type == 'NUM':
      return RyNode('Number', line, value=token.value)
    elif token.type == '[':
      items = self._kleene_until(']', self._value, allow_nl=True)
      if items is False:
        self._expected(f'a vector item or "]" when reading a vector', line)
      return RyNode('Vector', line, items=items)
    elif token.type == '(':
      inside = self._infix()
      if inside is False:
        self._expected('an expression', line)
      if self._consume(')') is False:
        self._expected('")"', line)
      return inside

  def _call(self):
    # call ::= (ID | BUILTIN | "(") {value} -> Call(callee, []args)
    #   | NEW ID {value} -> Instance(callee, []args)
    #   | value "!" -> Call(callee, [])
    #   | value
    line = self.line
    if self.token.type not in ('ID', 'NEW', 'BUILTIN', '('):
      return self._value()
    new = self._consume('NEW')
    callee = self._value()
    if self._consume('!'):
      return RyNode('Call', line, callee=callee, args=[])
    if new and callee is False:
      self._expected('object name', line)
    args = []
    while True:
      arg = self._value()
      if not arg:
        break
      args.append(arg)
    if new is False and not args:
      # If there was no arguments to follow the callee,
      # and it was not an object instantiation, don't
      # touch anything.
      return callee
    return RyNode('Instance' if new is not False else 'Call', line, callee=callee, args=args)

  def _prefix(self):
    # prefix ::= `switches/prefixes` prefix -> Call(callee, [1]args)
    #   | call
    line = self.line
    operator = self._consume(*self.switches['prefixes'])
    if operator is not False:
      operand = self._prefix()
      if operand is False:
        self._expected(f'a value to follow prefix "{operator.value}"', line)
      # NOTE: prefixes are function calls after parsing!
      return RyNode('Call', line,
        callee = RyNode('Path', line,
          parent = f'\'{operator.value.lower()}',
          path = []),
        args = [operand])
    return self._call()

  def _infix(self, depth=0):
    # infix ::= prefix `switches/precedence` infix -> Call(callee, [2]args)
    #   / False
    line = self.line
    left = self._prefix()
    if left is False:
      return False
    while True:
      assoc, prec = self.switches['precedence'].get(self.token.type, (0, 0))
      if depth >= prec:
        return left
      infix = self._consume(self.token.type).type
      # Pass one less precedence if it's right associative:
      right = self._infix(prec - int(assoc == 'right'))
      if right is False:
        self._expected('right hand side of an expression', line)
      # NOTE: infixes are function calls after parsing, too!
      left = RyNode('Call', line,
        callee = RyNode('Path', line,
          parent = f'\'{infix.lower()}',
          path = []),
        args = [left, right])
    return left

  #| Patterns:

  def _pattern_guard(self):
    # pattern_guard ::= ID ("," infix | <operator with precedence=2> value)
    #   -> P_Guard(param, guard)
    #   / False
    line = self.line
    param = self._consume('ID')
    if param is False:
      return False
    #- Complex guards, e.g., "(x, container? x and size x < 500)"
    if self._consume(','):
      guard = self._infix()
      if guard is False:
        self._expected('a guarding expression', line)
      return RyNode('P_Guard', line, param=param.value, guard=guard)
    #- Nuclear guards, e.g., "(x in [1 2 3])", or "(x not of num)"
    infix = self._consume(*[x for x, p in self.switches['precedence'].items() if p[1] == 2])
    if infix is not False:
      return RyNode('P_Guard', line,
        param = param.value,
        guard = RyNode('Call', line,
          callee = RyNode('Path', line,
            parent = f'\'{infix.type.lower()}',
            path = []),
          args = [RyNode('Path', line, parent=param.value, path=[]),
                  self._value() or self._expected('a value', line)]))
    return False

  def _pattern_extract(self):
    # pattern_extract ::= ID {pattern} -> P_Extract(obj, []fields)
    #   / False
    line = self.line
    obj = self._consume('ID')
    if obj is False:
      return False
    fields = self._kleene_until(')', self._pattern, chop=False)
    if fields is False:
      return False
    return RyNode('P_Extract', line, obj=obj.value, fields=fields)

  def _pattern_multi(self):
    # pattern_multi ::= "(" "*" ")" -> P_DiscardMany
    #   | "(" "+" ")" -> P_DiscardMulti
    #   | ID "*" -> P_NamedMany(name)
    #   | ID "+" -> P_NamedMulti(name)
    #   / False
    line = self.line
    if self._consume('('):
      unnamed = self._consume('+', '*')
      if unnamed is False:
        return False
      if self._consume(')') is False:
        self._expected('")"')
      return RyNode('P_DiscardMany' if unnamed.type == '*' else 'P_DiscardMulti', line)
    name = self._consume('ID')
    if name is False:
      return False
    if self._consume('+'):
      return RyNode('P_NamedMulti', line, name=name.value)
    elif self._consume('*'):
      return RyNode('P_NamedMany', line, name=name.value)
    else:
      return False

  def _pattern(self):
    # pattern ::= ID -> P_Identifier(name)
    #   | (NUM | STR) -> P_Compare(value)
    #   | _ -> P_Discard
    #   | "[" (pattern | pattern_multi)+ "]" -> P_Unpack([]members)
    #   | "(" (pattern_guard | pattern_extract) ")"
    #   / False
    line = self.line
    token = self._consume('ID', 'NUM', 'STR', '_', '[', '(')
    if token is False:
      return False
    if token.type == '[':
      members = self._kleene_until(']', lambda: self._any_of(self._pattern_multi, self._pattern))
      if not members: # XXX [] matches empty vector?
        return False
      return RyNode('P_Unpack', line, members=members)
    elif token.type == '(':
      inside = self._any_of(self._pattern_guard, self._pattern_extract)
      if inside is False:
        return False
      if self._consume(')') is False:
        self._expected('")"', line)
      return inside
    elif token.type == 'ID':
      return RyNode('P_Identifier', line, name=token.value)
    elif token.type in ('NUM', 'STR'):
      if token.type == 'NUM':
        node = RyNode('Number', line, value=token.value)
      else:
        node = RyNode('String', line, value=token.value[1:-1])
      return RyNode('P_Compare', line, value=node)
    elif token.type == '_':
      return RyNode('P_Discard', line)

  #| Block:

  def _block(self):
    # block ::= "{" terms:{term} "}" -> []terms
    #   / False
    terms = []
    if self._consume('{') is False:
      return False
    while term := self.next('}'):
      terms.append(term)
    if self._consume('}') is False:
      self._die('unexpected term while in block: expected "}"')
    return terms

  #| Top-level:

  def _assign(self):
    # assign ::= [pattern except guard] "=" infix -> Assign(pattern, value)
    #   / False
    line = self.line
    pattern = self._pattern()
    if pattern is False or not self._consume('='):
      return False
    if pattern.type == 'P_Guard':
      self._die('top-level guards forbidden in assignment', line)
    value = self._infix()
    if value is False:
      self._expected('a value', line)
    return RyNode('Assign', line, pattern=pattern, value=value)

  def _function(self):
    # function ::= ID {pattern} "->" (infix | block)
    #   -> Function(name, []params, []body)
    #   / False
    line = self.line
    name = self._consume('ID')
    if name is False:
      return False
    params = self._kleene_until('->', self._pattern)
    if params is False:
      return False
    body = self._any_of(self._block, self._infix)
    if body is False:
      self._expected('function body', line, got=False)
    return RyNode('Function', line,
      name = name.value,
      params = params,
      body = body if type(body) is list else [body])

  def _for(self):
    # for ::= FOR {pattern} "{" functions:function+ "}" -> ...functions
    #   / False
    """
    Here is what a for block does.
      >>> for (num a) (num b) {
            add -> a + b
            sub -> a - b
          }
    Expands to:
      >>> add (num a) (num b) -> a + b
      >>> sub (num a) (num b) -> a - b
    Since there is no clear mechanism for yielding multiple nodes at the same time,
    we postpone this problem to figure itself out. A middle-ground, now, is to
    return a tuple.
    """
    line = self.line
    if self._consume('FOR') is False:
      return False
    params = self._kleene_until('{', self._pattern)
    if params is False:
      self._expected('a common parameter pattern or "{"', line)
    functions = self._kleene_until('}', self._function, sep='NL', allow_nl=True) \
      or self._expected('at least one function in the block', line, got=False)
    for function in functions:
      function.set('params', params + function.params)
    return tuple(functions)

  def _umbrella(self):
    # umbrella ::= UMBRELLA ID FOR ID+ -> Umbrella(name, []covers)
    #   / False
    line = self.line
    if self._consume('UMBRELLA') is False:
      return False
    name = self._consume('ID')
    if name is False:
      self._expected('umbrella name', line)
    if self._consume('FOR') is False:
      self._expected('"for"', line)
    # Instruct not to chop off the newline since we'll confuse `parse`.
    objects = self._kleene_until('NL', lambda: self._consume('ID'), chop=False)
    if not objects:
      self._expected('at least one object', line, got=False)
    return RyNode('Umbrella', line, name=name.value, covers=[obj.value for obj in objects])

  def _obj(self):
    # obj ::= [SECRET] OBJ ID {ID} [block]
    #   -> Object(name, ~secret, []properties, []block)
    #   / False
    line = self.line
    secret = self._consume('SECRET')
    if self._consume('OBJ') is False:
      return False
    name = self._consume('ID')
    if name is False:
      self._expected('object name', line)
    properties = []
    while True:
      property_ = self._consume('ID')
      if property_ is False:
        break
      properties.append(property_.value)
    return RyNode('Object', line,
      name = name.value,
      secret = secret is not False,
      properties = properties,
      block = self._block() or [])

  def _ret(self):
    # ret ::= RET infix -> Ret(value)
    #   / False
    line = self.line
    if self._consume('RET') is False:
      return False
    return RyNode('Ret', line,
      value = self._infix() or self._expected('a value to return', line))

  def _needs(self):
    # needs ::= NEEDS [HIDDEN] ID [EXPOSED] -> Needs(module, ~hidden, ~expose)
    #   / False
    line = self.line
    if self._consume('NEEDS') is False:
      return False
    hidden = self._consume('HIDDEN')
    module = self._consume('ID', 'STR')
    if module is False:
      self._expected('dependency name', line, got=False)
    exposed = self._consume('EXPOSED')
    return RyNode('Needs', line,
      module = module.value[1:-1] if module.type == 'STR' else module.value,
      hidden = hidden is not False,
      expose = exposed is not False)

  def _expect(self):
    # expect ::= EXPECT infix -> Expect(guard)
    #   / False
    line = self.line
    if self._consume('EXPECT') is False:
      return False
    return RyNode('Expect', line, guard=self._infix() or self._expected('an expression', line))

  def _case_pattern(self):
    # case_pattern ::= pattern:pattern "->" -> ('pattern', pattern)
    #   / False
    pattern = self._pattern()
    if pattern is False:
      return False
    if self._consume('->') is False:
      return False
    return 'pattern', pattern

  def _case_infix(self):
    # case_infix ::= infix:infix "=>" -> ('infix', infix)
    #   / False
    infix = self._infix()
    if infix is False:
      return False
    if self._consume('=>') is False:
      return False
    return 'infix', infix

  def _case(self):
    # case ::= case_infix (infix | block) -> ValueCase(cond, []body)
    #   | case_pattern (infix | block) -> MatchCase(cond, []body)
    line = self.line
    cond = self._any_of(self._case_pattern, self._case_infix)
    if cond is False:
      self._die(
        'invalid expression or pattern; expected a valid expression ' \
        'or pattern followed by "=>" or "->", correspondinly, or "}"')
    body = self._any_of(self._block, self._infix)
    if body is False:
      self._expected('case body - an expression or a block', line)
    return RyNode('MatchCase' if cond[0] == 'pattern' else 'ValueCase', line,
      cond = cond[1],
      body = body if type(body) is list else [body])

  def _cases(self):
    # cases ::= CASE infix "{" case+ "}"
    #   -> Cases(head, [Case]cases)
    #   / False
    line = self.line
    if self._consume('CASE') is False:
      return False
    head = self._infix()
    if head is False:
      self._expected('case head - the value to match upon', line)
    if self._consume("{") is False:
      self._expected('"{"', line)
    cases = self._kleene_until('}', self._case, sep='NL', allow_nl=True)
    if cases is False:
      self._expected('one case or multiple cases separated by newline(s)', line)
    if not cases: # empty cases block
      self._expected('at least one case', line, got=False)
    return RyNode('Cases', line, head=head, cases=cases)

  def _if(self):
    # if ::= IF infix block [ELSE block] -> If(cond, []correct, []other)
    #   / False
    line = self.line
    if self._consume('IF') is False:
      return False
    cond = self._infix()
    if cond is False:
      self._expected('condition', line)
    correct = self._block()
    if correct is False:
      self._expected('a block')
    other = []
    if self._consume('ELSE'):
      other = self._block()
      if other is False:
        self._expected('a block')
    return RyNode('If', line, cond=cond, correct=correct, other=other)

  def _division(self):
    # division ::= [ID] "division" body:block -> ...body
    #   / False
    #- Here we meet the same problem we met in `for`: returning multiple nodes
    #  simultaneously and being transparent to the parents of ours, at the same time.
    #- This is impossible, so we again return a tuple of nodes.
    line = self.line
    _ = self._consume('ID') # ignore
    if self._consume('DIVISION') is False:
      return False
    body = self._block()
    if body is False:
      self._expected('division body', line)
    return tuple(body)

  def _term(self):
    return self._any_of(
      self._division,
      self._if,
      self._cases,
      self._expect,
      self._needs,
      self._ret,
      self._obj,
      self._umbrella,
      self._for,
      self._function,
      self._assign,
      self._infix)

  def next(self, stopper='EOF'):
    """Proceed to read the next top-level node. Return False if reached the end."""
    # XXX queue of nodes instead of returning tuples?
    if self.token.type == 'BOL':
      self.token = self._progress()
    if self.token.type == stopper:
      return False
    if self._consume('NL'):
      return self.next()
    line = self.line
    term = self._term()
    if term is False:
      self._expected('a valid term or EOF', line, got=False)
    if self._consume('NL') is False and self.token.type != stopper:
      if not isinstance(term, RyNode):
        self._die(f'two or more terms in a row')
      self._die(
          f'strange text (namely {self._pretty_token_type()}) ' \
          f'follows term `{term.type}`')
    return term


def pretty(reader, *, spaces=2):
  """Given a reader, pretty-print its top-level nodes up until reaching the end.
     Indent each new nesting with the given amount of spaces [default: 2]."""
  def _single(entity):
    buf = []
    if isinstance(entity, RyNode):
      buf.append(f'<{entity.type}:{entity.line}>')
      for prop, val in entity.props.items():
        buf.append(indent(prop, ' ' * spaces) + ':')
        buf.append(indent(_single(val), ' ' * (spaces * 2)))
    elif type(entity) in (tuple, list):
      for item in entity:
        buf.append(_single(item))
    return '\n'.join(buf) or repr(entity)
  def _iter():
    while node := reader.next():
      yield _single(node)
  return '\n'.join(_iter())
