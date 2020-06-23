"""
Usage: rydesta [SCRIPT]
"""

import sys
import docopt
import rydesta
import pathlib
import readline


class RyCLI:
  """A command-line interface to Rydesta."""

  VERSION = 'Rydesta rev. 001'

  @staticmethod
  def _master(filename):
    """Properly initialize a new master."""
    master = rydesta.Master(filename)
    master.kernel()
    master.load_init()
    return master

  @staticmethod
  def _report(error, *, quit=True):
    """Format and print given error. If quit is set to True, exit afterwards."""
    filename = error.meta['filename']
    lineno = error.meta['lineno']
    kind = error.meta['kind']
    (sys.exit if quit else print)(
      f'{filename}:{lineno}:\n  {kind}: {error.reason}')

  @staticmethod
  def enter():
    """The argument-parser and argument-evaluator of Rydesta."""
    args = docopt.docopt(__doc__, version=RyCLI.VERSION, options_first=True)
    if args['SCRIPT']:
      file = pathlib.Path(args['SCRIPT'])
      if not file.exists():
        sys.exit(f'No such file: "{file}"')
      master = RyCLI._master(file.absolute())
      try:
        master.feed(file.read_text())
      except rydesta.RyError as error:
        RyCLI._report(error)
    else:
      master = RyCLI._master('<interactive>')
      print(f'Welcome to {RyCLI.VERSION}!', 'Good luck!', sep='\n')
      while True:
        line = input(' * ').strip()
        try:
          result = master.feed(line)
          if result is not None:
            print('->', result)
        except rydesta.RyError as error:
          RyCLI._report(error, quit=False)


RyCLI.enter()
