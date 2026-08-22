#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def scalar(value: Any) -> Any:
    if isinstance(value, list):
        if len(value) == 1:
            return value[0]
        return value
    return value


def money_sum(*values: Any) -> float | int | None:
    total = 0.0
    found = False
    for value in values:
        try:
            if value is None or value == "":
                continue
            total += float(value)
            found = True
        except (TypeError, ValueError):
            pass
    if not found:
        return None
    return int(total) if total.is_integer() else round(total, 2)


def place_name(reverse: dict[str, Any], key: str) -> str | None:
    item = reverse.get(key)
    return item.get("name") if isinstance(item, dict) else None


def load_entry(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    identity = data.get("identity") or {}
    main = data.get("main") or {}
    location = data.get("location") or {}
    reverse = location.get("reverse_geocoding") or {}
    advertiser = data.get("advertiser") or {}
    source = data.get("source") or {}

    listing_id = identity.get("otodom_id_from_url") or path.stem
    price = main.get("price")
    czynsz = main.get("czynsz")
    fixed_total = money_sum(price, czynsz)

    district = place_name(reverse, "district")
    neighbourhood = place_name(reverse, "residential")
    street = location.get("street")
    area = main.get("area_m2")
    rooms = scalar(main.get("rooms"))

    location_label = " · ".join(
        str(x) for x in (street, neighbourhood or district) if x
    )
    label_parts = [location_label or identity.get("title") or listing_id]
    if area:
        label_parts.append(f"{area} m²")
    if rooms:
        label_parts.append(f"{rooms} pok.")

    return {
        "id": listing_id,
        "label": " · ".join(label_parts),
        "title": identity.get("title"),
        "street": street,
        "district": district,
        "neighbourhood": neighbourhood,
        "area_m2": area,
        "rooms": rooms,
        "price": price,
        "czynsz": czynsz,
        "fixed_monthly_total": fixed_total,
        "advert_type": identity.get("advert_type"),
        "advertiser": advertiser.get("owner_name") or advertiser.get("agency_name"),
        "scraped_at_utc": source.get("scraped_at_utc"),
        "source_url": source.get("url"),
        "file": path.as_posix(),
    }


def write_markdown(entries: list[dict[str, Any]], output: Path) -> None:
    lines = [
        "# Saved Otodom listings",
        "",
        "This file is rebuilt automatically after every export.",
        "",
        "| Saved | Listing | Area | Rooms | Rent | Czynsz | Fixed total | ID |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for e in entries:
        saved = (e.get("scraped_at_utc") or "")[:10] or "—"
        title = (e.get("label") or e.get("title") or "—").replace("|", "\\|")
        area = e.get("area_m2") or "—"
        rooms = e.get("rooms") or "—"
        price = f"{e['price']} zł" if e.get("price") is not None else "—"
        czynsz = f"{e['czynsz']} zł" if e.get("czynsz") is not None else "—"
        total = (
            f"{e['fixed_monthly_total']} zł"
            if e.get("fixed_monthly_total") is not None
            else "—"
        )
        lines.append(
            f"| {saved} | {title} | {area} | {rooms} | {price} | {czynsz} | {total} | {e['id']} |"
        )

    lines += [
        "",
        "You do not need to remember the ID. Ask ChatGPT to list or find saved Otodom offers by street, district, size, price, title, or recency.",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    export_dir = Path("exports")
    export_dir.mkdir(exist_ok=True)

    entries: list[dict[str, Any]] = []
    for path in export_dir.glob("*.json"):
        if path.name == "index.json":
            continue
        entry = load_entry(path)
        if entry:
            entries.append(entry)

    entries.sort(key=lambda x: x.get("scraped_at_utc") or "", reverse=True)

    index = {
        "schema_version": 1,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "listings": entries,
    }
    (export_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(entries, export_dir / "index.md")

    print(f"Catalog rebuilt: {len(entries)} listings")
    for e in entries:
        print(f"- {e['id']}: {e['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
