"""Launch the source app with its explicit asset directory from any CWD."""
from pathlib import Path
import sys


def main(argv=None):
    app_root = Path(__file__).resolve().parent
    source_root = app_root.parents[1]
    sys.path.insert(0, str(source_root))
    from backend.gui_test.standalone.cli import main as cli_main
    arguments = list(sys.argv[1:] if argv is None else argv)
    # The source app owns assets; the reusable backend never discovers apps/.
    if '--static-dir' not in arguments and not any(arg.startswith('--static-dir=') for arg in arguments):
        arguments.extend(['--static-dir', str(app_root / 'static')])
    return cli_main(arguments)


if __name__ == '__main__':
    main()
