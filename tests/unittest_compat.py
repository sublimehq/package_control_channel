import sys
import re
import unittest

from functools import wraps


def inject_into_unittest():
    assert sys.version_info < (3,)

    if sys.version_info < (2, 7):
        class PatchedTestCase(unittest.TestCase):
            def assertIn(self, member, container, msg=None):
                """Just like self.assertTrue(a in b), but with a nicer default message."""
                if member not in container:
                    if not msg:
                        msg = '%r not found in %r' % (member, container)
                    self.fail(msg)

            def assertNotIn(self, member, container, msg=None):
                """Just like self.assertTrue(a not in b), but with a nicer default message."""
                if member in container:
                    if not msg:
                        msg = '%s unexpectedly found in %s' % (member,
                                                               container)
                    self.fail(msg)

            def assertGreater(self, a, b, msg=None):
                """Just like self.assertTrue(a > b), but with a nicer default message."""
                if not a > b:
                    if not msg:
                        msg = '%s not greater than %s' % (a, b)
                    self.fail(msg)

            def assertRegex(self, text, expected_regexp, msg=None):
                """Fail the test unless the text matches the regular expression."""
                if isinstance(expected_regexp, basestring):
                    expected_regexp = re.compile(expected_regexp)
                if not expected_regexp.search(text):
                    msg = msg or "Regexp didn't match"
                    msg = '%s: %r not found in %r' % (msg, expected_regexp.pattern, text)
                    raise self.failureException(msg)

            def assertNotRegex(self, text, unexpected_regexp, msg=None):
                """Fail the test if the text matches the regular expression."""
                if isinstance(unexpected_regexp, basestring):
                    unexpected_regexp = re.compile(unexpected_regexp)
                match = unexpected_regexp.search(text)
                if match:
                    msg = msg or "Regexp matched"
                    msg = '%s: %r matches %r in %r' % (msg,
                                                       text[match.start():match.end()],
                                                       unexpected_regexp.pattern,
                                                       text)
                    raise self.failureException(msg)

            def assertIsInstance(self, obj, cls, msg=None):
                """Same as self.assertTrue(isinstance(obj, cls)), with a nicer
                default message."""
                if not isinstance(obj, cls):
                    if not msg:
                        msg = '%s is not an instance of %r' % (obj, cls)
                    self.fail(msg)

        unittest.TestCase = PatchedTestCase

        # Patch setUpClass and tearDownClass into unittest.TestSuite
        def run(self, result):
            def run_if_attr(obj, attrname):
                method = getattr(obj, attrname, None)
                if method:
                    method()

            last_class = None
            for test in self._tests:
                if isinstance(test, unittest.TestCase):
                    cur_class = test.__class__
                    if last_class.__class__ != cur_class:
                        if last_class is not None:
                            run_if_attr(last_class, 'tearDownClass')
                        run_if_attr(cur_class, 'setUpClass')
                        last_class = cur_class

                if result.shouldStop:
                    break
                test(result)

            if last_class is not None:
                run_if_attr(last_class, 'tearDownClass')

            return result
        unittest.TestSuite.run = run

    elif sys.version_info < (3, 2):
        unittest.TestCase.assertRegex = unittest.TestCase.assertRegexpMatches
        unittest.TestCase.assertNotRegex = unittest.TestCase.assertNotRegexpMatches
