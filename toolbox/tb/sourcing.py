"""Part sourcing: supplier search adapters (DigiKey, Mouser, Farnell), price comparison and search links.

Every adapter returns offers in one shape:
{supplier, mpn, manufacturer, description, unit_price, currency, price_breaks: [{qty, unit_price}],
 stock, lead_time_days, url, datasheet_url} (+ supplier_pn, moq where the supplier gives them).
API keys come from environment variables only. Defaults are UK: GBP, GB, UK storefronts.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, quote_plus

import httpx

from .common import load_json, project_dir, save_json

TIMEOUT_S = 20
CACHE_MAX_AGE_H = 24.0


class SupplierError(Exception):
    """A supplier call failed. The message is safe to show: it never contains a key or a full URL."""


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, headers={"Accept": "application/json"})


def _request(client: httpx.Client, supplier: str, method: str, url: str, **kwargs) -> dict:
    """One HTTP call. Errors are reduced to supplier + status so secrets in URLs never leak."""
    try:
        resp = client.request(method, url, **kwargs)
    except httpx.HTTPError as e:
        raise SupplierError(f"{supplier}: network error ({type(e).__name__})") from None
    if resp.status_code >= 400:
        hint = {401: "check the API key", 403: "key not authorised for this API", 429: "rate limit reached"}
        raise SupplierError(f"{supplier}: HTTP {resp.status_code}"
                            + (f" ({hint[resp.status_code]})" if resp.status_code in hint else ""))
    try:
        return resp.json()
    except ValueError:
        raise SupplierError(f"{supplier}: response was not JSON") from None


def _num(value) -> float | None:
    """'£0.523', '1,234', '56 Days', 12 -> number. European decimal commas are handled."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"\d[\d.,]*", str(value or ""))
    if not m:
        return None
    s = m.group().rstrip(".,")
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = head.replace(",", "") + tail if len(tail) == 3 else head.replace(",", "") + "." + tail
    try:
        return float(s)
    except ValueError:
        return None


def _offer(supplier: str, **kw) -> dict:
    breaks = sorted((b for b in kw.get("price_breaks", []) if b.get("unit_price") is not None),
                    key=lambda b: b["qty"])
    unit = kw.get("unit_price")
    if unit is None and breaks:
        unit = breaks[0]["unit_price"]
    stock = kw.get("stock")
    return {
        "supplier": supplier, "mpn": kw.get("mpn") or "", "manufacturer": kw.get("manufacturer") or "",
        "description": kw.get("description") or "", "unit_price": unit, "currency": kw.get("currency") or "",
        "price_breaks": breaks, "stock": int(stock) if stock is not None else None,
        "lead_time_days": kw.get("lead_time_days"), "url": kw.get("url") or "",
        "datasheet_url": kw.get("datasheet_url") or "",
        "supplier_pn": kw.get("supplier_pn") or "", "moq": kw.get("moq"),
        **({"lead_time_note": kw["lead_time_note"]} if kw.get("lead_time_note") else {}),
    }


# --------------------------------------------------------------------------------------
# Adapters
# --------------------------------------------------------------------------------------

class Adapter:
    name = ""
    env: tuple[str, ...] = ()
    signup = ""

    def missing(self) -> list[str]:
        return [v for v in self.env if not os.environ.get(v)]

    def configured(self) -> bool:
        return not self.missing()

    def not_configured(self) -> dict:
        miss = self.missing()
        return {"ok": False, "supplier": self.name,
                "error": f"{self.name}: set {' and '.join(miss)} (free API key from {self.signup})",
                "missing_env": miss, "signup": self.signup}

    def search(self, client: httpx.Client, query: str, limit: int) -> list[dict]:
        raise NotImplementedError

    def lookup(self, client: httpx.Client, mpn: str) -> list[dict]:
        raise NotImplementedError


