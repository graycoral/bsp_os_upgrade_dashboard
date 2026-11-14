"""Choose preview isolation before importing any production adapter."""
import argparse
import os
from pathlib import Path
import sys
import tempfile


def bootstrap_error(home, exc):
    from .logs import logger, redact
    logger(home).error('GUI_BOOTSTRAP_FAILED %s: %s',type(exc).__name__,redact(str(exc)))
    message='보드 커넥터를 시작하지 못했습니다. '+redact(str(exc))+'\n로그: '+str(Path(home)/'logs')
    if os.name=='nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,message,'보드 커넥터',0x10)
    if sys.stderr: print(message,file=sys.stderr)
    return 2


def main(argv=None):
    parser=argparse.ArgumentParser(description='보드 커넥터')
    parser.add_argument('--preview',action='store_true');parser.add_argument('--home')
    parser.add_argument('--ui', choices=('browser', 'qt'), default='browser')
    args=parser.parse_args(argv)
    temporary=None
    if args.preview:
        temporary=tempfile.TemporaryDirectory(prefix='test-board-connector-preview-')
        home=Path(temporary.name)
        if args.ui == 'qt':
            from .preview import MockConnector,install_guard
            adapter=MockConnector(home);install_guard()
    else: home=Path(args.home) if args.home else Path.home()/'.bsp-dashboard'/'windows'
    try:
        if args.ui == 'browser':
            from .web import open_browser, run_preview
            if args.preview:
                run_preview(home)
            else:
                from .supervisor import ensure_manager
                client = ensure_manager(home)
                open_browser(client.browser_ticket()['url'])
            return 0
        # Missing Qt fails visibly before starting a manager or touching production settings.
        from PySide6.QtWidgets import QApplication
        from .gui import ConnectorWindow
        if not args.preview:
            from .supervisor import ensure_manager
            adapter=ensure_manager(home)
        app=QApplication(sys.argv[:1]);app.setApplicationName('보드 커넥터')
        window=ConnectorWindow(adapter);window.show()
        return app.exec()
    except Exception as exc:
        return bootstrap_error(home,exc)
    finally:
        if temporary:temporary.cleanup()


if __name__=='__main__':raise SystemExit(main())
