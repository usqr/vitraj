"""
vitraj's build commands. Usage: python build.py <command>

PyInstaller makes the app. See src/build/python/build_impl/freeze.py.
"""
from argparse import ArgumentParser
from os.path import dirname, join

import sys

_PROJECT_DIR = dirname(__file__) or '.'
sys.path[:0] = [
	join(_PROJECT_DIR, 'src', 'build', 'python'),
	join(_PROJECT_DIR, 'src', 'main', 'python')
]

from build_impl import commands # noqa: E402 (needs the sys.path above)

def main(argv=None):
	parser = ArgumentParser(prog='build.py', description=__doc__.strip())
	subparsers = parser.add_subparsers(dest='command', required=True)
	for name, (fn, help_text) in commands.get_commands().items():
		subparsers.add_parser(name, help=help_text).set_defaults(fn=fn)
	parser.add_argument(
		'--release', action='store_true',
		help='Also load src/build/settings/release.json'
	)
	args = parser.parse_args(argv)
	commands.init(release=args.release)
	return args.fn()

if __name__ == '__main__':
	sys.exit(main() or 0)
