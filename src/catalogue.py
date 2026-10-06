"""Shared catalogue. Historical aliases are matched without rewriting saved records."""
import json
from pathlib import Path
CATALOGUE = json.loads(Path(__file__).with_name("production_catalogue.json").read_text(encoding="utf-8"))

def canonical(field, value):
    if value is None:
        return None
    names = CATALOGUE["products" if field == "product" else "customers"] if field != "shift" else [r["name"] for r in CATALOGUE["shifts"]]
    mapping = {v.casefold(): v for v in names}
    mapping.update({k.casefold(): v for k,v in CATALOGUE["aliases"][field].items()})
    return mapping.get(value.strip().casefold(), value.strip())

def aliases(field, value):
    target = canonical(field, value)
    return sorted({target.casefold()} | {k.casefold() for k,v in CATALOGUE["aliases"][field].items() if v == target})
