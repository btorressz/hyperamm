class KillSwitch:
    def __init__(self, risk_status): self.status=risk_status
    async def activate(self, execution, reason="manual kill switch"):
        self.status.kill_switch_active=True; self.status.last_reason=reason
        await execution.cancel_all()
    def resume(self):
        self.status.kill_switch_active=False; self.status.last_reason=None
