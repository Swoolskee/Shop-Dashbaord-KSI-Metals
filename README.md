# Shop Floor Status Dashboard

Prod KSI is the live shop-floor production board for Hayes, Snaplock, Bend, and Pull Pallets/Shear.

The production site is deployed from the `docs` folder by Netlify.

## Automatic refresh schedule

GitHub Actions runs `.github/workflows/prod-ksi-auto-refresh.yml` on Arizona time:

- 7:00 AM — first successful run of the day snapshots and freezes **Goal Today**
- 8:00 AM through 3:00 PM — hourly live refreshes
- 3:30 PM — final scheduled refresh
- Manual runs are also available from the GitHub Actions page

Arizona is UTC-7 year-round, so the workflow cron schedules use UTC.

## Dashboard rules

The automation in `scripts/update_prod_dashboard.py` follows the same rules as the established Prod KSI workflow:

- **Current Numbers** = production completed today in Arizona time
- **Goal Today** = frozen on the first successful refresh of a new business day
- **Can Produce** = current production plus all unfinished mapped work and can change as orders come in
- **Created Orders** = all Katana sales orders created during the current Arizona day
- **Top Operator** = operator with the greatest credited completed quantity at the station
- Past-due unfinished work is included when the morning Goal Today snapshot is created

Mapped Katana resources:

- `Load/Run Coil - Hayes` -> Hayes
- `Load/Run Coil - Snaplock` or `Load/Run Coil - Snap Lock` -> Snaplock
- `Break/Bend` -> Bend
- `Pull Pallets/Shear Flatsheet` -> Pull Pallets/Shear

Only aggregate station data is written to `docs/dashboard-data.json`.

## Required GitHub secret

The workflow requires this repository Actions secret:

- `KATANA_API_KEY`

Add it at:

**Repository -> Settings -> Secrets and variables -> Actions -> New repository secret**

Use a Katana API key with the access needed to read manufacturing operation rows, manufacturing orders, and sales orders.

The API key is never written to the website or dashboard JSON.

## Deployment

The workflow commits only `docs/dashboard-data.json`. Netlify watches the `main` branch and automatically publishes the existing Prod KSI site after the commit.

Manual ChatGPT refreshes and the GitHub automation use the same dashboard payload and frozen-goal rule.
