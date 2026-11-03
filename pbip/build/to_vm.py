"""Copy the report from this worktree to the folder the Windows VM sees, renamed.

The VM's shared folder is the main checkout's pbip/; the copy goes into its
own folder there, w21/, named nz_fuel_w21, away from the published nz_fuel_v2,
and gets its own display name and logical ids, so a stray publish from it
would create a separate item rather than overwrite the live report.

Refuses to overwrite a copy that Desktop has saved into since the last sync:
those edits have to come back here first.

Usage: python pbip/build/to_vm.py [--force]
"""
import json, pathlib, shutil, sys, uuid

HERE = pathlib.Path(__file__).resolve().parents[1]           # worktree pbip/
VM = pathlib.Path("/Users/Ray/nz-fuel-price-project/nz_fuel_price_project/pbip/w21")
SRC, DST = "nz_fuel_v2", "nz_fuel_w21"
STAMP = VM / f".{DST}.synced"
KEEP = {"localSettings.json", "cache.abf", ".DS_Store"}       # Desktop's own, never overwritten or deleted

def files(root):
    return [p for p in root.rglob("*") if p.is_file() and p.name not in KEEP]

def main(force=False):
    VM.mkdir(exist_ok=True)
    targets = [VM / f"{DST}.Report", VM / f"{DST}.SemanticModel", VM / f"{DST}.pbip"]
    if STAMP.exists() and not force:
        t = STAMP.stat().st_mtime
        changed = [p for d in targets if d.exists()
                   for p in ([d] if d.is_file() else files(d)) if p.stat().st_mtime > t + 1]
        if changed:
            print("Desktop has saved into the copy since the last sync; bring these back first:")
            for p in changed[:20]: print("  ", p.relative_to(VM))
            sys.exit(1)
    for kind in ("Report", "SemanticModel"):
        src, dst = HERE / f"{SRC}.{kind}", VM / f"{DST}.{kind}"
        if dst.exists():
            for p in files(dst): p.unlink()
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*KEEP))
        plat = json.loads((dst / ".platform").read_text())
        plat["metadata"]["displayName"] = DST
        plat["config"]["logicalId"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DST}.{kind}"))
        (dst / ".platform").write_text(json.dumps(plat, indent=2) + "\n")
    pbir = VM / f"{DST}.Report/definition.pbir"
    pbir.write_text(pbir.read_text().replace(f"../{SRC}.SemanticModel", f"../{DST}.SemanticModel"))
    pbip = json.loads((HERE / f"{SRC}.pbip").read_text())
    pbip["artifacts"][0]["report"]["path"] = f"{DST}.Report"
    (VM / f"{DST}.pbip").write_text(json.dumps(pbip, indent=2) + "\n")
    STAMP.write_text("synced\n")
    print(f"copied to {VM / (DST + '.pbip')}")

if __name__ == "__main__":
    main(force="--force" in sys.argv)
