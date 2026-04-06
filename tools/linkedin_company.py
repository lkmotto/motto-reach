"""
linkedin_company.py — LinkedIn company page posting

Posts content as the Motto Appraisal Service company page.
Uses the ads token which has rw_organization_admin scope.

Company page URN: urn:li:organization:112763283
Person URN: urn:li:person:4ddD3Av3fV (Luke's personal)

Strategy:
- Company page posts slightly more formal/brand-focused than personal posts
- Mix: 60% same content as personal post (rephrased for brand voice), 40% unique
- Always post personal first (personal posts get more reach), company page 2-4 hours later
- Use company page for: service announcements, market reports, educational content
- Do NOT post identical text — rephrase for brand voice
"""

import os
import json
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

ADS_TOKEN_PATH = Path("/home/user/workspace/linkedin_poster/ads_token.txt")
TOKEN_PATH = Path("/home/user/workspace/linkedin_poster/token.txt")
ORG_URN = "urn:li:organization:112763283"
PERSON_URN = "urn:li:person:4ddD3Av3fV"
API_BASE = "https://api.linkedin.com/v2"
API_VERSION = "202602"


def _get_token() -> str:
    """Use ads token (has org admin scope). Falls back to regular token."""
    if ADS_TOKEN_PATH.exists():
        return ADS_TOKEN_PATH.read_text().strip()
    return TOKEN_PATH.read_text().strip()


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "LinkedIn-Version": API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


def post_to_company_page(
    text: str,
    image_urn: Optional[str] = None,
    doc_urn: Optional[str] = None,
    schedule_delay_hours: int = 2,
) -> dict:
    """
    Publish a post as the company page.

    text: post text (rephrased for brand voice)
    image_urn: LinkedIn image asset URN (from upload_image_for_org)
    doc_urn: LinkedIn document asset URN (from upload_doc_for_org)
    schedule_delay_hours: not used (posts immediately), for tracking only

    Returns: {"post_urn": str, "company_page_url": str, "success": bool}
    """
    try:
        author = ORG_URN

        media_category = "NONE"
        media = []
        if image_urn:
            media_category = "IMAGE"
            media = [{"status": "READY", "media": image_urn}]
        elif doc_urn:
            media_category = "DOCUMENT"
            media = [
                {
                    "status": "READY",
                    "media": doc_urn,
                    "title": {"text": "Motto Appraisal Report"},
                }
            ]

        body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentaryV2": {"text": text},
                    "shareMediaCategory": media_category,
                    "media": media,
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        resp = requests.post(
            f"{API_BASE}/ugcPosts",
            headers=_headers(),
            json=body,
            timeout=30,
        )

        if resp.status_code in (200, 201):
            post_id = resp.headers.get("x-restli-id", "")
            log.info(f"Company page post published: {post_id}")
            return {
                "post_urn": post_id,
                "company_page_url": "https://www.linkedin.com/company/motto-appraisal-service/",
                "success": True,
                "org_urn": ORG_URN,
            }
        else:
            log.error(f"Company page post failed: {resp.status_code} — {resp.text[:200]}")
            return {
                "success": False,
                "error": resp.text[:300],
                "status_code": resp.status_code,
            }

    except Exception as e:
        log.error(f"post_to_company_page exception: {e}")
        return {"success": False, "error": str(e)}


