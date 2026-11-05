import sys
import shutil
import uuid
from pathlib import Path
from typing import Optional, List
import numpy as np

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.app.config import (
    PROJECT_ROOT,
    RAW_AUDIO_DIR,
    CLIPS_AUDIO_DIR,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_MARGIN_THRESHOLD,
    RECOGNITION_AGGREGATION_METHOD,
    TARGET_SAMPLE_RATE,
    ENCODER_MODEL_NAME,
)
from backend.app.database.connection import get_db_connection
from backend.app.database.vocabulary import (
    get_vocabulary_by_id,
    list_vocabulary,
    insert_vocabulary_entry,
    get_vocabulary_count,
)
from backend.app.database.recordings import (
    insert_recording_entry,
    get_recording_by_id,
    list_recordings_for_word,
    list_all_recordings,
)
from backend.app.audio.validation import validate_audio_file
from backend.app.audio.preprocessing import load_and_standardize_audio, save_standardized_audio
from backend.app.audio.segmentation import suggest_speech_segments_vad, create_segment_clip
from backend.app.embeddings.extraction import extract_audio_embedding
from backend.app.embeddings.storage import (
    save_embedding_with_metadata,
    get_embedding_file_path,
)
from backend.app.services.recognition import recognize_spoken_word
from backend.app.services.gemini_recognition import is_gemini_available, match_text_transliteration
from backend.app.services.tts_service import generate_neural_tts

app = FastAPI(
    title="Badaga & Marwari Audio Recognition API",
    description="Closed-vocabulary voice recognition and verified meaning retrieval for Badaga and Marwari.",
    version="1.0.0",
)

# Enable CORS for frontend Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Request Models ---

class VocabularyCreateRequest(BaseModel):
    word_id: str = Field(..., description="Canonical Word ID, e.g. BDG_W0001 or MWR_W0001")
    language: str = Field(..., pattern="^(Badaga|Marwari)$")
    tamil_meaning: str
    english_meaning: str
    optional_romanised_pronunciation: Optional[str] = None
    notes: Optional[str] = None
    verification_status: str = "verified"


class AudioSegmentRequest(BaseModel):
    file_path: str
    start_time: float
    end_time: float
    clip_id: str
    word_id: str
    speaker_id: str = "UNKNOWN"


class RecordingRegisterRequest(BaseModel):
    clip_id: str
    word_id: str
    speaker_id: str
    clip_file: str
    original_file: Optional[str] = None
    start_timestamp: float = 0.0
    end_timestamp: Optional[float] = None
    sample_rate: int = TARGET_SAMPLE_RATE
    duration: Optional[float] = None
    review_status: str = "reviewed"


class TextTranslateRequest(BaseModel):
    text: str = Field(..., description="Badaga or Marwari word written in English transliteration or English meaning")
    language: Optional[str] = Field("Badaga", pattern="^(Badaga|Marwari)$")



# --- API Endpoints ---

@app.get("/")
def root():
    """Root endpoint welcoming users and directing to frontend and API docs."""
    return {
        "status": "online",
        "app": "KURINJI Speech Translation API",
        "frontend": "http://localhost:5173",
        "api_docs": "http://127.0.0.1:8000/docs",
    }


@app.get("/api/health")
def health_check():
    """Returns application health, database status, and vocabulary/embedding counts."""
    with get_db_connection() as conn:
        vocab_count = conn.execute("SELECT COUNT(*) FROM vocabulary;").fetchone()[0]
        rec_count = conn.execute("SELECT COUNT(*) FROM recordings;").fetchone()[0]
        emb_count = conn.execute("SELECT COUNT(*) FROM embeddings;").fetchone()[0]

    return {
        "status": "healthy",
        "encoder": ENCODER_MODEL_NAME,
        "sample_rate": TARGET_SAMPLE_RATE,
        "gemini_enabled": is_gemini_available(),
        "counts": {
            "vocabulary": vocab_count,
            "recordings": rec_count,
            "embeddings": emb_count,
        },
    }


