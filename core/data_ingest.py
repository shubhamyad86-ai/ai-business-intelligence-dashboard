from __future__ import annotations
from pathlib import Path
import pandas as pd
from tools.sales_analysis import DEFAULT_DATA_PATH
from tools.inventory_analysis import DEFAULT_DATA_PATH as INV_PATH

SALES_COLUMNS={"date","product","customer","country","revenue"}
INV_COLUMNS={"product","warehouse","stock_level","reorder_threshold","unit_cost"}

def import_csv(file_path: str, dataset: str) -> dict:
    src=Path(file_path); df=pd.read_csv(src)
    required=SALES_COLUMNS if dataset=="sales" else INV_COLUMNS
    missing=required-set(df.columns)
    if missing: raise ValueError(f"Missing columns: {sorted(missing)}")
    dest=DEFAULT_DATA_PATH if dataset=="sales" else INV_PATH
    df.to_csv(dest,index=False)
    return {"dataset":dataset,"rows":len(df),"path":str(dest)}

def import_excel(file_path: str, dataset: str) -> dict:
    src=Path(file_path); df=pd.read_excel(src)
    required=SALES_COLUMNS if dataset=="sales" else INV_COLUMNS
    missing=required-set(df.columns)
    if missing: raise ValueError(f"Missing columns: {sorted(missing)}")
    dest=DEFAULT_DATA_PATH if dataset=="sales" else INV_PATH
    df.to_csv(dest,index=False)
    return {"dataset":dataset,"rows":len(df),"path":str(dest)}
