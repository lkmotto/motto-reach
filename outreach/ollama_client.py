"""
ollama_client.py — Free inference via local Ollama
Zero API cost. Luke Motto persona baked in.
"""

import os
import time
import requests
import logging

log = logging.getLogger("ollama")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Try models in priority order — luke-motto is our custom persona model
MODELS = ["luke-motto", "llama3.1:8b", "llama3.2:3b", "mistral:7b", "qwen2.5:7b"]

LUKE_SYSTEM = """You are Luke Motto. Licensed residential real estate appraiser, Trophy Club TX. 2,000+ appraisals across DFW since 2019 — Tarrant, Denton, Dallas, Collin, Kaufman counties.

Business: Motto Appraisal Service — mottoappraisal.cloud — (817) 217-4375

VOICE: Direct. Specific. Short paragraphs. Real numbers. No emoji. No "happy to help", "great question", "certainly". Sounds like someone who actually does this work every day.

DFW MARKET 2026: Median SFR $375K-$425K. 33,593 active listings (+10.7% YoY, 2nd highest nationally). 35-55 avg days on market (Fort Worth Q1: 67 days). Sale-to-list 96-97%. 6.47% 30yr fixed. DSCR loans 6-8%. Condos -19.8% YoY. Outer suburbs most pressure.

APPRAISAL KNOWLEDGE: DSCR = Rent/PITIA. Form 1007 = lender's market rent source. Hard money qualifies on ARV. Pre-listing prevents overpricing. PMI removal needs 20% equity appraisal. Tax protest deadline May 15 or 30 days from notice. Cost approach = Land + Build - Depreciation (physical deterioration, functional obsolescence, external obsolescence).

REPLY RULES:
1. Answer the question helpfully and specifically — always first
2. Mention appraisal services only if directly relevant, briefly, at the end
3. If not DFW, answer generally without the pitch
4. 2-3 short paragraphs max for comments
5. Be the most useful person in the thread — business follows naturally

DM RULES:
1. 2-3 sentences only
2. Reference their exact post situation
3. One specific, concrete offer
4. Sign: Luke Motto, Licensed DFW Appraiser, (817) 217-4375"""


def available() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return len(models) > 0
    except Exception:
        pass
    return False