def upload_image_for_org(file_path: str) -> Optional[str]:
    """
    Upload an image asset under the org identity.
    Returns the asset URN for use in post_to_company_page().
    """
    try:
        # Register upload
        reg_resp = requests.post(
            f"{API_BASE}/assets?action=registerUpload",
            headers=_headers(),
            json={
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": ORG_URN,
                    "serviceRelationships": [
                        {
                            "relationshipType": "OWNER",
                            "identifier": "urn:li:userGeneratedContent",
                        }
                    ],
                }
            },
            timeout=30,
        )

        if not reg_resp.ok:
            log.error(f"Org image register failed: {reg_resp.status_code} — {reg_resp.text[:200]}")
            return None

        upload_data = reg_resp.json()["value"]
        upload_url = upload_data["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = upload_data["asset"]

        # Upload file bytes
        with open(file_path, "rb") as f:
            put_resp = requests.put(
                upload_url,
                headers={"Authorization": f"Bearer {_get_token()}"},
                data=f.read(),
                timeout=60,
            )

        if put_resp.status_code in (200, 201):
            log.info(f"Org image uploaded: {asset_urn}")
            return asset_urn

        log.error(f"Org image upload failed: {put_resp.status_code}")
        return None

    except Exception as e:
        log.error(f"upload_image_for_org exception: {e}")
        return None


def upload_doc_for_org(file_path: str, title: str = "Motto Appraisal Report") -> Optional[str]:
    """
    Upload a document (PDF) asset under the org identity.
    Returns the asset URN for use in post_to_company_page().
    """
    try:
        reg_resp = requests.post(
            f"{API_BASE}/assets?action=registerUpload",
            headers=_headers(),
            json={
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-document"],
                    "owner": ORG_URN,
                    "serviceRelationships": [
                        {
                            "relationshipType": "OWNER",
                            "identifier": "urn:li:userGeneratedContent",
                        }
                    ],
                }
            },
            timeout=30,
        )

        if not reg_resp.ok:
            log.error(f"Org document register failed: {reg_resp.status_code} — {reg_resp.text[:200]}")
            return None

        upload_data = reg_resp.json()["value"]
        upload_url = upload_data["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = upload_data["asset"]

        with open(file_path, "rb") as f:
            put_resp = requests.put(
                upload_url,
                headers={"Authorization": f"Bearer {_get_token()}"},
                data=f.read(),
                timeout=120,
            )

        if put_resp.status_code in (200, 201):
            log.info(f"Org document uploaded: {asset_urn}")
            return asset_urn

        log.error(f"Org document upload failed: {put_resp.status_code}")
        return None

    except Exception as e:
        log.error(f"upload_doc_for_org exception: {e}")
        return None


def rephrase_for_brand(personal_post_text: str, pillar: int) -> str:
    """
    Use Claude to rephrase personal post text for company brand voice.
    Brand voice: professional, data-driven, DFW market authority.
    Slightly more formal than personal. Never identical to personal post.
    Returns rephrased text.
    """
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        prompt = f"""Rephrase this LinkedIn post for the company page of "Motto Appraisal Service", a licensed DFW residential appraisal firm.

RULES:
- Keep the same core insight and data
- Shift from first-person "I" to brand voice ("Our appraisers", "At Motto Appraisal", or third-person perspective)
- More formal than the personal post but still direct and data-driven
- No emoji
- Under 2800 characters
- Do not add or invent new data points

ORIGINAL PERSONAL POST:
{personal_post_text}

Return ONLY the rephrased post text. No commentary."""

        response = client.messages.create(
            model="claude-sonnet-4-5-20251101",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    except Exception as e:
        log.error(f"rephrase_for_brand failed: {e}")
        # Return a minimally modified version as fallback
        return personal_post_text.replace(" I ", " Motto Appraisal ").replace("I've", "We've").replace("I'm", "We're")


def get_company_page_stats() -> dict:
    """
    Fetch basic stats for the company page (follower count, etc.).
    Returns dict with stats or error.
    """
    try:
        resp = requests.get(
            f"{API_BASE}/organizationalEntityFollowerStatistics",
            headers=_headers(),
            params={"q": "organizationalEntity", "organizationalEntity": ORG_URN},
            timeout=30,
        )

        if resp.status_code == 200:
            data = resp.json()
            elements = data.get("elements", [])
            if elements:
                stats = elements[0]
                return {
                    "success": True,
                    "follower_count": stats.get("followerCounts", {}).get("organicFollowerCount", 0),
                    "org_urn": ORG_URN,
                }
            return {"success": True, "follower_count": 0, "org_urn": ORG_URN}
        else:
            log.warning(f"Could not fetch company stats ({resp.status_code}): {resp.text[:200]}")
            return {"success": False, "error": resp.text[:200], "status_code": resp.status_code}

    except Exception as e:
        log.error(f"get_company_page_stats exception: {e}")
        return {"success": False, "error": str(e)}
