# Setting up the CI identity — the part that cannot be committed

Everything else in W8 is a file in this repository. This is the part that is
state in Azure and in Fabric, done once, by someone holding the rights.

**Status, 8 Sep 2026: every grant is in place.** Steps 1, 3 and 5 were carried
out and are recorded below with what they produced; step 2 was done by the
Owner account (`andrei@…onmicrosoft.com` is Contributor and cannot grant
roles — `AuthorizationFailed` on `Microsoft.Authorization/roleDefinitions/write`
— so it needs `morozov_77@hotmail.com`, as with the billing upgrade on 3 Sep);
step 4 turned out not to exist. What remains is the run in step 6.

**Signing back in matters.** `az login` as the Owner replaces the cached
session, and everything in this project — dbt, the gate, every script — takes
its token from whoever is signed in. Log back in as the working account
afterwards, or the next run happens as the wrong identity.

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

## 1. The app registration and its federated credentials — **done 8 Sep 2026**

No client secret anywhere: GitHub mints a short-lived OIDC token per run and
Entra trusts it for this repository only.

| what | value |
|---|---|
| application (client) id | `3f465111-2a96-4c64-84f6-88dea76c6562` |
| service principal object id | `bb6f5f28-2bd2-43e6-9c8c-d27830e502ec` |
| tenant id | `66aed129-aced-4829-9701-6b7315675a04` |
| federated credential | `github-main`, subject `repo:AndRayFS/nz-fuel-price-azure-fabric:ref:refs/heads/main` |

Fabric wants the **service principal object id**; `azure/login` and the
secrets want the **application id**. Mixing them up produces a 401 that reads
like a permissions problem. The commands that produced this:

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

## 2. Azure RBAC on the capacity — **NOT DONE, needs the Owner account**

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

# as morozov_77@hotmail.com: Contributor cannot grant roles
APP_ID=3f465111-2a96-4c64-84f6-88dea76c6562

az role definition create --role-definition /tmp/capacity-operator.json
az role assignment create --assignee "$APP_ID" \
  --role "Fabric Capacity Operator" --scope "$CAP"
```

Without this the workflow authenticates fine, drives Fabric fine, and cannot
wake the capacity — which surfaces as every later step failing with `this
Fabric capacity is currently not active`.

## 3. Fabric — the tenant switch and the workspace role — **done 8 Sep 2026**

- **Tenant setting:** *Service principals can call Fabric public APIs* was
  **already enabled**, tenant-wide and with no security-group restriction —
  read back through `GET /v1/admin/tenantsettings`
  (`ServicePrincipalAccessPermissionAPIs`). Narrowing it to a group holding
  only this app would be tighter; leaving it as found is the status quo rather
  than a decision anyone made.
- **Workspace role:** the app is **Contributor** on `nz-fuel-price-project`
  (`bc2e3801-9a54-4154-9f46-2a9dc442cad7`), added through the Fabric REST API
  rather than the portal — which works because the signed-in user is Admin of
  that workspace. Verified by reading the assignments back: `Andrei` Admin,
  `nz-fuel-ci` Contributor. Member and Admin are more than the weekly chain
  needs; Viewer cannot start the pipeline.

## 4. The warehouse — **nothing to do, and the earlier instruction was wrong**

This step used to say: create a contained user from the external provider and
put it in `db_owner`. That is the Azure SQL / Synapse shape, written here from
memory rather than from a test, and Fabric Warehouse rejects it outright —
`CREATE USER is not a supported statement type` (tried 8 Sep 2026).

Fabric does not have SQL principals per identity at all. `sys.database_principals`
on `analytics_warehouse` holds four rows — `dbo`, `guest`, `sys`,
`INFORMATION_SCHEMA` — and no entry even for the human who writes to it daily.
Access comes from the workspace role granted in step 3: a Contributor can read
and write the warehouse's data. There is nothing to grant inside the database.

If finer control is ever wanted, it is item permissions and T-SQL `GRANT` on
existing principals, not `CREATE USER`. The check that this actually works is
the run in step 6, which writes.

## 5. GitHub — **done 8 Sep 2026**

Repository → Settings → Secrets and variables → Actions. All three are set;
`gh secret list` shows them.

| secret | value |
|---|---|
| `AZURE_CLIENT_ID` | `3f465111-2a96-4c64-84f6-88dea76c6562` |
| `AZURE_TENANT_ID` | `66aed129-aced-4829-9701-6b7315675a04` |
| `AZURE_SUBSCRIPTION_ID` | `e30d2fa4-fb6e-48c5-b3cd-5f9c3f270159` |

None of the three is a credential — they identify, they do not authenticate;
the authentication is the OIDC exchange. The subscription id is already
public in this repository. They are secrets only because that is where
workflow inputs live.

## 6. Proving it works, cheaply — **done 8 Sep 2026, and both schedules are on**

The proving run went green end to end on the second attempt, and the two
failures before it were worth more than the success:

- **The subject GitHub actually presents carries numeric ids.** Not
  `repo:AndRayFS/nz-fuel-price-azure-fabric:ref:refs/heads/main` as documented,
  but `repo:AndRayFS@159444042/nz-fuel-price-azure-fabric@1318804218:ref:refs/heads/main`.
  A second federated credential was added for that exact string; the
  documented one is kept in case the format reverts.
- **`task` reports its own exit code, 201, not the command's.** The gate's
  three codes are the entire point of the step, and the workflow's "exit 2 is
  fine" branch could therefore never fire — every quiet week would have gone
  red. Fixed with `task -x`, which passes the code through.

What the green run exercised: OIDC exchange, resume through the ARM role,
`ingest_mbie_weekly` started and polled through the job API, a Fabric API read
and a warehouse query from the gate, and pause. What it did NOT exercise is
everything after the gate — it answered `nothing_new`, correctly, because MBIE
publishes on Wednesdays. First real run of the chain proper: 10 Sep 2026.

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
