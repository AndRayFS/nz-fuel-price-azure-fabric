# Setting up the CI identity — the part that cannot be committed

Everything else in W8 is a file in this repository. This is the part that is
state in Azure and in Fabric, done once, by someone holding the rights.

**Status, 8 Sep 2026: every grant is in place.** Steps 1, 3 and 5 were carried
out and are recorded below with what they produced; step 2 was done by the
Owner account (`andrei@…onmicrosoft.com` is Contributor and cannot grant
roles — `AuthorizationFailed` on `Microsoft.Authorization/roleDefinitions/write`
— so it needs `morozov_77@hotmail.com`, as with the billing upgrade on 3 Sep);
step 4 turned out not to exist. Step 6 has since been run many times over:
the chain has gone through unattended on a schedule, most recently 16 Sep 2026.
Step 7, which moves the trigger off that schedule, was added on 19 Sep 2026 and
its two by-hand steps are still outstanding.

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

## 2. Azure RBAC on the capacity — **done 8 Sep 2026 by the Owner account**

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

Run the workflow by hand with **skip_ingest = true** on a week that is already
loaded. The gate then answers `2` (nothing new), the job ends green having
touched nothing, and the run has still exercised every grant that matters:
OIDC exchange, resume, a Fabric API call, a warehouse query, and pause.

The two `schedule` blocks — `weekly.yml` and the watchdog in
`pause-capacity.yml` — went live on 8 Sep 2026, switched on once that run was
green. They were kept commented out until then, so that a repository without
the identity behind it did not go red every Wednesday. Turning them on is the
last step of this document, not the first. Neither cron starts the load any
more: step 7 moved the trigger to a Logic App, `weekly.yml`'s schedule is gone
altogether, and the watchdog's is now belt and braces behind a `workflow_run`
event.

**What the proving run found.** It went green end to end on the second
attempt, and the two failures before it were worth more than the success:

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

If it fails, the plane is usually readable from the error:

| error | plane | fix |
|---|---|---|
| `AADSTS700213` / no matching federated credential | Entra | the subject in step 1 does not match the branch or event |
| `AuthorizationFailed` on resume | ARM | step 2 |
| Fabric API 401 | Fabric | tenant switch or workspace role, step 3 |
| `Login failed for user '<token-identified principal>'` | SQL | step 4 |
| `this Fabric capacity is currently not active` | none — timing | the resume returned before the capacity was Active; `task capacity-resume` waits, so this means the wait was skipped |

**A change to CI cannot be tested on a branch.** The credential's subject names
`refs/heads/main`, so a run from any other ref fails at `azure/login` with
`AADSTS700213` before it reaches the capacity — verified on run 34424623434,
which cost nothing because every step after the login was skipped. Workflow
edits therefore land on `main` and are proven there, which makes it worth
having something cheap to prove them with.

`pause-capacity.yml` is that something. On a button it runs `checkout` and
`azure/login`, reads the capacity state and stops when it is already paused —
no ingest, no warehouse, and nothing woken. It exercises the OIDC exchange and
the ARM read, which is most of what a workflow edit can break. Used that way
on 17 Sep 2026 to prove `azure/login@v3` before the weekly load met it: run
35169892649, 12 seconds.

## 7. Moving the clock off GitHub's scheduler — **done 19 Sep 2026, and proven the same hour**

**Status.** All three by-hand steps below were carried out on 19 Sep 2026 and
a hand-fired recurrence went green end to end: run 35423341610,
`workflow_dispatch`, 3.5 minutes, gate `2`, capacity back to `Paused` — and
behind it run 35423507593, the watchdog, triggered by `workflow_run` for the
first time. What has still never happened is the recurrence firing on its own
— the first one, on 24 Sep, was skipped, see 7e — and the alarm sending
anything.

W16, steps 1 and 2. The chain stays exactly where it is; what changes is the
thing holding the stopwatch, from GitHub's `schedule` trigger to a Logic App
recurrence that posts a `workflow_dispatch` — and the same Logic App then waits
an hour, asks GitHub what became of the run, and writes to a mailbox if the
answer is anything but success. Why the clock moved, in `weekly.yml`'s own
header: no SLA on one side, a Windows time zone on the other.

**The trigger watches itself because nothing else can.** `weekly.yml` has no
schedule behind it any more, so a dispatch that never lands produces no run, no
red, and no trace anywhere in this repository. The alarm is not an extra: it is
the other half of having one clock.

Nothing in steps 1–5 is touched. The Logic App calls GitHub, not Azure, so it
needs **no managed identity and no Azure role** — do not give it the resource
group `Contributor` the two capacity Logic Apps carry. The credential goes the
other way for the first time in this project: a GitHub token held in Azure,
where everything so far has been an Azure identity held by GitHub.

### 7a. A fine-grained PAT, and its expiry is a dated obligation

github.com → Settings → Developer settings → Personal access tokens →
Fine-grained tokens:

