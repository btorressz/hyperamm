from fastapi import Request
from app.runtime import HyperAmmRuntime


def runtime(request: Request) -> HyperAmmRuntime:
    return request.app.state.runtime
