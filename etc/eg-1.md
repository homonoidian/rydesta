# Rydesta: Clarity

Rydesta, it seems to me, is a clear language. Are there some examples of such
clarity, even theoretical, i.e., unpractical? There are.

### (1) Vector Addition

Though the code that follows does not show the usefulness of the language per se,
it still draws out a comparison that is rather interesting to observe.

To implement an operator in a programming language, if it supports such a modification,
I have to give up my time on writing a lot of unnecessary wrapping clutter. For
in Python, as example, a vector class that supports arithmetic operators `+`
and `-` spans eight meaningful lines:

```python
class Vector:
  def __init__(self, x, y):
    self.x = x
    self.y = y

  def __add__(self, other):
    return Vector(self.x + other.x, self.y + other.y)

  def __sub__(self, other):
    return Vector(self.x - other.x, self.y - other.y)
```

I spent four lines on class declaration, and four on the working semantics. I know
this is an exaggerated 'issue', and Python scales so well you won't notice any
problems in a project large enough -- for I wrote and write a lot of Python code
myself. But let us, for the sake of the argument, just look at an equivalent Rydesta
implementation.

```rydesta
obj Vector (x of num) (y of num)
'+ (Vector x1 y1) (Vector x2 y2) -> new Vector (x1 + x2) (y1 + y2)
'- (Vector x1 y1) (Vector x2 y2) -> new Vector (x1 - x2) (y1 - y2)
```

I can also gain two lines but remove the repeatedness. It seems that it
looks clearer.

```rydesta
obj Vector (x of num) (y of num)

for (Vector x1 y1) (Vector x2 y2) {
  '+ -> new Vector (x1 + x2) (y2 + x2)
  '- -> new Vector (x1 - x2) (y2 - x2)
}
```

Not only did I implement the same thing, it's now type-checked, too. Well, sort of.
It's a feature that emerges from Rydesta's patterns, and it's semantically identical
to Python's `type(x) is int` or `isinstance(x, int)`: when the 'type-checking'
returns false, in that case, the pattern matcher panics and dies. And so it works.

### (2) Novel operators

There is another cool but theoretic example, one on which it's good to look at,
but one one'll never use, with a rather high probability.

Defining a new operator (i.e., infix or prefix) is hard or even impossible in
the majority of the languages, but in Rydesta it's the same syntax as in the vector
problem shown before.

```rydesta
':: (a of vec) (b of vec) -> a + b
```

This thing makes Haskell-like operations possible, but only with two vectors:
`[x] :: [y]` will yield `[x y]`. Let's add some code so it supports appending
individual items. Here is the full implementation I wrote:

```rydesta
':: (a of vec) (b of vec) -> a + b
':: a (b of vec) -> [a] + b
':: (a of vec) b -> a + [b]
':: a b -> [a] + [b]
```

It's a little verbose, but I couldn't think of it smaller. Testing?

```rydesta
[(1::2) ([1]::2) (1::[2]) ([1]::[2])] all are [1 2]
```

> Such definitions are handled under the hood, and precedence is set by default to
the same level addition (`+`) and subtraction (`-`) are sitting on -- I think
that's the most optimal solution. If one is willing to set custom precedence, one
can mess with builtin `#:precedence` or module `Myself` (whose purpose is to
help building in-language DSLs, by the way -- and which doesn't exist yet, even
in project `\_*_*_/`)

### TODO?
