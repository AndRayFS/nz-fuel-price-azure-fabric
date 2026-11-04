"""Publish pbip/ over the live Report 1 in My Workspace - nz_fuel_v2, its report and its
semantic model - in place, without Power BI Desktop.

The same mechanism as to_dev.py (Fabric REST updateDefinition, as the signed-in az
account that owns My Workspace), with the targets fixed by id: the public link hangs
on the report's id and refresh_report_1 on the model's, so this never creates an
item, and stops if either id is gone or no longer named nz_fuel_v2. Each item's
current definition is saved first (getDefinition) under --backup, so a publish can
be put back by publishing that folder the same way.

Approved by the owner on 5 Nov 2026 in place of the Desktop republish. Afterwards,
with the capacity up, run `task refresh`: a change to measures or visuals keeps the
model's data, a new table or column needs the refresh.

Usage: python pbip/build/to_live.py --backup DIR [model] [report]
       (no parts named = both)
"""
import base64, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import to_dev as D

NAME = "nz_fuel_v2"
LIVE = {"SemanticModel": ("semanticModels", D.LIVE_MODEL, "?format=TMDL"),
        "Report": ("reports", "c31bf57c-86a4-40cb-908e-ea49ae773a2e", "")}

def check(ws, kind):
    collection, item, _ = LIVE[kind]
    _, _, it = D.call("GET", f"{D.FABRIC}/workspaces/{ws}/{collection}/{item}")
    if it.get("displayName") != NAME:
        sys.exit(f"{kind} {item} is named {it.get('displayName')!r}, not {NAME!r}: nothing published")

def backup(ws, kind, out):
    collection, item, fmt = LIVE[kind]
    res = D.long_running(*D.call("POST", f"{D.FABRIC}/workspaces/{ws}/{collection}/{item}/getDefinition{fmt}"))
    root = out / f"{NAME}.{kind}"
    for part in res["definition"]["parts"]:
        p = root / part["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(base64.b64decode(part["payload"]))
    print(f"{kind} backed up: {len(res['definition']['parts'])} parts in {root}")

def publish(ws, kind, definition):
    collection, item, _ = LIVE[kind]
    D.long_running(*D.call("POST", f"{D.FABRIC}/workspaces/{ws}/{collection}/{item}/updateDefinition",
                           {"definition": definition}))
    print(f"{kind} {NAME} updated in place ({item})")

def main(args):
    if "--backup" not in args:
        sys.exit(__doc__)
    out = pathlib.Path(args[args.index("--backup") + 1])
    which = [a for a in args if a in ("model", "report")] or ["model", "report"]
    _, _, wss = D.call("GET", f"{D.FABRIC}/workspaces")
    ws = next(w["id"] for w in wss["value"] if w["type"] == "Personal")
    for kind in ("SemanticModel", "Report"):
        check(ws, kind)
    for kind in ("SemanticModel", "Report"):
        backup(ws, kind, out)
    if "model" in which:
        publish(ws, "SemanticModel", {"format": "TMDL", "parts": D.parts(D.HERE / f"{NAME}.SemanticModel")})
    if "report" in which:
        def bind(rel, raw):
            if rel != "definition.pbir":
                return raw
            pbir = json.loads(raw)
            pbir["datasetReference"] = {"byConnection": {"connectionString":
                f'Data Source="powerbi://api.powerbi.com/v1.0/myorg/My workspace";initial catalog={NAME};'
                f"integrated security=ClaimsToken;semanticmodelid={D.LIVE_MODEL}"}}
            return json.dumps(pbir, indent=2).encode()
        publish(ws, "Report", {"format": "PBIR", "parts": D.parts(D.HERE / f"{NAME}.Report", bind)})

if __name__ == "__main__":
    main(sys.argv[1:])
