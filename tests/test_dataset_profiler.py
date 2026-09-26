import pandas as pd
from core.dataset_profiler import profile_csv

def test_electrification_profile(tmp_path):
    p = tmp_path / "bmw.csv"
    pd.DataFrame({
        "Quarter":["2019-Q1","2019-Q2"],
        "BEV":[100,120],
        "PHEV":[50,60],
        "Electrified":[150,180],
        "Total Deliveries":[1000,1100],
        "Electrified Share %":[15,16.36],
        "Inventories at End of Quarter":[20,25],
    }).to_csv(p,index=False)
    out = profile_csv(p)
    assert out["dataset_type"] == "electrification"
    assert out["dashboard"]["title"] == "Electrified Vehicle Operations"
    assert len(out["dashboard"]["charts"]) >= 3
