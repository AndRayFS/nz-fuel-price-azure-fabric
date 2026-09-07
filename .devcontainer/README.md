# `.devcontainer/` — the environment, buildable by someone other than one Mac

Python 3.12 to match the pinned lock, plus the Azure CLI: `export_panel.py`,
`pipeline/fabric_io.py` and the freshness gate all authenticate with a CLI
token, so a container without `az` can run the offline half of the project
and nothing else.

## Not yet built, and that is a real caveat

Written 7 Sep 2026 against a machine with no Docker installed — deliberately,
since the project runs on a venv rather than in a container. So this file is
**a specification that has never been executed**. Two things are most likely
to need a fix on the first real build:

- **`mssql-python` on Linux.** It ships its own ODBC driver
  (`mssql-python-odbc`) and needs no system unixODBC on macOS. Whether the
  Debian wheel behaves the same way is untested. If `import mssql_python`
  fails in the container, that is the first thing to look at.
- **`~/.dbt/profiles.yml` does not exist in a fresh container.** The host's
  profile is not mounted, so `dbt debug` will fail until one is provided.
  `DBT_PROFILES_DIR` above points at a `.dbt/` folder inside the workspace,
  which is **not in the repository** — the profile carries a warehouse
  endpoint and is not committed. Copy yours in, or wait for W8, which moves
  the profile into the repo behind `env_var()` for exactly this reason.

`az login` still has to be run by hand inside the container, and its token
does not survive a rebuild.
