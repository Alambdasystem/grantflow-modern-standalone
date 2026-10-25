"""Grant deep-enrichment — fetch full details from source URLs."""
import re
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import Grant
from auth.jwt_handler import get_current_user_token

router = APIRouter(prefix="/api/grants", tags=["grants"])


def _extract_fr_doc_number(url: str) -> str | None:
    """Pull document number from Federal Register URLs like /documents/2024/01/15/2024-00123/..."""
    m = re.search(r"/documents/\d{4}/\d{2}/\d{2}/(\d{4}-\d+)/", url or "")
    return m.group(1) if m else None


def _extract_grants_gov_opp_id(url: str) -> str | None:
    """Pull oppId from grants.gov opportunity URLs."""
    m = re.search(r"[?&]oppId=(\d+)", url or "")
    return m.group(1) if m else None


async def _enrich_federal_register(doc_number: str) -> dict:
    """Fetch full document details from Federal Register JSON API."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"https://www.federalregister.gov/api/v1/documents/{doc_number}.json",
            params={"fields[]": [
                "title", "abstract", "agencies", "publication_date",
                "action", "dates", "supplementary_information",
                "cfr_references", "document_number", "pdf_url", "html_url",
                "full_text_xml_url", "type",
            ]},
            headers={"User-Agent": "GrantFlowModern/1.0"},
        )
        r.raise_for_status()
        d = r.json()

    agencies = ", ".join(a.get("name", "") for a in (d.get("agencies") or []) if a.get("name"))
    cfr = ", ".join(f"{c.get('title')} CFR {c.get('part')}" for c in (d.get("cfr_references") or []))
    dates_text = d.get("dates") or ""
    abstract = d.get("abstract") or d.get("supplementary_information", "")[:800] or ""

    # Parse deadline from dates text
    deadline_match = re.search(r"(?:due|deadline|submit|close)[^.]*?(\w+ \d{1,2},?\s*\d{4})", dates_text, re.I)
    deadline_str = deadline_match.group(1) if deadline_match else d.get("publication_date")

    # Award amounts from abstract
    amounts = re.findall(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion))?", abstract, re.I)

    required_docs = []
    for keyword in ("application", "narrative", "budget", "SF-424", "letter", "audit", "990", "SAM", "UEI", "DUNS"):
        if keyword.lower() in (abstract or "").lower():
            required_docs.append(keyword)

    return {
        "cfda_number": cfr or None,
        "synopsis": abstract[:1200] if abstract else None,
        "deadline_str": deadline_str,
        "funding_agency": agencies or None,
        "award_amounts_mentioned": amounts[:4],
        "required_documents": required_docs,
        "application_url": d.get("html_url"),
        "pdf_url": d.get("pdf_url"),
        "action": d.get("action"),
        "document_type": d.get("type"),
        "source": "federal_register_api",
    }


async def _enrich_grants_gov_api(opp_id: str) -> dict:
    """Fetch full opportunity details from the Grants.gov REST API."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Verified public read contract: GET returns 405, JSON POST 415;
        # the endpoint accepts a form-encoded opportunity-ID lookup.
        r = await client.post(
            f"https://apply07.grants.gov/grantsws/rest/opportunity/details",
            data={"oppId": opp_id},
            headers={"User-Agent": "GrantFlowModern/1.0"},
        )
        r.raise_for_status()
        d = r.json()

    opp = d.get("opportunity") or d.get("data") or d

    raw_synopsis = opp.get("synopsis")
    details = raw_synopsis if isinstance(raw_synopsis, dict) else opp
    agency = details.get("agencyName") or opp.get("agencyName") or opp.get("agencyDetails", {}).get("agencyName") or opp.get("agencyCode", "")
    close_date = opp.get("closeDate") or opp.get("closingDate") or details.get("responseDateStr", "")
    synopsis = (details.get("synopsisDesc") or details.get("description", "")) if isinstance(raw_synopsis, dict) else (raw_synopsis or opp.get("description", ""))
    from bs4 import BeautifulSoup
    synopsis = BeautifulSoup(synopsis, "html.parser").get_text(" ", strip=True) if isinstance(synopsis, str) else ""

    def labels(values, keys):
        return [value if isinstance(value, str) else next((str(value[k]) for k in keys if value.get(k)), "")
                for value in values if isinstance(value, (str, dict))]

    cfda_list = labels(opp.get("cfdaList") or opp.get("cfdaNumbers") or opp.get("cfdas") or [], ('cfdaNumber', 'number'))
    award_ceiling = details.get("awardCeiling")
    award_floor = details.get("awardFloor")
    eligibilities = labels(opp.get("eligibilities") or details.get("applicantTypes") or [], ('description', 'name'))
    categories = labels(opp.get("categories") or details.get("fundingActivityCategories") or [], ('description', 'name'))
    opp_number = opp.get("number") or opp.get("opportunityNumber", "")

    amounts = []
    from decimal import Decimal, InvalidOperation
    for value, prefix in [(award_ceiling, 'Up to'), (award_floor, 'Min')]:
        if value:
            try:
                money = Decimal(str(value).replace(',', '').replace('$', ''))
                if money.is_finite() and money >= 0:
                    amounts.append(f"{prefix} ${money:,f}")
            except InvalidOperation:
                pass  # An unparseable provider amount remains unknown.

    required_docs = []
    for kw in ("SF-424", "budget narrative", "project narrative", "SAM", "UEI", "DUNS",
                "Form 990", "audit", "letters of support", "evaluation plan"):
        if kw.lower() in (synopsis or "").lower():
            required_docs.append(kw)

    return {
        "cfda_number": ", ".join(cfda_list) if cfda_list else None,
        "synopsis": synopsis,
        "deadline_str": close_date,
        "funding_agency": agency or None,
        "award_amounts_mentioned": amounts,
        "required_documents": required_docs,
        "eligibility": ", ".join(eligibilities) if eligibilities else None,
        "application_url": f"https://www.grants.gov/search-results-detail/{opp_id}",
        "opportunity_number": opp_number,
        "categories": categories,
        "source": "grants_gov_api",
    }