| field | value |
|---|---|
| resource owner | `AndRayFS` |
| repository access | only `nz-fuel-price-azure-fabric` |
| repository permission | **Actions: Read and write** (Metadata: read comes with it) |
| expiry | **No expiration** |

Read as well as write: the same token starts the run and then asks what became
of it. One permission on one repository, and nothing else is readable with it.

**No expiration, deliberately.** This document first said the opposite — a
year, with the date carried as a dated obligation. A token that expires
unnoticed produces exactly the silent non-run this step exists to remove, and
with `weekly.yml`'s backstop cron gone there is nothing behind it, so an expiry
is a scheduled outage with a calendar date on it. What it would buy is rotation
hygiene on a credential whose whole power is starting and cancelling runs in
one public repository with no secrets in it. The reflex replaces the date: if
it leaks, revoke and redeploy. See `.claude/rules/active-items.md`.

A PAT rather than a GitHub App for a different reason: an App needs an RS256
JWT, which a Logic App cannot sign without adding a Function, and the point of
W16 is to move the clock without adding compute.

### 7b. Deploy the Logic App and its mail connection

`infra/logic-apps/trigger-weekly-load.json` declares two resources: the
Consumption workflow, and an `outlook` API connection for the mail. Both land
in `australiaeast`, beside the two capacity Logic Apps. *Checked* 19 Sep 2026:
`az deployment group validate` accepts both.

One line for the read, deliberately — see 7d for what happens when this is
pasted as a block:

```bash
read -rs GH_DISPATCH_TOKEN && export GH_DISPATCH_TOKEN && echo "${#GH_DISPATCH_TOKEN} chars, ${GH_DISPATCH_TOKEN:0:11}"
```

```bash
az deployment group create \
  --resource-group nz-fuel-price-rg \
  --name trigger-weekly-load \
  --template-file infra/logic-apps/trigger-weekly-load.json \
  --parameters githubToken="$GH_DISPATCH_TOKEN"

unset GH_DISPATCH_TOKEN
```

`githubToken` is a `securestring` in three places at once, which is what keeps
it out of everything readable afterwards: the deployment history does not store
its value, a `GET` on the workflow returns it masked, and `secureData` on both
HTTP actions hides the run inputs that carry it.

### 7c. Authorise the mail connection, which only the portal can do

The deployment creates the connection but cannot consent on a mailbox's behalf.
Portal → `nz-fuel-price-rg` → `outlook-mail` → **Edit API connection** →
Authorize → sign in as `morozov_77@hotmail.com` → Save. The connector's
authorize endpoint is `login.microsoftonline.com/consumers/...` (*checked*
against the managed API definition), so it is the consumer Outlook.com sign-in,
not the work account.

**One line in the template could not be verified from here, and this is where
it was checked.** The send-mail operation is written as `path: /v2/Mail`. The
connector's swagger is not readable from the CLI — ARM returns
`apiDefinitions: null`, its `apiOperations` list names `SendEmailV2` but no
path, and the runtime endpoint answers 404. *Checked* 19 Sep 2026 the only way
left: both mail actions render as **Send an email (V2)** with their fields
filled in, in the designer. Worth repeating after any connector change — if
either ever shows as an unrecognised operation, take what the designer
generates and correct the template to match.

### 7d. Prove it for about six cents

Fire the recurrence by hand on a week that is already loaded. The dispatch
reaches GitHub, the gate answers `2`, and the run ends green having woken the
capacity for a few minutes — the same cheap proof step 6 uses.

```bash
LA=/subscriptions/$SUB/resourceGroups/nz-fuel-price-rg/providers/Microsoft.Logic/workflows/trigger-weekly-load
az rest --method post \
  --url "https://management.azure.com$LA/triggers/Recurrence/run?api-version=2016-06-01"

gh run list --workflow weekly.yml --event workflow_dispatch --limit 3
```

A run appearing within seconds is the first half of the test: it proves the
token, the permission and the URL together. If none appears, read the Logic
App's run history — a 401 is the token, a 404 is the repository or the workflow
file name, and a 422 is the `ref`.

The second half arrives an hour later, and it is the half that is easy to
forget: **no mail means the alarm agrees the load succeeded.** *Checked*
19 Sep 2026 on run `08584118121261199683681875057CU01`: the condition was
evaluated against the live run, both halves of it, and both mail actions were
skipped.

**The mail itself was proven by an accident, and the accident was a better
test than the one planned.** The plan was to redeploy with `waitMinutes=2` so
the check would catch a load still in flight. What happened instead: the
redeploy went out with an *empty* token, the dispatch came back `Unauthorized`,
and the second mail — "cannot tell whether the load ran" — arrived in the
mailbox. That exercised the connector, the `/v2/Mail` path and the mailbox end
to end, on the branch that matters most: a credential that has stopped working.
It also exercised, for the first time, `Wait_for_the_load_to_finish` running
after a *failed* dispatch, which is the whole reason its `runAfter` lists
`Failed` — and it cost nothing, because no load ever started.

