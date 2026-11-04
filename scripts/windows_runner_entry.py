"""Restricted, lazy entry point for the portable Windows Runner executable."""
import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    # The frozen interpreter can retain the Windows legacy code page even when
    # PYTHONUTF8 is supplied externally. Own our user-facing text/log encoding;
    # contained children inherit raw OS handles and keep their own TC encoding.
    if getattr(sys, 'frozen', False) and not (args and args[0] == '--contained-child'):
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    if args and args[0] == '--contained-child':
        if len(args) < 3 or args[1] != '--' or not args[2]:
            print('Usage: --contained-child -- executable [arguments]', file=sys.stderr)
            return 2
        from gui_test.execution.bundle import contained_child
        return contained_child(args[2:])
    if args and args[0] == '--runner':
        from gui_test.execution.host import main as runner_main
        return runner_main(args[1:])
    from scripts.setup_runtime import main as setup_main
    return setup_main(args)


if __name__ == '__main__':
    raise SystemExit(main())
