"""
Text-to-Speech service for listening module with word-level timestamp support.

This service provides an abstraction for generating audio with word-level timestamps.
It supports multiple TTS backends including Kokoro (default), ElevenLabs, Play.ht, and gTTS fallback.

Configuration:
    Set TTS_PROVIDER environment variable to: 'kokoro' (default, most natural), 'elevenlabs', 'playht', or 'gtts'
    For Kokoro: Automatically available, provides human-like natural voices
    For ElevenLabs: Set ELEVENLABS_API_KEY
    For Play.ht: Set PLAYHT_API_KEY and PLAYHT_USER_ID

Kokoro TTS Features:
    - Most natural-sounding voices, similar to real TOEFL exams
    - Multi-speaker support for conversations (distinct voices for Professor/Student)
    - Automatic natural pauses based on punctuation
    - No API key required (runs locally)
"""
from __future__ import annotations

import os
import time
import json
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

from flask import current_app
from gtts import gTTS
from werkzeug.utils import secure_filename

# Kokoro TTS imports (optional, will check availability)
try:
    import torch
    import numpy as np
    from kokoro import KPipeline
    from pydub import AudioSegment
    import soundfile as sf
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False


class TTSResult:
    """Result object for TTS generation."""

    def __init__(
        self,
        audio_path: str,
        duration_seconds: float,
        word_timestamps: List[Dict[str, any]],
        provider: str
    ):
        self.audio_path = audio_path
        self.duration_seconds = duration_seconds
        self.word_timestamps = word_timestamps  # [{word, start, end}, ...]
        self.provider = provider


