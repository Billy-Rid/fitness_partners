"""
Tennessee Secretary of State — TNCaB business entity search.
New portal (replaced TNBEAR): https://tncab.tnsos.gov/business-entity-search

Uses Playwright because the new portal is a JavaScript app.
"""

import re
import time
import random
import difflib
from playwright.sync_api import sync_playwright

TNCAB_URL = "https://tncab.tnsos.gov/business-entity-search"

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
"""


def _best_match(query: str, results: list[dict]) -> dict | None:
    if not results:
        return None
    if len(results) == 1:
        return results[0]
    query_clean = query.lower().strip()
    return max(
        results,
        key=lambda r: difflib.SequenceMatcher(
            None, query_clean, r.get("registered_name", "").lower()
        ).ratio(),
    )


def _search_one(page, name: str) -> list[dict]:
    """Type a business name into TNCaB and return matching rows."""
    try:
        page.goto(TNCAB_URL, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.uniform(1.5, 2.5))

        # Find and fill the search box
        search_box = (
            page.get_by_placeholder(re.compile(r"search|entity|business|name", re.I))
            or page.locator("input[type='text']").first
        )
        search_box.fill("")
        search_box.type(name, delay=80)
        time.sleep(0.5)

        # Submit — try Enter key first, then look for a Search button
        search_box.press("Enter")
        time.sleep(random.uniform(2.0, 3.5))

        # If Enter didn't work, click the search button
        for label in ("Search", "Find", "Submit", "Go"):
            try:
                btn = page.get_by_role("button", name=re.compile(label, re.I))
                if btn.is_visible():
                    btn.click()
                    time.sleep(random.uniform(2.0, 3.0))
                    break
            except Exception:
                pass

        # Parse results — the new portal renders a table or card list
        content = page.content()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, "lxml")

        results = []

        # Try table rows first
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # skip header
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                texts = [c.get_text(strip=True) for c in cells]
                entity = {
                    "registered_name": texts[0] if len(texts) > 0 else "",
                    "entity_type": texts[1] if len(texts) > 1 else "",
                    "sos_status": texts[2] if len(texts) > 2 else "",
                    "sos_id": texts[3] if len(texts) > 3 else "",
                }
                # Detail link
                link = row.find("a")
                if link and link.get("href"):
                    href = link["href"]
                    entity["detail_url"] = (
                        "https://tncab.tnsos.gov" + href
                        if href.startswith("/") else href
                    )
                if entity["registered_name"]:
                    results.append(entity)

        # Fallback: card/list layout
        if not results:
            cards = soup.find_all(
                attrs={"class": re.compile(r"card|result|entity|row", re.I)}
            )
            for card in cards:
                text = card.get_text(" ", strip=True)
                if not text or len(text) < 5:
                    continue
                link = card.find("a")
                entity = {
                    "registered_name": card.find("h2") or card.find("h3") or card.find("strong"),
                    "detail_url": "",
                }
                if entity["registered_name"]:
                    entity["registered_name"] = entity["registered_name"].get_text(strip=True)
                else:
                    continue
                if link and link.get("href"):
                    href = link["href"]
                    entity["detail_url"] = (
                        "https://tncab.tnsos.gov" + href
                        if href.startswith("/") else href
                    )
                results.append(entity)

        return results

    except Exception as exc:
        print(f"    Search error: {exc}")
        return []


def _get_owners(page, detail_url: str) -> str:
    """Visit an entity detail page and extract member/officer names."""
    if not detail_url:
        return ""
    try:
        page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.uniform(1.5, 2.5))

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page.content(), "lxml")
        full_text = soup.get_text(" ", strip=True)

        # Structured table of members/officers
        label = soup.find(
            string=re.compile(r"Member|Officer|Organizer|Manager|Registered Agent", re.I)
        )
        if label:
            table = label.find_parent("table") or label.find_next("table")
            if table:
                people = []
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if cells:
                        person = cells[0].get_text(strip=True)
                        role = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                        if person:
                            people.append(f"{person} ({role})" if role else person)
                if people:
                    return "; ".join(people)

        # Regex fallback
        matches = re.findall(
            r"(?:Member|Manager|Organizer|Officer|President|Owner)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)",
            full_text,
        )
        if matches:
            return "; ".join(dict.fromkeys(matches))

    except Exception as exc:
        print(f"    Detail error: {exc}")

    return ""


def enrich_with_owners(studios: list[dict]) -> list[dict]:
    """
    Looks up each studio in TN SOS TNCaB and adds owner_names + entity info.
    Uses a single persistent Playwright browser session for efficiency.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()

        for i, studio in enumerate(studios):
            name = studio.get("name", "").strip()
            if not name:
                continue

            print(f"  [{i+1}/{len(studios)}] {name}")

            matches = _search_one(page, name)
            best = _best_match(name, matches)

            if best:
                studio["registered_name"] = best.get("registered_name", "")
                studio["entity_type"] = best.get("entity_type", "")
                studio["sos_status"] = best.get("sos_status", "")
                studio["sos_id"] = best.get("sos_id", "")

                if best.get("detail_url"):
                    time.sleep(random.uniform(1.0, 2.0))
                    owners = _get_owners(page, best["detail_url"])
                    studio["owner_names"] = owners
                    if owners:
                        print(f"    -> {owners[:80]}")
            else:
                studio["owner_names"] = ""
                studio["sos_status"] = "Not Found in TN SOS"

            time.sleep(random.uniform(2.0, 3.5))

        browser.close()

    return studios