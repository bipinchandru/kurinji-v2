from pathlib import Path
from typing import Dict, Any, Optional, Union
import numpy as np

from backend.app.config import (
    TARGET_SAMPLE_RATE,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_MARGIN_THRESHOLD,
    RECOGNITION_AGGREGATION_METHOD,
)
from backend.app.audio.preprocessing import load_and_standardize_audio
from backend.app.audio.validation import validate_audio_file, detect_excessive_silence
from backend.app.embeddings.extraction import extract_audio_embedding
from backend.app.embeddings.storage import load_all_reference_embeddings
from backend.app.matching.candidate_ranking import rank_candidates
from backend.app.matching.rejection import evaluate_recognition_decision
from backend.app.services.gemini_recognition import is_gemini_available, recognize_with_gemini


def recognize_spoken_word(
    audio_input: Union[str, Path, np.ndarray],
    language: Optional[str] = None,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    margin_threshold: float = DEFAULT_MARGIN_THRESHOLD,
    aggregation_method: str = RECOGNITION_AGGREGATION_METHOD,
) -> Dict[str, Any]:
    """
    Executes the end-to-end recognition pipeline:
    1. Audio preprocessing (16kHz mono standardization).
    2. Validation & excessive silence check.
    3. Primary Recognition: Gemini Multimodal Audio AI (if GEMINI_API_KEY is configured).
    4. Secondary / Fallback: Frozen XLS-R 300M embedding matching (100% offline).
    5. Verified wordbank lookup from SQLite (Tamil & English meanings).
    """
    # 1. Standardize Audio
    file_path = None
    if isinstance(audio_input, (str, Path)):
        file_path = Path(audio_input)
        is_valid, reason, meta = validate_audio_file(file_path)
        if not is_valid:
            return {
                "status": "invalid_audio",
                "message": reason,
                "word_id": None,
                "language": language,
                "tamil_meaning": None,
                "english_meaning": None,
                "similarity": 0.0,
            }
        waveform, sr = load_and_standardize_audio(file_path, target_sr=TARGET_SAMPLE_RATE)
    else:
        waveform = audio_input.astype(np.float32)
        sr = TARGET_SAMPLE_RATE

    # 2. Silence check
    if detect_excessive_silence(waveform, sample_rate=sr):
        return {
            "status": "excessive_silence",
            "message": "Audio recording contains excessive silence or inaudible speech.",
            "word_id": None,
            "language": language,
            "tamil_meaning": None,
            "english_meaning": None,
            "similarity": 0.0,
        }

    # 3. Primary Recognition: Try Gemini Audio AI if API key is present
    if is_gemini_available() and file_path and file_path.is_file():
        try:
            gemini_result = recognize_with_gemini(file_path, language=language)
            if gemini_result is not None:
                return gemini_result
        except Exception as e:
            print(f"[Gemini Recognition Fallback] Falling back to local XLS-R: {e}")

    # 3. Extract XLS-R Embedding
    query_vector, _ = extract_audio_embedding(
        waveform=waveform,
        sample_rate=sr,
        pooling_method="mean",
    )

    # 4. Load Reference Embeddings from DB
    ref_entries = load_all_reference_embeddings(language=language)
    if not ref_entries:
        return {
            "status": "no_references",
            "message": "Speech AI requires GEMINI_API_KEY in .env on the server for real-time acoustic recognition.",
            "word_id": None,
            "language": language,
            "tamil_meaning": None,
            "english_meaning": None,
            "similarity": 0.0,
        }

    # 5. Rank Candidates with Selected Aggregation Method
    ranked_candidates = rank_candidates(
        query_vector=query_vector,
        reference_entries=ref_entries,
        aggregation_method=aggregation_method,
        top_n=10,
    )

    # 6. Apply Decision Rules (Rejection & Uncertainty check)
    decision = evaluate_recognition_decision(
        ranked_candidates=ranked_candidates,
        similarity_threshold=similarity_threshold,
        margin_threshold=margin_threshold,
    )

    status = decision["status"]
    top_cand = decision.get("top_candidate")

    if status == "recognized" and top_cand:
        return {
            "status": "recognized",
            "word_id": top_cand["word_id"],
            "language": top_cand["language"],
            "tamil_meaning": top_cand["tamil_meaning"],
            "english_meaning": top_cand["english_meaning"],
            "similarity": top_cand["score"],
            "margin": decision["margin"],
            "message": decision["message"],
            "ranked_candidates": decision["ranked_candidates"],
        }
    elif status == "uncertain" and top_cand:
        return {
            "status": "uncertain",
            "word_id": top_cand["word_id"],
            "language": top_cand["language"],
            "tamil_meaning": top_cand["tamil_meaning"],
            "english_meaning": top_cand["english_meaning"],
            "similarity": top_cand["score"],
            "margin": decision["margin"],
            "message": decision["message"],
            "ranked_candidates": decision["ranked_candidates"],
        }
    else:  # unknown
        return {
            "status": "unknown",
            "word_id": None,
            "language": language,
            "tamil_meaning": None,
            "english_meaning": None,
            "similarity": decision["best_score"],
            "margin": decision["margin"],
            "message": decision["message"],
            "ranked_candidates": decision["ranked_candidates"],
        }
