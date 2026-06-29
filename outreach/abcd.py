"""
abcd.py — Thompson Sampling ABCD experiment tracker
Tracks 4 message variants. Sends more traffic to winners automatically.
State persists in data/abcd_state.json.
"""

import json
import random
import time
import logging
from pathlib import Path

log = logging.getLogger("abcd")
STATE_FILE = Path(__file__).parent / "data" / "abcd_state.json"

# Variant definitions — what each one tests
VARIANTS = {
    "A": {
        "name": "Direct professional",
        "description": "Reference post → answer helpfully → identify as appraiser at end",
        "hypothesis": "Direct credibility-first approach performs best with professional intent posts",
        "hypothesis_source": "market_default",
    },
    "B": {
        "name": "Data-led",
        "description": "Open with specific DFW market stat relevant to their situation, then answer",
        "hypothesis": "Leading with concrete data signals expertise before asking for anything",
        "hypothesis_source": "jtbd_consideration_stage",
    },
    "C": {
        "name": "Problem-first",
        "description": "Name their exact problem, offer the solution, mention appraiser last",
        "hypothesis": "Problem-first framing shows empathy and increases engagement",
        "hypothesis_source": "jtbd_awareness_stage",
    },
    "D": {
        "name": "Purely helpful",
        "description": "Answer fully and helpfully, zero service mention, just sign as appraiser",
        "hypothesis": "Zero-pitch approach builds trust that converts on second touch",
        "hypothesis_source": "anti_pattern_inversion",
    },
}


def _load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    # Initialize with weak priors — slight advantage to A (control) as prior
    return {
        "channel_dm": {
            v: {
                "alpha": 1.2 if v == "A" else 1.0,
                "beta": 1.0,
                "sends": 0,
                "replies": 0,
            }
            for v in VARIANTS
        },
        "channel_comment": {
            v: {
                "alpha": 1.2 if v == "A" else 1.0,
                "beta": 1.0,
                "sends": 0,
                "replies": 0,
            }
            for v in VARIANTS
        },
        "experiment_start": time.time(),
        "total_sends": 0,
        "total_replies": 0,
        "last_updated": time.time(),
    }


def _save(state: dict):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def sample_variant(channel: str = "dm") -> str:
    """
    Thompson Sampling: sample from each variant's Beta posterior.
    Return the variant with the highest sample — send it more traffic.
    channel: 'dm' or 'comment'
    """
    state = _load()
    key = f"channel_{channel}"
    if key not in state:
        key = "channel_dm"

    samples = {}
    for v, stats in state[key].items():
        # Sample from Beta(alpha, beta) — higher alpha/beta ratio = more likely to be selected
        sample = random.betavariate(stats["alpha"], stats["beta"])
        samples[v] = sample

    chosen = max(samples, key=samples.get)
    log.debug(f"Thompson sampling ({channel}): chose {chosen} | samples: {samples}")
    return chosen


def record_send(variant: str, channel: str = "dm"):
    """Record that a message was sent using this variant."""
    state = _load()
    key = f"channel_{channel}"
    if key not in state:
        key = "channel_dm"
    state[key][variant]["sends"] += 1
    state["total_sends"] += 1
    state["last_updated"] = time.time()
    _save(state)


def record_reply(variant: str, channel: str = "dm", positive: bool = True):
    """Record a reply to a message of this variant. Updates Beta posterior."""
    state = _load()
    key = f"channel_{channel}"
    if key not in state:
        key = "channel_dm"

    if positive:
        state[key][variant]["alpha"] += 1  # success
        state[key][variant]["replies"] += 1
        state["total_replies"] += 1
    else:
        state[key][variant]["beta"] += 1  # failure

    state["last_updated"] = time.time()
    _save(state)
    log.info(
        f"Recorded {'positive' if positive else 'negative'} reply for variant {variant} ({channel})"
    )


def get_status(channel: str = "dm") -> dict:
    """Return current experiment status with P(best) for each variant."""
    state = _load()
    key = f"channel_{channel}"
    if key not in state:
        return {}

    variants_data = state[key]

    # Estimate P(variant is best) via Monte Carlo (1000 samples)
    n_samples = 1000
    win_counts = {v: 0 for v in variants_data}
    for _ in range(n_samples):
        draws = {
            v: random.betavariate(stats["alpha"], stats["beta"])
            for v, stats in variants_data.items()
        }
        winner = max(draws, key=draws.get)
        win_counts[winner] += 1

    results = {}
    for v, stats in variants_data.items():
        rr = stats["replies"] / stats["sends"] if stats["sends"] > 0 else 0
        results[v] = {
            "name": VARIANTS[v]["name"],
            "sends": stats["sends"],
            "replies": stats["replies"],
            "reply_rate": round(rr * 100, 1),
            "p_best": round(win_counts[v] / n_samples * 100, 1),
            "alpha": round(stats["alpha"], 2),
            "beta": round(stats["beta"], 2),
        }

    # Find leader
    leader = max(results, key=lambda v: results[v]["p_best"])
    return {
        "variants": results,
        "leader": leader,
        "leader_p_best": results[leader]["p_best"],
        "total_sends": state["total_sends"],
        "total_replies": state["total_replies"],
        "days_running": round((time.time() - state["experiment_start"]) / 86400, 1),
    }


def format_report(channel: str = "dm") -> str:
    """Return formatted string for email report."""
    status = get_status(channel)
    if not status:
        return "No experiment data yet."

    lines = [
        f"ABCD EXPERIMENT ({channel.upper()}) — {status['days_running']} days running"
    ]
    lines.append(
        f"Total: {status['total_sends']} sends, {status['total_replies']} replies"
    )
    lines.append("")

    for v_id, v in status["variants"].items():
        leader_tag = " ← LEADING" if v_id == status["leader"] else ""
        lines.append(
            f"  Variant {v_id} ({v['name']}): "
            f"{v['sends']} sends | {v['replies']} replies | "
            f"{v['reply_rate']}% rate | P(best)={v['p_best']}%{leader_tag}"
        )

    lines.append(
        f"\nCurrent allocation: sending more to Variant {status['leader']} "
        f"(P(best) = {status['leader_p_best']}%)"
    )
    return "\n".join(lines)
