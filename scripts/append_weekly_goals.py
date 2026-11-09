from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule
from pathlib import Path

# Verified frozen goals and last available same-day snapshots from the Prod KSI GitHub history.
# Sources: https://github.com/Swoolskee/Shop-Dashbaord-KSI-Metals/commits/main/docs/dashboard-data.json
SNAPSHOTS = [
 ("2026-11-02","2026-11-02T23:06:46Z","4ba880b9f9d9a62f0ba7258e676ab0e52ef612c8",[(838.25,2447.5),(0,0),(396,307),(244,259)]),
 ("2026-11-03","2026-11-04T00:53:11Z","0e8b280be4f66929d3b9a32ea1753c7c6ec56e7b",[(700.25,559.08167),(0,3122.9167),(244,256),(82,386)]),
 ("2026-11-04","2026-11-04T20:49:25.519Z","976104a91965b5f7c25171a5363b8cc88af11fcb",[(775.25,2524.8333),(0,175.75),(249,152),(82,22)]),
 ("2026-11-05","2026-11-06T01:47:18Z","9a440af887de17d1f3c72e33b29ae50773feeecf",[(954.7625,1339.197),(0,302.16663),(307,300),(248,498)]),
 ("2026-11-06","2026-11-07T02:29:03Z","569566fd3fb094fdd02a56ec3bb3a9c7ccc98b6d",[(832.7625,3190.2499),(0,0),(250,200),(79,184)]),
]
STATIONS=[("Hayes","LF"),("Snaplock","LF"),("Bend","PCS"),("Pull Pallets/Shear","PCS")]
src=Path("reports/Weekly_Ops_Report_2026-11-02.xlsx")
dst=Path("reports/KSI_Weekly_Production_Report_2026-11-02_GOALS_VERIFIED.xlsx")
wb=load_workbook(src)
if "Goals vs Actual" in wb:del wb["Goals vs Actual"]
ws=wb.create_sheet("Goals vs Actual",1)
ws.sheet_view.showGridLines=False
ws.freeze_panes="D6"
ws.merge_cells("A1:J1");ws["A1"]="KSI METALS | WEEKLY GOAL ATTAINMENT";ws["A1"].font=Font(name="Aptos Display",size=17,bold=True,color="183153")
ws.merge_cells("A2:J2");ws["A2"]="November 2–6, 2026 | Arizona time | frozen morning goals vs last available daily board snapshots"
ws.merge_cells("A3:J3");ws["A3"]="Snapshots are historical board readings; last available snapshot may differ from final Katana operation totals."
headers=["Date","Station","Unit","Morning Goal","Snapshot Actual","Variance","Goal %","Hit Goal?","Snapshot Time (UTC)","Source Commit"]
for c,v in enumerate(headers,1):
 x=ws.cell(5,c,v);x.fill=PatternFill("solid",fgColor="183153");x.font=Font(bold=True,color="FFFFFF");x.alignment=Alignment(wrap_text=True)
ws.row_dimensions[5].height=30
row=6
for date,stamp,sha,values in SNAPSHOTS:
 for i,(station,unit) in enumerate(STATIONS):
  goal,actual=values[i]
  for c,v in enumerate([date,station,unit,goal,actual],1):ws.cell(row,c,v)
  ws.cell(row,6,f"=E{row}-D{row}")
  ws.cell(row,7,f'=IF(D{row}=0,IF(E{row}=0,1,""),E{row}/D{row})')
  ws.cell(row,8,f'=IF(D{row}=0,IF(E{row}=0,"No goal","Exceeded no-goal plan"),IF(E{row}>=D{row},"YES","NO"))')
  ws.cell(row,9,stamp)
  ws.cell(row,10,f"https://github.com/Swoolskee/Shop-Dashbaord-KSI-Metals/blob/{sha}/docs/dashboard-data.json")
  ws.cell(row,7).number_format="0.0%"
  for c in (4,5,6):ws.cell(row,c).number_format='#,##0.00;[Red](#,##0.00);-'
  if row%4 in (2,3):
   for c in range(1,11):ws.cell(row,c).fill=PatternFill("solid",fgColor="F2F6FB")
  row+=1
ws.auto_filter.ref=f"A5:J{row-1}"
for c,w in {"A":17,"B":25,"C":9,"D":17,"E":18,"F":15,"G":14,"H":24,"I":28,"J":90}.items():ws.column_dimensions[c].width=w
summary=wb.create_sheet("Weekly Goal Summary",1)
summary.sheet_view.showGridLines=False
summary["A1"]="KSI METALS | WEEKLY GOAL SUMMARY"
summary["A1"].font=Font(size=17,bold=True,color="183153")
summary["A2"]="Week of November 2–6, 2026 | LF and PCS are never combined"
for c,v in enumerate(["Station","Unit","Weekly Goal","Weekly Snapshot Actual","Variance","Goal %","Days Met","Days With Goal"],1):
 x=summary.cell(4,c,v);x.fill=PatternFill("solid",fgColor="183153");x.font=Font(color="FFFFFF",bold=True);x.alignment=Alignment(wrap_text=True)
for i,(station,unit) in enumerate(STATIONS,5):
 summary.cell(i,1,station);summary.cell(i,2,unit)
 summary.cell(i,3,f'=SUMIF(\'Goals vs Actual\'!B$6:B$25,A{i},\'Goals vs Actual\'!D$6:D$25)')
 summary.cell(i,4,f'=SUMIF(\'Goals vs Actual\'!B$6:B$25,A{i},\'Goals vs Actual\'!E$6:E$25)')
 summary.cell(i,5,f'=D{i}-C{i}')
 summary.cell(i,6,f'=IF(C{i}=0,"",D{i}/C{i})')
 summary.cell(i,7,f'=COUNTIFS(\'Goals vs Actual\'!B$6:B$25,A{i},\'Goals vs Actual\'!H$6:H$25,"YES")')
 summary.cell(i,8,f'=COUNTIFS(\'Goals vs Actual\'!B$6:B$25,A{i},\'Goals vs Actual\'!D$6:D$25,">0")')
 summary.cell(i,6).number_format="0.0%"
summary["A11"]="No-goal days are excluded from days-met and days-with-goal metrics. Snapshot actuals remain visible."
summary["A12"]="Weekly attainment compares the sum of five daily frozen goals to five last-available board snapshots."
summary["A13"]="The original Summary and Raw tabs retain the live Katana weekly reporting data."
for c,w in {"A":26,"B":12,"C":20,"D":26,"E":18,"F":15,"G":15,"H":20}.items():summary.column_dimensions[c].width=w
summary.freeze_panes="C5"
wb.save(dst)
check=load_workbook(dst,read_only=True)
assert "Goals vs Actual" in check.sheetnames and check["Goals vs Actual"].max_row==25
print(f"GOAL_VERIFIED_FILE={dst}")
