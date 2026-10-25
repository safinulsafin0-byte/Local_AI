"""
Intent Confusion Matrix Test: 30 Non-File Prompts with Generic Words
=====================================================================
Validates that prompts containing words like "information", "clear", "all",
"today", "details" in non-file contexts (search, image generation, general chat,
weather, news, media) are NEVER misrouted to filesystem operations.
"""

import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intent.engine import IntentEngine

PROMPTS = [
    # Prompts mentioning "information"
    "give me all information about AI",
    "give me all information of Today.com for today",
    "can you provide information about the solar system",
    "search for information on renewable energy",
    "what information do you have on quantum computing",
    "I need detailed information regarding the latest SpaceX launch",

    # Prompts mentioning "clear"
    "generate an image of a futuristic city and make the sky clear",
    "generate an image of a cybernetic warrior make the faces clear",
    "draw a painting of a mountain lake with crystal clear water",
    "is the weather clear in London today",
    "please clear my confusion about photosynthesis",
    "give me a clear explanation of recursion",

    # Prompts mentioning "all"
    "show all top news headlines for today",
    "list all planets in our galaxy",
    "tell me all about Albert Einstein",
    "who won all the Nobel prizes in physics last year",
    "what are all the steps to bake sourdough bread",
    "give me all the details about the latest iPhone release",

    # Prompts mentioning "today"
    "what's new today",
    "what is today's weather forecast",
    "show today's trending technology news",
    "who is the president of the United States today",
    "what is the price of Bitcoin today",
    "tell me what happened today in history",

    # Prompts mentioning "details"
    "explain the details of how transformers work in machine learning",
    "give me details on the rules of chess",
    "search for details regarding the upcoming solar eclipse",
    "can you provide more details about ancient Rome",
    "what are the architectural details of the Eiffel Tower",
    "give me the full details of the theory of relativity",
]

def run_confusion_matrix_test():
    engine = IntentEngine()
    passed = 0
    failed = 0
    results = []

    print("\n" + "=" * 90)
    print("   INTENT CONFUSION MATRIX TEST (30 NON-FILE PROMPTS)")
    print("=" * 90)
    print(f"{'#':<3} | {'Prompt':<55} | {'Intent':<15} | {'File Tool?':<10}")
    print("-" * 90)

    for i, p in enumerate(PROMPTS, 1):
        res = engine.parse(p, use_llm=False)
        is_file_tool = (res.intent in ("filesystem", "fs_list_dir", "file_op") or
                        getattr(res, "action", "") in ("create_file", "create_folder", "list_dir", "delete_file", "delete_folder"))

        p_display = (p[:52] + "...") if len(p) > 55 else p
        status_str = "YES (FAIL)" if is_file_tool else "NO (PASS)"
        print(f"{i:<3} | {p_display:<55} | {res.intent:<15} | {status_str:<10}")

        results.append({
            "index": i,
            "prompt": p,
            "intent": res.intent,
            "confidence": res.confidence,
            "is_file_tool": is_file_tool
        })

        if is_file_tool:
            failed += 1
        else:
            passed += 1

    print("-" * 90)
    print(f"TOTAL: {len(PROMPTS)} | PASSED (Zero File Tools): {passed} | FAILED: {failed}")
    print("=" * 90 + "\n")

    assert failed == 0, f"Confusion matrix test failed: {failed} non-file prompts were classified as filesystem operations!"
    return results

if __name__ == "__main__":
    run_confusion_matrix_test()