class DigiKey(Adapter):
    """DigiKey Product Information API v4, OAuth2 client credentials (2-legged).

    Docs: https://developer.digikey.com/products/product-information-v4/productsearch/keywordsearch
    (Swagger: https://developer.digikey.com/node/2357/oas-download). Token: POST
    https://api.digikey.com/v1/oauth2/token. Search: POST /products/v4/search/keyword with headers
    X-DIGIKEY-Client-Id and X-DIGIKEY-Locale-Site/-Language/-Currency. Lookup: GET
    /products/v4/search/{productNumber}/productdetails.
    """
    name = "digikey"
    env = ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET")
    signup = "https://developer.digikey.com/"
    base = "https://api.digikey.com"
    _token: tuple[str, float] | None = None

    def _headers(self, client: httpx.Client) -> dict:
        if not self._token or self._token[1] < time.time() + 30:
            data = _request(client, self.name, "POST", f"{self.base}/v1/oauth2/token", data={
                "client_id": os.environ["DIGIKEY_CLIENT_ID"], "client_secret": os.environ["DIGIKEY_CLIENT_SECRET"],
                "grant_type": "client_credentials"})
            if not data.get("access_token"):
                raise SupplierError("digikey: token endpoint returned no access_token")
            DigiKey._token = (data["access_token"], time.time() + float(data.get("expires_in", 600)))
        return {"Authorization": f"Bearer {self._token[0]}", "X-DIGIKEY-Client-Id": os.environ["DIGIKEY_CLIENT_ID"],
                "X-DIGIKEY-Locale-Site": "GB", "X-DIGIKEY-Locale-Language": "en", "X-DIGIKEY-Locale-Currency": "GBP"}

    @staticmethod
    def parse_product(p: dict, currency: str = "GBP") -> dict:
        variations = [v for v in p.get("ProductVariations") or [] if v.get("StandardPricing")]
        # The smallest-MOQ packaging (usually cut tape) is the one a prototype BOM buys.
        v = min(variations, key=lambda v: v.get("MinimumOrderQuantity") or 1, default={})
        weeks = _num(p.get("ManufacturerLeadWeeks"))
        return _offer(
            "digikey", mpn=p.get("ManufacturerProductNumber"),
            manufacturer=(p.get("Manufacturer") or {}).get("Name"),
            description=(p.get("Description") or {}).get("ProductDescription"),
            unit_price=p.get("UnitPrice"), currency=currency,
            price_breaks=[{"qty": b.get("BreakQuantity"), "unit_price": b.get("UnitPrice")}
                          for b in v.get("StandardPricing") or []],
            stock=p.get("QuantityAvailable"), lead_time_days=round(weeks * 7) if weeks is not None else None,
            url=p.get("ProductUrl"), datasheet_url=p.get("DatasheetUrl"),
            supplier_pn=v.get("DigiKeyProductNumber"), moq=v.get("MinimumOrderQuantity"))

    @staticmethod
    def _currency(data: dict) -> str:
        return (data.get("SearchLocaleUsed") or {}).get("Currency") or "GBP"

    def search(self, client, query, limit):
        data = _request(client, self.name, "POST", f"{self.base}/products/v4/search/keyword",
                        headers=self._headers(client), json={"Keywords": query[:250], "Limit": limit, "Offset": 0})
        cur = self._currency(data)
        seen, out = set(), []
        for p in (data.get("ExactMatches") or []) + (data.get("Products") or []):
            key = (p.get("ManufacturerProductNumber"), (p.get("Manufacturer") or {}).get("Name"))
            if key not in seen:
                seen.add(key)
                out.append(self.parse_product(p, cur))
        return out[:limit]

    def lookup(self, client, mpn):
        data = _request(client, self.name, "GET",
                        f"{self.base}/products/v4/search/{quote(mpn, safe='')}/productdetails",
                        headers=self._headers(client))
        return [self.parse_product(data["Product"], self._currency(data))] if data.get("Product") else []


