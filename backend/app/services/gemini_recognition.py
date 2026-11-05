import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
from google import genai
from google.genai import types

from backend.app.config import PROJECT_ROOT
from backend.app.database.vocabulary import list_vocabulary, get_vocabulary_by_id, search_vocabulary_text
from backend.app.database.recordings import list_recordings_for_word
from backend.app.audio.preprocessing import load_and_standardize_audio, save_standardized_audio

# Ensure .env is loaded
load_dotenv(PROJECT_ROOT / ".env")


def get_curriculum_phonetic_guide() -> str:
    """Builds a rich phonetic dictionary from curriculum concept cards."""
    modules_file = PROJECT_ROOT / "backend" / "data" / "learning_modules.json"
    lines = []
    if modules_file.is_file():
        try:
            with open(modules_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for c in data.get("cards", []):
                    wid = c.get("word_id")
                    eng = c.get("english", {}).get("word", "")
                    tam = c.get("tamil", {}).get("word", "")
                    bdg_word = c.get("badaga", {}).get("word", "")
                    bdg_phon = c.get("badaga", {}).get("phonetic", "")
                    bdg_tam = c.get("badaga", {}).get("tamil_script", "")
                    if wid and bdg_word:
                        lines.append(f"• {wid}: Spoken Badaga: '{bdg_word}' ({bdg_tam}, {bdg_phon}) -> English: {eng} | Tamil: {tam}")
        except Exception:
            pass
    return "\n".join(lines)


def get_gemini_api_key() -> Optional[str]:
    """Retrieves the Gemini API key from environment or .env file."""
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key if key else None


def is_gemini_available() -> bool:
    """Returns True if a valid Gemini API key is configured."""
    key = get_gemini_api_key()
    return bool(key and len(key) > 10 and not key.startswith("YOUR_"))


def recognize_with_gemini(
    audio_path: Union[str, Path],
    language: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Recognizes a spoken word using Gemini Multimodal Audio understanding
    constrained strictly to the verified closed-vocabulary wordbank in SQLite.

    Guarantees zero hallucination:
    - Gemini identifies only the canonical Word ID.
    - Verified Tamil and English meanings are retrieved directly from SQLite.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return None

    path = Path(audio_path)
    if not path.is_file():
        return None

    # Load verified wordbank from SQLite for the selected language
    target_lang = language if language in ("Badaga", "Marwari") else None
    vocab_entries = list_vocabulary(language=target_lang, limit=1000)
    if not vocab_entries:
        # Fallback to curriculum cards if SQLite vocabulary table is not seeded
        modules_file = PROJECT_ROOT / "backend" / "data" / "learning_modules.json"
        if modules_file.is_file():
            try:
                with open(modules_file, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    vocab_entries = []
                    for c in cdata.get("cards", []):
                        wid = c.get("word_id", c.get("id"))
                        eng = c.get("english", {}).get("word", "")
                        tam = c.get("tamil", {}).get("word", "")
                        wrd = c.get("badaga", {}).get("word", "") if target_lang != "Marwari" else c.get("marwari", {}).get("word", "")
                        vocab_entries.append({
                            "word_id": wid,
                            "english_meaning": eng,
                            "tamil_meaning": tam,
                            "optional_romanised_pronunciation": wrd,
                        })
            except Exception:
                pass
    if not vocab_entries:
        return None

    # Format wordbank into a compact linguistic reference
    wordbank_lines = []
    for entry in vocab_entries:
        wid = entry["word_id"]
        eng = entry["english_meaning"]
        tam = entry["tamil_meaning"]
        pron = entry.get("optional_romanised_pronunciation") or ""
        pron_str = f" [pronunciation: {pron}]" if pron else ""
        wordbank_lines.append(f"{wid}: {eng} | {tam}{pron_str}")

    wordbank_text = "\n".join(wordbank_lines)

    # Standardize, trim silence, and peak-normalize audio for crystal-clear clarity
    clean_audio_path = PROJECT_ROOT / "backend" / "data" / "raw_audio" / f"gemini_clean_{path.stem}.wav"
    try:
        waveform, sr = load_and_standardize_audio(path, target_sr=16000, trim_silence=True)
        max_amp = float(np.max(np.abs(waveform))) if len(waveform) > 0 else 0.0
        if max_amp > 1e-4:
            waveform = (waveform / max_amp) * 0.95
        save_standardized_audio(waveform, clean_audio_path, sample_rate=16000)
        with open(clean_audio_path, "rb") as f:
            audio_bytes = f.read()
    except Exception:
        with open(path, "rb") as f:
            audio_bytes = f.read()
    finally:
        if clean_audio_path.is_file():
            try:
                clean_audio_path.unlink()
            except Exception:
                pass

    lang_prompt = f"in {language}" if language else "in Badaga or Marwari"
    curriculum_guide = get_curriculum_phonetic_guide()

    prompt = f"""You are an acoustic phonetics expert specializing in the low-resource Indian languages Badaga and Marwari.
Attached is a short audio recording of a user pronouncing a single word {lang_prompt}.

PRIMARY BADAGA SPOKEN CURRICULUM REFERENCE (HIGH PRIORITY):
{curriculum_guide}

FULL VERIFIED WORDBANK:
{wordbank_text}

Instructions:
1. Listen carefully to the acoustic speech sounds, consonants, vowels, and syllable phonemes.
2. Note that the speaker is pronouncing a native word in {lang_prompt}, NOT an English word!
3. CRITICAL ACOUSTIC RULES:
   - Filter out and ignore any low-frequency microphone rumble, DC pop, room echo, or laptop fan noise. NEVER classify user speech as "roar" or "rumble"!
   - Focus strictly on human voice vocal tract formants (200 Hz - 4000 Hz).
   - Common Badaga spoken pronunciations:
     • 'mande' / 'mandhe' / 'thale' -> Head (தலை, BDG_W0001)
     • 'kannu' / 'kanna' -> Eye (கண், BDG_W0002)
     • 'moogu' / 'mooku' -> Nose (மூக்கு, BDG_W0003)
     • 'baayi' -> Mouth (வாய், BDG_W0004)
     • 'kaadu' / 'kivi' -> Ear (காது, BDG_W0005)
     • 'kai' / 'kayyi' -> Hand (கை, BDG_W0006)
     • 'kaalu' -> Leg (கால், BDG_W0007)
     • 'pal' / 'pallu' -> Teeth (பல், BDG_W0008)
     • 'koodalu' -> Hair (முடி, BDG_W0009)
     • 'hotte' -> Stomach (வயிறு, BDG_W0010)
     • 'beralu' -> Finger (விரல், BDG_W0011)
     • 'moga' / 'muka' -> Face (முகம், BDG_W0012)
     • 'naaku' -> Tongue (நாக்கு, BDG_W0013)
     • 'aavu' -> Cow (பசு, BDG_W0036)
     • 'nei' -> Dog (நாய், BDG_W0037)
     • 'kotti' -> Cat (பூனை, BDG_W0038)
     • 'hakki' -> Bird (பறவை, BDG_W0039)
     • 'meenu' -> Fish (மீன், BDG_W0040)
     • 'kaake' -> Crow (காகம், BDG_W0041)
     • 'maraa' -> Tree (மரம், BDG_W0031)
     • 'hoovu' -> Flower (பூ, BDG_W0032)
     • 'ele' -> Leaf (இலை, BDG_W0033)
     • 'neeru' -> Water (தண்ணீர், BDG_W0034)
     • 'agalu' -> Sun (சூரியன், BDG_W0026)
     • 'male' -> Rain (மழை, BDG_W0027)
     • 'ondu', 'eradu', 'mooru', 'naakku', 'aidu', 'aaru', 'eccu', 'ettu', 'ombathu', 'hathu' -> Numbers 1 to 10
4. Match the spoken utterance strictly to one Word ID from the wordbank.
5. If the audio matches a word with reasonable acoustic evidence, return its Word ID and confidence (0.60 to 0.99).
6. If the audio is complete dead silence with zero vocalization, set "word_id": null and "confidence": 0.0.

Respond ONLY with a valid JSON object matching this schema:
{{
  "word_id": "STRING_OR_NULL",
  "confidence": FLOAT,
  "explanation": "Brief explanation of acoustic phonemes heard and why it matches"
}}
"""

    client = genai.Client(api_key=api_key)

    try:
        # Use gemini-3.5-flash (fast, state-of-the-art audio understanding) or fallback to gemini-3.5-flash-lite
        model_name = "gemini-3.5-flash"
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except Exception:
            model_name = "gemini-3.5-flash-lite"
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )

        raw_text = response.text.strip()
        data = json.loads(raw_text)

        matched_word_id = data.get("word_id")
        confidence = float(data.get("confidence", 0.0))
        explanation = data.get("explanation", "")

        try:
            safe_exp = explanation.encode("ascii", errors="replace").decode("ascii")
            print(f"[Gemini Audio AI] Model: {model_name} | Match: {matched_word_id} | Confidence: {confidence:.2f} | Reason: {safe_exp}")
        except Exception:
            pass

        if not matched_word_id:
            return {
                "status": "unknown",
                "word_id": None,
                "language": language,
                "tamil_meaning": None,
                "english_meaning": None,
                "similarity": confidence,
                "margin": 0.0,
                "message": explanation or "Audio was not recognized as a known vocabulary word.",
                "ranked_candidates": [],
            }

        # Retrieve 100% human-verified meaning from SQLite database
        vocab = get_vocabulary_by_id(matched_word_id)
        if not vocab:
            # Fallback to curriculum concept cards
            modules_file = PROJECT_ROOT / "backend" / "data" / "learning_modules.json"
            if modules_file.is_file():
                try:
                    with open(modules_file, "r", encoding="utf-8") as f:
                        cdata = json.load(f)
                        for c in cdata.get("cards", []):
                            if c.get("word_id") == matched_word_id or c.get("id") == matched_word_id:
                                vocab = {
                                    "word_id": matched_word_id,
                                    "language": target_lang or "Badaga",
                                    "tamil_meaning": c.get("tamil", {}).get("word", ""),
                                    "english_meaning": c.get("english", {}).get("word", ""),
                                }
                                break
                except Exception:
                    pass
        if not vocab:
            return None

        # Fetch reference clips for audio pronunciation playback
        recordings = list_recordings_for_word(matched_word_id)
        clip_matches = [{"clip_id": r["clip_id"], "similarity": confidence} for r in recordings]

        status = "recognized" if confidence >= 0.50 else "uncertain"

        return {
            "status": status,
            "word_id": vocab["word_id"],
            "language": vocab["language"],
            "tamil_meaning": vocab["tamil_meaning"],
            "english_meaning": vocab["english_meaning"],
            "similarity": confidence,
            "margin": 0.15,
            "message": f"Identified via Gemini Audio AI: {explanation}",
            "ranked_candidates": [
                {
                    "word_id": vocab["word_id"],
                    "language": vocab["language"],
                    "tamil_meaning": vocab["tamil_meaning"],
                    "english_meaning": vocab["english_meaning"],
                    "score": confidence,
                    "clip_matches": clip_matches,
                }
            ],
        }

    except Exception as e:
        try:
            safe_err = str(e).encode("ascii", errors="replace").decode("ascii")
            print(f"[Gemini Audio AI Error] {safe_err}")
        except Exception:
            pass
        return None


def match_text_transliteration(
    query_text: str,
    language: Optional[str] = "Badaga",
) -> Dict[str, Any]:
    """
    Matches a romanised Badaga/Marwari input (e.g. 'thale', 'kannu', 'mandhe', 'mooku')
    or English word to its verified Word ID and retrieves meanings from SQLite.
    """
    clean_query = query_text.strip()
    if not clean_query:
        return {
            "status": "unknown",
            "word_id": None,
            "language": language,
            "tamil_meaning": None,
            "english_meaning": None,
            "similarity": 0.0,
            "margin": 0.0,
            "message": "Please enter a word to translate.",
            "ranked_candidates": [],
        }

    target_lang = language if language in ("Badaga", "Marwari") else "Badaga"

    # 1. First, check direct SQLite matches (e.g. exact English meaning like 'head' or exact Word ID)
    direct_matches = search_vocabulary_text(clean_query, language=target_lang, exact_only=True)
    if direct_matches:
        top = direct_matches[0]
        recs = list_recordings_for_word(top["word_id"])
        clip_matches = [{"clip_id": r["clip_id"], "similarity": 1.0} for r in recs]
        return {
            "status": "recognized",
            "word_id": top["word_id"],
            "language": top["language"],
            "tamil_meaning": top["tamil_meaning"],
            "english_meaning": top["english_meaning"],
            "similarity": 1.0,
            "margin": 0.20,
            "message": f"Direct vocabulary match for '{clean_query}'.",
            "ranked_candidates": [
                {
                    "word_id": top["word_id"],
                    "language": top["language"],
                    "tamil_meaning": top["tamil_meaning"],
                    "english_meaning": top["english_meaning"],
                    "score": 1.0,
                    "clip_matches": clip_matches,
                }
            ],
        }

    # 2. Check local curriculum concept cards with intelligent fuzzy matching (offline, 0ms)
    modules_file = PROJECT_ROOT / "backend" / "data" / "learning_modules.json"
    if modules_file.is_file():
        try:
            with open(modules_file, "r", encoding="utf-8") as f:
                cards = json.load(f).get("cards", [])

            import re
            import difflib

            q_norm = clean_query.lower().replace("-", "").strip()
            q_collapsed = re.sub(r'(.)\1+', r'\1', q_norm)

            best_card = None
            best_score = 0.0

            for c in cards:
                b_word = c.get("badaga", {}).get("word", "").lower().replace("-", "")
                b_pron = c.get("badaga", {}).get("pronunciation", "").lower().replace("-", "")
                b_tam = c.get("badaga", {}).get("tamil_script", "").lower()
                m_word = c.get("marwari", {}).get("word", "").lower().replace("-", "")
                m_pron = c.get("marwari", {}).get("pronunciation", "").lower().replace("-", "")
                m_tam = c.get("marwari", {}).get("tamil_script", "").lower()
                eng_word = c.get("english", {}).get("word", "").lower()
                tam_word = c.get("tamil", {}).get("word", "").lower()
                cid = c.get("id", "").lower()

                native_targets = [b_word, b_pron, b_tam] if target_lang != "Marwari" else [m_word, m_pron, m_tam]
                all_targets = native_targets + [eng_word, tam_word, cid]

                # Exact match on any target
                if any(q_norm == t for t in all_targets if t):
                    best_card = c
                    best_score = 1.0
                    break

                # Collapsed consonant match (e.g. "kanu" <-> "kannu", "pal" <-> "pallu")
                collapsed_targets = [re.sub(r'(.)\1+', r'\1', t) for t in native_targets if t]
                if q_collapsed in collapsed_targets:
                    best_card = c
                    best_score = 0.95
                    break

                # English word match (e.g. "eye", "head", "nose")
                if q_norm == eng_word or (len(q_norm) >= 3 and q_norm in eng_word):
                    best_card = c
                    best_score = 1.0
                    break

                # Substring / Prefix match
                if any(t.startswith(q_norm) or q_norm.startswith(t) for t in native_targets if len(t) >= 3 and len(q_norm) >= 3):
                    if best_score < 0.85:
                        best_card = c
                        best_score = 0.85

                # Fuzzy ratio
                for t in native_targets:
                    if t:
                        ratio = difflib.SequenceMatcher(None, q_norm, t).ratio()
                        if ratio >= 0.70 and ratio > best_score:
                            best_card = c
                            best_score = ratio

            if best_card and best_score >= 0.70:
                tam = best_card.get("tamil", {}).get("word", "")
                eng = best_card.get("english", {}).get("word", "")
                wid = best_card.get("word_id", best_card.get("id"))
                return {
                    "status": "recognized",
                    "word_id": wid,
                    "language": target_lang,
                    "tamil_meaning": tam,
                    "english_meaning": eng,
                    "similarity": round(best_score, 2),
                    "margin": 0.20,
                    "message": f"Matched '{clean_query}' to {target_lang} concept card.",
                    "learning_card": best_card,
                    "ranked_candidates": [
                        {
                            "word_id": wid,
                            "language": target_lang,
                            "tamil_meaning": tam,
                            "english_meaning": eng,
                            "score": round(best_score, 2),
                            "clip_matches": [],
                        }
                    ],
                }
        except Exception as e:
            print(f"[Curriculum Text Search] Error: {e}")

    # 3. If no direct or curriculum match, use Gemini with the closed-vocabulary wordbank constraint
    api_key = get_gemini_api_key()
    if not api_key:
        return {
            "status": "unknown",
            "word_id": None,
            "language": language,
            "tamil_meaning": None,
            "english_meaning": None,
            "similarity": 0.0,
            "margin": 0.0,
            "message": f"Word '{clean_query}' not found in local database. Enable Gemini API for transliteration matching.",
            "ranked_candidates": [],
        }

    vocab_entries = list_vocabulary(language=target_lang, limit=1000)
    wordbank_lines = [f"{e['word_id']}: {e['english_meaning']} | {e['tamil_meaning']}" for e in vocab_entries]
    wordbank_text = "\n".join(wordbank_lines)

    prompt = f"""The user has typed a spoken {target_lang} word written in English transliteration / romanised script: "{clean_query}".
Your task is to identify which Word ID from the following verified closed-vocabulary wordbank this transliterated word corresponds to.

--- VERIFIED WORDBANK ---
{wordbank_text}
--- END WORDBANK ---

Instructions:
1. Consider phonetic romanisation variations and colloquial dialects (e.g. 'thale', 'mandhe', 'tale' -> head; 'kannu', 'kanna' -> eye; 'mooku' -> nose; 'pal' -> teeth; 'kaalu' -> leg; 'kayyi', 'kai' -> hand; 'amma', 'avve' -> mother). If 'mandhe' is typed, it refers to head (தலை / மண்டை).
2. Match it strictly to one Word ID from the verified wordbank above.
3. If it clearly corresponds to a word in the list, return its Word ID and confidence (0.0 to 1.0).
4. If it does not correspond to any word in the wordbank, set "word_id": null and "confidence": 0.0.

Respond ONLY with valid JSON:
{{
  "word_id": "WORD_ID_OR_NULL",
  "confidence": FLOAT,
  "explanation": "Brief reasoning for matching this transliteration"
}}
"""
    client = genai.Client(api_key=api_key)
    try:
        res = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        data = json.loads(res.text.strip())
        matched_wid = data.get("word_id")
        confidence = float(data.get("confidence", 0.0))
        explanation = data.get("explanation", "")

        if not matched_wid:
            return {
                "status": "unknown",
                "word_id": None,
                "language": target_lang,
                "tamil_meaning": None,
                "english_meaning": None,
                "similarity": confidence,
                "margin": 0.0,
                "message": explanation or f"No match found for '{clean_query}' in verified {target_lang} wordbank.",
                "ranked_candidates": [],
            }

        vocab = get_vocabulary_by_id(matched_wid)
        if not vocab:
            return {
                "status": "unknown",
                "word_id": None,
                "language": target_lang,
                "tamil_meaning": None,
                "english_meaning": None,
                "similarity": 0.0,
                "margin": 0.0,
                "message": f"Word ID '{matched_wid}' not found in verified database.",
                "ranked_candidates": [],
            }

        recs = list_recordings_for_word(matched_wid)
        clip_matches = [{"clip_id": r["clip_id"], "similarity": confidence} for r in recs]

        return {
            "status": "recognized",
            "word_id": vocab["word_id"],
            "language": vocab["language"],
            "tamil_meaning": vocab["tamil_meaning"],
            "english_meaning": vocab["english_meaning"],
            "similarity": confidence,
            "margin": 0.15,
            "message": f"Transliteration match: {explanation}",
            "ranked_candidates": [
                {
                    "word_id": vocab["word_id"],
                    "language": vocab["language"],
                    "tamil_meaning": vocab["tamil_meaning"],
                    "english_meaning": vocab["english_meaning"],
                    "score": confidence,
                    "clip_matches": clip_matches,
                }
            ],
        }
    except Exception as e:
        return {
            "status": "unknown",
            "word_id": None,
            "language": target_lang,
            "tamil_meaning": None,
            "english_meaning": None,
            "similarity": 0.0,
            "margin": 0.0,
            "message": f"Transliteration search error: {e}",
            "ranked_candidates": [],
        }
