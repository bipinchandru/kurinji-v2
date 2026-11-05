import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.tts_service import generate_neural_tts, TTS_CACHE_DIR


async def warmup_all_curriculum_audio():
    modules_file = PROJECT_ROOT / "backend" / "data" / "learning_modules.json"
    if not modules_file.is_file():
        print(f"Error: Could not find {modules_file}")
        return

    with open(modules_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    cards = data.get("cards", [])
    print(f"Loaded {len(cards)} curriculum concept cards.")

    # Collect all unique text items to synthesize
    tamil_items = set()
    english_items = set()

    for card in cards:
        # 1. Tamil words and letter units
        tam = card.get("tamil", {})
        if tam.get("word"):
            tamil_items.add(tam["word"])
        for letter in tam.get("letters", []):
            if letter.strip():
                tamil_items.add(letter.strip())
        if tam.get("example"):
            tamil_items.add(tam["example"])

        # 2. English words and letter units
        eng = card.get("english", {})
        if eng.get("word"):
            english_items.add(eng["word"])
        for letter in eng.get("letters", []):
            if letter.strip():
                english_items.add(letter.strip())
        if eng.get("example"):
            english_items.add(eng["example"])

    total_tasks = len(tamil_items) + len(english_items)
    print(f"\nUnique audio snippets to cache:")
    print(f"  • Tamil snippets:   {len(tamil_items)}")
    print(f"  • English snippets: {len(english_items)}")
    print(f"  • Total snippets:   {total_tasks}")
    print(f"Cache directory: {TTS_CACHE_DIR}")

    # Remove any corrupted or silent files under 1KB
    cleaned_count = 0
    if TTS_CACHE_DIR.is_dir():
        for old_file in TTS_CACHE_DIR.glob("*.mp3"):
            if old_file.stat().st_size < 1000:
                old_file.unlink()
                cleaned_count += 1
    if cleaned_count > 0:
        print(f"Cleaned up {cleaned_count} silent/corrupted cache files.")
    print("")

    # Semaphore to prevent throttling while keeping generation fast
    semaphore = asyncio.Semaphore(4)
    completed_count = 0

    async def synthesize_item(text: str, lang: str):
        nonlocal completed_count
        async with semaphore:
            try:
                path = await generate_neural_tts(text=text, lang=lang)
                completed_count += 1
                progress = (completed_count / total_tasks) * 100
                display_text = (text[:24] + "..") if len(text) > 24 else text
                print(f"[{completed_count:3d}/{total_tasks:3d}] ({progress:5.1f}%) Cached [{lang}]: '{display_text}' -> {path.name}")
            except Exception as e:
                print(f"[ERROR] Failed to synthesize [{lang}] '{text}': {e}")

    tasks = []
    for item in sorted(tamil_items):
        tasks.append(synthesize_item(item, "ta"))
    for item in sorted(english_items):
        tasks.append(synthesize_item(item, "en"))

    print("Beginning batch neural synthesis...")
    await asyncio.gather(*tasks)
    print(f"\nWarmup complete! All {completed_count} audio files are cached on disk.")
    print("Now all first clicks in the browser will play with 0ms latency!")


if __name__ == "__main__":
    asyncio.run(warmup_all_curriculum_audio())

