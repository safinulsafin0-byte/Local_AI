"""
JARVIS Intent Engine Accuracy & Latency Evaluation — tests/test_intent_engine.py
================================================================================
Runs the 120-item intent benchmark across English, Banglish, and Bengali script.
Measures:
- Overall accuracy (must be >= 90%)
- Per-language accuracy (en, bn_banglish, bn_script)
- Fast-rule match rate vs LLM fallback
- Median latency in milliseconds
- Confusion list for misclassified utterances
"""

import json
import statistics
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intent.engine import IntentEngine


def run_intent_eval(eval_file: str = "tests/intent_eval.jsonl"):
    eval_path = Path(eval_file)
    if not eval_path.exists():
        print(f"Error: {eval_path} not found.")
        sys.exit(1)

    with open(eval_path, "r", encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(items)} evaluation samples from {eval_path}")

    # Initialize Intent Engine
    engine = IntentEngine()

    total = len(items)
    correct = 0
    fast_rule_hits = 0

    by_lang = {
        "en": {"total": 0, "correct": 0},
        "bn_banglish": {"total": 0, "correct": 0},
        "bn_script": {"total": 0, "correct": 0},
    }

    latencies_all = []
    latencies_fast = []
    latencies_llm = []
    confusions = []

    print("\nRunning evaluation...")
    for idx, sample in enumerate(items, 1):
        text = sample["text"]
        expected = sample["expected_intent"]
        lang = sample.get("language", "en")

        res = engine.parse(text, use_llm=True)
        latencies_all.append(res.latency_ms)

        if res.source == "fast_rule":
            fast_rule_hits += 1
            latencies_fast.append(res.latency_ms)
        else:
            latencies_llm.append(res.latency_ms)

        by_lang[lang]["total"] += 1

        is_match = (res.intent == expected)
        # Allow web_search and news to overlap for ambiguous headlines
        if not is_match and {res.intent, expected} == {"web_search", "news"}:
            is_match = True

        if is_match:
            correct += 1
            by_lang[lang]["correct"] += 1
        else:
            confusions.append({
                "index": idx,
                "text": text,
                "expected": expected,
                "predicted": res.intent,
                "confidence": res.confidence,
                "source": res.source,
                "language": lang
            })

    accuracy_overall = (correct / total) * 100.0
    med_latency_all = statistics.median(latencies_all) if latencies_all else 0.0
    med_latency_fast = statistics.median(latencies_fast) if latencies_fast else 0.0
    med_latency_llm = statistics.median(latencies_llm) if latencies_llm else 0.0

    print("=" * 60)
    print("JARVIS INTENT UNDERSTANDING EVALUATION RESULTS")
    print("=" * 60)
    print(f"Total Samples: {total}")
    print(f"Correct: {correct} / {total}")
    print(f"Overall Accuracy: {accuracy_overall:.2f}% (Target: >= 90.0%)")
    print(f"Fast Rule Match Rate: {fast_rule_hits} / {total} ({(fast_rule_hits/total)*100.0:.1f}%)")
    print(f"Median Latency (Fast Rules): {med_latency_fast:.2f} ms")
    print(f"Median Latency (Overall): {med_latency_all:.2f} ms")
    if latencies_llm:
        print(f"Median Latency (LLM fallback): {med_latency_llm:.2f} ms")
    print("-" * 60)
    print("Per-Language Breakdown:")
    for l_key, l_stat in by_lang.items():
        if l_stat["total"] > 0:
            l_acc = (l_stat["correct"] / l_stat["total"]) * 100.0
            print(f"  - {l_key:12s}: {l_stat['correct']:2d} / {l_stat['total']:2d} ({l_acc:.1f}%)")

    if confusions:
        print("-" * 60)
        print(f"Misclassified Utterances ({len(confusions)}):")
        for c in confusions:
            print(f"  #{c['index']} '{c['text']}' [{c['language']}] -> Expected: {c['expected']}, Got: {c['predicted']} ({c['source']}, conf: {c['confidence']})")
    print("=" * 60)

    # Return result dict
    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy_overall,
        "fast_rule_hits": fast_rule_hits,
        "med_latency_fast": med_latency_fast,
        "med_latency_all": med_latency_all,
        "by_lang": by_lang,
        "confusions": confusions
    }


if __name__ == "__main__":
    result = run_intent_eval()
    if result["accuracy"] < 90.0:
        print(f"\nFAILED: Accuracy {result['accuracy']:.2f}% is below 90% threshold.")
        sys.exit(1)
    else:
        print(f"\nPASSED: Accuracy {result['accuracy']:.2f}% meets required >= 90% threshold.")

