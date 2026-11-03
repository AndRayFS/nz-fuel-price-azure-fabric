"""Validate every PBIR JSON file under a report folder against the schema it names.
Schemas are fetched once and cached; $refs to other schema URLs are resolved the same way."""
import json, sys, pathlib, urllib.request, hashlib
from jsonschema import Draft7Validator
from referencing import Registry, Resource

CACHE = pathlib.Path(sys.argv[2])
def fetch(uri):
    p = CACHE / (hashlib.sha1(uri.encode()).hexdigest() + ".json")
    if not p.exists():
        with urllib.request.urlopen(uri, timeout=30) as r:
            p.write_bytes(r.read())
    return json.loads(p.read_text())

registry = Registry(retrieve=lambda uri: Resource.from_contents(fetch(uri)))
bad = 0; n = 0
for f in sorted(pathlib.Path(sys.argv[1]).rglob("*.json")):
    doc = json.loads(f.read_text())
    uri = doc.get("$schema") if isinstance(doc, dict) else None
    if not uri:
        continue
    n += 1
    v = Draft7Validator(fetch(uri), registry=registry)
    errs = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
    for e in errs[:5]:
        bad += 1
        print(f"{f.relative_to(sys.argv[1])}: {'/'.join(map(str, e.path))}: {e.message[:200]}")
print(f"{n} files checked, {bad} errors")
sys.exit(1 if bad else 0)
