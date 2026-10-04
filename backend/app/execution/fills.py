from .models import Fill


class FillStore:
    def __init__(self): self._fills: list[Fill]=[]
    def add(self, fill: Fill): self._fills.append(fill)
    def all(self) -> list[Fill]: return list(self._fills)
