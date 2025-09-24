from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/binance", response_class=HTMLResponse)
async def binance_page(request: Request):
    return templates.TemplateResponse("binance.html", {"request": request})

@router.get("/bitget", response_class=HTMLResponse)
async def bitget_page(request: Request):
    return templates.TemplateResponse("bitget.html", {"request": request})

@router.get("/gap", response_class=HTMLResponse)
async def gap_page(request: Request):
    return templates.TemplateResponse("gap.html", {"request": request})

@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    return templates.TemplateResponse("account.html", {"request": request})

@router.get("/order", response_class=HTMLResponse)
async def order_page(request: Request):
    return templates.TemplateResponse("order.html", {"request": request})
