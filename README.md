# Shop Floor Status Dashboard

A live TV dashboard showing each station's Due Today goal and Scheduled stretch
pool, pulled straight from Katana.

- **Due Today** — the goal. Open jobs whose deadline falls exactly on today.
- **Scheduled** — everything else open (overdue backlog *and* future-dated work) —
  the stretch pool if the day's goal gets cleared early.

## How it works

1. `.github/workflows/update-dashboard.yml` runs every 15 minutes, calls the
   Katana API using the `KATANA_API_KEY` repo secret, and writes
   `docs/workload.json`.
2. `docs/index.html` is a static page (served by GitHub Pages) that reads
   `docs/workload.json` and refreshes itself every 60 seconds.

**Only aggregate station numbers are written to `workload.json`** — no customer
names, order numbers, or dollar figures — since this repo/site is public on the
free GitHub plan.

## One-time setup

1. Push this repo to GitHub (public repo, required for free Pages).
2. Repo → Settings → Secrets and variables → Actions → New repository secret:
   - Name: `KATANA_API_KEY`
   - Value: a Katana API key (Katana → Settings → API)
3. Repo → Settings → Pages → Source: "Deploy from a branch" → Branch: `main`,
   folder: `/docs`. Save.
4. Repo → Actions tab → find "Update shop-floor dashboard" → "Run workflow" to
   trigger the first pull manually (otherwise wait up to 15 minutes for the
   schedule).
5. Your dashboard URL will be `https://<your-username>.github.io/<repo-name>/`.
   Open that on the shop-floor TV's browser in full-screen/kiosk mode.

## Changing the refresh interval

Edit the `cron` line in `.github/workflows/update-dashboard.yml`. GitHub Actions
won't reliably run more often than every 5 minutes, and free-tier public repos
get unlimited Actions minutes, so 15 minutes is a reasonable default.

## If a station name changes in Katana

Update `RESOURCE_LABELS` in `scripts/fetch_workload.py` to match.
