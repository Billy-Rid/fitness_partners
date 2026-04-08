"""
Google Maps scraper for Nashville fitness studios, gyms, and membership groups
that could be potential IV therapy partnership targets.
"""

import asyncio
import random
import re
from pathlib import Path
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SEARCH_TERMS = [
    "boutique fitness studio Nashville TN",
    "pilates studio Nashville TN",
    "yoga studio Nashville TN",
    "barre studio Nashville TN",
    "CrossFit gym Nashville TN",
    "personal training studio Nashville TN",
    "cycling studio Nashville TN",
    "HIIT studio Nashville TN",
    "fitness membership Nashville TN",
    "gym Nashville TN",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""

# Large national chains — not useful partnership targets, skip them
CHAIN_BLACKLIST = {
    "planet fitness", "la fitness", "anytime fitness", "24 hour fitness",
    "gold's gym", "crunch fitness", "equinox", "lifetime fitness",
    "life time", "ymca", "snap fitness", "eos fitness", "orange theory",
    "orangetheory", "f45", "pure barre corporate", "club pilates corporate",
}


def _is_chain(name: str) -> bool:
    return any(chain in name.lower() for chain in CHAIN_BLACKLIST)


async def _scroll_results_panel(page) -> None:
    try:
        panel = await page.query_selector('div[role="feed"]')
        if not panel:
            return
        prev_count = 0
        for _ in range(20):
            await page.evaluate("(p) => { p.scrollTop += 1200; }", panel)
            await asyncio.sleep(random.uniform(1.5, 2.5))
            items = await page.query_selector_all('div[role="feed"] > div > div[jsaction]')
            if len(items) == prev_count:
                break
            prev_count = len(items)
    except Exception:
        pass


async def _get_listing_links(page) -> list[str]:
    return await page.evaluate("""
        () => {
            const anchors = document.querySelectorAll('a[href*="/maps/place/"]');
            const hrefs = new Set();
            anchors.forEach(a => {
                const href = a.href;
                if (href && href.includes('/maps/place/')) {
                    hrefs.add(href.split('?')[0]);
                }
            });
            return Array.from(hrefs);
        }
    """)


async def _extract_detail(page, url: str, debug: bool = False) -> dict | None:
    biz = {}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random.uniform(2.0, 3.5))
        await page.wait_for_selector("h1", timeout=8000)

        content = await page.content()

        if debug:
            debug_dir = Path("data/debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[^a-z0-9]', '_', url.split('/place/')[-1][:40].lower())
            (debug_dir / f"gmaps_{safe}.html").write_text(content, encoding="utf-8")

        soup = BeautifulSoup(content, "lxml")
        full_text = soup.get_text(" ", strip=True)

        # Name
        h1 = soup.find("h1")
        if not h1:
            return None
        biz["name"] = h1.get_text(strip=True)
        if not biz["name"] or _is_chain(biz["name"]):
            return None

        biz["google_maps_url"] = url

        # Address
        addr_btn = soup.find("button", attrs={"data-item-id": "address"})
        if addr_btn:
            biz["address"] = addr_btn.get_text(strip=True)
        else:
            addr_match = re.search(
                r"\d+\s[\w\s]+(?:Ave|Blvd|Dr|Ln|Pike|Rd|St|Way)[,\s]+Nashville",
                full_text, re.I,
            )
            if addr_match:
                biz["address"] = addr_match.group(0).strip()

        # Phone
        phone_btn = soup.find("button", attrs={"data-item-id": re.compile(r"phone")})
        if phone_btn:
            biz["phone"] = phone_btn.get_text(strip=True)
        else:
            phone_match = re.search(r"\(?\d{3}\)?[\s\-]\d{3}[\s\-]\d{4}", full_text)
            if phone_match:
                biz["phone"] = phone_match.group(0).strip()

        # Website
        website_link = soup.find("a", attrs={"data-item-id": "authority"})
        if website_link:
            biz["website"] = website_link.get("href", "")

        # Rating
        rating_match = re.search(r"(\d\.\d)\s*\([\d,]+\s*review", full_text, re.I)
        if rating_match:
            biz["rating"] = float(rating_match.group(1))

        review_match = re.search(r"\(([\d,]+)\s*review", full_text, re.I)
        if review_match:
            biz["review_count"] = int(review_match.group(1).replace(",", ""))

        # Category
        for cat in (
            "Pilates", "Yoga", "CrossFit", "Barre", "Cycling", "HIIT",
            "Personal Training", "Fitness Studio", "Gym", "Martial Arts",
        ):
            if cat.lower() in full_text.lower():
                biz["category"] = cat
                break

    except Exception as exc:
        if debug:
            print(f"    [debug] Error on {url}: {exc}")
        return None

    return biz


async def run_fitness_scraper(fetch_details: bool = True, debug: bool = False) -> list:
    """
    Scrapes Google Maps for Nashville fitness studios.
    Returns a list of business dicts ready for TN SOS enrichment.
    """
    all_links: dict[str, None] = {}
    all_studios: list[dict] = []
    seen_names: set[str] = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=not debug,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=USER_AGENT,
            locale="en-US",
        )
        await context.add_init_script(STEALTH_SCRIPT)
        page = await context.new_page()

        # ── Phase 1: Collect listing URLs ─────────────────────────────────────
        for term in SEARCH_TERMS:
            search_url = f"https://www.google.com/maps/search/{term.replace(' ', '+')}"
            print(f"  Searching: '{term}'...")

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(random.uniform(2.0, 3.5))

                for btn_text in ("Accept all", "Reject all", "Accept", "I agree"):
                    try:
                        btn = page.get_by_role("button", name=btn_text)
                        if await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(1.0)
                            break
                    except Exception:
                        pass

                await _scroll_results_panel(page)
                links = await _get_listing_links(page)

                new = sum(1 for l in links if l not in all_links)
                for l in links:
                    all_links[l] = None
                print(f"    +{new} new links (total: {len(all_links)})")

            except Exception as exc:
                print(f"    Warning: failed '{term}': {exc}")

            await asyncio.sleep(random.uniform(3.0, 5.0))

        # ── Phase 2: Extract details from each listing ────────────────────────
        if fetch_details:
            print(f"\n  Pulling details for {len(all_links)} listings...")
            for i, url in enumerate(all_links):
                print(f"  [{i+1}/{len(all_links)}] {url.split('/place/')[-1][:50]}")

                studio = await _extract_detail(page, url, debug=debug)
                if studio:
                    key = studio.get("name", "").lower().strip()
                    if key and key not in seen_names:
                        seen_names.add(key)
                        all_studios.append(studio)
                        print(f"    -> {studio['name']}")

                await asyncio.sleep(random.uniform(2.5, 4.0))
        else:
            all_studios = [{"google_maps_url": u} for u in all_links]

        await browser.close()

    return all_studios