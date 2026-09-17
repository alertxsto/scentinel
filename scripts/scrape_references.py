"""Scrape Scentinel reference data with Scrapling.

Usage:
    .venv/bin/python scripts/scrape_references.py

Outputs raw HTML + extracted JSON into docs/references/ and docs/data/.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scrapling.fetchers import Fetcher

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "docs" / "references"
DATA = ROOT / "docs" / "data"
REFS.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)


def save_raw(name: str, html: str) -> Path:
    path = REFS / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    return path


def fetch(url: str, name: str) -> "Fetcher.Response":
    print(f"[fetch] {name}: {url}")
    resp = Fetcher.get(url, timeout=60)
    print(f"[fetch] {name}: status={resp.status} len={len(resp.html_content)}")
    save_raw(name, resp.html_content)
    return resp


def _main_text(resp: "Fetcher.Response") -> str:
    text = " ".join(resp.css("main ::text").getall())
    return re.sub(r"\s+", " ", text)


def scrape_epa_lfg() -> dict:
    """EPA LMOP landfill gas composition + heating value (basic + FAQ pages)."""
    resp = fetch("https://www.epa.gov/lmop/basic-information-about-landfill-gas", "epa_lfg_basics")
    text = _main_text(resp)
    facts: dict = {}
    m = re.search(r"composed of roughly (\d+) percent methane[^.]*?(\d+) percent carbon dioxide", text)
    if m:
        facts["ch4_percent"] = int(m.group(1))
        facts["co2_percent"] = int(m.group(2))
    m = re.search(r"less than (\d+) percent non-methane organic compounds", text)
    if m:
        facts["nmoc_percent_max"] = int(m.group(1))

    faq = fetch("https://www.epa.gov/lmop/frequent-questions-about-landfill-gas", "epa_lfg_faq")
    faq_text = _main_text(faq)
    m = re.search(r"heating value of ([\d,]+) to ([\d,]+) British thermal units \(Btu\) per cubic foot", faq_text)
    if m:
        facts["heating_value_btu_per_cft"] = [
            int(m.group(1).replace(",", "")),
            int(m.group(2).replace(",", "")),
        ]
    m = re.search(r"about (\d+) percent methane and (\d+) percent carbon dioxide and water vapor", faq_text)
    if m:
        facts["faq_ch4_percent"] = int(m.group(1))
        facts["faq_co2_h2o_percent"] = int(m.group(2))
    m = re.search(r"contains small amounts of nitrogen, oxygen, and hydrogen", faq_text)
    if m:
        facts["has_n2_o2_h2_trace"] = True
    return facts


def download_ap42_documents(docs: list[dict]) -> list[dict]:
    """Download final AP-42 emission factor spreadsheets/PDFs into docs/data."""
    wanted = ("c2s4_2024_final.pdf", "ap-42-chapter-2-section-4-tables-final.xlsx")
    downloaded = []
    for doc in docs:
        url = doc["url"]
        if not any(name in url for name in wanted):
            continue
        filename = url.rsplit("/", 1)[-1]
        target = DATA / filename
        if target.exists():
            print(f"[download] skip existing {filename}")
        else:
            print(f"[download] {filename}")
            resp = Fetcher.get(url, timeout=120)
            target.write_bytes(resp.body)
            print(f"[download] {filename}: {len(resp.body)} bytes")
        downloaded.append({"file": str(target.relative_to(ROOT)), "url": url})
    return downloaded


def scrape_epa_ap42() -> dict:
    """EPA AP-42 Ch 2.4 page: links to final emission factor documents."""
    resp = fetch(
        "https://www.epa.gov/air-emissions-factors-and-quantification/final-emissions-factors-ap-42-chapter-2-section-4",
        "epa_ap42_ch2s4",
    )
    docs = []
    for a in resp.css("main a"):
        href = a.attrib.get("href", "")
        label = a.text.strip()
        if href and (href.endswith(".pdf") or href.endswith(".xlsx")):
            docs.append({"label": label, "url": href})
    return {"documents": docs}


def scrape_crossref(query: str, rows: int = 10) -> dict:
    """Crossref REST API for paper metadata (structured, not HTML scraping)."""
    from urllib.parse import quote

    url = (
        "https://api.crossref.org/works"
        f"?query={quote(query)}&rows={rows}"
        "&select=DOI,title,author,issued,container-title,URL"
    )
    print(f"[crossref] {query}")
    resp = Fetcher.get(url, timeout=60)
    payload = json.loads(resp.body.decode("utf-8"))
    items = []
    for it in payload["message"]["items"]:
        authors = [
            f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
            for a in it.get("author", [])
        ]
        items.append(
            {
                "title": (it.get("title") or [""])[0],
                "authors": authors,
                "year": (it.get("issued", {}).get("date-parts", [[None]])[0][0]),
                "container": (it.get("container-title") or [""])[0],
                "doi": it.get("DOI"),
                "url": it.get("URL"),
            }
        )
    return {"query": query, "items": items}


def scrape_crossref_title(title: str, rows: int = 3) -> dict:
    """Search Crossref by exact title for precise metadata."""
    from urllib.parse import quote

    url = (
        "https://api.crossref.org/works"
        f"?query.bibliographic={quote(title)}&rows={rows}"
        "&select=DOI,title,author,issued,container-title,URL"
    )
    print(f"[crossref-title] {title[:60]}")
    resp = Fetcher.get(url, timeout=60)
    payload = json.loads(resp.body.decode("utf-8"))
    items = []
    for it in payload["message"]["items"]:
        authors = [
            f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
            for a in it.get("author", [])
        ]
        items.append(
            {
                "title": (it.get("title") or [""])[0],
                "authors": authors,
                "year": (it.get("issued", {}).get("date-parts", [[None]])[0][0]),
                "container": (it.get("container-title") or [""])[0],
                "doi": it.get("DOI"),
                "url": it.get("URL"),
            }
        )
    return {"query": title, "items": items}


OPENFOAM_DOCS = {
    "of_scalar_transport": "https://doc.cfd.direct/openfoam/user-guide-v13/post-processing-functionality",
    "of_solver_modules": "https://doc.cfd.direct/openfoam/user-guide-v13/solvers-modules",
    "of_sampling_monitoring": "https://doc.cfd.direct/openfoam/user-guide-v13/graphs-monitoring",
    "of_boundary_conditions": "https://doc.cfd.direct/openfoam/user-guide-v13/boundary-conditions",
    "of_turbulence": "https://doc.cfd.direct/openfoam/user-guide-v13/turbulence",
}


def scrape_openfoam_docs() -> dict:
    """Fetch OpenFOAM v13 user guide sections relevant to the simulation."""
    sections = {}
    for key, url in OPENFOAM_DOCS.items():
        resp = fetch(url, key)
        text = " ".join(resp.css("main ::text, #content ::text").getall())
        text = re.sub(r"\s+", " ", text)
        sections[key] = {"url": url, "chars": len(text)}
        (REFS / f"{key}.txt").write_text(text, encoding="utf-8")
    return sections


def main() -> None:
    results: dict[str, dict] = {}

    results["epa_lfg"] = scrape_epa_lfg()
    results["epa_ap42"] = scrape_epa_ap42()
    results["epa_ap42"]["downloaded"] = download_ap42_documents(
        results["epa_ap42"]["documents"]
    )

    queries = {
        "cfd_sensor_placement": "CFD gas dispersion sensor placement optimization",
        "landfill_gas_dispersion": "landfill gas dispersion CFD simulation",
        "passive_scalar_transport": "passive scalar transport turbulent dispersion CFD",
        "waste_bunker_ventilation": "waste bunker ventilation CFD airflow",
    }
    for key, query in queries.items():
        try:
            results[key] = scrape_crossref(query)
        except Exception as exc:  # noqa: BLE001
            print(f"[crossref] {key} failed: {exc}")
            results[key] = {"query": query, "items": [], "error": str(exc)}

    known_papers = {
        "legg_detector_placement": "A stochastic programming approach for gas detector placement using CFD-based dispersion simulations",
        "lang_sensor_placement": "A novel CFD-MILP-ANN approach for optimizing sensor placement, number, and source localization in large-scale gas dispersion from unknown locations",
        "zi_methane_monitoring": "Distributionally robust optimal sensor placement method for site-scale methane-emission monitoring",
        "abbassi_indoor_monitoring": "Risk-based prioritisation of indoor air pollution monitoring using computational fluid dynamics",
    }
    for key, title in known_papers.items():
        try:
            results[key] = scrape_crossref_title(title)
        except Exception as exc:  # noqa: BLE001
            print(f"[crossref-title] {key} failed: {exc}")
            results[key] = {"query": title, "items": [], "error": str(exc)}

    results["openfoam_docs"] = scrape_openfoam_docs()

    out = DATA / "scraped_references.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[saved] {out}")
    print(f"[saved] raw HTML in {REFS}")


if __name__ == "__main__":
    main()