class Mouser(Adapter):
    """Mouser Search API v1, API key as the apiKey query parameter.

    Docs: https://api.mouser.com/api/docs/ui/index (Swagger: https://api.mouser.com/api/docs/V1).
    Keyword: POST /api/v1/search/keyword body {"SearchByKeywordRequest": {keyword, records,
    startingRecord, searchOptions}}. Part number: POST /api/v1/search/partnumber body
    {"SearchByPartRequest": {mouserPartNumber, partSearchOptions}}. Prices and currency follow the
    country of the Mouser account that owns the key.
    """
    name = "mouser"
    env = ("MOUSER_API_KEY",)
    signup = "https://www.mouser.co.uk/api-hub/"
    base = "https://api.mouser.com/api/v1/search"

    @staticmethod
    def parse_part(p: dict) -> dict:
        breaks = p.get("PriceBreaks") or []
        return _offer(
            "mouser", mpn=p.get("ManufacturerPartNumber"), manufacturer=p.get("Manufacturer"),
            description=p.get("Description"), currency=(breaks[0].get("Currency") if breaks else ""),
            price_breaks=[{"qty": b.get("Quantity"), "unit_price": _num(b.get("Price"))} for b in breaks],
            stock=_num(p.get("AvailabilityInStock") or p.get("Availability")) or 0,
            lead_time_days=(lambda d: round(d) if d is not None else None)(_num(p.get("LeadTime"))),
            url=p.get("ProductDetailUrl"), datasheet_url=p.get("DataSheetUrl"),
            supplier_pn=p.get("MouserPartNumber"), moq=_num(p.get("Min")))

    def _post(self, client, path: str, body: dict) -> list[dict]:
        data = _request(client, self.name, "POST", f"{self.base}/{path}",
                        params={"apiKey": os.environ["MOUSER_API_KEY"]}, json=body)
        if data.get("Errors"):
            raise SupplierError(f"mouser: {data['Errors'][0].get('Message', 'API error')}")
        return [self.parse_part(p) for p in (data.get("SearchResults") or {}).get("Parts") or []]

    def search(self, client, query, limit):
        return self._post(client, "keyword", {"SearchByKeywordRequest": {
            "keyword": query, "records": min(limit, 50), "startingRecord": 0, "searchOptions": "None"}})[:limit]

    def lookup(self, client, mpn):
        return self._post(client, "partnumber", {"SearchByPartRequest": {
            "mouserPartNumber": mpn, "partSearchOptions": "Exact"}})


class Farnell(Adapter):
    """Farnell / element14 Product Search API (REST), API key as callInfo.apiKey.

    Docs: https://partner.element14.com/docs/Product_Search_API_REST__Description
    GET https://api.element14.com/catalog/products with term=any:<keywords> or
    term=manuPartNum:<mpn>, storeInfo.id=uk.farnell.com, resultsSettings.offset/.numberOfResults/
    .responseGroup, callInfo.responseDataFormat=JSON. UK store prices are GBP ex VAT.
    stock.leastLeadTime is returned as lead_time_raw: the docs do not state its unit.
    """
    name = "farnell"
    env = ("FARNELL_API_KEY",)
    signup = "https://partner.element14.com/"
    url = "https://api.element14.com/catalog/products"
    store = "uk.farnell.com"

    @classmethod
    def parse_product(cls, p: dict) -> dict:
        stock = p.get("stock") or {}
        sheets = p.get("datasheets") or []
        offer = _offer(
            "farnell", mpn=p.get("translatedManufacturerPartNumber"),
            manufacturer=p.get("brandName") or p.get("vendorName"), description=p.get("displayName"),
            currency="GBP",
            price_breaks=[{"qty": b.get("from"), "unit_price": b.get("cost")} for b in p.get("prices") or []],
            stock=stock.get("level"), lead_time_days=None,
            url=p.get("productURL") or f"https://{cls.store}/search?st={quote_plus(str(p.get('sku', '')))}",
            datasheet_url=sheets[0].get("url") if sheets else "",
            supplier_pn=p.get("sku"), moq=p.get("translatedMinimumOrderQuality"),
            lead_time_note="Farnell leastLeadTime unit is not documented; see lead_time_raw")
        offer["lead_time_raw"] = stock.get("leastLeadTime")
        return offer

    def _get(self, client, term: str, limit: int) -> list[dict]:
        data = _request(client, self.name, "GET", self.url, params={
            "term": term, "storeInfo.id": self.store, "resultsSettings.offset": 0,
            "resultsSettings.numberOfResults": limit, "resultsSettings.responseGroup": "large",
            "callInfo.responseDataFormat": "JSON", "callInfo.apiKey": os.environ["FARNELL_API_KEY"]})
        # The wrapper key depends on the search type (keywordSearchReturn, ...): take whichever has products.
        body = next((v for k, v in data.items() if k.endswith("Return") and isinstance(v, dict)), {})
        return [self.parse_product(p) for p in body.get("products") or []]

    def search(self, client, query, limit):
        return self._get(client, f"any:{query}", limit)

    def lookup(self, client, mpn):
        return self._get(client, f"manuPartNum:{mpn}", 10)


ADAPTERS: dict[str, Adapter] = {a.name: a for a in (DigiKey(), Mouser(), Farnell())}


