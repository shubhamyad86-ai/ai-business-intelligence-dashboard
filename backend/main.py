"""Production-oriented FastAPI service for AI Operations Engineer."""
from __future__ import annotations
import io, logging, os, sys, time
from collections import defaultdict, deque
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
from backend.dataset_api import router as dataset_router
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from agent.ai_agent import AIAgent
from core.advanced import operational_alerts, sales_health
from core.data_ingest import import_csv, import_excel
from core.metrics import observe_chat, observe_request, snapshot
from db.database import create_user, get_user, log_chat, recent_logs
from reports.report_generator import generate_report_markdown, generate_report_pdf_bytes
from security.auth import create_token, hash_password, verify_password, current_user, require_role
from tools.customer_analysis import analyze_customers
from tools.inventory_analysis import analyze_inventory
from tools.sales_analysis import analyze_sales
load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger=logging.getLogger("aioe")
app=FastAPI(title="AI Operations Engineer API",version="1.0.0",description="Local-first business intelligence and AI operations platform")
origins=[x.strip() for x in os.getenv("ALLOWED_ORIGINS","http://localhost:8000,http://127.0.0.1:8000").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=["*"],allow_headers=["*"])
AUTH_ENABLED=os.getenv("AUTH_ENABLED","false").lower()=="true"
RATE_LIMIT=int(os.getenv("RATE_LIMIT_PER_MINUTE","30"))
_rate:dict[str,deque]=defaultdict(deque)
_agent=None

def get_agent():
    global _agent
    if _agent is None:_agent=AIAgent()
    return _agent

def maybe_auth(user=Depends(current_user)):
    return user

@app.middleware("http")
async def request_metrics(request,call_next):
    start=time.perf_counter(); error=False
    try:return await call_next(request)
    except Exception:error=True;raise
    finally:observe_request((time.perf_counter()-start)*1000,error)

def rate_limit(request):
    now=time.time(); key=request.client.host if request.client else "unknown"; q=_rate[key]
    while q and now-q[0]>60:q.popleft()
    if len(q)>=RATE_LIMIT: raise HTTPException(429,detail="Rate limit exceeded; try again shortly")
    q.append(now)

class ChatMessage(BaseModel):
    role:str; content:str=Field(min_length=1,max_length=4000)
class ChatRequest(BaseModel):
    question:str=Field(min_length=1,max_length=2000); history:list[ChatMessage]=Field(default_factory=list,max_length=6)
class ChatResponse(BaseModel): answer:str; latency_ms:float; fast_path:bool=False
class AuthRequest(BaseModel): username:str=Field(min_length=3,max_length=64,pattern=r"^[A-Za-z0-9_.-]+$"); password:str=Field(min_length=8,max_length=256)

@app.exception_handler(Exception)
async def unhandled(request,exc):
    logger.exception("Unhandled exception on %s",request.url.path)
    from fastapi.responses import JSONResponse
    return JSONResponse(500,{"detail":"Internal server error"})

@app.get("/health")
def health():
    return {"status":"ok","auth_enabled":AUTH_ENABLED,"model":os.getenv("OLLAMA_MODEL","llama3.2:1b")}

@app.get("/api/health/ollama")
def ollama_health():
    try:
        models=get_agent().client.list()
        return {"status":"ok","models":models.get("models",[])}
    except Exception as exc:return {"status":"unavailable","detail":str(exc)}

@app.get("/api/metrics")
def metrics(_=Depends(maybe_auth) if AUTH_ENABLED else None): return snapshot()

@app.post("/api/auth/register")
def register(req:AuthRequest):
    if get_user(req.username): raise HTTPException(409,"Username already exists")
    role="admin" if not recent_logs(1) and os.getenv("ALLOW_FIRST_ADMIN","true").lower()=="true" else "user"
    if not create_user(req.username,hash_password(req.password),role): raise HTTPException(409,"Username already exists")
    return {"created":True,"username":req.username,"role":role}

@app.post("/api/auth/login")
def login(req:AuthRequest):
    user=get_user(req.username)
    if not user or not verify_password(req.password,user["password_hash"]): raise HTTPException(401,"Invalid credentials")
    return {"access_token":create_token(user["username"],user["role"]),"token_type":"bearer","role":user["role"]}

@app.get("/api/auth/me")
def me(user=Depends(current_user)): return user

def guard(user=Depends(current_user)):
    if AUTH_ENABLED:return user
    return {"username":"local","role":"admin"}

def rate_guard(request): rate_limit(request); return guard()

@app.get("/api/sales-summary")
def sales_summary(): return analyze_sales()
@app.get("/api/customer-summary")
def customer_summary(): return analyze_customers()
@app.get("/api/inventory-summary")
def inventory_summary(): return analyze_inventory()
@app.get("/api/report",response_class=PlainTextResponse)
def report(): return generate_report_markdown()
@app.get("/api/report.pdf")
def report_pdf(): return Response(generate_report_pdf_bytes(),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=business_report.pdf"})
@app.get("/api/advanced/health")
def advanced_health(): return sales_health()
@app.get("/api/alerts")
def alerts(): return {"alerts":operational_alerts()}

@app.post("/api/chat",response_model=ChatResponse)
def chat(req:ChatRequest, request:Request):
    # Explicit limiter without requiring auth in local mode.
    if request is not None: rate_limit(request)
    start=time.perf_counter()
    try:
        history=[h.model_dump() for h in req.history]
        answer=get_agent().ask(req.question,history=history)
        ms=(time.perf_counter()-start)*1000
        observe_chat(ms); log_chat("local",req.question,answer,ms)
        fast_path=ms<100 # heuristic only; API remains truthful about answer
        return ChatResponse(answer=answer,latency_ms=round(ms,1),fast_path=fast_path)
    except Exception as exc:
        logger.exception("agent failed")
        raise HTTPException(502,detail=f"Could not reach the local LLM: {exc}")

@app.get("/api/admin/chat-logs")
def chat_logs(user=Depends(require_role("admin"))): return {"logs":recent_logs(100)}

@app.post("/api/data/upload")
async def data_upload(dataset:str,file:UploadFile=File(...),user=Depends(require_role("admin")) if AUTH_ENABLED else None):
    if dataset not in {"sales","inventory"}:raise HTTPException(400,"dataset must be sales or inventory")
    suffix=Path(file.filename or "").suffix.lower()
    if suffix not in {".csv",".xlsx"}:raise HTTPException(400,"Only CSV and XLSX are supported")
    temp=Path("data")/f"_upload_{int(time.time()*1000)}{suffix}"
    try:
        temp.write_bytes(await file.read())
        result=import_excel(str(temp),dataset) if suffix==".xlsx" else import_csv(str(temp),dataset)
        return result
    finally:
        temp.unlink(missing_ok=True)

frontend_dir=Path(__file__).resolve().parent.parent/"frontend"
# IMPORTANT: include_router must come BEFORE the static-files mount below.
# Starlette matches routes in registration order, and Mount("/") matches
# every path (StaticFiles just 404s/405s anything it can't find) — so if
# it were registered first, it would shadow every /api/dataset/* route
# and silently return 405 Method Not Allowed instead of reaching the
# actual endpoint. This bit us once already; don't reorder these two lines.
app.include_router(dataset_router)
if frontend_dir.exists():app.mount("/",StaticFiles(directory=str(frontend_dir),html=True),name="frontend")
