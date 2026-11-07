"""Controlled local acceptance evidence. No real exchange recording is supplied."""
import json
from pathlib import Path
from app.research_replay.importers import ImportAssertions, import_file
from app.research_replay.validation import validate_bytes
from test_phase162_replay import capture


def dataset(kind="complete", market="BTC"):
    options = dict(market=market, native=market == "BTC" and kind != "crossing")
    if kind in ("gap", "generation"):
        options.update(times=(0, .2, 2, 2.2), gaps=((.2, 2, "OBSERVER_RESTART" if kind == "generation" else "DISCONNECT"),))
        if kind == "generation":
            options["generations"] = (1, 1, 2, 2)
    elif kind == "missing":
        options["partial"] = {i: {"mark_price": "60000"} for i in range(4)}
    else:
        options["times"] = (0, .000001, .000002, .000003) if market == "ETH" and kind == "complete" else (0, .1, .2, .3)
    value = capture(**options).model_dump(mode="json")
    value.update(dataset_id=f"{market}-{kind}-fixture", dataset_fingerprint=None)
    value["source"]["source_id"] = f"local-acceptance:{market}:{kind}"
    # Market-scaled, retained multi-level books; BTC's recorded label is a user
    # assertion on generated values, never a genuine recording acceptance claim.
    price = {"BTC": 60000, "ETH": 3000, "SOL": 150}[market]
    for index, point in enumerate(value["observations"]):
        if kind == "crossing": price = {"BTC":60000,"ETH":3000,"SOL":150}[market] * (100 + (0, 4, -4, 5)[index//2]) // 100
        if point["kind"] == "L2":
            point["order_book"] = dict(bids=[dict(price=str(price-i), size="0.25", order_count=2) for i in range(3)],
                asks=[dict(price=str(price+1+i), size="0.5", order_count=3) for i in range(3)], truncated=True)
        else:
            ctx = point["perp_context"]
            for key in ("mark_price", "oracle_price"):
                if key in ctx and ctx[key] is not None: ctx[key] = str(price)
    return validate_bytes(json.dumps(value).encode())


def admit(vault, incoming, value):
    """Exercise the existing explicit importer before private storage admission."""
    incoming = Path(incoming)
    incoming.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = value.dataset_id + ".json"
    (incoming / name).write_text(value.model_dump_json())
    imported = import_file(incoming, name, assertions=ImportAssertions(market=f"{value.market}-PERP",
        source_id=value.source.source_id, source_kind=value.source.source_kind, permitted_use=True))
    return vault.save(imported)