class TTSService:
    """Main TTS service with support for multiple providers."""

    def __init__(self):
        self.provider = os.getenv('TTS_PROVIDER', 'kokoro').lower()  # Default to Kokoro for natural voice
        self.audio_dir = None  # Will be set when app context is available
        self.kokoro_pipe = None  # Lazy-loaded Kokoro pipeline

    def _ensure_audio_dir(self) -> Path:
        """Ensure audio directory exists."""
        if self.audio_dir is None:
            self.audio_dir = Path(current_app.root_path) / "static" / "listening_audio"
            self.audio_dir.mkdir(parents=True, exist_ok=True)
        return self.audio_dir

    def generate_audio(
        self,
        text: str,
        filename_prefix: str = "audio",
        voice: str = "default",
        language: str = "en"
    ) -> Optional[TTSResult]:
        """
        Generate audio from text with word-level timestamps.

        Args:
            text: The text to convert to speech
            filename_prefix: Prefix for the audio filename
            voice: Voice ID or name (provider-specific)
            language: Language code (e.g., 'en')

        Returns:
            TTSResult object with audio path, duration, and timestamps, or None on failure
        """
        try:
            if self.provider == 'kokoro' and KOKORO_AVAILABLE:
                return self._generate_kokoro(text, filename_prefix, voice)
            elif self.provider == 'elevenlabs':
                return self._generate_elevenlabs(text, filename_prefix, voice)
            elif self.provider == 'playht':
                return self._generate_playht(text, filename_prefix, voice)
            else:
                # Fallback to gTTS
                return self._generate_gtts(text, filename_prefix, language)
        except Exception as e:
            current_app.logger.error(f"TTS generation failed: {e}")
            return None

    def _generate_gtts(
        self,
        text: str,
        filename_prefix: str,
        language: str = "en"
    ) -> Optional[TTSResult]:
        """
        Generate audio using gTTS with improved naturalness settings.

        Note: gTTS doesn't provide word-level timestamps, so we estimate them
        based on word count and audio duration.

        For more natural speech, we:
        1. Use different TLD (top-level domains) for varied voice characteristics
        2. Adjust speaking speed to be more natural
        3. Add pauses by inserting punctuation
        """
        audio_dir = self._ensure_audio_dir()

        # Create safe filename
        timestamp = int(time.time() * 1000)
        safe_prefix = secure_filename(filename_prefix)
        filename = f"{safe_prefix}_{timestamp}.mp3"
        file_path = audio_dir / filename

        # Improve naturalness by using different TLD for voice variation
        # 'com' = US English (default), 'co.uk' = British, 'com.au' = Australian
        # Using 'com' for American accent which is standard for TOEFL
        tld = 'com'

        # Pre-process text to add natural pauses
        # This helps gTTS sound more natural by inserting slight pauses
        natural_text = self._add_natural_pauses(text)

        # Generate audio with optimized settings
        try:
            tts = gTTS(
                text=natural_text,
                lang=language,
                slow=False,  # Normal speed, not slow
                tld=tld,  # US English accent
            )
            tts.save(str(file_path))
        except Exception as e:
            current_app.logger.error(f"gTTS generation failed: {e}")
            return None

        # Get audio duration (estimate based on word count)
        # Slightly slower rate for more natural academic speech: ~140 words per minute = 2.33 words per second
        words = text.split()
        words_per_second = 2.33  # More natural academic speaking rate
        estimated_duration = len(words) / words_per_second

        # Generate estimated timestamps
        word_timestamps = self._estimate_word_timestamps(words, estimated_duration)

        # Return relative path for web serving
        relative_path = f"listening_audio/{filename}"

        return TTSResult(
            audio_path=relative_path,
            duration_seconds=estimated_duration,
            word_timestamps=word_timestamps,
            provider='gtts'
        )

    def _add_natural_pauses(self, text: str) -> str:
        """
        Add natural pauses to text to make TTS sound more human.

        Inserts commas and periods strategically to create natural speech rhythm.
        """
        import re

        # Already has good punctuation
        if text.count(',') > 2 or text.count('.') > 1:
            return text

        # Add comma after transitional phrases if not present
        transitions = [
            'however', 'therefore', 'moreover', 'furthermore',
            'in addition', 'for example', 'for instance',
            'in contrast', 'on the other hand', 'as a result',
            'in fact', 'in other words', 'that is'
        ]

        for transition in transitions:
            # Add comma after transition if not present
            pattern = r'\b' + transition + r'\b(?!\,)'
            text = re.sub(pattern, transition + ',', text, flags=re.IGNORECASE)

        return text

    def _estimate_word_timestamps(
        self,
        words: List[str],
        total_duration: float
    ) -> List[Dict]:
        """
        Estimate word-level timestamps based on uniform distribution.

        This is a fallback for TTS providers that don't provide timestamps.
        Real implementations should use actual timestamps from the TTS API.
        """
        if not words:
            return []

        timestamps = []
        time_per_word = total_duration / len(words)

        for i, word in enumerate(words):
            start_time = i * time_per_word
            end_time = (i + 1) * time_per_word

            timestamps.append({
                'word': word,
                'start': round(start_time, 3),
                'end': round(end_time, 3)
            })

        return timestamps

    def _generate_kokoro(
        self,
        text: str,
        filename_prefix: str,
        voice: str = "default"
    ) -> Optional[TTSResult]:
        """
        Generate audio using Kokoro TTS for natural, human-like speech.

        Kokoro provides the most natural-sounding voices, similar to real TOEFL exams.

        Args:
            text: The text to convert to speech
            filename_prefix: Prefix for the audio filename
            voice: Voice ID ('default' or specific voice like 'af_heart', 'af_alloy', 'am_adam', etc.)

        Returns:
            TTSResult with audio path, duration, and timestamps
        """
        if not KOKORO_AVAILABLE:
            current_app.logger.warning("Kokoro not available, falling back to gTTS")
            return self._generate_gtts(text, filename_prefix)

        # Lazy-load Kokoro pipeline
        if self.kokoro_pipe is None:
            try:
                current_app.logger.info("Loading Kokoro pipeline...")
                self.kokoro_pipe = KPipeline(lang_code='a')  # Auto language routing
                current_app.logger.info("Kokoro pipeline loaded successfully")
            except Exception as e:
                current_app.logger.error(f"Failed to load Kokoro pipeline: {e}")
                return self._generate_gtts(text, filename_prefix)

        audio_dir = self._ensure_audio_dir()
        timestamp = int(time.time() * 1000)
        safe_prefix = secure_filename(filename_prefix)
        filename = f"{safe_prefix}_{timestamp}.mp3"
        file_path = audio_dir / filename

        # Select voice
        if voice == "default":
            # Use af_heart for female, natural academic voice
            voice_id = 'af_heart'
        else:
            voice_id = voice

        try:
            # Generate audio with Kokoro
            # Kokoro follows punctuation naturally for pauses
            gen = self.kokoro_pipe(text, voice=voice_id)

            audio_chunks = []
            for _, _, audio_data in gen:
                if isinstance(audio_data, torch.Tensor):
                    audio_chunks.append(audio_data.detach().cpu().numpy())
                else:
                    audio_chunks.append(np.asarray(audio_data))

            if not audio_chunks:
                raise ValueError("Kokoro returned no audio data")

            combined_audio = np.concatenate(audio_chunks)

            # Convert to AudioSegment using soundfile
            buf = io.BytesIO()
            sf.write(buf, combined_audio, 24000, format='WAV')
            buf.seek(0)

            audio_segment = AudioSegment.from_file(buf, format="wav")

            # Export as MP3
            audio_segment.export(str(file_path), format="mp3")

            # Calculate duration
            duration_seconds = len(audio_segment) / 1000.0  # pydub uses milliseconds

            # Generate estimated timestamps
            words = text.split()
            word_timestamps = self._estimate_word_timestamps(words, duration_seconds)

            # Return relative path for web serving
            relative_path = f"listening_audio/{filename}"

            return TTSResult(
                audio_path=relative_path,
                duration_seconds=duration_seconds,
                word_timestamps=word_timestamps,
                provider='kokoro'
            )

        except Exception as e:
            current_app.logger.error(f"Kokoro generation failed: {e}")
            return self._generate_gtts(text, filename_prefix)

    def _generate_elevenlabs(
        self,
        text: str,
        filename_prefix: str,
        voice_id: str = "default"
    ) -> Optional[TTSResult]:
        """
        Generate audio using ElevenLabs API with word-level timestamps.

        To use this:
        1. Set TTS_PROVIDER=elevenlabs
        2. Set ELEVENLABS_API_KEY in environment
        3. Optionally set ELEVENLABS_VOICE_ID for custom voice

        ElevenLabs API reference:
        https://elevenlabs.io/docs/api-reference/text-to-speech
        """
        api_key = os.getenv('ELEVENLABS_API_KEY')
        if not api_key:
            current_app.logger.warning("ElevenLabs API key not configured, falling back to gTTS")
            return self._generate_gtts(text, filename_prefix)

        # Use default voice if not specified
        if voice_id == "default":
            voice_id = os.getenv('ELEVENLABS_VOICE_ID', '21m00Tcm4TlvDq8ikWAM')  # Rachel voice

        audio_dir = self._ensure_audio_dir()
        timestamp = int(time.time() * 1000)
        safe_prefix = secure_filename(filename_prefix)
        filename = f"{safe_prefix}_{timestamp}.mp3"
        file_path = audio_dir / filename

        # ElevenLabs API endpoint
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"

        headers = {
            "Accept": "application/json",
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()

            result = response.json()

            # Save audio file
            audio_base64 = result.get('audio_base64')
            if audio_base64:
                import base64
                audio_bytes = base64.b64decode(audio_base64)
                with open(file_path, 'wb') as f:
                    f.write(audio_bytes)

            # Extract word timestamps
            alignment = result.get('alignment', {})
            characters = alignment.get('characters', [])
            character_start_times = alignment.get('character_start_times_seconds', [])
            character_end_times = alignment.get('character_end_times_seconds', [])

            # Convert character-level timestamps to word-level
            word_timestamps = self._characters_to_words(
                characters,
                character_start_times,
                character_end_times
            )

            # Get duration from last timestamp
            duration = character_end_times[-1] if character_end_times else 0

            relative_path = f"listening_audio/{filename}"

            return TTSResult(
                audio_path=relative_path,
                duration_seconds=duration,
                word_timestamps=word_timestamps,
                provider='elevenlabs'
            )

        except Exception as e:
            current_app.logger.error(f"ElevenLabs API error: {e}")
            # Fall back to gTTS
            return self._generate_gtts(text, filename_prefix)

    def _generate_playht(
        self,
        text: str,
        filename_prefix: str,
        voice: str = "default"
    ) -> Optional[TTSResult]:
        """
        Generate audio using Play.ht API with word-level timestamps.

        To use this:
        1. Set TTS_PROVIDER=playht
        2. Set PLAYHT_API_KEY in environment
        3. Set PLAYHT_USER_ID in environment

        Play.ht API reference:
        https://docs.play.ht/reference/api-getting-started
        """
        api_key = os.getenv('PLAYHT_API_KEY')
        user_id = os.getenv('PLAYHT_USER_ID')

        if not api_key or not user_id:
            current_app.logger.warning("Play.ht API credentials not configured, falling back to gTTS")
            return self._generate_gtts(text, filename_prefix)

        # Use default voice if not specified
        if voice == "default":
            voice = os.getenv('PLAYHT_VOICE_ID', 'en-US-JennyNeural')

        audio_dir = self._ensure_audio_dir()
        timestamp = int(time.time() * 1000)
        safe_prefix = secure_filename(filename_prefix)
        filename = f"{safe_prefix}_{timestamp}.mp3"
        file_path = audio_dir / filename

        # Play.ht API endpoint
        url = "https://api.play.ht/api/v2/tts"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-User-Id": user_id,
            "Content-Type": "application/json"
        }

        payload = {
            "text": text,
            "voice": voice,
            "output_format": "mp3",
            "voice_engine": "PlayHT2.0-turbo",
            "quality": "medium"
        }

        try:
            # Request audio generation
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()

            # Play.ht returns audio URL, download it
            result = response.json()
            audio_url = result.get('audio_url')

            if audio_url:
                audio_response = requests.get(audio_url, timeout=60)
                audio_response.raise_for_status()

                with open(file_path, 'wb') as f:
                    f.write(audio_response.content)

            # Note: Play.ht doesn't provide word-level timestamps in standard API
            # You would need to use their advanced features or estimate timestamps
            words = text.split()
            duration = result.get('duration', len(words) / 2.5)
            word_timestamps = self._estimate_word_timestamps(words, duration)

            relative_path = f"listening_audio/{filename}"

            return TTSResult(
                audio_path=relative_path,
                duration_seconds=duration,
                word_timestamps=word_timestamps,
                provider='playht'
            )

        except Exception as e:
            current_app.logger.error(f"Play.ht API error: {e}")
            # Fall back to gTTS
            return self._generate_gtts(text, filename_prefix)

    def _characters_to_words(
        self,
        characters: List[str],
        start_times: List[float],
        end_times: List[float]
    ) -> List[Dict]:
        """
        Convert character-level timestamps to word-level timestamps.

        Used for ElevenLabs API response processing.
        """
        if not characters or not start_times or not end_times:
            return []

        words = []
        current_word = []
        word_start = None

        for char, start, end in zip(characters, start_times, end_times):
            if char.strip():  # Non-whitespace character
                if word_start is None:
                    word_start = start
                current_word.append(char)
            else:  # Whitespace - end of word
                if current_word:
                    words.append({
                        'word': ''.join(current_word),
                        'start': round(word_start, 3),
                        'end': round(end, 3)
                    })
                    current_word = []
                    word_start = None

        # Handle last word if text doesn't end with whitespace
        if current_word and word_start is not None:
            words.append({
                'word': ''.join(current_word),
                'start': round(word_start, 3),
                'end': round(end_times[-1], 3)
            })

        return words

    def generate_multi_speaker_audio(
        self,
        segments: List[Dict[str, str]],
        filename_prefix: str = "conversation"
    ) -> Optional[TTSResult]:
        """
        Generate audio for multi-speaker content (conversations) with Kokoro TTS.

        Args:
            segments: List of {'speaker': 'Professor', 'text': 'Hello', 'voice': 'voice_id'}
            filename_prefix: Prefix for the audio filename

        Returns:
            TTSResult with combined audio and timestamps

        Uses Kokoro to generate natural multi-speaker conversations with distinct voices.
        """
        # If Kokoro is available and we're using it, use multi-speaker implementation
        if self.provider == 'kokoro' and KOKORO_AVAILABLE:
            return self._generate_kokoro_multi_speaker(segments, filename_prefix)

        # Fallback: concatenate all text and generate single audio
        full_text_parts = []
        for segment in segments:
            text = segment.get('text', '')
            full_text_parts.append(text)

        full_text = " ".join(full_text_parts)
        return self.generate_audio(full_text, filename_prefix)

    def _generate_kokoro_multi_speaker(
        self,
        segments: List[Dict[str, str]],
        filename_prefix: str
    ) -> Optional[TTSResult]:
        """
        Generate multi-speaker conversation using Kokoro TTS with distinct voices.

        Different speakers get different voices for natural conversation flow.
        """
        if not KOKORO_AVAILABLE:
            current_app.logger.warning("Kokoro not available, falling back")
            full_text = " ".join([s.get('text', '') for s in segments])
            return self._generate_gtts(full_text, filename_prefix)

        # Lazy-load Kokoro pipeline
        if self.kokoro_pipe is None:
            try:
                current_app.logger.info("Loading Kokoro pipeline for multi-speaker...")
                self.kokoro_pipe = KPipeline(lang_code='a')
                current_app.logger.info("Kokoro pipeline loaded")
            except Exception as e:
                current_app.logger.error(f"Failed to load Kokoro: {e}")
                full_text = " ".join([s.get('text', '') for s in segments])
                return self._generate_gtts(full_text, filename_prefix)

        audio_dir = self._ensure_audio_dir()
        timestamp = int(time.time() * 1000)
        safe_prefix = secure_filename(filename_prefix)
        filename = f"{safe_prefix}_{timestamp}.mp3"
        file_path = audio_dir / filename

        try:
            # Voice mapping: distinct voices for different speakers
            # Uses the voice specified in segment, or falls back to speaker-based mapping
            VOICE_MAP = {
                'Professor': 'am_adam',     # Male professor
                'Student': 'af_heart',      # Female student
                'Woman': 'af_heart',        # Female voice
                'Female': 'af_heart',
                'Man': 'am_adam',           # Male voice
                'Male': 'am_adam',
                'Advisor': 'af_alloy',      # Alternative female voice
                'default': 'af_heart'
            }

            # Generate audio for each segment with appropriate voice
            combined_audio = AudioSegment.silent(0)
            all_words = []
            current_time = 0.0

            for segment in segments:
                speaker = segment.get('speaker', 'default')
                text = segment.get('text', '')
                # Use voice from segment if provided, otherwise map from speaker
                voice = segment.get('voice') or VOICE_MAP.get(speaker, VOICE_MAP['default'])

                if not text.strip():
                    continue

                # Generate audio for this segment
                gen = self.kokoro_pipe(text, voice=voice)
                segment_chunks = []
                for _, _, audio_data in gen:
                    if isinstance(audio_data, torch.Tensor):
                        segment_chunks.append(audio_data.detach().cpu().numpy())
                    else:
                        segment_chunks.append(np.asarray(audio_data))

                if not segment_chunks:
                    current_app.logger.warning(f"Kokoro returned no audio for segment speaker={speaker}")
                    continue

                segment_waveform = np.concatenate(segment_chunks)

                # Convert to AudioSegment
                buf = io.BytesIO()
                sf.write(buf, segment_waveform, 24000, format='WAV')
                buf.seek(0)
                segment_audio = AudioSegment.from_file(buf, format="wav")

                # Add segment to combined audio
                combined_audio += segment_audio

                # Add natural pause between speakers (400ms)
                combined_audio += AudioSegment.silent(400)

                # Calculate timestamps for this segment's words
                segment_duration = len(segment_audio) / 1000.0
                words = text.split()
                time_per_word = segment_duration / len(words) if words else 0

                for i, word in enumerate(words):
                    all_words.append({
                        'word': word,
                        'start': round(current_time + (i * time_per_word), 3),
                        'end': round(current_time + ((i + 1) * time_per_word), 3)
                    })

                current_time += segment_duration + 0.4  # Add pause time

            # Export combined audio
            combined_audio.export(str(file_path), format="mp3")

            # Total duration
            total_duration = len(combined_audio) / 1000.0

            # Return relative path
            relative_path = f"listening_audio/{filename}"

            return TTSResult(
                audio_path=relative_path,
                duration_seconds=total_duration,
                word_timestamps=all_words,
                provider='kokoro'
            )

        except Exception as e:
            current_app.logger.error(f"Kokoro multi-speaker generation failed: {e}")
            # Fallback
            full_text = " ".join([s.get('text', '') for s in segments])
            return self._generate_gtts(full_text, filename_prefix)


def get_tts_service() -> TTSService:
    """Factory function to get TTS service instance."""
    return TTSService()
