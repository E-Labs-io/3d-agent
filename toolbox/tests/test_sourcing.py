"""Sourcing tests. Offline: supplier responses are mocks built from each supplier's documented schema.

Live calls to DigiKey, Mouser and Farnell are NOT exercised here (no API keys on the build machine).
"""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

import tb.common as common
from tb import sourcing as s

ENV = ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET", "MOUSER_API_KEY", "FARNELL_API_KEY")

# Shapes follow the DigiKey ProductSearch v4 Swagger (KeywordResponse / Product / ProductVariation / PriceBreak).
DIGIKEY_PRODUCT = {
    "Description": {"ProductDescription": "IC REG LINEAR 5V 1.5A TO220AB", "DetailedDescription": "Linear regulator"},
    "Manufacturer": {"Id": 497, "Name": "STMicroelectronics"},
    "ManufacturerProductNumber": "L7805CV",
    "UnitPrice": 0.52,
    "ProductUrl": "https://www.digikey.co.uk/en/products/detail/stmicroelectronics/L7805CV/585964",
    "DatasheetUrl": "https://www.st.com/resource/en/datasheet/l78.pdf",
    "QuantityAvailable": 48211,
    "ManufacturerLeadWeeks": "12",
    "ProductVariations": [
        {"DigiKeyProductNumber": "497-1443-5-ND", "PackageType": {"Id": 2, "Name": "Tube"},
         "MinimumOrderQuantity": 1, "QuantityAvailableforPackageType": 48211,
         "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": 0.52, "TotalPrice": 0.52},
                             {"BreakQuantity": 10, "UnitPrice": 0.431, "TotalPrice": 4.31},
                             {"BreakQuantity": 100, "UnitPrice": 0.3105, "TotalPrice": 31.05}]},
        {"DigiKeyProductNumber": "497-1443-BULK", "PackageType": {"Id": 3, "Name": "Bulk"},
         "MinimumOrderQuantity": 1000, "StandardPricing": [{"BreakQuantity": 1000, "UnitPrice": 0.25, "TotalPrice": 250}]},
    ],
}
DIGIKEY_KEYWORD = {"Products": [DIGIKEY_PRODUCT], "ProductsCount": 1, "ExactMatches": [DIGIKEY_PRODUCT],
                   "SearchLocaleUsed": {"Site": "GB", "Language": "en", "Currency": "GBP"}}
DIGIKEY_DETAILS = {"Product": DIGIKEY_PRODUCT, "SearchLocaleUsed": {"Site": "GB", "Language": "en", "Currency": "GBP"}}

# Shape follows the Mouser Search API V1 Swagger (SearchResponseRoot / MouserPart / Pricebreak).
MOUSER_RESPONSE = {"Errors": [], "SearchResults": {"NumberOfResult": 1, "Parts": [{
    "Availability": "6384 In Stock", "AvailabilityInStock": "6384",
    "DataSheetUrl": "https://www.mouser.co.uk/datasheet/2/389/l78-1849632.pdf",
    "Description": "Linear Voltage Regulators 5.0V 1.5A Positive", "LeadTime": "56 Days",
    "Manufacturer": "STMicroelectronics", "ManufacturerPartNumber": "L7805CV", "Min": "1", "Mult": "1",
    "MouserPartNumber": "511-L7805CV",
    "PriceBreaks": [{"Quantity": 1, "Price": "£0.48", "Currency": "GBP"},
                    {"Quantity": 10, "Price": "£0.412", "Currency": "GBP"},
                    {"Quantity": 100, "Price": "£0.33", "Currency": "GBP"}],
    "ProductDetailUrl": "https://www.mouser.co.uk/ProductDetail/511-L7805CV"}]}}

