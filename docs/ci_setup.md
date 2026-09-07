# Setting up the CI identity — the part that cannot be committed

Everything else in W8 is a file in this repository. This is the part that is
state in Azure and in Fabric, done once, by hand, by someone holding the
rights. Written 7 Sep 2026, verified against the live subscription where it
says *checked*; the steps that create things were not run — that is the
person doing the setup.

**Three permission planes, and they do not overlap.** This is the thing most
likely to waste an afternoon: an identity can be perfectly able to drive
Fabric and still unable to wake the capacity, because those are different
systems with different grants.

| plane | what it governs | granted where |
|---|---|---|
| Azure RBAC (ARM) | resume / suspend the capacity resource | subscription → the capacity |
| Fabric | reading and running items in the workspace | Fabric workspace roles + a tenant switch |
| SQL | tables in `analytics_warehouse` | `create user … from external provider` in the warehouse |

The signed-in human has all three today only because they hold `Contributor`
on the whole subscription (*checked*). A service principal inherits none of
that.

## 1. The app registration and its federated credentials

No client secret anywhere: GitHub mints a short-lived OIDC token per run and
Entra trusts it for this repository only.

```bash
az ad app create --display-name nz-fuel-ci
APP_ID=$(az ad app list --display-name nz-fuel-ci --query '[0].appId' -o tsv)
az ad sp create --id "$APP_ID"

# One credential per subject. The scheduled run and a manual dispatch both
# come from the branch, so this single subject covers them; a run from a pull
# request or another branch would need its own and deliberately does not have
# one.
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:AndRayFS/nz-fuel-price-azure-fabric:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

## 2. Azure RBAC on the capacity — the grant that is easy to miss

`Microsoft.Fabric/capacities/resume/action` and `.../suspend/action` are ARM
operations (*checked* against `az provider operation show --namespace
Microsoft.Fabric`). Nothing in the Fabric workspace grants them.

The two Logic App identities that already exist — `auto-pause-fabric-capacity`
and `auto-resume-fabric-capacity` — hold `Contributor` on the entire resource
group (*checked*), which is far more than either needs. Do not copy that
pattern for CI. A role with exactly three operations, scoped to the one
resource:

```bash
SUB=e30d2fa4-fb6e-48c5-b3cd-5f9c3f270159
CAP=/subscriptions/$SUB/resourceGroups/nz-fuel-price-rg/providers/Microsoft.Fabric/capacities/nzfuelcapacity

cat > /tmp/capacity-operator.json <<JSON
{
  "Name": "Fabric Capacity Operator",
  "Description": "Read, resume and suspend one Fabric capacity. Nothing else.",
  "Actions": [
    "Microsoft.Fabric/capacities/read",
    "Microsoft.Fabric/capacities/resume/action",
    "Microsoft.Fabric/capacities/suspend/action"
  ],
  "AssignableScopes": ["$CAP"]
}
JSON

az role definition create --role-definition /tmp/capacity-operator.json
az role assignment create --assignee "$APP_ID" \
  --role "Fabric Capacity Operator" --scope "$CAP"
```

## 3. Fabric — the tenant switch and the workspace role

Both in the Fabric portal, neither reachable from `az`:

- **Tenant setting:** admin portal → Developer settings → *Service principals
  can use Fabric APIs*. Without it every call in `fabric_io.py` and
  `run_ingest.py` returns 401 no matter what else is granted. Restrict it to a
  security group containing this one app rather than enabling it tenant-wide.
- **Workspace role:** `nz-fuel-price-project`
  (`bc2e3801-9a54-4154-9f46-2a9dc442cad7`) → Manage access → add the app as
  **Contributor**. Member and Admin are more than the weekly chain needs;
  Viewer cannot start the pipeline.

## 4. The warehouse

Fabric workspace roles reach the item, not the SQL engine inside it. Once, in
a query window on `analytics_warehouse`:

```sql
create user [nz-fuel-ci] from external provider;
alter role db_owner add member [nz-fuel-ci];
```

`db_owner` because the chain creates and drops tables on every
`--full-refresh` and writes `pipeline.processed_weeks`. Narrower grants are
possible and would need revisiting every time a schema is added.

## 5. GitHub

Repository → Settings → Secrets and variables → Actions:

| secret | value |
|---|---|
| `AZURE_CLIENT_ID` | the `appId` from step 1 |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | `e30d2fa4-fb6e-48c5-b3cd-5f9c3f270159` |

None of the three is a credential — they identify, they do not authenticate;
the authentication is the OIDC exchange. The subscription id is already
public in this repository. They are secrets only because that is where
workflow inputs live.

## 6. Proving it works, cheaply

Run the workflow by hand with **skip_ingest = true** on a week that is already
loaded. The gate then answers `2` (nothing new), the job ends green having
touched nothing, and the run has still exercised every grant that matters:
OIDC exchange, resume, a Fabric API call, a warehouse query, and pause.

Once it is green, **turn the schedule on**: uncomment the two `schedule`
lines at the top of `.github/workflows/weekly.yml`. It ships disabled so that
a repository without the identity does not go red every Wednesday.

If it fails, the plane is usually readable from the error:

| error | plane | fix |
|---|---|---|
| `AADSTS700213` / no matching federated credential | Entra | the subject in step 1 does not match the branch or event |
| `AuthorizationFailed` on resume | ARM | step 2 |
| Fabric API 401 | Fabric | tenant switch or workspace role, step 3 |
| `Login failed for user '<token-identified principal>'` | SQL | step 4 |
| `this Fabric capacity is currently not active` | none — timing | the resume returned before the capacity was Active; `task capacity-resume` waits, so this means the wait was skipped |
