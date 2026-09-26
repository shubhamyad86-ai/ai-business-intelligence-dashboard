"""Fast, grounded local AI agent with deterministic fast paths."""
from __future__ import annotations
import os, re, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import ollama
from dotenv import load_dotenv
from agent.context_router import build_context
from agent.prompts import SYSTEM_PROMPT
from tools.sales_analysis import analyze_sales
from tools.inventory_analysis import analyze_inventory
from tools.customer_analysis import analyze_customers
from rag.document_store import search_documents
load_dotenv()
DEFAULT_MODEL=os.getenv("OLLAMA_MODEL","llama3.2:1b")
DEFAULT_HOST=os.getenv("OLLAMA_HOST","http://localhost:11434")
KEEP_ALIVE=os.getenv("OLLAMA_KEEP_ALIVE","30m")
MAX_HISTORY_TURNS=3
GEN_OPTIONS={"num_predict":160,"temperature":0.2,"top_p":0.9,"num_ctx":1024}

def _fast_answer(q:str):
    ql=q.lower().strip()
    s=analyze_sales()
    if re.search(r"\b(total|overall)\b.*\brevenue\b|\brevenue\b.*\btotal\b",ql) and not any(x in ql for x in ("why","drop","decline","trend","month","product","country")):
        return f"Total revenue is €{s['total_revenue']:,.2f} across {s['total_orders']} orders.\n\n_Sources: sales.csv_"
    if ("top product" in ql or "best product" in ql) and "country" not in ql:
        p=s['top_product']; return f"The top product by revenue is **{p}**, generating €{s['product_revenue'][p]:,.2f}.\n\n_Sources: sales.csv_"
    if "top country" in ql or "best country" in ql:
        c=s['top_country']; return f"The top country by revenue is **{c}**, generating €{s['country_revenue'][c]:,.2f}.\n\n_Sources: sales.csv_"
    if "low stock" in ql or "below reorder" in ql:
        inv=analyze_inventory(); low=inv['low_stock']
        if not low: return "No inventory items are below their reorder thresholds.\n\n_Sources: inventory.csv_"
        items="; ".join(f"{x['product']} at {x['warehouse']} ({x['stock_level']}/{x['reorder_threshold']})" for x in low[:5])
        return f"There are {len(low)} low-stock item(s): {items}.\n\n_Sources: inventory.csv_"
    if "top customer" in ql:
        c=analyze_customers()['top_customers']
        if c: return "Top customer by revenue is **%s**, at €%s.\n\n_Sources: sales.csv (customer view)_"%(c[0]['customer'],f"{c[0]['revenue']:,.2f}")
    # Document-only common policy questions can also bypass the LLM.
    if any(k in ql for k in ("return window","return period","shipping time","damaged item","defective item")):
        docs=search_documents(q,top_k=2)
        if docs:
            return "Based on the relevant company policy:\n\n"+"\n\n".join(f"- {d['text'].replace(chr(10),' ')}" for d in docs[:1])+f"\n\n_Sources: {docs[0]['source']}_"
    return None

class AIAgent:
    def __init__(self,model=DEFAULT_MODEL,host=DEFAULT_HOST):
        self.model=model; self.client=ollama.Client(host=host,timeout=600)
    def ask(self,question,history=None,verbose=False):
        fast=_fast_answer(question)
        if fast: return fast
        context=build_context(question)
        messages=[{"role":"system","content":SYSTEM_PROMPT}]
        if history:
            for h in history[-MAX_HISTORY_TURNS*2:]:
                if h.get("role") in {"user","assistant"} and isinstance(h.get("content"),str): messages.append({"role":h["role"],"content":h["content"][:4000]})
        messages.append({"role":"user","content":f"DATA CONTEXT:\n{context.text}\n\nQUESTION: {question}"})
        if verbose: print(f"[agent] sources={context.sources}")
        response=self.client.chat(model=self.model,messages=messages,keep_alive=KEEP_ALIVE,options=GEN_OPTIONS)
        answer=response["message"].get("content","").strip()
        extra=[s for s in context.sources if s!="sales.csv"]
        if extra: answer+=f"\n\n_Sources: {', '.join(extra)}_"
        return answer
if __name__=="__main__":
    q=" ".join(sys.argv[1:]) or "Analyze our sales performance for the last 3 months"
    print(AIAgent().ask(q,verbose=True))
