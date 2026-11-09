#!/usr/bin/env python3
"""KSI weekly operations workbook, using live read-only Katana API."""
import datetime as dt
import os, time
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

API="https://api.katanamrp.com/v1"
TOKEN=os.environ["KATANA_API_KEY"].removeprefix("Bearer ").strip()
SESSION=requests.Session()
SESSION.headers.update({"Authorization":f"Bearer {TOKEN}","Accept":"application/json"})
AZ=ZoneInfo("America/Phoenix")
MONDAY=dt.date.fromisoformat(os.getenv("WEEK_START","2026-11-02"))
DAYS=[MONDAY+dt.timedelta(days=i) for i in range(5)]
START=dt.datetime.combine(MONDAY,dt.time.min,AZ).astimezone(dt.timezone.utc)
END=dt.datetime.combine(MONDAY+dt.timedelta(days=5),dt.time.min,AZ).astimezone(dt.timezone.utc)
def iso(t):return t.isoformat().replace("+00:00","Z")
def parse(t):return dt.datetime.fromisoformat(t.replace("Z","+00:00"))
def get(path):
    for attempt in range(5):
        r=SESSION.get(API+path,timeout=65)
        if r.status_code in (429,500,502,503,504):
            time.sleep(min(3*(attempt+1),15));continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Katana failed after retries: {path}")
def pages(path):
    all_rows=[]
    for p in range(1,100):
        sep="&" if "?" in path else "?"
        data=get(f"{path}{sep}limit=100&page={p}")
        batch=data["data"]
        all_rows.extend(batch)
        if len(batch)<100:return all_rows
    raise RuntimeError(f"Pagination safety limit reached: {path}")
def day(t):return parse(t).astimezone(AZ).date()
def inweek(t):return t and START<=parse(t)<END
factory=get("/factory")
currency=factory.get("base_currency_code","USD")
sales=pages(f"/sales_orders?created_at_min={iso(START)}&created_at_max={iso(END)}")
sales=[s for s in sales if inweek(s.get("created_at")) and not s.get("deleted_at")]
operations=pages(f"/manufacturing_order_operation_rows?updated_at_min={iso(START)}")
resources={"Load/Run Coil - Hayes":"Hayes","Load/Run Coil - Snaplock":"Snaplock","Load/Run Coil - Snap Lock":"Snaplock","Break/Bend":"Bend","Pull Pallets/Shear Flatsheet":"Pull Pallets/Shear"}
ops=[o for o in operations if o.get("status")=="COMPLETED" and inweek(o.get("completed_at")) and o.get("completed_by_operators") and o.get("resource_name") in resources and not o.get("deleted_at")]
mo_ids=sorted({o["manufacturing_order_id"] for o in ops})
mos={}
for idx in range(0,len(mo_ids),75):
    ids=mo_ids[idx:idx+75]
    for mo in pages("/manufacturing_orders?"+ "&".join(f"ids[]={i}" for i in ids)):
        mos[mo["id"]]=mo
missing=set(mo_ids)-set(mos)
if missing:raise RuntimeError(f"Missing manufacturing orders: {len(missing)}")
row_ids=sorted({m.get("sales_order_row_id") for m in mos.values() if m.get("sales_order_row_id")})
so_rows={}
for idx in range(0,len(row_ids),75):
    for sr in pages("/sales_order_rows?"+"&".join(f"ids[]={i}" for i in row_ids[idx:idx+75])):
        so_rows[sr["id"]]=sr
if set(row_ids)-set(so_rows):raise RuntimeError("Missing linked sales rows")
raw=[]
for o in ops:
    mo=mos[o["manufacturing_order_id"]]
    operators=", ".join(x.get("name","") for x in o["completed_by_operators"])
    sr=so_rows.get(mo.get("sales_order_row_id"))
    raw.append((o["completed_at"],str(day(o["completed_at"])),resources[o["resource_name"]],operators,o.get("operation_name",""),mo.get("order_no",str(mo["id"])),float(mo["planned_quantity"]),float(sr.get("total_in_base_currency") or 0) if sr else 0,o["id"],mo["id"]))
raw.sort(key=lambda r:(r[1],r[2],r[3],r[0]))
wb=Workbook()
ws=wb.active;ws.title="Summary"
salesws=wb.create_sheet("Raw - Sales Orders")
mows=wb.create_sheet("Raw - MO Completions")
navy="183153";blue="DCEAF6";teal="D9F0ED";white="FFFFFF";gray="5B6774"
for sh in wb:
    sh.sheet_view.showGridLines=False
    sh.freeze_panes="C6" if sh==ws else "A2"
def header(sh,row,cols):
    for c in range(1,cols+1):
        x=sh.cell(row,c);x.fill=PatternFill("solid",fgColor=navy);x.font=Font(name="Aptos",bold=True,color=white,size=10);x.alignment=Alignment(vertical="center",wrap_text=True)
    sh.row_dimensions[row].height=27
def section(row,title):
    ws.merge_cells(start_row=row,start_column=2,end_row=row,end_column=9)
    c=ws.cell(row,2,title);c.fill=PatternFill("solid",fgColor=navy);c.font=Font(bold=True,color=white,size=11)
    ws.row_dimensions[row].height=23