def best_model() -> str:
    """Return the best available model from MODELS list."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            loaded = [m["name"] for m in r.json().get("models", [])]
            for preferred in MODELS:
                # Match on base name (llama3.1:8b matches llama3.1:8b)
                for loaded_model in loaded:
                    if preferred.split(":")[0] in loaded_model:
                        return loaded_model
    except Exception:
        pass
    return MODELS[0]  # Try anyway even if check fails


def chat(messages: list, temperature: float = 0.72) -> str:
    """
    Generate a response. messages = [{"role": "...", "content": "..."}]
    Returns empty string if Ollama unavailable.
    """
    model = best_model()

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 450,
                    "top_p": 0.9,
                },
            },
            timeout=90,
        )
        if r.status_code == 200:
            content = r.json().get("message", {}).get("content", "").strip()
            if content:
                log.debug(f"Generated {len(content)} chars via {model}")
                return content
        log.warning(f"Ollama {r.status_code}: {r.text[:100]}")
    except Exception as e:
        log.warning(f"Ollama error: {e}")
    return ""


def draft_comment(
    title: str,
    body: str,
    subreddit: str,
    intent_hits: list,
    is_dfw: bool,
    variant: str = "A",
) -> str:
    geo = "in DFW" if is_dfw else "(I cover all of DFW metro)"

    # ABCD variant framing
    variant_instructions = {
        "A": "Answer helpfully. Identify as a DFW appraiser at the end if relevant.",
        "B": "Open with a specific DFW market stat or data point relevant to their situation, then answer.",
        "C": "Open by naming the exact problem they're dealing with, then provide the solution.",
        "D": "Answer fully and helpfully. Do not mention appraisal services at all. Just be useful.",
    }
    instruction = variant_instructions.get(variant, variant_instructions["A"])

    messages = [
        {"role": "system", "content": LUKE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Write a Reddit reply to this r/{subreddit} post.\n\n"
                f"Title: {title}\n"
                f"Body: {body[:400] if body else '(no body text)'}\n\n"
                f"Context: You are a licensed appraiser {geo}. "
                f"Intent signals: {', '.join(intent_hits[:2]) if intent_hits else 'real estate'}\n\n"
                f"Variant instruction: {instruction}\n\n"
                f"Write 2-3 short paragraphs."
            ),
        },
    ]
    return chat(messages)


def draft_dm(
    title: str, author: str, subreddit: str, is_dfw: bool, variant: str = "A"
) -> str:
    geo = "in DFW" if is_dfw else "across DFW metro"

    variant_instructions = {
        "A": "Direct professional intro. Reference their post, offer specific help, sign off.",
        "B": "Lead with one specific data point or number relevant to their situation. Then identify as appraiser.",
        "C": "Open by naming the specific problem they're facing. Then offer the solution.",
        "D": "Be purely helpful. Answer something concrete. Don't pitch. Just sign as Luke Motto Licensed Appraiser.",
    }
    instruction = variant_instructions.get(variant, variant_instructions["A"])

    messages = [
        {"role": "system", "content": LUKE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Write a 2-3 sentence Reddit DM to u/{author} "
                f"who posted '{title}' in r/{subreddit}.\n\n"
                f"Context: You're a licensed appraiser {geo}.\n"
                f"Variant: {instruction}\n\n"
                f"Sign as: Luke Motto, Licensed DFW Appraiser, (817) 217-4375"
            ),
        },
    ]
    return chat(messages, temperature=0.75)


def draft_x_reply(tweet: str, username: str, intent_hits: list, is_dfw: bool) -> str:
    geo = "in DFW" if is_dfw else ""
    messages = [
        {"role": "system", "content": LUKE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Write an X/Twitter reply to @{username} who tweeted: '{tweet}'\n\n"
                f"Context: Licensed appraiser {geo}. Intent: {', '.join(intent_hits[:2])}.\n"
                f"Max 240 characters. Helpful and specific. No hashtags. No pitch unless they asked."
            ),
        },
    ]
    reply = chat(messages, temperature=0.72)
    return reply[:240] if reply else ""


def draft_conversation_reply(history: list, new_message: str) -> str:
    """Continue an active conversation toward a service offer when appropriate."""
    messages = [{"role": "system", "content": LUKE_SYSTEM}]
    messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": (
                f"They replied: '{new_message}'\n\n"
                f"Continue the conversation. If they show buying intent (asking about "
                f"cost, process, timeline, scheduling), guide toward "
                f"mottoappraisal.cloud or (817) 217-4375. If not yet, ask one good "
                f"follow-up question to understand their situation better. "
                f"2-3 sentences max."
            ),
        }
    )
    return chat(messages, temperature=0.78)


def sharpen(recent_sends: list) -> dict:
    """
    Analyze recent send/reply data to generate improvement recommendations.
    Called once per day by sharpener.py.
    Returns: {observations, proposed_variant_e, proposed_variant_f}
    """
    if not available():
        return {}

    # Build summary for analysis
    total = len(recent_sends)
    replied = sum(1 for s in recent_sends if s.get("replied"))
    by_variant = {}
    for s in recent_sends:
        v = s.get("variant", "A")
        if v not in by_variant:
            by_variant[v] = {"sends": 0, "replies": 0}
        by_variant[v]["sends"] += 1
        if s.get("replied"):
            by_variant[v]["replies"] += 1

    summary = f"Total sends: {total}, replies: {replied} ({replied/total*100:.0f}% if total > 0 else 0)\n"
    for v, stats in by_variant.items():
        rr = stats["replies"] / stats["sends"] * 100 if stats["sends"] > 0 else 0
        summary += f"Variant {v}: {stats['sends']} sends, {stats['replies']} replies ({rr:.0f}%)\n"

    # Sample of actual messages
    sample = recent_sends[-5:] if len(recent_sends) >= 5 else recent_sends
    examples = "\n".join(
        [
            f"[Variant {s.get('variant','?')}] {s.get('dm_preview','')[:100]} | replied: {s.get('replied', False)}"
            for s in sample
        ]
    )

    messages = [
        {
            "role": "system",
            "content": "You are a conversion rate optimization expert for a local service business.",
        },
        {
            "role": "user",
            "content": (
                f"Analyze these Reddit DM outreach results for a DFW real estate appraiser:\n\n"
                f"PERFORMANCE:\n{summary}\n"
                f"RECENT EXAMPLES:\n{examples}\n\n"
                f"1. What pattern explains the reply rate differences between variants?\n"
                f"2. Propose a specific Variant E message approach (2 sentences describing the strategy, not the actual message)\n"
                f"3. Propose a Variant F approach based on what's working\n"
                f"Keep observations to 2-3 sentences each."
            ),
        },
    ]
    analysis = chat(messages, temperature=0.5)
    return {"timestamp": time.time(), "analysis": analysis, "stats": by_variant}
