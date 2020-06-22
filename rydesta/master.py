from .reader import Reader

from .machine import RyState, visit
from .machine import RyBool, RyVec, RyStr, RyNum

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
    """Initialize the kernel of Rydesta. It mainly consists of builtins
       like #:getattr, to interact with Python intimately, and some required
       values like PATH, MODULES, etc."""
    # Values:
    self.define('PATH', RyStr(f'.;{self.basis}'))
    self.define('MODULES', RyVec([]))
    self.define('*PREC*', RyNum(1))
    self.define('true', RyBool(True))
    self.define('false', RyBool(False))
    # Functions:
    self.builtin('precedence',
      lambda _, level: self.define('*PREC*', level))
    self.builtin('getattr',
      lambda _, obj, attr, default=None: getattr(obj, attr.value, default))
    self.builtin('equals?',
      lambda _, left, right: RyBool(left == right))

  def load_init(self):
    """Load basis/init.ry."""
    self.get('MODULES').value.append(RyStr(f'{self.basis / "init.ry"}'))
    self.feed((self.basis / 'init.ry').read_text())

  def feed(self, string):
    """Feed a string of source to the interpreter."""
    self.reader.update(string)
    return visit(self.state)
