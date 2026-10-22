"""Ledger DCF - local server.

Serves index.html and a small JSON API that pulls prices and financial
statements from Yahoo Finance's public endpoints (no API key needed).

Run:  python server.py    then open http://localhost:8765
"""
import json
import math
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8765
ROOT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}

ANNUAL = ["FreeCashFlow", "OperatingCashFlow", "CapitalExpenditure", "TotalRevenue",
          "NetIncome", "EBIT", "PretaxIncome", "TaxProvision", "InterestExpense"]
QUARTERLY = ["TotalDebt", "CashCashEquivalentsAndShortTermInvestments",
             "OrdinarySharesNumber", "MinorityInterest"]

_cache = {}


def get_json(url, ttl=600):
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    _cache[url] = (time.time(), data)
    return data


def chart(symbol, rng="5d", interval="1d"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?range={rng}&interval={interval}")
    return get_json(url)["chart"]["result"][0]


def fundamentals(symbol):
    types = [f"annual{t}" for t in ANNUAL] + [f"quarterly{t}" for t in QUARTERLY]
    now = int(time.time())
    url = ("https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
           f"{urllib.parse.quote(symbol)}?type={','.join(types)}"
           f"&period1={now - 7 * 365 * 86400}&period2={now + 86400}")
    out, currency = {}, None
    for res in get_json(url)["timeseries"]["result"]:
        key = res["meta"]["type"][0]
        rows = [x for x in (res.get(key) or []) if x and x.get("reportedValue")]
        rows.sort(key=lambda x: x["asOfDate"])
        out[key] = [{"date": x["asOfDate"], "value": x["reportedValue"]["raw"]} for x in rows]
        if rows and not currency:
            currency = rows[-1].get("currencyCode")
    return out, currency


def latest(series):
    return series[-1]["value"] if series else None


def monthly_returns(result):
    closes = result["indicators"]["adjclose"][0]["adjclose"]
    ts = result["timestamp"]
    pts = [(t, c) for t, c in zip(ts, closes) if c]
    return {pts[i][0]: pts[i][1] / pts[i - 1][1] - 1 for i in range(1, len(pts))}


BENCHMARKS = {
    ".T": "^N225", ".L": "^FTSE", ".HK": "^HSI", ".TO": "^GSPTSE", ".DE": "^GDAXI",
    ".PA": "^FCHI", ".AX": "^AXJO", ".NS": "^NSEI", ".BO": "^BSESN", ".KS": "^KS11",
    ".TW": "^TWII", ".SS": "000001.SS", ".SZ": "399001.SZ", ".AS": "^AEX",
    ".SW": "^SSMI", ".MI": "FTSEMIB.MI", ".MC": "^IBEX", ".SI": "^STI", ".SA": "^BVSP",
}


def benchmark_for(symbol):
    for suffix, index in BENCHMARKS.items():
        if symbol.endswith(suffix):
            return index
    return "^GSPC"


def compute_beta(symbol, benchmark="^GSPC"):
    """5-year monthly regression beta against the home-market index."""
    try:
        a = monthly_returns(chart(symbol, "5y", "1mo"))
        b = monthly_returns(chart(benchmark, "5y", "1mo"))
    except Exception:
        return None
    # Match months by calendar month since timestamps can differ by a day or two.
    def by_month(d):
        return {time.strftime("%Y-%m", time.gmtime(t)): v for t, v in d.items()}
    a, b = by_month(a), by_month(b)
    keys = sorted(set(a) & set(b))
    if len(keys) < 24:
        return None
    x = [b[k] for k in keys]
    y = [a[k] for k in keys]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    var = sum((xi - mx) ** 2 for xi in x)
    return cov / var if var else None


def fx_rate(src, dst):
    if not src or not dst or src == dst:
        return 1.0
    try:
        return chart(f"{src}{dst}=X")["meta"]["regularMarketPrice"]
    except Exception:
        return None


def company(symbol):
    symbol = symbol.strip().upper()
    meta = chart(symbol)["meta"]
    if meta.get("instrumentType") not in (None, "EQUITY"):
        raise ValueError(f"{symbol} is a {meta.get('instrumentType', 'non-equity').lower()}, "
                         "not a company stock.")
    price = meta.get("regularMarketPrice")
    price_ccy = meta.get("currency")
    fin, fin_ccy = fundamentals(symbol)
    if not fin.get("annualFreeCashFlow") and not fin.get("annualOperatingCashFlow"):
        raise ValueError(f"No cash flow statements found for {symbol}.")

    # Prices for London listings are quoted in pence.
    price_divisor = 100 if price_ccy in ("GBp", "GBX", "ZAc", "ILA") else 1
    price_ccy_norm = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(price_ccy, price_ccy)

    fcf_hist = fin.get("annualFreeCashFlow") or []
    if not fcf_hist:
        ocf = {r["date"]: r["value"] for r in fin.get("annualOperatingCashFlow", [])}
        capex = {r["date"]: r["value"] for r in fin.get("annualCapitalExpenditure", [])}
        fcf_hist = [{"date": d, "value": v + capex.get(d, 0)} for d, v in sorted(ocf.items())]

    pretax = {r["date"]: r["value"] for r in fin.get("annualPretaxIncome", [])}
    taxes = {r["date"]: r["value"] for r in fin.get("annualTaxProvision", [])}
    rates = [taxes[d] / pretax[d] for d in pretax if d in taxes and pretax[d] > 0]
    tax_rate = min(max(sum(rates[-3:]) / len(rates[-3:]), 0.0), 0.4) if rates else 0.21

    debt = latest(fin.get("quarterlyTotalDebt")) or 0
    interest = latest(fin.get("annualInterestExpense"))
    cost_of_debt = abs(interest) / debt if interest and debt else None
    if cost_of_debt is not None and not (0.005 <= cost_of_debt <= 0.15):
        cost_of_debt = None

    benchmark = benchmark_for(symbol)
    beta = compute_beta(symbol, benchmark)

    return {
        "symbol": symbol,
        "name": meta.get("longName") or meta.get("shortName") or symbol,
        "exchange": meta.get("fullExchangeName"),
        "price": price / price_divisor if price else None,
        "priceCurrency": price_ccy_norm,
        "financialCurrency": fin_ccy or price_ccy_norm,
        "fxToPrice": fx_rate(fin_ccy, price_ccy_norm),
                "benchmark": benchmark,
        "beta": round(beta, 2) if beta is not None and not math.isnan(beta) else None,
        "taxRate": round(tax_rate, 4),
        "costOfDebt": round(cost_of_debt, 4) if cost_of_debt else None,
        "totalDebt": debt,
        "cash": latest(fin.get("quarterlyCashCashEquivalentsAndShortTermInvestments")) or 0,
        "minorityInterest": latest(fin.get("quarterlyMinorityInterest")) or 0,
        "shares": latest(fin.get("quarterlyOrdinarySharesNumber")),
        "history": {
            "fcf": fcf_hist[-5:],
            "revenue": (fin.get("annualTotalRevenue") or [])[-5:],
            "netIncome": (fin.get("annualNetIncome") or [])[-5:],
        },
        "riskFree": risk_free(),
    }


def risk_free():
    try:
        return round(chart("^TNX")["meta"]["regularMarketPrice"] / 100, 4)
    except Exception:
        return 0.043


def search(q):
    url = ("https://query1.finance.yahoo.com/v1/finance/search?"
           + urllib.parse.urlencode({"q": q, "quotesCount": 7, "newsCount": 0}))
    quotes = get_json(url, ttl=3600).get("quotes", [])
    return [{"symbol": x["symbol"], "name": x.get("longname") or x.get("shortname") or "",
             "exchange": x.get("exchDisp", "")}
            for x in quotes if x.get("quoteType") == "EQUITY"]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/company":
                self._send(200, company(qs.get("ticker", [""])[0]))
            elif url.path == "/api/search":
                self._send(200, search(qs.get("q", [""])[0]))
            else:
                self._send(404, {"error": "Not found"})
        except urllib.error.HTTPError as e:
            msg = "Ticker not found." if e.code == 404 else f"Yahoo Finance returned {e.code}. Try again shortly."
            self._send(502, {"error": msg})
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"Could not load data: {e}"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Ledger DCF running at http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
