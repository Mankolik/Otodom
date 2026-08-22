# Otodom Share Code

A phone-friendly way to give ChatGPT the **exact** data from an Otodom listing without uploading screenshots or files.

## How it works

1. Open this repository on GitHub.
2. Open **Actions**.
3. Choose **Export Otodom listing**.
4. Tap **Run workflow**.
5. Paste the exact `otodom.pl` offer URL.
6. Run it.
7. When the job finishes, open its summary and copy the code, for example:

```text
OTO-ID4CJVk
```

Send only that code to ChatGPT.

The workflow stores the complete listing snapshot as:

```text
exports/ID4CJVk.json
```

The code uses Otodom's own offer ID, so it is deterministic and unique to that listing.

## What is stored

The JSON contains:

- exact source URL and scrape timestamp
- title and Otodom identifiers
- price, currency and `czynsz`
- deposit when exposed
- area, rooms, floor, build year, building type
- equipment
- extras
- media/utilities
- security
- all secondary `target` fields
- Otodom characteristics
- street/city/district-level location data
- advertiser/agency name when exposed
- description
- image metadata

The committed export deliberately omits precise coordinates, phone/e-mail contact data and the full raw ad payload, making it safer for a public repository while preserving the fields needed for listing analysis.

## Privacy

A **private repository is still recommended** if you plan to archive many listings.

## Re-running a listing

Running the same listing again updates the same `exports/<ID>.json` snapshot, so the share code stays the same.

## Technical notes

The workflow uses Playwright/Chromium from GitHub Actions and reads the listing's embedded `__NEXT_DATA__` payload. It makes only a few attempts and is intended for low-volume personal use.

If Otodom changes its site structure or blocks GitHub-hosted browsers, the Action will fail rather than substituting a different listing.
