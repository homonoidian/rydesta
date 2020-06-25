# A specification of Rydesta

### Section 0. Explicit types.

Explicit types are granular, distinguishable data types.

+ `str` (string): `"foo bar baz"`; supports several escape sequences; interpolation
  via `$NAME`, e.g.: `"My name is $name"`;
+ `num` (number):  `1234`, `12.34`, `.1234`, `0x0123456789abcdef`, `0o01234567`, `0b01`;
  represented with Python's `Fraction`, so, e.g., `.1 + .2 is .3` yields `true`.
+ `vec` (vector): `[1 2 3 4]`; items must be atomar (i.e., these data types plus
  parenthesized expressions, e.g.: `[(2 + 2 * 2) 2 3 (foo bar baz)]`)

### Section 1. Implicit types.

Implicit types could be known of only after interpretation of a corresponding construction.

+ `type`: the root of the type hierarchy; `[num str vec bool ...] are of type`
  yields `true`;
+ `variations`: a group of variations under single name; variations are sorted by
  signature; e.g., when `square n -> n ^ 2`, `square of variations` yields `true`;
+ `function`: a particular variation of a function; could be interacted with
  via indexing `dump: (x of variations)`, which returns vector of `function`s;
+ `object`: an uninstantiated object; e.g., when `obj Vector x y`, `Vector of object`
  yields `true`;
+ `routeable`: an entity that supports `.` (dot); instances of objects (made with `new`)
  are `routeable`, e.g.: `obj Vector x y` makes `new Vector 1 2 of routeable` yield
  `true`, since `vector = new Vector 1 2` can be a part of Path: `vector.x` yields 1
  and `vector.y` 2;
+ `excerpt`: a thin wrapper around `RyNode`, the sole AST node class; issued on quoting,
  e.g., `quote (1 + 1) of excerpt` yields `true`;
+ `builtin`: a wrapper-type around Python callables; prefixed with `#:`, by convention;
  they are defined in kernel; e.g., `#:getattr of builtin` yields `true`;
+ `bool`: supertype for `true` and `false`; they are mutably defined in the kernel, so
  `true of bool` yields `true`.

### Section 2. Function signatures.

Function signatures (priority of function invokation):

| **Name**                     | **Signature**                             | **Example** (separated by `;`)           |
|------------------------------|-------------------------------------------|------------------------------------------|
| Identity pattern             | 2^24                                      | 1 ; [] ; "foobar"                        |
| Guarding pattern             | 2^21                                      | (x of num) ; (x, is-ok? x)               |
| Routeable extraction         | 2^18 + rec(fields) * (no. of fields + 1)  | (Vector x1 x2) ; (Number (value of num)) |
| Vector unpacking             | 2^15 + rec(members) * (no. of fields + 1) | [1 2 3 a b c "he"] ; [["a" "b" c] 2]     |
| Identifier, discard          | 2^12                                      | _ ; foobar ; quux                        |
| Named groups (captures)      | 2^9                                       | x* y+                                    |
| Discarding groups (captures) | 2^6                                       | (*) (+)                                  |
| Anything else                | 0                                         |                                          |

### Section 3.
