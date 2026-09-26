"""Deterministic forecasting, anomaly detection and alert generation."""
from __future__ import annotations
import math
import pandas as pd
from tools.sales_analysis import load_sales
from tools.inventory_analysis import load_inventory

def sales_health() -> dict:
    df=load_sales()
    monthly=df.groupby(df["date"].dt.to_period("M"))["revenue"].sum().sort_index()
    values=monthly.tolist()
    anomalies=[]
    if len(values)>=3:
        mean=sum(values[:-1])/len(values[:-1]); variance=sum((x-mean)**2 for x in values[:-1])/len(values[:-1]); sd=math.sqrt(variance)
        if sd:
            z=(values[-1]-mean)/sd
            if abs(z)>=2: anomalies.append({"month":str(monthly.index[-1]),"revenue":round(values[-1],2),"z_score":round(z,2)})
    forecast=[]
    if len(values)>=2:
        n=len(values); x=list(range(n)); mx=sum(x)/n; my=sum(values)/n
        den=sum((i-mx)**2 for i in x) or 1
        slope=sum((i-mx)*(y-my) for i,y in zip(x,values))/den; intercept=my-slope*mx
        for step in range(1,4): forecast.append({"period":str(monthly.index[-1]+step),"revenue":round(max(0,intercept+slope*(n-1+step)),2)})
    return {"anomalies":anomalies,"forecast_next_3_months":forecast}

def operational_alerts() -> list[dict]:
    alerts=[]
    inv=load_inventory()
    for _,r in inv[inv.stock_level < inv.reorder_threshold].iterrows():
        alerts.append({"severity":"high" if r.stock_level <= r.reorder_threshold*0.5 else "medium","type":"low_stock","message":f"{r.product} at {r.warehouse} is below reorder threshold by {int(r.reorder_threshold-r.stock_level)} units."})
    for a in sales_health()["anomalies"]:
        alerts.append({"severity":"high","type":"sales_anomaly","message":f"Revenue in {a['month']} is statistically unusual (z={a['z_score']})."})
    return alerts
