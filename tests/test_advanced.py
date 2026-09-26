import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.advanced import operational_alerts, sales_health

def test_forecast_shape():
    r=sales_health(); assert len(r["forecast_next_3_months"]) in (0,3)

def test_alerts_are_structured():
    for a in operational_alerts(): assert {"severity","type","message"} <= set(a)
