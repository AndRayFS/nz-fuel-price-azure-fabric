"""Check Now's title in DAX against its Python mirror, headline_check.py, for every week.

Two texts per `As Of` week, from one read-only query (POST executeQueries):
  model    - the published model's own [Headline];
  worktree - the Headline in this worktree's prices.tmdl, declared in the query with
             DEFINE MEASURE, so a changed measure is checked before it is published.
Each is compared with the mirror run over the archive's CSVs. Before a publish the
model's text matches the old mirror, not this one; after it, both should match.
No capacity is needed: the model is imported and lives in My Workspace.

Usage: python pbip/build/headline_dax_check.py ARCHIVE_DIR [MODEL_ID]
       ARCHIVE_DIR - an unpacked nz-fuel zip from the same load as the model's data;
       MODEL_ID    - default the live nz_fuel_v2 model.
"""
import pathlib, re, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import to_dev as D
import headline_check as H

def worktree_measure():
    text = (HERE.parent / "nz_fuel_v2.SemanticModel/definition/tables/prices.tmdl").read_text()
    m = re.search(r"\tmeasure Headline =\n(.*?)\n\t\tdisplayFolder", text, re.S)
    if not m:
        sys.exit("Headline not found in prices.tmdl")
    return m.group(1)

def mirror(price, gap, w):
    a = H.clause_a(price, w)[1] or ""; b = H.clause_b(gap, w)[1] or ""
    return a + (" " if a and b else "") + b

def main(archive, model=D.LIVE_MODEL):
    q = ("DEFINE MEASURE prices[Headline Worktree] =\n" + worktree_measure() +
         "\nEVALUATE ADDCOLUMNS(VALUES('As Of'[As of week]),"
         " \"Model\", [Headline], \"Worktree\", [Headline Worktree])")
    _, _, res = D.call("POST", f"{D.PBI}/datasets/{model}/executeQueries",
                       {"queries": [{"query": q}], "serializerSettings": {"includeNulls": True}})
    r0 = res["results"][0]
    if "error" in r0:
        sys.exit(str(r0["error"])[:1500])
    price, gap = H.load(archive)
    newest = max(price)
    n, ok, bad = 0, {"Model": 0, "Worktree": 0}, []
    for row in r0["tables"][0]["rows"]:
        w = row["As Of[As of week]"][:10]
        if w > newest or w not in price:
            continue
        n += 1; want = mirror(price, gap, w)
        for k in ok:
            if row[f"[{k}]"] == want: ok[k] += 1
            elif len(bad) < 10: bad.append((k, w, row[f"[{k}]"], want))
    print(f"weeks {n} (archive through {newest}) | model = mirror: {ok['Model']} | worktree = mirror: {ok['Worktree']}")
    for k, w, got, want in bad:
        print(f"  {k} {w}\n    dax:    {got}\n    mirror: {want}")

if __name__ == "__main__":
    main(*sys.argv[1:3])