**How the token went missing, because it will happen again.** `read -rs`
prints no prompt and echoes nothing, so pasting the whole three-line block at
once feeds the *second line* to it: `GH_DISPATCH_TOKEN` ended up holding the
literal string `export GH_DISPATCH_TOKEN`, 24 characters. Two deployments went
out that way before anyone looked. Two habits prevent it:

```bash
# one line, so there is no next line to swallow
read -rs GH_DISPATCH_TOKEN && export GH_DISPATCH_TOKEN && echo "${#GH_DISPATCH_TOKEN} chars, ${GH_DISPATCH_TOKEN:0:11}"
# expect: 93 chars, github_pat_

# and ask GitHub before asking Azure — this separates a bad token from a bad template
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $GH_DISPATCH_TOKEN" \
  https://api.github.com/repos/AndRayFS/nz-fuel-price-azure-fabric/actions/workflows/weekly.yml
# 200 = good; 401 = token; 404 = the token does not cover this repository
```

Restored the same hour and verified rather than assumed: `waitMinutes` back to
60, and a second hand-fired recurrence produced run 35427381482, green, with
the watchdog 35427530147 behind it on `workflow_run` and the capacity back to
`Paused`. A masked `githubToken` reads as `{}` whatever it holds, so a live
dispatch is the only proof the deployed token works.

### 7e. The first Thursday did not fire, and nothing said so — 24 Sep 2026

The Logic App was last deployed on 19 Sep at 06:39 UTC with `startTime`
`2026-09-24T09:07:00`, New Zealand time. On 24 Sep it did not fire: no trigger
history after 19 Sep, and `nextExecutionTime` already set to
`2026-09-30T20:07:00Z`, the Thursday after. No dispatch meant no run, and no
run meant no mail. The missing week was found by hand and loaded with
`gh workflow run weekly.yml` at 04:43 UTC (run 35956879448).

**The cause is documented behaviour, not an outage.** Microsoft's page on
schedules for recurring triggers says a `Week` recurrence given a future start
date should be set up at least seven days ahead, or the first recurrence may be
skipped. This one was set up 4.6 days ahead. The other suspect, `startTime`
landing exactly on the scheduled slot, is ruled out by the same page: its own
Saturday example has the start time equal to the first run.

**The rule, therefore: `startTime` in the past, or at least seven days after
the deployment.** The template's `2026-09-24T09:07:00` is now in the past, so
every redeploy from here on is safe as it stands. Do not move it forward.

**What it exposed is the blind spot at the end of this section**, and that is
now closed by a check that does not live in Azure at all.

### One trigger, and nothing behind it

| where | when | what it is |
|---|---|---|
| `trigger-weekly-load` | Thursday 09:07 NZ | the trigger, and the only one |
| the same, an hour later | Thursday ~10:07 NZ | asks what became of the run, mails if it did not succeed |
| `weekly.yml` | on dispatch only | no schedule at all |
| `pause-capacity.yml` | on `workflow_run`, plus Wednesday 23:52 UTC | the watchdog, following the load rather than racing it |
| the same, job `missed-load` | its cron only, Wednesday 23:52 UTC | fails, and GitHub mails, if no `Weekly load` has succeeded or is running since Wednesday 18:00 UTC |

**There is deliberately no second way to start a load.** A backstop cron was
written first and taken out again on 19 Sep 2026, along with the `guard` job it
needed: a cron fires every week whether or not the Logic App already did, so
the pair is not a trigger and a reserve but two schedules that have to be kept
from colliding. One clock, and something that says so when it fails to strike.

**What the alarm deliberately does not do** is judge the data. It asks whether
the chain ran and reached a conclusion, nothing more. Whether the week that
arrived is any good is the gate's question, one stage later, and a quiet week
with nothing new is a legitimate `success` here. Two things asking that question
would eventually disagree.

**Where the alarm was blind: its own recurrence — closed 24 Sep 2026.** If
the Logic App does not run at all, nothing inside it can say so. This file used
to answer that with Azure's SLA and, as a belt, a Monitor alert on the
workflow's failed runs. The first Thursday showed both were the wrong answer:
the platform behaved exactly as documented (7e), and a recurrence that does not
fire leaves no failed run for an alert to count.

The check that catches it has to sit outside the Logic App, so it is the
`missed-load` job in `pause-capacity.yml`, on GitHub's cron: no `Weekly load`
that succeeded or is still running since Wednesday 18:00 UTC, and the job
fails. That cron is often hours late, which costs nothing here. *Checked*
24 Sep 2026 against the live API, by running the step's script locally: it
passes on this week's run, fails when given a time in the future, and run
against the day as it happened it would have failed at 01:40 UTC — three hours
before the load was started by hand.

- **The mail comes from GitHub, not from the Logic App**, so it goes to the
  GitHub account's notification address rather than to the Outlook mailbox.
  *Not yet proven.* After the merge, one dispatch should produce it:
  `gh workflow run pause-capacity.yml -f since=2099-01-01T00:00:00Z`.
