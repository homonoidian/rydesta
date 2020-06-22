class RyError(Exception):
  """A generic error that is raised when during some process inside
     the Rydesta interpreter a fatal interrupt occurs."""

  def __init__(self, reason, meta):
    """`reason` -- a textual explanation of the error; `meta` -- a dictionary
       of some useful meta information that may be important to understand/show
       the problem that happened."""
    self.reason = reason
    self.meta = meta