ws["B2"]="Weekly Operations Report";ws["B2"].font=Font(name="Aptos Display",size=19,bold=True,color=navy)
ws["B3"]=f"Week of {MONDAY:%B %d, %Y} (Arizona) — final through {DAYS[-1]:%B %d, %Y} | {currency}"
section(5,"SALES ORDERS — New Orders Per Day")
for col,v in enumerate(["Metric"]+[f"{d:%a %m/%d}" for d in DAYS]+["Week Avg / Total"],2):ws.cell(6,col,v)
header(ws,6,8)
for r,title in [(7,"New Sales Orders"),(8,"Sales Revenue")]:
    ws.cell(r,2,title)
    for i,d in enumerate(DAYS):
        col=3+i
        if r==7:val=sum(day(s["created_at"])==d for s in sales)
        else:val=sum(float(s.get("total_in_base_currency") or 0) for s in sales if day(s["created_at"])==d)
        ws.cell(r,col,val)
    ws.cell(r,8,f"=SUM(C{r}:G{r})")
    if r==8:
        for col in range(3,9):ws.cell(r,col).number_format='"$"#,##0.00;[Red]("$"#,##0.00);-'
section(11,"MANUFACTURING — Completed Quantity Per Day, by Resource & Operator")
for col,v in enumerate(["Resource","Operator"]+[f"{d:%a %m/%d}" for d in DAYS]+["Total","Linked Revenue"],2):ws.cell(12,col,v)
header(ws,12,9)
r=13
for station in ["Hayes","Snaplock","Bend","Pull Pallets/Shear"]:
    names=sorted({x[3] for x in raw if x[2]==station})
    first=r
    for name in names:
        ws.cell(r,2,station);ws.cell(r,3,name)
        for i,d in enumerate(DAYS):
            ws.cell(r,4+i,sum(x[6] for x in raw if x[2]==station and x[3]==name and x[1]==str(d)))
        ws.cell(r,9,f"=SUM(D{r}:H{r})")
        r+=1
    ws.cell(r,2,f"{station} — Total")
    for col in range(4,10):
        letter=get_column_letter(col)
        ws.cell(r,col,f"=SUM({letter}{first}:{letter}{r-1})" if first<r else 0)
    ws.cell(r,10,sum(x[7] for x in raw if x[2]==station))
    ws.cell(r,10).number_format='"$"#,##0.00;[Red]("$"#,##0.00);-'
    for col in range(2,11):
        c=ws.cell(r,col);c.fill=PatternFill("solid",fgColor=blue);c.font=Font(bold=True,color=navy)
    r+=1
ws.cell(r+2,2,"* Linked station revenue measures revenue touched by completed operations; do not add across stations.")
ws.cell(r+3,2,"Source: live Katana API | Arizona completion and creation dates | linked sales-order row base-currency totals.")
salesheaders=["Order Number","Created At UTC","Arizona Date","Status","Total (Base Currency)","Katana Order ID"]
salesws.append(salesheaders);header(salesws,1,len(salesheaders))
for s in sorted(sales,key=lambda s:s["created_at"]):
    salesws.append([s.get("order_no"),s["created_at"],str(day(s["created_at"])),s.get("status"),float(s.get("total_in_base_currency") or 0),s["id"]])
    salesws.cell(salesws.max_row,5).number_format='"$"#,##0.00'
moheaders=["Completed At UTC","Arizona Date","Resource","Operator","Operation","MO Number","Job Qty","Linked Sales Revenue","Operation Row ID","MO ID"]
mows.append(moheaders);header(mows,1,len(moheaders))
for x in raw:
    mows.append(list(x));mows.cell(mows.max_row,8).number_format='"$"#,##0.00'
for sh in (salesws,mows):
    sh.auto_filter.ref=sh.dimensions
    for row in sh.iter_rows(min_row=2):
        for c in row:
            c.font=Font(name="Aptos",size=10,color="087650" if c.column in (5,7,8) else "222222")
ws.column_dimensions["A"].width=3
for col,width in {"B":24,"C":25,"D":15,"E":15,"F":15,"G":15,"H":15,"I":18,"J":22}.items():ws.column_dimensions[col].width=width
for sh,widths in [(salesws,[28,29,18,19,25,22]),(mows,[29,17,27,31,28,25,17,25,20,20])]:
    for i,w in enumerate(widths,1):sh.column_dimensions[get_column_letter(i)].width=w
wb.calculation=CalcProperties(calcMode="auto")
out=Path("reports")/f"Weekly_Ops_Report_{MONDAY.isoformat()}.xlsx"
out.parent.mkdir(exist_ok=True)
wb.save(out)
print(f"REPORT={out}")
print(f"SALES_ORDERS={len(sales)}")
print(f"SALES_REVENUE={sum(float(s.get('total_in_base_currency') or 0) for s in sales):.2f}")
print(f"COMPLETED_OPERATIONS={len(raw)}")
print(f"CURRENCY={currency}")
