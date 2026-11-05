import React from 'react';
import { Volume2 } from 'lucide-react';
import { Illustration } from './Illustrations';

export default function ModuleGrid({
  modules = [],
  cards = [],
  selectedModuleId,
  onSelectModule,
  onSelectCard,
  selectedLanguage = 'Badaga',
}) {
  const filteredCards = selectedModuleId
    ? cards.filter((c) => c.category === selectedModuleId)
    : cards;

  // Quick pronunciation via Neural AI Voice (with Web Speech fallback)
  const quickSpeak = (e, text, lang) => {
    e.stopPropagation();
    if (!text) return;

    if (window.speechSynthesis) window.speechSynthesis.cancel();

    const langCode = lang && lang.startsWith('ta') ? 'ta' : 'en';
    const audio = new Audio(`/api/tts?text=${encodeURIComponent(text)}&lang=${langCode}`);
    audio.play().catch(() => {
      if (!window.speechSynthesis) return;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang;
      utterance.rate = 0.92;
      window.speechSynthesis.speak(utterance);
    });
  };

  return (
    <section className="topics-section-container">
      {/* Textbook Topic Navigation Tabs (Clean, institutional design) */}
      <nav className="topics-nav-track" aria-label="Learning Topics">
        <button
          type="button"
          className={`topic-tab-pill ${!selectedModuleId ? 'active' : ''}`}
          onClick={() => onSelectModule(null)}
        >
          <span className="topic-tab-title">All Topics</span>
          <span className="topic-tab-count">({cards.length})</span>
        </button>

        {modules.map((mod) => (
          <button
            key={mod.id}
            type="button"
            className={`topic-tab-pill ${selectedModuleId === mod.id ? 'active' : ''}`}
            onClick={() => onSelectModule(mod.id)}
          >
            <span className="topic-tab-title">{mod.title}</span>
            <span className="topic-tab-tamil">{mod.tamil_title}</span>
          </button>
        ))}
      </nav>

      {/* Grid of Kindergarten Concept Cards */}
      <div className="cards-mosaic-grid">
        {filteredCards.map((card) => {
          const nativeWord = selectedLanguage === 'Marwari' ? card.marwari.word : card.badaga.word;
          const nativeScript = selectedLanguage === 'Marwari' ? card.marwari.tamil_script : card.badaga.tamil_script;

          return (
            <div
              key={card.id}
              className={`concept-visual-card category-${card.category}`}
              onClick={() => onSelectCard(card)}
              tabIndex={0}
              role="button"
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelectCard(card);
                }
              }}
              title={`Click to learn ${card.english.word} in Tamil and English`}
            >
              {/* Textbook Vector Cartoon Illustration with Thematic Tint */}
              <div className={`card-illustration-frame theme-${card.category}`}>
                <span className="card-category-subtle-badge">{card.category.toUpperCase()}</span>
                <Illustration name={card.illustration_name} size={92} />
              </div>

              {/* Learning Information Area */}
              <div className="card-info-pane">
                {/* 1. Native Word (Child's Mother Tongue) */}
                <div className="card-native-header">
                  <span className="native-primary-word">{nativeWord}</span>
                  <span className="native-script-hint">({nativeScript})</span>
                </div>

                {/* 2. Target Bridge Languages: Tamil & English */}
                <div className="card-target-cluster">
                  {/* Tamil */}
                  <div className="target-language-row">
                    <span className="target-lang-label">தமிழ்:</span>
                    <span className="target-word-val tamil-font">{card.tamil.word}</span>
                    <button
                      type="button"
                      className="inline-audio-btn"
                      onClick={(e) => quickSpeak(e, card.tamil.word, 'ta-IN')}
                      title={`Listen Tamil pronunciation: ${card.tamil.word}`}
                    >
                      <Volume2 size={13} />
                    </button>
                  </div>

                  {/* English */}
                  <div className="target-language-row">
                    <span className="target-lang-label">English:</span>
                    <span className="target-word-val english-val">{card.english.word}</span>
                    <button
                      type="button"
                      className="inline-audio-btn"
                      onClick={(e) => quickSpeak(e, card.english.word, 'en-US')}
                      title={`Listen English pronunciation: ${card.english.word}`}
                    >
                      <Volume2 size={13} />
                    </button>
                  </div>
                </div>

                {/* 3. Phonics Blending Formula Hint */}
                <div className="card-phonics-strip">
                  <span className="phonics-formula-text tamil-font">
                    {card.tamil.phonics} = {card.tamil.word}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
