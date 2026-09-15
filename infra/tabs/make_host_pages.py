"""Create local host pages that transclude a strip, before and after.

    uv run python infra/tabs/make_host_pages.py 'תבנית:כדורסל/סטטיסטיקה/שיאני נקודות'

A template page shows nothing when viewed directly - its body is inside
<includeonly> - so a browser test pointed at the template sees an empty page
and every assertion fails for the wrong reason. The browser needs a page that
TRANSCLUDES the template. This writes two, on the local wiki only:

    ארגז חול/טאבים/לפני   -> {{the original}}
    ארגז חול/טאבים/אחרי   -> {{the converted sandbox}}
"""
import argparse
import sys

sys.path.insert(0, 'infra/tabs')

from verify_tabs import SANDBOX_SUFFIX, write_local  # noqa: E402

BEFORE = 'ארגז חול/טאבים/לפני'
AFTER = 'ארגז חול/טאבים/אחרי'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('title', help='the ORIGINAL template title')
    parser.add_argument('--parameters', default='',
                        help='parameters to pass, e.g. "|עונה=2021/22"')
    options = parser.parse_args()

    original = options.title.removeprefix('תבנית:')
    converted = original + SANDBOX_SUFFIX

    write_local(BEFORE, '{{%s%s}}' % (original, options.parameters))
    write_local(AFTER, '{{%s%s}}' % (converted, options.parameters))

    print(f'{BEFORE}  -> {{{{{original}}}}}')
    print(f'{AFTER}  -> {{{{{converted}}}}}')


if __name__ == '__main__':
    main()
