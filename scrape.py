#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

OTODOM_HOSTS = {"otodom.pl", "www.otodom.pl"}
ID_RE = re.compile(r"(ID[A-Za-z0-9]+)(?:[/?#]|$)")


def require_otodom_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in {"http", "https"} or p.hostname not in OTODOM_HOSTS:
        raise SystemExit("Only https://www.otodom.pl/... listing URLs are accepted.")


def listing_id_from_url(url: str) -> str | None:
    m = ID_RE.search(url)
    return m.group(1) if m else None


def clean_html_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)


def find_ad(next_data: dict[str, Any]) -> dict[str, Any]:
    ad = next_data.get("props", {}).get("pageProps", {}).get("ad")
    if isinstance(ad, dict) and ad:
        return ad

    candidates: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if "title" in obj and isinstance(obj.get("target"), dict):
                candidates.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(next_data)
    if not candidates:
        raise RuntimeError("Could not find the listing payload in __NEXT_DATA__.")
    return max(candidates, key=lambda x: len(json.dumps(x, ensure_ascii=False)))


def map_characteristics(ad: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in ad.get("characteristics") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("label") or f"item_{len(result)+1}")
        result[key] = item
    return result


def normalize(ad: dict[str, Any], source_url: str) -> dict[str, Any]:
    target = ad.get("target") if isinstance(ad.get("target"), dict) else {}
    location = ad.get("location") if isinstance(ad.get("location"), dict) else {}
    address = location.get("address") if isinstance(location.get("address"), dict) else {}
    owner = ad.get("owner") if isinstance(ad.get("owner"), dict) else {}
    agency = ad.get("agency") if isinstance(ad.get("agency"), dict) else {}
    prop = ad.get("property") if isinstance(ad.get("property"), dict) else {}

    street = address.get("street")
    if isinstance(street, dict):
        street = street.get("name")

    reverse = location.get("reverseGeocoding")
    reverse_locations = reverse.get("locations", []) if isinstance(reverse, dict) else []
    geo_levels = {}
    for item in reverse_locations or []:
        if isinstance(item, dict):
            geo_levels[str(item.get("locationLevel") or len(geo_levels) + 1)] = item

    images = ad.get("images") or ad.get("photos") or []
    if not isinstance(images, list):
        images = []

    building_props = prop.get("buildingProperties")
    if not isinstance(building_props, dict):
        building_props = {}

    return {
        "schema_version": 1,
        "source": {
            "site": "otodom.pl",
            "url": source_url,
            "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "identity": {
            "otodom_id_from_url": listing_id_from_url(source_url),
            "id": ad.get("id"),
            "slug": ad.get("slug"),
            "title": clean_html_text(ad.get("title")),
            "status": ad.get("status"),
            "advert_type": ad.get("advertType"),
            "market": ad.get("market"),
        },
        "main": {
            "price": target.get("Price"),
            "currency": target.get("Currency") or ad.get("currency"),
            "czynsz": target.get("Rent"),
            "deposit": (
                target.get("Deposit")
                or target.get("Deposit_amount")
                or target.get("Security_deposit")
            ),
            "area_m2": target.get("Area"),
            "rooms": target.get("Rooms_num"),
            "floor": target.get("Floor_no"),
            "building_floors": target.get("Building_floors_num"),
            "build_year": target.get("Build_year"),
            "property_type": target.get("ProperType"),
            "building_type": target.get("Building_type"),
            "building_material": target.get("Building_material"),
            "heating": building_props.get("heating") or target.get("Heating"),
            "windows": target.get("Windows_type"),
            "price_per_m2": target.get("Price_per_m"),
        },
        "features": {
            "equipment": target.get("Equipment_types"),
            "extras": target.get("Extras_types"),
            "media": target.get("Media_types"),
            "security": target.get("Security_types"),
            "characteristics": map_characteristics(ad),
            "target_all": target,
        },
        "location": {
            "street": street,
            "city": target.get("City"),
            "province": target.get("Province"),
            "reverse_geocoding": geo_levels,
        },
        "advertiser": {
            "owner_name": owner.get("name") or owner.get("displayName"),
            "agency_name": agency.get("name") or agency.get("displayName"),
        },
        "dates": {
            "created_at": ad.get("createdAt"),
            "modified_at": ad.get("modifiedAt"),
            "pushed_up_at": ad.get("pushedUpAt"),
        },
        "description": clean_html_text(ad.get("description")),
        "images": images,
        "links": ad.get("links"),
    }


async def extract_next_data(page) -> dict[str, Any]:
    text = await page.locator("script#__NEXT_DATA__").text_content(timeout=25_000)
    if not text:
        raise RuntimeError("__NEXT_DATA__ was empty.")
    return json.loads(text)


async def scrape(url: str) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            viewport={"width": 1440, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
                "DNT": "1",
            },
        )
        page = await context.new_page()

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(2500 + attempt * 1500)

                title = await page.title()
                body_start = (await page.locator("body").inner_text())[:1000]
                if "403" in title or "Access Denied" in body_start:
                    raise RuntimeError("Otodom returned an access-denied page.")

                next_data = await extract_next_data(page)
                await browser.close()
                return next_data
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await page.wait_for_timeout(3000 * (attempt + 1))
                    await page.reload(wait_until="domcontentloaded", timeout=60_000)

        diagnostic = {
            "title": await page.title(),
            "url": page.url,
            "body_prefix": (await page.locator("body").inner_text())[:1500],
        }
        await browser.close()
        raise RuntimeError(
            f"Failed to read Otodom after 3 attempts: {last_error}\n"
            f"Diagnostic: {json.dumps(diagnostic, ensure_ascii=False)}"
        )


def share_code(url: str, ad: dict[str, Any]) -> str:
    oid = listing_id_from_url(url)
    if oid:
        return f"OTO-{oid}"

    payload = str(ad.get("id") or ad.get("slug") or url).encode("utf-8")
    return "OTO-" + hashlib.sha256(payload).hexdigest()[:10].upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--output-dir", default="exports")
    args = ap.parse_args()

    require_otodom_url(args.url)
    next_data = asyncio.run(scrape(args.url))
    ad = find_ad(next_data)
    data = normalize(ad, args.url)

    code = share_code(args.url, ad)
    data["share_code"] = code

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    file_id = code.removeprefix("OTO-")
    output_path = output_dir / f"{file_id}.json"
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    Path("share_code.txt").write_text(code + "\n", encoding="utf-8")
    print(f"SHARE_CODE={code}")
    print(f"OUTPUT_FILE={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
