"""Authenticated advisory-analysis transport; never a TC execution endpoint."""
from fastapi import APIRouter, Request
from pydantic import Field
from ..core.models import StrictModel, TestError
from ..core.failure_analysis import AnalysisResult


class Claim(StrictModel):
    consumer: str = Field(min_length=1, max_length=100)
    lease_seconds: int = Field(default=60, strict=True, ge=1, le=600)


class Requeue(StrictModel):
    expected_version: int = Field(strict=True, ge=1)


class Submission(StrictModel):
    lease_token: str = Field(min_length=1, max_length=100)
    result: AnalysisResult


def create_router(manager):
    api = APIRouter(prefix='/api/v1/gui-test/live/integration/analyses')

    def principal(request):
        value = getattr(request.state, 'gui_principal', None)
        if not value:
            raise TestError('Authenticated plugin principal required', 'CONTROL_REQUIRED', 401)
        return value

    @api.get('')
    def analyses(request: Request):
        return {'analyses': manager.analysis.list(principal(request))}

    @api.get('/runtime')
    def runtime_status(request: Request):
        principal(request)
        automation = getattr(manager, 'analysis_runtime', None)
        return automation.status() if automation else {'state':'EXTERNAL', 'mode':'external'}

    @api.get('/{identity}')
    def analysis(identity: str, request: Request):
        return manager.analysis.get(identity, principal(request))

    @api.post('/claim')
    def claim(body: Claim, request: Request):
        return {'analysis': manager.analysis.claim(principal(request), body.consumer, body.lease_seconds)}

    @api.post('/{identity}/submit')
    def submit(identity: str, body: Submission, request: Request):
        return manager.analysis.submit(identity, principal(request), body.lease_token, body.result.model_dump())

    @api.post('/{identity}/requeue')
    def requeue(identity: str, body: Requeue, request: Request):
        return manager.analysis.requeue(identity, principal(request), body.expected_version)

    return api
