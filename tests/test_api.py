import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
import backend.main as main

def test_health():
    c=TestClient(main.app); r=c.get("/health"); assert r.status_code==200; assert r.json()["status"]=="ok"

def test_sales_endpoint():
    r=TestClient(main.app).get("/api/sales-summary"); assert r.status_code==200; assert r.json()["total_orders"]>0

def test_pdf_endpoint():
    r=TestClient(main.app).get("/api/report.pdf"); assert r.status_code==200; assert r.headers["content-type"]=="application/pdf"; assert len(r.content)>500