@app.post("/api/audio/upload")
async def upload_audio(file: UploadFile = File(...)):
    """
    Uploads an audio file, standardizes it to 16 kHz mono WAV,
    validates duration and signal integrity, and generates VAD segmentation suggestions.
    """
    RAW_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    temp_filename = f"upload_{uuid.uuid4().hex[:8]}_{Path(file.filename or 'audio.wav').stem}.wav"
    raw_dest = RAW_AUDIO_DIR / temp_filename

    # Save uploaded file
    with open(raw_dest, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Validate audio
    is_valid, msg, meta = validate_audio_file(raw_dest)
    if not is_valid:
        if raw_dest.is_file():
            raw_dest.unlink()
        raise HTTPException(status_code=400, detail=msg)

    # Standardize to 16kHz mono float32
    waveform, sr = load_and_standardize_audio(raw_dest, target_sr=TARGET_SAMPLE_RATE)
    save_standardized_audio(waveform, raw_dest, sample_rate=sr)

    # Suggest segments for repeated pronunciations (Section 2.3)
    vad_suggestions = suggest_speech_segments_vad(waveform, sample_rate=sr)

    return {
        "status": "success",
        "file_path": str(raw_dest),
        "filename": temp_filename,
        "sample_rate": sr,
        "duration": round(len(waveform) / float(sr), 3),
        "vad_suggestions": vad_suggestions,
    }


@app.post("/api/audio/segment")
def create_segment(req: AudioSegmentRequest):
    """
    Creates a confirmed audio segment between start_time and end_time,
    saves the clip, and registers it in the recordings database.
    """
    input_path = Path(req.file_path)
    if not input_path.is_file():
        raise HTTPException(status_code=404, detail="Original audio file not found.")

    CLIPS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_clip_path = CLIPS_AUDIO_DIR / f"{req.clip_id}.wav"

    try:
        saved_path, duration = create_segment_clip(
            original_audio_path=input_path,
            start_time=req.start_time,
            end_time=req.end_time,
            output_clip_path=out_clip_path,
        )

        rec = insert_recording_entry(
            clip_id=req.clip_id,
            word_id=req.word_id,
            speaker_id=req.speaker_id,
            clip_file=str(saved_path),
            original_file=str(input_path),
            start_timestamp=req.start_time,
            end_timestamp=req.end_time,
            duration=duration,
            sample_rate=TARGET_SAMPLE_RATE,
            review_status="reviewed",
        )

        return {"status": "success", "recording": rec}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recognize")
async def recognize_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    similarity_threshold: float = Form(DEFAULT_SIMILARITY_THRESHOLD),
    margin_threshold: float = Form(DEFAULT_MARGIN_THRESHOLD),
    aggregation_method: str = Form(RECOGNITION_AGGREGATION_METHOD),
):
    """
    Processes an incoming query audio recording, extracts its XLS-R representation,
    matches against stored reference embeddings, and returns predicted word with verified meanings.
    """
    temp_query_path = RAW_AUDIO_DIR / f"query_{uuid.uuid4().hex[:8]}.wav"
    try:
        with open(temp_query_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = temp_query_path.stat().st_size
        print(f"[Audio Ingest] Received query: {file.filename} ({file.content_type}, {file_size} bytes) for language: {language}")

        result = recognize_spoken_word(
            audio_input=temp_query_path,
            language=language,
            similarity_threshold=similarity_threshold,
            margin_threshold=margin_threshold,
            aggregation_method=aggregation_method,
        )

        top_cand = result.get("word_id")
        sim = result.get("similarity", 0.0)
        status = result.get("status", "unknown")

        # Attach matched learning card if available
        if top_cand:
            modules_file = Path(__file__).resolve().parent.parent / "data" / "learning_modules.json"
            if modules_file.is_file():
                import json
                try:
                    with open(modules_file, "r", encoding="utf-8") as f:
                        mdata = json.load(f)
                        for card in mdata.get("cards", []):
                            if card.get("word_id") == top_cand:
                                result["learning_card"] = card
                                break
                except Exception:
                    pass

        try:
            print(f"[Audio Match] Status: {status} | Top Candidate: {top_cand} | Similarity: {sim:.4f} | Margin: {result.get('margin', 0.0):.4f}")
        except Exception:
            pass
        return result
    finally:
        if temp_query_path.is_file():
            try:
                temp_query_path.unlink()
            except Exception:
                pass


@app.get("/api/modules")
def get_learning_modules():
    """Returns the primary learning modules and concept cards for kindergarten to class 5."""
    modules_file = Path(__file__).resolve().parent.parent / "data" / "learning_modules.json"
    if modules_file.is_file():
        import json
        with open(modules_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"modules": [], "cards": []}


@app.post("/api/translate/text")
def translate_text(req: TextTranslateRequest):
    """
    Translates a Badaga or Marwari word written in English transliteration
    (e.g. 'thale', 'kannu', 'mandhe', 'mooku', 'pal') and retrieves verified Tamil/English meanings.
    """
    result = match_text_transliteration(query_text=req.text, language=req.language)

    # Attach matched learning card if available
    matched_word_id = result.get("word_id")
    if matched_word_id:
        modules_file = Path(__file__).resolve().parent.parent / "data" / "learning_modules.json"
        if modules_file.is_file():
            import json
            try:
                with open(modules_file, "r", encoding="utf-8") as f:
                    mdata = json.load(f)
                    for card in mdata.get("cards", []):
                        if card.get("word_id") == matched_word_id:
                            result["learning_card"] = card
                            break
            except Exception:
                pass

    return result




@app.get("/api/vocabulary")
def get_vocabulary(
    language: Optional[str] = Query(None, pattern="^(Badaga|Marwari)$"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Lists verified vocabulary entries."""
    entries = list_vocabulary(language=language, limit=limit, offset=offset)
    total = get_vocabulary_count(language=language)
    return {"total": total, "entries": entries}


@app.post("/api/vocabulary")
def add_vocabulary_entry(entry: VocabularyCreateRequest):
    """Adds a human-verified vocabulary entry."""
    vocab = insert_vocabulary_entry(
        word_id=entry.word_id,
        language=entry.language,
        tamil_meaning=entry.tamil_meaning,
        english_meaning=entry.english_meaning,
        optional_romanised_pronunciation=entry.optional_romanised_pronunciation,
        notes=entry.notes,
        verification_status=entry.verification_status,
    )
    return {"status": "success", "vocabulary": vocab}


@app.get("/api/vocabulary/{word_id}")
def get_vocabulary_detail(word_id: str):
    """Retrieves vocabulary details and associated reference recordings."""
    vocab = get_vocabulary_by_id(word_id)
    if not vocab:
        raise HTTPException(status_code=404, detail="Word ID not found.")

    recordings = list_recordings_for_word(word_id)
    return {"vocabulary": vocab, "recordings": recordings}


@app.post("/api/recordings")
def register_recording(rec: RecordingRegisterRequest):
    """Registers a reference recording entry."""
    res = insert_recording_entry(
        clip_id=rec.clip_id,
        word_id=rec.word_id,
        speaker_id=rec.speaker_id,
        clip_file=rec.clip_file,
        original_file=rec.original_file,
        start_timestamp=rec.start_timestamp,
        end_timestamp=rec.end_timestamp,
        sample_rate=rec.sample_rate,
        duration=rec.duration,
        review_status=rec.review_status,
    )
    return {"status": "success", "recording": res}


@app.post("/api/embeddings/extract")
def extract_single_embedding(clip_id: str = Form(...)):
    """Generates and stores an XLS-R embedding for an existing reference clip."""
    rec = get_recording_by_id(clip_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Clip ID not found in database.")

    clip_path = Path(rec["clip_file"])
    if not clip_path.is_file():
        raise HTTPException(status_code=404, detail=f"Audio file not found on disk: {clip_path}")

    try:
        waveform, sr = load_and_standardize_audio(clip_path, target_sr=TARGET_SAMPLE_RATE)
        vec, _ = extract_audio_embedding(waveform, sample_rate=sr)
        saved_path = save_embedding_with_metadata(
            clip_id=clip_id,
            word_id=rec["word_id"],
            vector=vec,
        )
        return {
            "status": "success",
            "clip_id": clip_id,
            "word_id": rec["word_id"],
            "embedding_file": str(saved_path),
            "dimension": vec.shape[0],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audio/playback/{clip_id}")
def stream_audio_clip(clip_id: str):
    """Serves audio clip for browser playback."""
    rec = get_recording_by_id(clip_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")

    audio_path = Path(rec["clip_file"])
    if not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file missing on disk.")

    return FileResponse(str(audio_path), media_type="audio/wav")


@app.get("/api/tts")
async def get_neural_tts(
    text: str = Query(..., min_length=1, max_length=500, description="Text to synthesize"),
    lang: str = Query("ta", description="Language: 'ta' or 'en'"),
):
    """
    Synthesizes crystal-clear studio quality speech using neural voices
    (ta-IN-PallaviNeural for Tamil, en-US-JennyNeural for English).
    Returns cached MP3 audio stream for instant playback.
    """
    try:
        audio_path = await generate_neural_tts(text=text, lang=lang)
        return FileResponse(str(audio_path), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(e)}")


# Mount static production frontend build if available (single-service Render deployment)
frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
