## Nose2 plugin for test dependencies

*This is based on https://github.com/Zitrax/nose-dep/, ported to nose2 and tweaked slightly.*

This plugin allows you to express dependencies between your tests, or a preferred running order for them. Although this contravenes best practices (unit tests should be separate, and be runnable independently - Ruby's minitest randomises the test order for exactly this reason), it may be useful in some cases:

- you may have very slow integration tests where redoing what test A did just to run test B would simply be too costly
- you may have 'smoke tests' which should run first, so that the rest can be skipped if those tests fail - for example, if you're writing a multiplication library and `2*2` doesn't work, there's no point testing anything more complicated

To use it, import the depends decorator (`from nose2dep.core import depends`) and decorate your testcases with `@depends(before="test_name")`, `@depends(after=["test_name", "test_name2"])` or `@depends(priority=6)` (or some combination of those arguments, e.g. `@depends(before="test_name", after="test_other", priority=100)`).

### Dependencies

To declare that your test needs to run before or after some other specific test(s), pass `before=` or the `after=` parameters to `@depends`. The arguments can be:

- the name of the other test method as a string
- the other test method object itself
- a list of either of the above

If test B depends on test A, and test A fails, then B will be skipped (allowing the 'smoke tests' use-case above).

Note that all dependencies are treated as soft, unlike the original nosedep. They will only affect the test ordering, not force inclusion. For example if we have:

    @depends(after=test_b)
    def test_a:
      pass

    def test_b:
      pass

and run all tests they would run in the order b,a. If you run only test_a, though, it won't pull in test_b to satisfy the dependency - it'll just run test_a. 

### Priorities

Each test can be given an integer priority (defaulting to 50) and the tests will run in order from lowest to highest. Dependencies take precedence so in total the ordering will be:

1. All tests with a priority lower or equal to the default that are not part of any dependency chain ordered first by priority then by name.
2. Priority groups in order, while each priority group is internally ordered the same as point 1.
3. All tests with priority higher than the default that are not part of any dependency chain ordered first by priority then by name.

*Note: Currently no support for Python 2.6 and 3.2. Should work for 2.7 and 3.3+.*
