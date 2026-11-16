"""Test-only loopback browser fixture. Never starts production connector code."""
import argparse
import os
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from backend.gui_test.connector.preview import MockConnector
from backend.gui_test.connector.web import BrowserUI
from backend.gui_test.connector.web_actions import PreviewActions
from backend.gui_test.core.models import TestError


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);args=parser.parse_args()
    origin='http://127.0.0.1:'+str(args.port)
    with tempfile.TemporaryDirectory(prefix='connector-web-fixture-') as directory:
        home=Path(directory)
        app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        ui=BrowserUI(PreviewActions(MockConnector(home)),origin)
        @app.middleware('http')
        async def guard(request,call_next):
            if request.url.path=='/fixture-ticket':
                if request.client.host!='127.0.0.1' or not secrets.compare_digest(request.headers.get('x-test-driver',''),os.environ['CONNECTOR_FIXTURE_KEY']):
                    return JSONResponse({},status_code=403)
                if request.headers.get('x-test-reset')=='true':
                    ui.actions.adapter=MockConnector(home)
                return JSONResponse(ui.ticket())
            return await ui.guard(request,call_next)
        @app.exception_handler(TestError)
        async def error(request,exc):return JSONResponse({'code':exc.code,'message':exc.message},status_code=exc.status)
        ui.routes(app)
        uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning')


if __name__=='__main__':main()