# Shape follows the JSON sample in the element14 Product Search API description (large response group).
FARNELL_RESPONSE = {"manufacturerPartNumberSearchReturn": {"numberOfResults": 1, "products": [{
    "sku": "9756078", "displayName": "STMICROELECTRONICS - L7805CV - Linear Voltage Regulator, 5V, 1.5A, TO-220",
    "brandName": "STMICROELECTRONICS", "translatedManufacturerPartNumber": "L7805CV",
    "translatedMinimumOrderQuality": 5,
    "datasheets": [{"type": "T", "description": "Technical Data Sheet", "url": "https://www.farnell.com/datasheets/70315.pdf"}],
    "prices": [{"to": 9, "from": 5, "cost": 0.55}, {"to": 99, "from": 10, "cost": 0.40},
               {"to": 1000000000, "from": 100, "cost": 0.29}],
    "stock": {"level": 518, "leastLeadTime": 63, "status": 1}}]}}


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    for v in ENV:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("TB_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(s.DigiKey, "_token", None)


@pytest.fixture
def api(monkeypatch):
    """Fake supplier servers. Records every request so tests can assert on what was sent."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        host, path = request.url.host, request.url.path
        if host == "api.digikey.com" and path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 599, "token_type": "Bearer"})
        if host == "api.digikey.com" and path == "/products/v4/search/keyword":
            return httpx.Response(200, json=DIGIKEY_KEYWORD)
        if host == "api.digikey.com" and path.endswith("/productdetails"):
            return httpx.Response(200, json=DIGIKEY_DETAILS)
        if host == "api.mouser.com":
            return httpx.Response(200, json=MOUSER_RESPONSE)
        if host == "api.element14.com":
            return httpx.Response(200, json=FARNELL_RESPONSE)
        return httpx.Response(404)

    monkeypatch.setattr(s, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return calls


def all_keys(monkeypatch):
    for v in ENV:
        monkeypatch.setenv(v, f"secret-{v.lower()}")


SHAPE = {"supplier", "mpn", "manufacturer", "description", "unit_price", "currency", "price_breaks", "stock",
         "lead_time_days", "url", "datasheet_url"}


def test_links_need_no_keys_and_encode_the_query():
    r = s.sourcing_links("M3 x 8 cap screw")
    assert r["ok"]
    assert set(r["links"]) == {"digikey", "mouser", "farnell", "rs", "lcsc", "accu", "octopart"}
    assert r["links"]["accu"] == "https://www.accu.co.uk/search?q=M3+x+8+cap+screw"
    assert r["links"]["digikey"] == "https://www.digikey.co.uk/en/products/result?keywords=M3+x+8+cap+screw"
    assert r["links"]["farnell"] == "https://uk.farnell.com/search?st=M3+x+8+cap+screw"
    assert not s.sourcing_links("  ")["ok"]


def test_status_and_missing_keys_name_the_variable_and_signup():
    st = s.sourcing_status()
    assert st["ok"] and st["configured"] == []
    r = s.part_search("L7805CV")
    assert r["ok"] is False
    for var in ENV:
        assert var in r["error"]
    assert {n["supplier"]: n["signup"] for n in r["not_configured"]} == {
        "digikey": "https://developer.digikey.com/", "mouser": "https://www.mouser.co.uk/api-hub/",
        "farnell": "https://partner.element14.com/"}
    assert r["links"]["mouser"].endswith("q=L7805CV")  # a BOM still gets links


def test_partial_digikey_credentials_are_not_configured(monkeypatch):
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", "id-only")
    assert s.ADAPTERS["digikey"].missing() == ["DIGIKEY_CLIENT_SECRET"]


def test_parsers_return_the_common_shape():
    dk = s.DigiKey.parse_product(DIGIKEY_PRODUCT)
    mo = s.Mouser.parse_part(MOUSER_RESPONSE["SearchResults"]["Parts"][0])
    fa = s.Farnell.parse_product(FARNELL_RESPONSE["manufacturerPartNumberSearchReturn"]["products"][0])
    for o in (dk, mo, fa):
        assert SHAPE <= set(o)
        assert o["mpn"] == "L7805CV"
    assert dk["unit_price"] == 0.52 and dk["stock"] == 48211 and dk["lead_time_days"] == 84
    assert dk["supplier_pn"] == "497-1443-5-ND" and dk["moq"] == 1  # smallest-MOQ packaging chosen
    assert dk["price_breaks"] == [{"qty": 1, "unit_price": 0.52}, {"qty": 10, "unit_price": 0.431},
                                  {"qty": 100, "unit_price": 0.3105}]
    assert mo["unit_price"] == 0.48 and mo["currency"] == "GBP" and mo["stock"] == 6384 and mo["lead_time_days"] == 56
    assert fa["unit_price"] == 0.55 and fa["stock"] == 518 and fa["moq"] == 5
    assert fa["lead_time_days"] is None and fa["lead_time_raw"] == 63  # unit undocumented: not converted
    assert fa["datasheet_url"].endswith("70315.pdf") and fa["url"] == "https://uk.farnell.com/search?st=9756078"


@pytest.mark.parametrize("text,value", [("£0.523", 0.523), ("1,234", 1234.0), ("0,52 €", 0.52),
                                        ("1.234,50 €", 1234.5), ("$1,234.50", 1234.5), ("56 Days", 56.0),
                                        ("None", None), (7, 7.0)])
def test_number_parsing(text, value):
    assert s._num(text) == value


def test_search_sends_documented_requests(monkeypatch, api):
    all_keys(monkeypatch)
    r = s.part_search("L7805CV", limit=3)
    assert r["ok"] and [o["supplier"] for o in r["offers"]] == ["digikey", "mouser", "farnell"]
    by = {(c.url.host, c.url.path): c for c in api}

    token = by[("api.digikey.com", "/v1/oauth2/token")]
    assert b"grant_type=client_credentials" in token.content and b"client_id=secret-digikey_client_id" in token.content
    dk = by[("api.digikey.com", "/products/v4/search/keyword")]
    assert dk.method == "POST" and json.loads(dk.content) == {"Keywords": "L7805CV", "Limit": 3, "Offset": 0}
    assert dk.headers["Authorization"] == "Bearer tok-123"
    assert dk.headers["X-DIGIKEY-Client-Id"] == "secret-digikey_client_id"
    assert (dk.headers["X-DIGIKEY-Locale-Site"], dk.headers["X-DIGIKEY-Locale-Currency"]) == ("GB", "GBP")

    mo = by[("api.mouser.com", "/api/v1/search/keyword")]
    assert mo.url.params["apiKey"] == "secret-mouser_api_key"
    assert json.loads(mo.content)["SearchByKeywordRequest"]["keyword"] == "L7805CV"

    fa = by[("api.element14.com", "/catalog/products")]
    assert fa.url.params["term"] == "any:L7805CV" and fa.url.params["storeInfo.id"] == "uk.farnell.com"
    assert fa.url.params["callInfo.apiKey"] == "secret-farnell_api_key"
    assert fa.url.params["callInfo.responseDataFormat"] == "JSON"


def test_lookup_uses_part_number_endpoints(monkeypatch, api):
    all_keys(monkeypatch)
    r = s.part_lookup("l7805-cv")
    assert r["ok"] and all(o["exact"] for o in r["offers"])  # punctuation and case ignored
    paths = {(c.url.host, c.url.path) for c in api}
    assert ("api.digikey.com", "/products/v4/search/l7805-cv/productdetails") in paths
    assert ("api.mouser.com", "/api/v1/search/partnumber") in paths
    farnell = next(c for c in api if c.url.host == "api.element14.com")
    assert farnell.url.params["term"] == "manuPartNum:l7805-cv"


def test_cache_saves_quota(monkeypatch, api):
    monkeypatch.setenv("MOUSER_API_KEY", "k")
    first = s.part_search("L7805CV", suppliers="mouser")
    again = s.part_search("L7805CV", suppliers="mouser")
    assert len(api) == 1
    assert first["sources"][0]["cached"] is False and again["sources"][0]["cached"] is True
    assert again["offers"] == first["offers"]
    s.part_search("L7805CV", suppliers="mouser", max_age_h=0)  # forced refresh
    assert len(api) == 2


def test_cache_goes_in_the_project_when_given(monkeypatch, api, tmp_path):
    monkeypatch.setenv("MOUSER_API_KEY", "k")
    s.part_search("L7805CV", suppliers="mouser", project="demo")
    files = list((tmp_path / "projects" / "demo" / "out" / "sourcing" / "cache").glob("mouser-search-*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text())["fetched_at"] > 0


def test_best_price_hand_calculation(monkeypatch, api):
    all_keys(monkeypatch)
    r = s.part_best_price("L7805CV", qty=25)
    assert r["ok"] and r["currency"] == "GBP"
    totals = {o["supplier"]: (o["order_qty"], o["unit_price"], o["total"]) for o in r["ranked"]}
    # 25 off: DigiKey 10+ break 0.431 -> 10.775; Mouser 10+ break 0.412 -> 10.30; Farnell 10+ break 0.40 -> 10.00
    assert totals == {"digikey": (25, 0.431, 10.775), "mouser": (25, 0.412, 10.3), "farnell": (25, 0.40, 10.0)}
    assert r["best"]["supplier"] == "farnell"
    one = s.part_best_price("L7805CV", qty=1)
    # 1 off: Farnell's minimum order of 5 at 0.55 = 2.75 loses to Mouser 0.48
    assert one["best"]["supplier"] == "mouser" and one["best"]["total"] == 0.48
    farnell = next(o for o in one["ranked"] if o["supplier"] == "farnell")
    assert farnell["order_qty"] == 5 and farnell["total"] == 2.75


def test_out_of_stock_ranks_last(monkeypatch, api):
    all_keys(monkeypatch)
    r = s.part_best_price("L7805CV", qty=600)  # Farnell has 518
    assert r["ranked"][-1]["supplier"] == "farnell" and r["ranked"][-1]["in_stock"] is False
    # In stock: DigiKey 600 x 0.3105 = 186.30 beats Mouser 600 x 0.33 = 198.00
    assert r["best"]["supplier"] == "digikey" and r["best"]["total"] == pytest.approx(186.3)


def test_supplier_error_never_leaks_the_key(monkeypatch):
    monkeypatch.setenv("MOUSER_API_KEY", "SUPER-SECRET-KEY")
    monkeypatch.setattr(s, "_client", lambda: httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(401, json={"Errors": []}))))
    r = s.part_search("L7805CV", suppliers="mouser")
    assert r["ok"] is False and "HTTP 401" in r["error"]
    assert "SUPER-SECRET-KEY" not in json.dumps(r)


def test_one_supplier_failing_does_not_sink_the_rest(monkeypatch):
    all_keys(monkeypatch)

    def handler(request):
        if request.url.host == "api.mouser.com":
            return httpx.Response(200, json=MOUSER_RESPONSE)
        return httpx.Response(500)

    monkeypatch.setattr(s, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    r = s.part_search("L7805CV")
    assert r["ok"] and [o["supplier"] for o in r["offers"]] == ["mouser"]
    assert {e["supplier"] for e in r["errors"]} == {"digikey", "farnell"}


def test_unknown_supplier_and_empty_query():
    assert "Unknown supplier" in s.part_search("x", suppliers="acme")["error"]
    assert not s.part_search("")["ok"]
    assert not s.part_best_price("x", qty=0)["ok"]
