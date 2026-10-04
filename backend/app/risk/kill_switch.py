import asyncio


class KillSwitch:
    def __init__(self, risk_status, lock=None):
        self.status=risk_status
        self.lock=lock if lock is not None else asyncio.Lock()

    async def activate(self, execution, reason="manual kill switch"):
        # Revoke authority before waiting for an in-flight transmission to finish.
        self.status.kill_switch_active=True
        self.status.last_reason=reason
        async with self.lock:
            await execution.cancel_all()

    def resume(self):
        self.status.kill_switch_active=False
        self.status.last_reason=None
