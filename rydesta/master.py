import operator

from .reader import Reader

from .machine import RyState, visit
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

  def kernel(self):
    """Initialize the kernel of Rydesta. It consists of builtins like #:getattr,
       to interact with Python intimately, some required values like PATH, MODULES,
       etc., and of Rydesta's type hierarchy."""
    # Values:
    self.define('PATH', RyStr(f'.;{self.basis}'))
    self.define('MODULES', RyVec([]))
    # Type hierarchy:
    self.define('true', RyBool(True))
    self.define('false', RyBool(False))
    for klass in HasType.__subclasses__():
      self.define(klass.type, RyTypeType(klass.type))
    # Functions:
    def _from_operator(_, symbol, args):
      return getattr(operator, symbol.value)(
        *[x.value if hasattr(x, 'value') else x for x in args.value])
    def _kernel_builtin_call(_, name, args):
      if type(__builtins__) is dict:
        return __builtins__[name.value](*args.value)
      else: # PyPy compatibility (?)
        return getattr(__builtins__, name.value)(*args.value)
    self.builtin('state',
      lambda state: state)
    self.builtin('print',
      lambda _, value: print(value.value if isinstance(value, RyStr) else value))
    self.builtin('set-guard-precedence',
      lambda state, level: state.reader.switches.update({'guard-precedence': int(level.value)}))
    self.builtin('set-precedence',
      lambda _, level: setattr(self.state.reader, 'precedence', int(level.value)))
    self.builtin('kernel-glob-call',
      lambda _, name, args: globals()[name.value](*args.value))
    self.builtin('getattr',
      lambda _, obj, attr: getattr(obj, attr.value, RyBool(False)))
    self.builtin('equals?',
      lambda _, left, right: RyBool(left == right))
    self.builtin('kernel-builtin-call', _kernel_builtin_call)
    self.builtin('from-operator', _from_operator)

  def load_init(self):
    """Load basis/init.ry."""
    self.get('MODULES').value.append(RyStr(f'{self.basis / "init.ry"}'))
    self.feed((self.basis / 'init.ry').read_text())

  def feed(self, string):
    """Feed a string of source to the interpreter."""
    self.reader.update(string)
    return visit(self.state)