# --------------------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------------------

def _cache_dir(project: str) -> Path:
    if project:
        return project_dir(project, create=True) / "out" / "sourcing" / "cache"
    return Path(os.environ.get("TB_CACHE_DIR") or Path.home() / ".cache" / "3d-agent-toolbox") / "sourcing"


def _cache_file(project: str, supplier: str, kind: str, query: str, limit: int) -> Path:
    digest = hashlib.sha1(f"{supplier}|{kind}|{query.strip().lower()}|{limit}".encode()).hexdigest()[:16]
    return _cache_dir(project) / f"{supplier}-{kind}-{digest}.json"


def _fetch(adapter: Adapter, kind: str, query: str, limit: int, project: str, max_age_h: float) -> dict:
    """Offers from cache if fresh, otherwise from the supplier (then cached with a timestamp)."""
    f = _cache_file(project, adapter.name, kind, query, limit)
    hit = load_json(f)
    if hit and max_age_h > 0 and time.time() - hit.get("fetched_at", 0) < max_age_h * 3600:
        return {"offers": hit["offers"], "cached": True, "fetched_at": hit["fetched_at"]}
    with _client() as client:
        offers = adapter.search(client, query, limit) if kind == "search" else adapter.lookup(client, query)
    now = time.time()
    save_json(f, {"supplier": adapter.name, "kind": kind, "query": query, "fetched_at": now, "offers": offers})
    return {"offers": offers, "cached": False, "fetched_at": now}


# --------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------

# Search-page URL patterns. Each was opened once on 2026-11-10 and resolved to that site's results
# page, except Octopart, which answered with a bot check (the pattern is its normal search URL).
_LINKS = {
    "digikey": "https://www.digikey.co.uk/en/products/result?keywords={q}",
    "mouser": "https://www.mouser.co.uk/c/?q={q}",
    "farnell": "https://uk.farnell.com/search?st={q}",
    "rs": "https://uk.rs-online.com/web/c/?searchTerm={q}",
    "lcsc": "https://www.lcsc.com/search?q={q}",
    "accu": "https://www.accu.co.uk/search?q={q}",
    "octopart": "https://octopart.com/search?q={q}",
}


