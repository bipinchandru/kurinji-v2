import React, { useState, useEffect, useRef } from 'react';
import { Volume2, X, ChevronLeft, ChevronRight, Check, Play } from 'lucide-react';
import { Illustration } from './Illustrations';

export default function LearningCardModal({
  card,
  onClose,
  onNext,
  onPrev,
  hasPrev,
  hasNext,
  selectedLanguage = 'Badaga',
}) {
  const [playingState, setPlayingState] = useState(null); // 'native' | 'tamil' | 'english' | letterId
  const [isPlayingNative, setIsPlayingNative] = useState(false);
  const activeAudioRef = useRef(null);

  // Keyboard navigation & audio cleanup on unmount
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight' && hasNext) onNext();
      if (e.key === 'ArrowLeft' && hasPrev) onPrev();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (activeAudioRef.current) {
        activeAudioRef.current.pause();
        activeAudioRef.current = null;
      }
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, [hasNext, hasPrev, onNext, onPrev, onClose]);

  // Pre-buffer audio for current card's letters and words in browser memory
  useEffect(() => {
    if (!card) return;
    const itemsToPreload = [
      { text: card.tamil?.word, lang: 'ta' },
      ...(card.tamil?.letters || []).map((ch) => ({ text: ch, lang: 'ta' })),
      { text: card.english?.word, lang: 'en' },
      ...(card.english?.letters || []).map((ch) => ({ text: ch, lang: 'en' })),
    ];
    itemsToPreload.forEach(({ text, lang }) => {
      if (!text) return;
      const preAudio = new Audio(`/api/tts?text=${encodeURIComponent(text)}&lang=${lang}`);
      preAudio.preload = 'auto';
    });
  }, [card]);

  if (!card) return null;

  const nativeInfo = selectedLanguage === 'Marwari' ? card.marwari : card.badaga;

  // Speak via Studio-Grade Neural AI Voice (with Web Speech fallback)
  const speakText = async (text, lang, key) => {
    if (!text) return;

    // Interrupt any currently playing audio or speech
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
      activeAudioRef.current = null;
    }
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }

    setPlayingState(key);

    const langCode = lang && lang.startsWith('ta') ? 'ta' : 'en';
    const audioUrl = `/api/tts?text=${encodeURIComponent(text)}&lang=${langCode}`;

    try {
      const audio = new Audio(audioUrl);
      activeAudioRef.current = audio;

      audio.onended = () => {
        setPlayingState(null);
        activeAudioRef.current = null;
      };

      audio.onerror = () => {
        activeAudioRef.current = null;
        fallbackWebSpeech(text, lang, key);
      };

      await audio.play();
    } catch {
      fallbackWebSpeech(text, lang, key);
    }
  };

  const fallbackWebSpeech = (text, lang, key) => {
    if (!window.speechSynthesis || !text) {
      setPlayingState(null);
      return;
    }
    window.speechSynthesis.cancel();
    setPlayingState(key);

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 0.92;
    utterance.onend = () => setPlayingState(null);
    utterance.onerror = () => setPlayingState(null);
    window.speechSynthesis.speak(utterance);
  };

  // Play authentic native speaker audio from verified dataset
  const playNativeClip = async () => {
    setIsPlayingNative(true);
    setPlayingState('native');

    // 1. Direct audio file provided in frontend/public/audio/
    const directAudioUrl = selectedLanguage === 'Marwari'
      ? card.marwari_audio_url
      : card.badaga_audio_url;

    if (directAudioUrl) {
      try {
        const audio = new Audio(directAudioUrl);
        audio.onended = () => {
          setIsPlayingNative(false);
          setPlayingState(null);
        };
        audio.onerror = () => {
          setIsPlayingNative(false);
          setPlayingState(null);
        };
        await audio.play();
        return;
      } catch (err) {
        console.warn('Direct audio play failed, falling back to API:', err);
      }
    }

    // 2. Fallback: check dynamic backend recordings from database
    if (card.word_id) {
      try {
        const res = await fetch(`/api/vocabulary/${card.word_id}`);
        const data = await res.json();

        if (data.recordings && data.recordings.length > 0) {
          const clipId = data.recordings[0].clip_id;
          const audio = new Audio(`/api/audio/playback/${clipId}`);
          audio.onended = () => {
            setIsPlayingNative(false);
            setPlayingState(null);
          };
          audio.onerror = () => {
            setIsPlayingNative(false);
            setPlayingState(null);
          };
          await audio.play();
          return;
        }
      } catch (err) {
        console.error('API playback error:', err);
      }
    }

    setIsPlayingNative(false);
    setPlayingState(null);
  };

  return (
    <div className="learning-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="learning-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Top Control Bar */}
        <header className="modal-top-bar">
          <div className="modal-topic-badge">
            <span>TOPIC: {card.category ? card.category.toUpperCase() : 'GENERAL'}</span>
          </div>

          <div className="modal-controls-group">
            {hasPrev && (
              <button
                type="button"
                className="modal-nav-btn"
                onClick={onPrev}
                title="Previous concept (Left arrow)"
              >
                <ChevronLeft size={18} />
                <span>Prev</span>
              </button>
            )}
            {hasNext && (
              <button
                type="button"
                className="modal-nav-btn"
                onClick={onNext}
                title="Next concept (Right arrow)"
              >
                <span>Next</span>
                <ChevronRight size={18} />
              </button>
            )}
            <button
              type="button"
              className="modal-close-btn"
              onClick={onClose}
              title="Close card (Esc)"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* Modal Main Body */}
        <div className="modal-scroll-area">
          {/* Card Hero: Vector Cartoon Illustration */}
          <div className={`modal-illustration-hero theme-${card.category}`}>
            <div className="illustration-display-box">
              <Illustration name={card.illustration_name} size={130} />
            </div>
            <div className="hero-titles-block">
              <span className="hero-english-title">{card.english.word}</span>
              <span className="hero-tamil-title tamil-font">{card.tamil.word}</span>
            </div>
          </div>

          {/* SECTION 1: Mother Tongue (What Child Knows) */}
          <div className="learning-tier-card native-tier-card">
            <div className="tier-header-bar">
              <h3 className="tier-section-heading">Spoken Heritage ({selectedLanguage})</h3>
              <button
                type="button"
                className={`native-audio-action-btn ${isPlayingNative ? 'playing' : ''}`}
                onClick={playNativeClip}
                disabled={isPlayingNative}
                title={`Hear authentic native ${selectedLanguage} voice from dataset`}
              >
                <Volume2 size={16} />
                <span>{isPlayingNative ? 'Playing Audio...' : `Hear ${selectedLanguage} Voice`}</span>
              </button>
            </div>

            <div className="native-pronounce-box">
              <span className="native-spoken-text">{nativeInfo.word}</span>
              <span className="native-script-text">({nativeInfo.tamil_script})</span>
            </div>
            <p className="native-phonetic-caption">Pronounced as: /{nativeInfo.pronunciation}/</p>
          </div>

          {/* SECTION 2: Tamil Bridge (Letter-by-Letter Blending) */}
          <div className="learning-tier-card tamil-tier-card">
            <div className="tier-header-bar">
              <h3 className="tier-section-heading">Tamil Script & Blending (தமிழ்)</h3>
              <button
                type="button"
                className={`bridge-listen-btn ${playingState === 'tamil' ? 'playing' : ''}`}
                onClick={() => speakText(card.tamil.word, 'ta-IN', 'tamil')}
                title="Hear full Tamil pronunciation"
              >
                <Volume2 size={15} />
                <span>Listen Tamil</span>
              </button>
            </div>

            {/* Letter Blending Equation */}
            <div className="phonics-equation-wrap">
              <span className="equation-label">Letter Blending:</span>
              <div className="equation-chips-row">
                {card.tamil.letters.map((char, idx) => (
                  <React.Fragment key={idx}>
                    <button
                      type="button"
                      className={`letter-unit-chip tamil-font ${playingState === `ta_${idx}` ? 'active-unit' : ''}`}
                      onClick={() => speakText(char, 'ta-IN', `ta_${idx}`)}
                      title={`Click to hear letter: ${char}`}
                    >
                      {char}
                    </button>
                    {idx < card.tamil.letters.length - 1 && (
                      <span className="math-operator">+</span>
                    )}
                  </React.Fragment>
                ))}

                <span className="math-operator math-equals">=</span>

                <button
                  type="button"
                  className={`blended-result-chip tamil-font ${playingState === 'tamil' ? 'active-unit' : ''}`}
                  onClick={() => speakText(card.tamil.word, 'ta-IN', 'tamil')}
                  title="Click to hear blended word"
                >
                  {card.tamil.word}
                </button>
              </div>
            </div>

            {card.tamil.example && (
              <div className="usage-sentence-box">
                <span className="sentence-label">எடுத்துக்காட்டு:</span>
                <span className="sentence-text tamil-font">"{card.tamil.example}"</span>
              </div>
            )}
          </div>

          {/* SECTION 3: English Bridge (Letter-by-Letter Spelling) */}
          <div className="learning-tier-card english-tier-card">
            <div className="tier-header-bar">
              <h3 className="tier-section-heading">English Phonics & Spelling</h3>
              <button
                type="button"
                className={`bridge-listen-btn ${playingState === 'english' ? 'playing' : ''}`}
                onClick={() => speakText(card.english.word, 'en-US', 'english')}
                title="Hear full English pronunciation"
              >
                <Volume2 size={15} />
                <span>Listen English</span>
              </button>
            </div>

            {/* Letter Spelling Equation */}
            <div className="phonics-equation-wrap">
              <span className="equation-label">Letter Spelling:</span>
              <div className="equation-chips-row">
                {card.english.letters.map((char, idx) => (
                  <React.Fragment key={idx}>
                    <button
                      type="button"
                      className={`letter-unit-chip ${playingState === `en_${idx}` ? 'active-unit' : ''}`}
                      onClick={() => speakText(char, 'en-US', `en_${idx}`)}
                      title={`Click to hear letter: ${char}`}
                    >
                      {char}
                    </button>
                    {idx < card.english.letters.length - 1 && (
                      <span className="math-operator">-</span>
                    )}
                  </React.Fragment>
                ))}

                <span className="math-operator math-equals">=</span>

                <button
                  type="button"
                  className={`blended-result-chip ${playingState === 'english' ? 'active-unit' : ''}`}
                  onClick={() => speakText(card.english.word, 'en-US', 'english')}
                  title="Click to hear word"
                >
                  {card.english.word}
                </button>
              </div>
            </div>

            {card.english.example && (
              <div className="usage-sentence-box">
                <span className="sentence-label">Example:</span>
                <span className="sentence-text">"{card.english.example}"</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
