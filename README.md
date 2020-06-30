# Rydesta

> Rydesta is a draft; it is rather unstable and slow; to me it feels unreliable.
> Nevertheless, you can play with it.

### How to try?

Make sure to have Python, of course. The latest release (3.8.3) is what I'm using.
Latest PyPy works, too.
+ Obtain the repo in any way you prefer, and do `python -m rydesta` in the repo's
  root. That way, a REPL would pop out.
+ If instead you want to run a script, the command is `python -m rydesta path/to/script.ry`.
+ To evaluate the tests found in `suite/`, type `python -m rydesta suite`.
+ If you want to see the measurements of the *bootstrap time* (time it took to
  initialize the kernel and to include/evaluate `basis/boot.ry`) and the *evaluation time*
  (time it took to evaluate a line of code (REPL), or a whole script), pass flag
  `-t` (or `--time`).

### The state of the language?

It's rev. 001. Meaning if you feed it some code, chances are — it won't work. And probably
it's not going to be your fault at all.

### Guides?

It's just too early and naive to have any guide right now, I think. Rydesta's
an ambiguous language and an unfinished language, too, and that's a killing pair.
Nonetheless, the closest to a guide (though an unfinished one, too) is the specification
found in `etc/` and the source code itself (i.e., `rydesta/reader.py` and `rydesta/machine.py`).