async def _enrich_generic_url(url: str) -> dict:
    """Fetch a grant page and extract key fields with BeautifulSoup."""
    from bs4 import BeautifulSoup
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; GrantFlowBot/1.0)"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

    # Remove nav/footer/script noise
    for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)[:4000]

    amounts = re.findall(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|k))?", text, re.I)
    cfda = re.findall(r"\b\d{2}\.\d{3}\b", text)  # CFDA format: XX.XXX
    deadline_match = re.search(
        r"(?:due|deadline|close|receipt)\s*[:\-]?\s*(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})",
        text, re.I
    )
    eligibility_match = re.search(
        r"(?:eligible|eligibility|who can apply)[^\n.]{0,20}[:\-]?\s*([^\n]{40,300})",
        text, re.I
    )

    required_docs = []
    for kw in ("SF-424", "budget narrative", "project narrative", "501(c)(3)", "IRS determination",
                "board list", "audit", "Form 990", "SAM.gov", "UEI", "DUNS", "logic model",
                "letters of support", "evaluation plan", "sustainability plan"):
        if kw.lower() in text.lower():
            required_docs.append(kw)

    # Grab page title or first H1/H2
    title_tag = soup.find("title") or soup.find("h1") or soup.find("h2")
    page_title = title_tag.get_text(strip=True)[:200] if title_tag else None

    return {
        "cfda_number": cfda[0] if cfda else None,
        "synopsis": text[:800],
        "deadline_str": deadline_match.group(1) if deadline_match else None,
        "eligibility": eligibility_match.group(1).strip() if eligibility_match else None,
        "award_amounts_mentioned": amounts[:4],
        "required_documents": required_docs,
        "application_url": url,
        "page_title": page_title,
        "source": "generic_scrape",
    }


@router.post("/{grant_id}/enrich")
async def enrich_grant(
    grant_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Fetch the grant's source URL and extract full details."""
    grant = await db.get(Grant, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    if not grant.source_url:
        raise HTTPException(status_code=422, detail="Grant has no source_url to enrich from")

    enriched: dict = {}
    error: str | None = None

    try:
        fr_doc = _extract_fr_doc_number(grant.source_url)
        opp_id = _extract_grants_gov_opp_id(grant.source_url)
        if fr_doc:
            enriched = await _enrich_federal_register(fr_doc)
        elif opp_id:
            enriched = await _enrich_grants_gov_api(opp_id)
        else:
            enriched = await _enrich_generic_url(grant.source_url)
    except Exception as exc:
        error = str(exc)

    # Update grant fields from enriched data
    if enriched.get("synopsis") and not grant.description:
        grant.description = enriched["synopsis"]
    if enriched.get("deadline_str") and not grant.deadline_str:
        grant.deadline_str = enriched["deadline_str"]
    if enriched.get("eligibility") and not grant.eligibility:
        grant.eligibility = enriched["eligibility"]
    if enriched.get("funding_agency") and not grant.funding_agency:
        grant.funding_agency = enriched["funding_agency"]
    if enriched.get("required_documents"):
        existing = grant.requirements or []
        merged = list({r for r in existing + enriched["required_documents"]})
        grant.requirements = merged

    # Store full enrichment in meta
    current_meta = grant.meta or {}
    current_meta["enrichment"] = {k: v for k, v in enriched.items() if v}
    if error:
        current_meta["enrichment"]["error"] = error
    grant.meta = current_meta

    await db.commit()
    await db.refresh(grant)

    return {
        "grant_id": grant_id,
        "source_url": grant.source_url,
        "enriched": enriched,
        "error": error,
        "requirements": grant.requirements,
        "description": grant.description,
        "eligibility": grant.eligibility,
    }