def sourcing_links(query: str) -> dict:
    """Ready-made search URLs for a part number or keywords. Needs no API key and no network.

    Returns links for DigiKey UK, Mouser UK, Farnell UK, RS, LCSC, Accu (fasteners and hardware)
    and Octopart (cross-supplier comparison).
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "query is empty"}
    return {"ok": True, "query": q, "links": {name: url.format(q=quote_plus(q)) for name, url in _LINKS.items()}}


def sourcing_status() -> dict:
    """Which supplier APIs are configured, and for the others the env variables to set and where to sign up."""
    rows = [{"supplier": a.name, "configured": a.configured(), "env": list(a.env), "missing_env": a.missing(),
             "signup": a.signup} for a in ADAPTERS.values()]
    return {"ok": True, "suppliers": rows, "configured": [r["supplier"] for r in rows if r["configured"]],
            "links_only": ["rs", "lcsc", "accu", "octopart"],
            "note": "With no keys set, sourcing_links still gives search URLs for every supplier."}


def _pick(suppliers) -> tuple[list[Adapter], list[dict]]:
    """Adapters to query and the not-configured notices for the rest."""
    if suppliers in ("auto", "", None):
        names = list(ADAPTERS)
    else:
        names = [s.strip().lower() for s in (suppliers.split(",") if isinstance(suppliers, str) else suppliers)]
    unknown = [n for n in names if n not in ADAPTERS]
    if unknown:
        raise ValueError(f"Unknown supplier(s) {unknown}. Options: {list(ADAPTERS)} or 'auto'")
    chosen = [ADAPTERS[n] for n in names]
    return [a for a in chosen if a.configured()], [a.not_configured() for a in chosen if not a.configured()]


def _run(kind: str, query: str, suppliers, limit: int, project: str, max_age_h: float) -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "query is empty"}
    try:
        active, skipped = _pick(suppliers)
        if project:
            project_dir(project, create=True)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    links = sourcing_links(query)["links"]
    if not active:
        return {"ok": False, "error": "No supplier API is configured. " + " ".join(s["error"] for s in skipped),
                "not_configured": skipped, "links": links}
    offers, errors, sources = [], [], []
    for a in active:
        try:
            got = _fetch(a, kind, query, limit, project, max_age_h)
        except SupplierError as e:
            errors.append({"supplier": a.name, "error": str(e)})
            continue
        offers += got["offers"]
        sources.append({"supplier": a.name, "results": len(got["offers"]), "cached": got["cached"],
                        "fetched_at": got["fetched_at"]})
    return {"ok": bool(sources), "query": query, "offers": offers, "sources": sources, "errors": errors,
            "not_configured": skipped, "links": links,
            **({} if sources else {"error": "; ".join(e["error"] for e in errors)})}


def part_search(query: str, suppliers: str = "auto", limit: int = 5, project: str = "",
                max_age_h: float = CACHE_MAX_AGE_H) -> dict:
    """Search supplier catalogues by keyword. Returns offers in the common shape plus search links.

    suppliers: "auto" (every configured API) or a comma list of digikey, mouser, farnell. limit is
    per supplier (max 50). Results are cached for max_age_h hours (0 = always refetch) under the
    project's out/sourcing/ if project is given. Prices are per unit, ex VAT, in the offer's currency.
    """
    return _run("search", query, suppliers, max(1, min(int(limit), 50)), project, max_age_h)


def _same_mpn(a: str, b: str) -> bool:
    def norm(s):
        return re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return norm(a) == norm(b)


def part_lookup(mpn: str, suppliers: str = "auto", project: str = "", max_age_h: float = CACHE_MAX_AGE_H) -> dict:
    """Look up one manufacturer part number at each configured supplier.

    Returns offers in the common shape; each has exact=True when the supplier's part number
    matches mpn (ignoring punctuation and case).
    """
    res = _run("lookup", mpn, suppliers, 10, project, max_age_h)
    for o in res.get("offers", []):
        o["exact"] = _same_mpn(o["mpn"], mpn)
    return res


def _price_at(offer: dict, qty: int) -> dict | None:
    """Unit price and order quantity for qty units, honouring price breaks and the minimum order."""
    breaks = offer.get("price_breaks") or []
    if not breaks:
        if offer.get("unit_price") is None:
            return None
        breaks = [{"qty": 1, "unit_price": offer["unit_price"]}]
    order_qty = max(qty, int(offer.get("moq") or 0), int(breaks[0]["qty"] or 1))
    unit = [b for b in breaks if b["qty"] <= order_qty][-1]["unit_price"]
    return {"order_qty": order_qty, "unit_price": unit, "total": round(unit * order_qty, 4)}


def part_best_price(mpn: str, qty: int = 1, suppliers: str = "auto", project: str = "",
                    max_age_h: float = CACHE_MAX_AGE_H) -> dict:
    """Compare the price of one manufacturer part number across the configured suppliers for qty units.

    Returns the cheapest exact-match offer that has stock for qty (best), and every offer ranked by
    total cost with order_qty (raised to the minimum order where needed), unit_price and total.
    Offers in a currency other than the best one's are listed but not ranked against it.
    """
    if qty < 1:
        return {"ok": False, "error": "qty must be at least 1"}
    res = part_lookup(mpn, suppliers, project, max_age_h)
    if not res["ok"]:
        return res
    ranked = []
    for o in res["offers"]:
        price = _price_at(o, qty) if o.get("exact") else None
        if price:
            ranked.append({**o, **price, "in_stock": o["stock"] is not None and o["stock"] >= qty})
    if not ranked:
        return {"ok": False, "error": f"No exact match for {mpn!r} with a price at the configured suppliers",
                "offers": res["offers"], "errors": res["errors"], "not_configured": res["not_configured"],
                "links": res["links"]}
    currency = "GBP" if any(o["currency"] == "GBP" for o in ranked) else ranked[0]["currency"]
    comparable = sorted((o for o in ranked if o["currency"] == currency),
                        key=lambda o: (not o["in_stock"], o["total"]))
    return {"ok": True, "mpn": mpn, "qty": qty, "currency": currency, "best": comparable[0],
            "ranked": comparable, "other_currency": [o for o in ranked if o["currency"] != currency],
            "errors": res["errors"], "not_configured": res["not_configured"], "links": res["links"]}


def register(mcp) -> None:
    for fn in (part_search, part_lookup, part_best_price, sourcing_status, sourcing_links):
        mcp.tool()(fn)
