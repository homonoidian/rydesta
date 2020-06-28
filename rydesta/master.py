import operator

from .reader import Reader

from .machine import RyState, visit, _die
from .machine import RyBool, RyVec, RyStr, RyNum, HasType, RyTypeType

from pathlib import Path


class Master:
  """A simple, intuitive way to interact with the complete Rydesta
     infrastructure. And the sole way to get the kernel, too."""

  def __init__(self, filename):
    self.reader = Reader()
    self.state = RyState(str(filename), self.reader)
    self.basis = Path(__file__).parents[1] / "basis"

  def define(self, name, value):
    """Define a constant-like (but may not be a constant) value."""
    self.state.env[name] = value

  def get(self, name):
    """Grab a value from the environment. Return False if found none."""
    return self.state.env.get(name, False)

  def builtin(self, name, expression):
    """Define a builtin under the given name, with the expression being
       a Python callable. Note that this callable always receives RyState
       as its first argument. It also should return a value Rydesta can
       understand (RyNum, RyVec, ...) and should not return None."""
    self.state.env[f'#:{name}'] = expression

  def _k_set_precedence(self, state, precedence):
    """Set global precedence."""
    if not isinstance(precedence, RyNum):
      _die(state, '"set-precedence" (no. 1) expects a num')
    self.state.reader.precedence = int(precedence.value)

  def _k_set_guard_precedence(self, state, precedence):
    """Set global guard precedence, a level with which guards work."""
    if not isinstance(precedence, RyNum):
      _die(state, '"set-guard-precedence" (no. 1) expects a num')
    self.state.reader.switches['guard-precedence'] = int(precedence.value)

  def _k_builtin(self, state, name):
    """Get Python builtin from __builtins__."""
    get = dict.get if type(__builtins__) is dict else getattr
    if not isinstance(name, RyStr):
      _die(state, '"builtin" (no. 1) expects a str')
    return get(__builtins__, name.value) or _die(state, f'Python has no builtin {name}')

  def _k_call(self, _, callee, args):
    """Call Python callable 'callee' with a 'vec' of arguments' items."""
    return callee(*args.value)

  def _k_to_py(self, state, obj):
    """Try to extract a Python value from a HasType object."""
    attr = getattr(obj, 'value')
    if attr is None:
      _die(state, f'could not convert "{obj}" to Python')
    if type(attr) is list:
      return [i.value if hasattr(i, 'value') else i for i in attr]
    return attr

  def _k_wraps(self, state, typ, obj):
    """Wraps an object in 'typ', of TypeType."""
    if not isinstance(typ, RyTypeType):
      _die(state, f'"wraps" (no. 1) expects a type')
    # XXX speed up!
    for klass in HasType.__subclasses__():
      if klass.type == typ.value:
        return klass(obj)

  def _k_import(self, state, name):
    if not isinstance(name, RyStr):
      _die(state, f'"import" (no. 1) expects a str')
    try:
      return __import__(name.value)
    except ImportError:
      _die(state, f'module "{name}" not found')

  def kernel(self):
    """Initialize the kernel of Rydesta. It consists of builtins like #:getattr,
       to interact with Python intimately, some required values like PATH, MODULES,
       etc., and of Rydesta's type hierarchy."""
    # Values:
    self.define('PATH', RyStr(f'.;{self.basis}'))
    self.define('MODULE-CACHE', RyVec(set()))
    # Type hierarchy:
    self.define('true', RyBool(True))
    self.define('false', RyBool(False))
    for klass in HasType.__subclasses__():
      self.define(klass.type, RyTypeType(klass.type))
    # Builtins:
    for name in dir(self):
      if name.startswith('_k_'):
        self.builtin(name[3:].replace('_', '-'), getattr(self, name))

  def load_init(self):
    """Load basis/init.ry."""
    self.get('MODULE-CACHE').value.add(RyStr(f'{self.basis / "boot.ry"}'))
    self.feed((self.basis / 'boot.ry').read_text())

  def feed(self, string):
    """Feed a string of source to the interpreter."""
    self.reader.update(string)
    return visit(self.state)
