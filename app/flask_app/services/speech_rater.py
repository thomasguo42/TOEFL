"""
Speech assessment service using Whisper, librosa, and parselmouth.
Provides comprehensive analysis of fluency, pronunciation, and rhythm.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional
import numpy as np

from flask import current_app

# Try to import required libraries
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    whisper = None

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    librosa = None

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    AudioSegment = None

try:
    import parselmouth
    from parselmouth.praat import call
    PARSELMOUTH_AVAILABLE = True
except ImportError:
    PARSELMOUTH_AVAILABLE = False
    parselmouth = None
    call = None


@dataclass
class SpeechMetrics:
    """Container for all speech metrics"""
    speech_rate: float
    articulation_rate: float
    pause_count: int
    mean_pause_duration: float
    long_pause_count: int
    filler_word_count: int
    filler_ratio: float
    phonation_ratio: float
    pronunciation_consistency: float
    pitch_mean: float
    pitch_std: float
    pitch_range: float
    pitch_variation_coef: float
    speaking_time_ratio: float
    total_duration: float
    speaking_duration: float
    word_count: int
    syllable_count: int

    def to_dict(self):
        """Convert to dictionary"""
        return asdict(self)


class SpeechRater:
    """Comprehensive speech assessment system"""

    def __init__(self, model_size='base'):
        """Initialize the speech rater"""
        self.is_available = WHISPER_AVAILABLE and LIBROSA_AVAILABLE and PARSELMOUTH_AVAILABLE and PYDUB_AVAILABLE

        if not self.is_available:
            missing = []
            if not WHISPER_AVAILABLE:
                missing.append("whisper")
            if not LIBROSA_AVAILABLE:
                missing.append("librosa")
            if not PARSELMOUTH_AVAILABLE:
                missing.append("praat-parselmouth")
            if not PYDUB_AVAILABLE:
                missing.append("pydub")
            current_app.logger.warning(f"SpeechRater not fully available. Missing: {', '.join(missing)}")
            return

        current_app.logger.info(f"Loading Whisper {model_size} model...")
        self.whisper_model = whisper.load_model(model_size)
        self.filler_words = {
            'um', 'uh', 'er', 'ah', 'like', 'you know', 'i mean',
            'sort of', 'kind of', 'basically', 'actually'
        }
        current_app.logger.info("✅ Speech Rater initialized!")

    def convert_to_wav(self, audio_path: str) -> str:
        """Convert any audio format to WAV"""
        if not PYDUB_AVAILABLE:
            return audio_path

        if audio_path.endswith('.wav'):
            return audio_path

        current_app.logger.info(f"Converting {audio_path} to wav...")
        try:
            audio = AudioSegment.from_file(audio_path)
            temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            wav_path = temp_wav.name
            audio.export(wav_path, format='wav')
            current_app.logger.info(f"✅ Converted to wav")
            return wav_path
        except Exception as e:
            current_app.logger.error(f"Error converting audio: {e}")
            return audio_path

    def transcribe_with_word_timestamps(self, audio_path: str) -> Dict:
        """Transcribe audio with word-level timestamps"""
        if not WHISPER_AVAILABLE:
            return {'text': '', 'segments': []}

        current_app.logger.info("Transcribing audio...")
        try:
            result = self.whisper_model.transcribe(
                audio_path,
                word_timestamps=True,
                language='en'
            )
            return result
        except Exception as e:
            current_app.logger.error(f"Transcription error: {e}")
            return {'text': '', 'segments': []}

    def detect_voice_activity(self, audio: np.ndarray, sr: int) -> List[Tuple[float, float]]:
        """Detect voice activity segments"""
        if not LIBROSA_AVAILABLE:
            return []

        rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
        threshold = np.mean(rms) * 0.3
        voiced_frames = rms > threshold
        times = librosa.frames_to_time(np.arange(len(voiced_frames)), sr=sr, hop_length=512)

        segments = []
        start = None
        for is_voiced, time in zip(voiced_frames, times):
            if is_voiced and start is None:
                start = time
            elif not is_voiced and start is not None:
                segments.append((start, time))
                start = None
        if start is not None:
            segments.append((start, times[-1]))
        return segments

    def estimate_syllable_count(self, text: str) -> int:
        """Estimate syllable count for a word"""
        text = text.lower()
        vowels = 'aeiouy'
        syllable_count = 0
        previous_was_vowel = False

        for char in text:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel

        if text.endswith('e'):
            syllable_count -= 1
        return max(syllable_count, 1)

    def count_filler_words(self, words: List[str]) -> int:
        """Count filler words in speech"""
        count = 0
        text = ' '.join(words).lower()
        for word in words:
            if word.lower() in self.filler_words:
                count += 1
        for filler in ['you know', 'i mean', 'sort of', 'kind of']:
            count += text.count(filler)
        return count

    def analyze_prosody(self, audio_path: str) -> Dict[str, float]:
        """Analyze pitch and prosody"""
        if not PARSELMOUTH_AVAILABLE:
            return {'pitch_mean': 0, 'pitch_std': 0, 'pitch_range': 0,
                   'pitch_variation_coef': 0, 'phonation_ratio': 0}

        current_app.logger.info("Analyzing prosody...")
        try:
            snd = parselmouth.Sound(audio_path)
            pitch = call(snd, "To Pitch", 0.0, 75, 600)
            pitch_values = pitch.selected_array['frequency']
            pitch_values = pitch_values[pitch_values > 0]

            if len(pitch_values) > 0:
                pitch_mean = np.mean(pitch_values)
                pitch_std = np.std(pitch_values)
                pitch_range = np.max(pitch_values) - np.min(pitch_values)
                pitch_variation_coef = pitch_std / pitch_mean if pitch_mean > 0 else 0
            else:
                pitch_mean = pitch_std = pitch_range = pitch_variation_coef = 0

            total_frames = len(pitch.selected_array['frequency'])
            voiced_frames = np.sum(pitch.selected_array['frequency'] > 0)
            phonation_ratio = voiced_frames / total_frames if total_frames > 0 else 0

            return {
                'pitch_mean': pitch_mean,
                'pitch_std': pitch_std,
                'pitch_range': pitch_range,
                'pitch_variation_coef': pitch_variation_coef,
                'phonation_ratio': phonation_ratio
            }
        except Exception as e:
            current_app.logger.warning(f"Prosody analysis failed: {e}")
            return {'pitch_mean': 0, 'pitch_std': 0, 'pitch_range': 0,
                   'pitch_variation_coef': 0, 'phonation_ratio': 0}

    def calculate_metrics(self, audio_path: str, transcription: Dict) -> SpeechMetrics:
        """Calculate all speech metrics"""
        if not LIBROSA_AVAILABLE:
            return None

        current_app.logger.info("Calculating metrics...")
        audio, sr = librosa.load(audio_path, sr=16000)
        total_duration = len(audio) / sr

        segments = transcription.get('segments', [])
        all_words = []
        for segment in segments:
            if 'words' in segment:
                all_words.extend(segment['words'])

        if not all_words:
            words = transcription['text'].split()
            word_count = len(words)
        else:
            words = [w['word'].strip() for w in all_words]
            word_count = len(words)

        speech_segments = self.detect_voice_activity(audio, sr)
        speaking_duration = sum([end - start for start, end in speech_segments])

        pauses = []
        for i in range(len(speech_segments) - 1):
            pause_duration = speech_segments[i + 1][0] - speech_segments[i][1]
            if pause_duration > 0.1:
                pauses.append(pause_duration)

        pause_count = len(pauses)
        mean_pause_duration = np.mean(pauses) if pauses else 0
        long_pause_count = sum(1 for p in pauses if p > 1.0)
        speech_rate = (word_count / total_duration) * 60 if total_duration > 0 else 0
        syllable_count = sum(self.estimate_syllable_count(word) for word in words)
        articulation_rate = syllable_count / speaking_duration if speaking_duration > 0 else 0
        filler_word_count = self.count_filler_words(words)
        filler_ratio = filler_word_count / word_count if word_count > 0 else 0
        speaking_time_ratio = speaking_duration / total_duration if total_duration > 0 else 0

        prosody = self.analyze_prosody(audio_path)
        rms = librosa.feature.rms(y=audio)[0]
        pronunciation_consistency = 1.0 - (np.std(rms) / np.mean(rms)) if np.mean(rms) > 0 else 0
        pronunciation_consistency = max(0, min(1, pronunciation_consistency))

        return SpeechMetrics(
            speech_rate=speech_rate, articulation_rate=articulation_rate,
            pause_count=pause_count, mean_pause_duration=mean_pause_duration,
            long_pause_count=long_pause_count, filler_word_count=filler_word_count,
            filler_ratio=filler_ratio, phonation_ratio=prosody['phonation_ratio'],
            pronunciation_consistency=pronunciation_consistency,
            pitch_mean=prosody['pitch_mean'], pitch_std=prosody['pitch_std'],
            pitch_range=prosody['pitch_range'],
            pitch_variation_coef=prosody['pitch_variation_coef'],
            speaking_time_ratio=speaking_time_ratio,
            total_duration=total_duration, speaking_duration=speaking_duration,
            word_count=word_count, syllable_count=syllable_count
        )

    def score_fluency(self, metrics: SpeechMetrics) -> Dict[str, float]:
        """Score fluency based on metrics"""
        # Speech rate scoring
        if 130 <= metrics.speech_rate <= 170:
            rate_score = 100
        elif 110 <= metrics.speech_rate < 130:
            rate_score = 75 + ((metrics.speech_rate - 110) / 20) * 25
        elif 170 < metrics.speech_rate <= 190:
            rate_score = 85 + ((190 - metrics.speech_rate) / 20) * 15
        elif 90 <= metrics.speech_rate < 110:
            rate_score = 50 + ((metrics.speech_rate - 90) / 20) * 25
        elif 190 < metrics.speech_rate <= 210:
            rate_score = 70 + ((210 - metrics.speech_rate) / 20) * 15
        elif metrics.speech_rate < 90:
            rate_score = max(20, (metrics.speech_rate / 90) * 50)
        else:  # > 210
            rate_score = max(40, 70 - ((metrics.speech_rate - 210) / 40) * 30)

        # Pause scoring
        if metrics.word_count > 0:
            pause_frequency = metrics.pause_count / metrics.word_count

            if pause_frequency < 0.15:
                pause_score = 100
            elif pause_frequency < 0.25:
                pause_score = 85 + ((0.25 - pause_frequency) / 0.10) * 15
            elif pause_frequency < 0.35:
                pause_score = 65 + ((0.35 - pause_frequency) / 0.10) * 20
            else:
                pause_score = max(30, 65 - ((pause_frequency - 0.35) / 0.20) * 35)

            # Long pause penalty
            if metrics.long_pause_count <= 2:
                long_pause_penalty = 0
            elif metrics.long_pause_count <= 4:
                long_pause_penalty = (metrics.long_pause_count - 2) * 5
            else:
                long_pause_penalty = 10 + (metrics.long_pause_count - 4) * 7

            pause_score = max(0, pause_score - long_pause_penalty)
        else:
            pause_score = 50

        # Filler word scoring
        if metrics.filler_ratio <= 0.03:
            filler_score = 100
        elif metrics.filler_ratio <= 0.06:
            filler_score = 85 + ((0.06 - metrics.filler_ratio) / 0.03) * 15
        elif metrics.filler_ratio <= 0.10:
            filler_score = 60 + ((0.10 - metrics.filler_ratio) / 0.04) * 25
        else:
            filler_score = max(20, 60 - ((metrics.filler_ratio - 0.10) / 0.10) * 40)

        # Speaking time ratio
        if metrics.speaking_time_ratio >= 0.75:
            speaking_ratio_score = 100
        elif metrics.speaking_time_ratio >= 0.65:
            speaking_ratio_score = 85 + ((metrics.speaking_time_ratio - 0.65) / 0.10) * 15
        elif metrics.speaking_time_ratio >= 0.50:
            speaking_ratio_score = 60 + ((metrics.speaking_time_ratio - 0.50) / 0.15) * 25
        else:
            speaking_ratio_score = max(30, (metrics.speaking_time_ratio / 0.50) * 60)

        fluency_score = (
            rate_score * 0.35 + pause_score * 0.30 +
            filler_score * 0.20 + speaking_ratio_score * 0.15
        )

        return {
            'overall': round(fluency_score, 1),
            'rate_score': round(rate_score, 1),
            'pause_score': round(pause_score, 1),
            'filler_score': round(filler_score, 1),
            'speaking_ratio_score': round(speaking_ratio_score, 1)
        }

    def score_pronunciation(self, metrics: SpeechMetrics) -> Dict[str, float]:
        """Score pronunciation based on metrics (slightly more lenient)"""
        # Phonation ratio scoring - more lenient ranges
        if 0.60 <= metrics.phonation_ratio <= 0.85:  # Widened from 0.65-0.80
            phonation_score = 100
        elif 0.50 <= metrics.phonation_ratio < 0.60:  # Lowered from 0.55
            phonation_score = 85 + ((metrics.phonation_ratio - 0.50) / 0.10) * 15  # Raised min from 80
        elif 0.85 < metrics.phonation_ratio <= 0.90:  # Raised from 0.88
            phonation_score = 92 + ((0.90 - metrics.phonation_ratio) / 0.05) * 8  # Raised min from 90
        elif 0.40 <= metrics.phonation_ratio < 0.50:  # Lowered from 0.45
            phonation_score = 65 + ((metrics.phonation_ratio - 0.40) / 0.10) * 20  # Raised min from 55
        elif metrics.phonation_ratio < 0.40:  # Lowered from 0.45
            phonation_score = max(40, (metrics.phonation_ratio / 0.40) * 65)  # Raised min from 20/55
        else:  # > 0.90
            phonation_score = max(80, 92 - ((metrics.phonation_ratio - 0.90) / 0.10) * 12)  # Raised min from 70

        # Consistency scoring - more generous
        adjusted_consistency = metrics.pronunciation_consistency * 0.90 + 0.10  # Changed from 0.85/0.15
        consistency_score = min(100, adjusted_consistency * 105)  # Slightly boosted

        if metrics.pronunciation_consistency > 0.75:  # Lowered threshold from 0.8
            consistency_score = min(100, consistency_score * 1.08)  # Reduced bonus from 1.1

        pronunciation_score = phonation_score * 0.6 + consistency_score * 0.4

        return {
            'overall': round(pronunciation_score, 1),
            'phonation_score': round(phonation_score, 1),
            'consistency_score': round(consistency_score, 1)
        }

    def score_rhythm(self, metrics: SpeechMetrics) -> Dict[str, float]:
        """Score rhythm and prosody based on metrics (slightly more rigorous)"""
        # Pitch variation scoring - narrower optimal range
        if 0.20 <= metrics.pitch_variation_coef <= 0.30:  # Narrowed from 0.18-0.32
            pitch_var_score = 100
        elif 0.14 <= metrics.pitch_variation_coef < 0.20:  # Raised from 0.12
            pitch_var_score = 70 + ((metrics.pitch_variation_coef - 0.14) / 0.06) * 30  # Lowered min from 75
        elif 0.30 < metrics.pitch_variation_coef <= 0.38:  # Narrowed from 0.40
            pitch_var_score = 80 + ((0.38 - metrics.pitch_variation_coef) / 0.08) * 20  # Lowered min from 85
        elif 0.10 <= metrics.pitch_variation_coef < 0.14:  # Raised from 0.08
            pitch_var_score = 45 + ((metrics.pitch_variation_coef - 0.10) / 0.04) * 25  # Lowered min from 50
        elif metrics.pitch_variation_coef < 0.10:  # Raised from 0.08
            pitch_var_score = max(15, (metrics.pitch_variation_coef / 0.10) * 45)  # Lowered min from 20/50
        else:  # > 0.38
            pitch_var_score = max(50, 80 - ((metrics.pitch_variation_coef - 0.38) / 0.20) * 30)  # Lowered min from 55

        # Articulation rate scoring - narrower optimal range
        if 4.2 <= metrics.articulation_rate <= 5.8:  # Narrowed from 4.0-6.0
            articulation_score = 100
        elif 3.2 <= metrics.articulation_rate < 4.2:  # Raised from 3.0
            articulation_score = 70 + ((metrics.articulation_rate - 3.2) / 1.0) * 30  # Lowered min from 75
        elif 5.8 < metrics.articulation_rate <= 6.8:  # Narrowed from 7.0
            articulation_score = 80 + ((6.8 - metrics.articulation_rate) / 1.0) * 20  # Lowered min from 85
        elif 2.7 <= metrics.articulation_rate < 3.2:  # Raised from 2.5
            articulation_score = 45 + ((metrics.articulation_rate - 2.7) / 0.5) * 25  # Lowered min from 50
        elif metrics.articulation_rate < 2.7:  # Raised from 2.5
            articulation_score = max(20, (metrics.articulation_rate / 2.7) * 45)  # Lowered min from 25/50
        else:  # > 6.8
            articulation_score = max(55, 80 - ((metrics.articulation_rate - 6.8) / 2.0) * 25)  # Lowered min from 60

        # Pitch range scoring - higher standards
        if metrics.pitch_range >= 110:  # Raised from 100
            range_score = min(100, 82 + (metrics.pitch_range - 110) / 100 * 18)  # Lowered base from 85
        elif metrics.pitch_range >= 70:  # Raised from 60
            range_score = 65 + ((metrics.pitch_range - 70) / 40) * 17  # Lowered min from 70
        elif metrics.pitch_range >= 50:  # Raised from 40
            range_score = 45 + ((metrics.pitch_range - 50) / 20) * 20  # Lowered min from 50
        else:
            range_score = max(20, (metrics.pitch_range / 50) * 45)  # Lowered min from 25/50

        rhythm_score = (
            pitch_var_score * 0.4 + articulation_score * 0.35 + range_score * 0.25
        )

        return {
            'overall': round(rhythm_score, 1),
            'pitch_variation_score': round(pitch_var_score, 1),
            'articulation_score': round(articulation_score, 1),
            'range_score': round(range_score, 1)
        }

    def calculate_overall_score(self, fluency: float, pronunciation: float,
                               rhythm: float) -> float:
        """Calculate overall score from component scores"""
        return round(fluency * 0.45 + pronunciation * 0.35 + rhythm * 0.20, 1)

    def get_feedback(self, metrics: SpeechMetrics, scores: Dict) -> List[str]:
        """Generate actionable feedback"""
        feedback = []

        # Speech rate feedback
        if metrics.speech_rate < 110:
            feedback.append(f"Your speech rate is slow ({metrics.speech_rate:.0f} WPM). Try to speak faster, aim for 130-170 WPM.")
        elif metrics.speech_rate > 190:
            feedback.append(f"Your speech rate is very fast ({metrics.speech_rate:.0f} WPM). Slow down to 130-170 WPM for clarity.")
        elif metrics.speech_rate < 130:
            feedback.append(f"Speech rate is a bit slow ({metrics.speech_rate:.0f} WPM). Optimal is 130-170 WPM.")
        elif metrics.speech_rate > 170:
            feedback.append(f"Speech rate is a bit fast ({metrics.speech_rate:.0f} WPM). Optimal is 130-170 WPM.")

        # Filler word feedback
        if metrics.filler_ratio > 0.10:
            feedback.append(f"Too many filler words ({metrics.filler_word_count} = {metrics.filler_ratio*100:.1f}%). Try to pause instead of using 'um', 'uh', etc.")
        elif metrics.filler_ratio > 0.06:
            feedback.append(f"Noticeable filler words ({metrics.filler_word_count} = {metrics.filler_ratio*100:.1f}%). Try to reduce them.")

        # Pause feedback
        if metrics.long_pause_count > 6:
            feedback.append(f"Too many long pauses ({metrics.long_pause_count}). Try to maintain flow.")
        elif metrics.long_pause_count > 4:
            feedback.append(f"Several long pauses detected ({metrics.long_pause_count}). Work on continuity.")

        # Phonation feedback
        if metrics.phonation_ratio < 0.45:
            feedback.append(f"Low voice clarity (phonation: {metrics.phonation_ratio:.2f}). Speak more clearly and project your voice.")
        elif metrics.phonation_ratio < 0.55:
            feedback.append(f"Voice projection could be clearer (phonation: {metrics.phonation_ratio:.2f}).")

        # Pitch variation feedback
        if metrics.pitch_variation_coef < 0.08:
            feedback.append(f"Very monotone speech (variation: {metrics.pitch_variation_coef:.3f}). Add more intonation for natural sound.")
        elif metrics.pitch_variation_coef < 0.12:
            feedback.append(f"Speech is somewhat monotone (variation: {metrics.pitch_variation_coef:.3f}). Try varying your pitch more.")
        elif metrics.pitch_variation_coef > 0.40:
            feedback.append(f"Pitch varies quite a bit (variation: {metrics.pitch_variation_coef:.3f}). Try speaking more evenly.")

        # Articulation feedback
        if metrics.articulation_rate < 3.0:
            feedback.append(f"Slow articulation ({metrics.articulation_rate:.1f} syl/sec). Try to speak more fluently.")
        elif metrics.articulation_rate > 7.0:
            feedback.append(f"Very fast articulation ({metrics.articulation_rate:.1f} syl/sec). Slow down for clarity.")

        # Speaking time ratio
        if metrics.speaking_time_ratio < 0.50:
            feedback.append(f"Low speaking time ({metrics.speaking_time_ratio*100:.0f}%). Too many pauses relative to speech.")

        # Positive feedback
        if scores['fluency']['overall'] >= 90:
            feedback.append("Excellent fluency!")
        elif scores['fluency']['overall'] >= 80:
            feedback.append("Very good fluency!")
        elif scores['fluency']['overall'] >= 70:
            feedback.append("Good fluency with minor areas to improve.")

        if scores['pronunciation']['overall'] >= 90:
            feedback.append("Excellent pronunciation quality!")
        elif scores['pronunciation']['overall'] >= 80:
            feedback.append("Very good pronunciation!")
        elif scores['pronunciation']['overall'] >= 70:
            feedback.append("Good pronunciation with minor areas to improve.")

        if scores['rhythm']['overall'] >= 90:
            feedback.append("Excellent rhythm and prosody!")
        elif scores['rhythm']['overall'] >= 80:
            feedback.append("Very good rhythm!")
        elif scores['rhythm']['overall'] >= 70:
            feedback.append("Good rhythm with minor areas to improve.")

        return feedback if feedback else ["Overall good performance!"]

    def rate_speech(self, audio_path: str) -> Dict:
        """Main method to rate a speech audio file"""
        if not self.is_available:
            return {
                'error': 'Speech rating service not available',
                'overall_score': 0,
                'transcription': ''
            }

        current_app.logger.info(f"Starting speech rating analysis for: {audio_path}")

        # Convert to WAV if needed
        wav_path = self.convert_to_wav(audio_path)

        # Transcribe
        transcription = self.transcribe_with_word_timestamps(wav_path)

        # Calculate metrics
        metrics = self.calculate_metrics(wav_path, transcription)

        if metrics is None:
            return {
                'error': 'Failed to calculate metrics',
                'overall_score': 0,
                'transcription': transcription.get('text', '')
            }

        # Score
        fluency_scores = self.score_fluency(metrics)
        pronunciation_scores = self.score_pronunciation(metrics)
        rhythm_scores = self.score_rhythm(metrics)

        overall_score = self.calculate_overall_score(
            fluency_scores['overall'],
            pronunciation_scores['overall'],
            rhythm_scores['overall']
        )

        feedback = self.get_feedback(metrics, {
            'fluency': fluency_scores,
            'pronunciation': pronunciation_scores,
            'rhythm': rhythm_scores
        })

        # Clean up temporary WAV file if created
        if wav_path != audio_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except:
                pass

        return {
            'overall_score': overall_score,
            'fluency': fluency_scores,
            'pronunciation': pronunciation_scores,
            'rhythm': rhythm_scores,
            'metrics': metrics.to_dict(),
            'transcription': transcription.get('text', ''),
            'feedback': feedback
        }


def get_speech_rater(model_size='base') -> SpeechRater:
    """Factory function to get a SpeechRater instance"""
    return SpeechRater(model_size=model_size)
