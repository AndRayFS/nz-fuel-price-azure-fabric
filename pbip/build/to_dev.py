"""Publish the report from this worktree to a private copy in My Workspace, so a
page can be looked at in the browser without Power BI Desktop.

The copy is a separate pair of items, nz_fuel_w21_dev, never the live nz_fuel_v2:
the semantic model from TMDL, the report from PBIR bound to that model. Both go
through the Fabric REST API (create, or updateDefinition when they exist) as the
signed-in az account, which owns My Workspace; a service principal could not.

A new or changed model holds no data until it is refreshed. --refresh binds it to
the warehouse's ShareableCloud connection (the one the live model uses), wakes
the capacity if it is paused, refreshes, and pauses the capacity again only if
this script woke it - a running weekly chain is never paused from here.

Usage: python pbip/build/to_dev.py [model] [report] [--refresh]
       (no parts named = both)
"""
import base64, json, pathlib, subprocess, sys, time, urllib.error, urllib.request

HERE = pathlib.Path(__file__).resolve().parents[1]           # worktree pbip/
SRC, DEV = "nz_fuel_v2", "nz_fuel_w21_dev"
LIVE_MODEL = "221ea91d-5855-4c0c-a5da-4c4af0a2650a"          # only read, for its connection
CAPACITY = ("/subscriptions/e30d2fa4-fb6e-48c5-b3cd-5f9c3f270159/resourceGroups/nz-fuel-price-rg"
            "/providers/Microsoft.Fabric/capacities/nzfuelcapacity")
FABRIC, PBI = "https://api.fabric.microsoft.com/v1", "https://api.powerbi.com/v1.0/myorg"
SKIP = {".platform", "localSettings.json", "cache.abf", ".DS_Store"}

def az(*args):
    return subprocess.run(["az", *args], check=True, capture_output=True, text=True).stdout.strip()

TOKENS = {}
def token(resource):
    if resource not in TOKENS:
        TOKENS[resource] = az("account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv")
    return TOKENS[resource]

def call(method, url, body=None):
    """One HTTP call; returns (status, headers, parsed body or None)."""
    resource = "https://api.fabric.microsoft.com" if url.startswith(FABRIC) else "https://analysis.windows.net/powerbi/api"
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Bearer " + token(resource), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, r.headers, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url} -> {e.code}: {e.read().decode()[:600]}")

def long_running(status, headers, body):
    """Follow a Fabric long-running operation to its end; returns its result, if any."""
    if status != 202:
        return body
    op = headers["x-ms-operation-id"]
    while True:
        time.sleep(int(headers.get("Retry-After", 5)))
        _, headers, st = call("GET", f"{FABRIC}/operations/{op}")
        if st["status"] in ("Succeeded", "Failed"):
            break
    if st["status"] == "Failed":
        sys.exit(f"operation {op} failed: {st.get('error')}")
    _, _, result = call("GET", f"{FABRIC}/operations/{op}/result") if headers.get("Location") else (None, None, None)
    return result

def parts(root, rewrite=None):
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name in SKIP or ".pbi" in p.relative_to(root).parts:
            continue
        rel = p.relative_to(root).as_posix()
        raw = rewrite(rel, p.read_bytes()) if rewrite else p.read_bytes()
        out.append({"path": rel, "payload": base64.b64encode(raw).decode(), "payloadType": "InlineBase64"})
    return out

def find(ws, kind):
    _, _, items = call("GET", f"{FABRIC}/workspaces/{ws}/items?type={kind}")
    return next((i["id"] for i in items["value"] if i["displayName"] == DEV), None)

def push(ws, kind, collection, definition):
    item = find(ws, kind)
    if item:
        long_running(*call("POST", f"{FABRIC}/workspaces/{ws}/{collection}/{item}/updateDefinition", {"definition": definition}))
        print(f"{kind} {DEV} updated ({item})")
    else:
        long_running(*call("POST", f"{FABRIC}/workspaces/{ws}/{collection}", {"displayName": DEV, "definition": definition}))
        item = find(ws, kind)
        print(f"{kind} {DEV} created ({item})")
    return item

def capacity_state():
    return az("resource", "show", "--ids", CAPACITY, "--query", "properties.state", "-o", "tsv")

def refresh(model):
    _, _, live = call("GET", f"{PBI}/datasets/{LIVE_MODEL}/datasources")
    src = live["value"][0]
    _, _, mine = call("GET", f"{PBI}/datasets/{model}/datasources")
    if not mine["value"] or mine["value"][0].get("gatewayId") != src["gatewayId"]:
        call("POST", f"{PBI}/datasets/{model}/Default.BindToGateway",
             {"gatewayObjectId": src["gatewayId"], "datasourceObjectIds": [src["datasourceId"]]})
        print("bound to the warehouse connection")
    woke = capacity_state() != "Active"
    if woke:
        print("resuming the capacity - NZ$0.729/hour from now")
        az("resource", "invoke-action", "--ids", CAPACITY, "--action", "resume")
        while capacity_state() != "Active":
            time.sleep(15)
    try:
        call("POST", f"{PBI}/datasets/{model}/refreshes", {"type": "Full", "retryCount": 0})
        while True:
            time.sleep(10)
            _, _, h = call("GET", f"{PBI}/datasets/{model}/refreshes?$top=1")
            last = h["value"][0]
            if last["status"] != "Unknown":
                break
        print("refresh", last["status"], last.get("serviceExceptionJson", ""))
    finally:
        if woke:
            az("resource", "invoke-action", "--ids", CAPACITY, "--action", "suspend")
            print("capacity paused again")

def main(args):
    which = [a for a in args if a in ("model", "report")] or ["model", "report"]
    _, _, wss = call("GET", f"{FABRIC}/workspaces")
    ws = next(w["id"] for w in wss["value"] if w["type"] == "Personal")
    model = find(ws, "SemanticModel")
    if "model" in which:
        model = push(ws, "SemanticModel", "semanticModels",
                     {"format": "TMDL", "parts": parts(HERE / f"{SRC}.SemanticModel")})
    if not model:
        sys.exit("no dev model yet: publish the model first")
    if "--refresh" in args:
        refresh(model)
    if "report" in which:
        def bind(rel, raw):
            if rel != "definition.pbir":
                return raw
            pbir = json.loads(raw)
            pbir["datasetReference"] = {"byConnection": {"connectionString":
                f'Data Source="powerbi://api.powerbi.com/v1.0/myorg/My workspace";initial catalog={DEV};'
                f"integrated security=ClaimsToken;semanticmodelid={model}"}}
            return json.dumps(pbir, indent=2).encode()
        report = push(ws, "Report", "reports", {"format": "PBIR", "parts": parts(HERE / f"{SRC}.Report", bind)})
        print(f"https://app.powerbi.com/groups/me/reports/{report}/p1now")

if __name__ == "__main__":
    main(sys.argv[1:])
