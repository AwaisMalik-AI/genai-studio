"""Prompt lab — generate A/B variants and a cheap quality heuristic."""

from __future__ import annotations


def variants(brief: str, style: str = "direct") -> dict:
    base = brief.strip()
    options = [
        {"name": "direct", "prompt": f"Write {style} copy for: {base}. Be specific. No filler."},
        {"name": "story", "prompt": f"Open with a 1-line scene, then deliver: {base}."},
        {"name": "proof", "prompt": f"Lead with a metric or proof point, then explain: {base}."},
    ]
    ranked = []
    for opt in options:
        score = 0.5
        if len(opt["prompt"]) < 280:
            score += 0.15
        if style in opt["prompt"]:
            score += 0.1
        if opt["name"] == "proof":
            score += 0.05
        ranked.append({**opt, "heuristic_score": round(min(1.0, score), 2)})
    ranked.sort(key=lambda x: x["heuristic_score"], reverse=True)
    return {"brief": base, "winner": ranked[0]["name"], "variants": ranked}
