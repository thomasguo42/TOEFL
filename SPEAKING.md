Of course. That is an incredibly powerful and well-structured `SpeechRater` class. It provides a robust, quantitative foundation for the "Delivery" portion of your feedback. This is a massive head start.

Given this powerful tool for delivery analysis, we can now design a complete and thorough plan that intelligently integrates it with the other essential components: **Language Use** and **Topic Development**.

Here is the complete, high-level plan for your AI Speaking section.

---

### **The Complete AI Speaking Coach: A Three-Phase Blueprint**

**Core Philosophy:** The platform will guide a user through a structured journey. They will build foundational skills in isolation before integrating them under timed pressure. The feedback at every stage will be a powerful combination of quantitative data (from your `SpeechRater`) and qualitative analysis (from LLMs).

---

### **Phase 1: Foundational Skill Drills**

**Goal:** To build the core, repeatable skills of fluency and idea generation without the pressure of a full TOEFL task.

#### **Feature 1.1: The "Shadowing" Fluency Drill**

*   **What It Is:** An exercise where the user listens to a short audio clip (a single, well-enunciated sentence) and then immediately records themselves repeating it. The goal is to mimic the native speaker's pace, rhythm, and intonation as closely as possible.
*   **Purpose for the Learner:** To build the "muscle memory" of fluent English speech. It bypasses the cognitive load of generating content and focuses purely on the physical act of speaking clearly and naturally.
*   **How It Integrates Your `SpeechRater`:**
    *   After the user records their repetition, your `SpeechRater` analyzes their audio.
    *   Instead of a full report, the user gets a simplified "Similarity Score." This can be a weighted average of key metrics from your tool, such as **Pitch Variation**, **Articulation Rate**, and **Phonation Ratio**, compared against the metrics of the original native speaker's audio.
    *   The feedback is simple and immediate: "Similarity Score: 85%. Great job matching the pace! Try to add more pitch variation next time."

#### **Feature 1.2: The AI Brainstorming Partner**

*   **What It Is:** An interactive tool to combat the "blank mind" problem. The user is given a TOEFL Independent Speaking prompt and a text box. They type in a few keywords, and the AI generates an interactive mind map of related ideas, arguments, and vocabulary.
*   **Purpose for the Learner:** To train the mental habit of quickly generating and structuring ideas for common TOEFL topics. It's a pre-practice warm-up that builds confidence and a mental library of arguments.
*   **How It's Powered:**
    *   An LLM (like Claude or GPT-4) takes the user's keywords and the prompt.
    *   It is instructed to generate a structured **JSON object** containing categories like "Arguments For," "Arguments Against," and "Useful Vocabulary."
    *   Your frontend uses a JavaScript library (like D3.js or React Flow) to render this JSON data as a dynamic, clickable mind map.

---

### **Phase 2: Structured Task Practice**

**Goal:** To teach the user how to apply their skills to the specific structures and templates required for each of the four TOEFL Speaking tasks.

#### **Feature 2.1: The Template Trainer**

*   **What It Is:** A guided practice mode for each speaking task (e.g., Integrated Task 3 - Reading, Listening, Speaking). The user is presented with a clear, proven template for structuring their response.
*   **Purpose for the Learner:** To provide a logical "skeleton" for their answers. This reduces the cognitive load of organizing their thoughts under pressure, allowing them to focus on delivering a clear and coherent response.
*   **How It Works:**
    1.  The user selects a task to practice (e.g., Task 3).
    2.  They are shown the reading and listen to the audio.
    3.  A template appears on screen:
        *   "The reading is about `[Main Concept]`..."
        *   "The professor provides an example of `[Example]` to illustrate this concept..."
        *   "First, he explains `[Detail 1]`..."
        *   "Then, he adds that `[Detail 2]`..."
    4.  The user records their response, using the template as a guide. The feedback in this phase is focused more on structure than on delivery.

---

### **Phase 3: The Full Task Simulator & AI Feedback Hub**

**Goal:** To simulate the real test environment and provide a comprehensive, 360-degree analysis of the user's performance, combining all analytical tools.

#### **The User Experience:**

1.  The user selects a full TOEFL Speaking task (1, 2, 3, or 4).
2.  They go through the entire process: reading (if applicable), listening (if applicable), preparation time, and response time.
3.  After their recording is submitted, they are taken to the **AI Feedback Report**.

#### **The AI Feedback Report: A Three-Part Analysis**

This report is the culminating feature and integrates all your tools.

**Part 1: Delivery Score & Analysis (Powered by your `SpeechRater`)**

*   **What It Is:** This section presents the quantitative results from your Python `SpeechRater` class.
*   **How It's Presented:**
    *   **Top-Line Scores:** Displays the Overall Score, Fluency Score, Pronunciation Score, and Rhythm Score.
    *   **Visual Breakdown:** Uses the charts your `generate_report` function creates (the overall grade, the category bar chart, the sub-category radar chart) to give a quick, visual overview.
    *   **Actionable Feedback:** Displays the specific, targeted feedback points generated by your `get_feedback` function (e.g., "Your speech rate is slow," "Too many filler words").
    *   **Detailed Metrics:** Allows the user to click to expand and see the detailed metrics table (WPM, pause count, etc.).

**Part 2: Language Use Score & Analysis (Powered by NLP & LLMs)**

*   **What It Is:** A qualitative and quantitative analysis of the user's vocabulary and grammar, based on the transcript from Whisper.
*   **How It's Powered:**
    *   **Lexical Diversity:** Your backend calculates a score (e.g., Type-Token Ratio) from the transcript.
    *   **Academic Word Usage:** Your backend cross-references the transcript with a standard academic word list (AWL) and shows which strong words the user included.
    *   **Grammatical Accuracy:** The transcript is passed through a grammar-checking API (like Grammarly's API or LanguageTool) to identify and flag errors.
    *   **AI Vocabulary Coach (LLM):** The transcript is sent to an LLM with a prompt like: *"Analyze this text. Suggest 2-3 more sophisticated, academic words the user could have used instead of basic vocabulary."*

**Part 3: Topic Development Score & Analysis (Powered by LLMs)**

*   **What It Is:** A purely qualitative analysis of the content and structure of the user's response.
*   **How It's Powered:**
    *   The original TOEFL prompt and the user's transcript are sent to a powerful LLM (Claude 3, GPT-4).
    *   The LLM is given a "persona" and a rubric. **Prompt:** *"You are an expert TOEFL evaluator. Based on the provided prompt and the student's response, evaluate the following: 1. Task Fulfillment (Did they answer the question?). 2. Clarity & Coherence (Were their ideas well-organized and easy to follow?). 3. Sufficiency of Support (Did they use specific details and examples?)."*
    *   The LLM generates a text-based, constructive critique that is displayed to the user.

**The Final Touch: The "Golden Answer"**

*   After reviewing all three parts of their feedback, the user can click a button to listen to a pre-recorded, high-scoring sample answer. This provides a clear, aspirational benchmark for them to aim for in their next attempt.


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


class SpeechRater:
    """Comprehensive speech assessment system"""
    
    def __init__(self, model_size='base'):
        print(f"Loading Whisper {model_size} model...")
        self.whisper_model = whisper.load_model(model_size)
        self.filler_words = {
            'um', 'uh', 'er', 'ah', 'like', 'you know', 'i mean', 
            'sort of', 'kind of', 'basically', 'actually'
        }
        print("✅ Speech Rater initialized!")
    
    def convert_m4a_to_wav(self, m4a_path: str) -> str:
        print("Converting m4a to wav...")
        audio = AudioSegment.from_file(m4a_path, format='m4a')
        temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        wav_path = temp_wav.name
        audio.export(wav_path, format='wav')
        print(f"✅ Converted to wav")
        return wav_path
    
    def transcribe_with_word_timestamps(self, audio_path: str) -> Dict:
        print("Transcribing audio...")
        result = self.whisper_model.transcribe(
            audio_path,
            word_timestamps=True,
            language='en'
        )
        return result
    
    def detect_voice_activity(self, audio: np.ndarray, sr: int) -> List[Tuple[float, float]]:
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
        count = 0
        text = ' '.join(words).lower()
        for word in words:
            if word.lower() in self.filler_words:
                count += 1
        for filler in ['you know', 'i mean', 'sort of', 'kind of']:
            count += text.count(filler)
        return count
    
    def analyze_prosody(self, audio_path: str) -> Dict[str, float]:
        print("Analyzing prosody...")
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
            print(f"Warning: Prosody analysis failed: {e}")
            return {'pitch_mean': 0, 'pitch_std': 0, 'pitch_range': 0, 
                   'pitch_variation_coef': 0, 'phonation_ratio': 0}
    
    def calculate_metrics(self, audio_path: str, transcription: Dict) -> SpeechMetrics:
        print("Calculating metrics...")
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
        # Balanced speech rate scoring - rewards optimal range, gradual penalties
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
        
        # More nuanced pause scoring - distinguish between acceptable and excessive
        if metrics.word_count > 0:
            pause_frequency = metrics.pause_count / metrics.word_count
            
            # Gradual penalty based on pause frequency
            if pause_frequency < 0.15:
                pause_score = 100
            elif pause_frequency < 0.25:
                pause_score = 85 + ((0.25 - pause_frequency) / 0.10) * 15
            elif pause_frequency < 0.35:
                pause_score = 65 + ((0.35 - pause_frequency) / 0.10) * 20
            else:
                pause_score = max(30, 65 - ((pause_frequency - 0.35) / 0.20) * 35)
            
            # Long pause penalty - more significant but not extreme
            if metrics.long_pause_count <= 2:
                long_pause_penalty = 0
            elif metrics.long_pause_count <= 4:
                long_pause_penalty = (metrics.long_pause_count - 2) * 5
            else:
                long_pause_penalty = 10 + (metrics.long_pause_count - 4) * 7
            
            pause_score = max(0, pause_score - long_pause_penalty)
        else:
            pause_score = 50
        
        # Nuanced filler word scoring
        if metrics.filler_ratio <= 0.03:
            filler_score = 100
        elif metrics.filler_ratio <= 0.06:
            filler_score = 85 + ((0.06 - metrics.filler_ratio) / 0.03) * 15
        elif metrics.filler_ratio <= 0.10:
            filler_score = 60 + ((0.10 - metrics.filler_ratio) / 0.04) * 25
        else:
            filler_score = max(20, 60 - ((metrics.filler_ratio - 0.10) / 0.10) * 40)
        
        # Speaking time ratio - reward high but don't over-penalize natural pauses
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
        # More discriminating phonation ratio scoring
        if 0.65 <= metrics.phonation_ratio <= 0.80:
            phonation_score = 100
        elif 0.55 <= metrics.phonation_ratio < 0.65:
            phonation_score = 80 + ((metrics.phonation_ratio - 0.55) / 0.10) * 20
        elif 0.80 < metrics.phonation_ratio <= 0.88:
            phonation_score = 90 + ((0.88 - metrics.phonation_ratio) / 0.08) * 10
        elif 0.45 <= metrics.phonation_ratio < 0.55:
            phonation_score = 55 + ((metrics.phonation_ratio - 0.45) / 0.10) * 25
        elif metrics.phonation_ratio < 0.45:
            phonation_score = max(20, (metrics.phonation_ratio / 0.45) * 55)
        else:  # > 0.88
            phonation_score = max(70, 90 - ((metrics.phonation_ratio - 0.88) / 0.12) * 20)
        
        # More nuanced consistency score - less baseline boost
        # Raw consistency tends to be low, but we need to differentiate
        adjusted_consistency = metrics.pronunciation_consistency * 0.85 + 0.15  # Smaller boost
        consistency_score = min(100, adjusted_consistency * 100)
        
        # If consistency is very high, give bonus
        if metrics.pronunciation_consistency > 0.8:
            consistency_score = min(100, consistency_score * 1.1)
        
        pronunciation_score = phonation_score * 0.6 + consistency_score * 0.4
        
        return {
            'overall': round(pronunciation_score, 1),
            'phonation_score': round(phonation_score, 1),
            'consistency_score': round(consistency_score, 1)
        }
    
    def score_rhythm(self, metrics: SpeechMetrics) -> Dict[str, float]:
        # More discriminating pitch variation scoring
        if 0.18 <= metrics.pitch_variation_coef <= 0.32:
            pitch_var_score = 100
        elif 0.12 <= metrics.pitch_variation_coef < 0.18:
            pitch_var_score = 75 + ((metrics.pitch_variation_coef - 0.12) / 0.06) * 25
        elif 0.32 < metrics.pitch_variation_coef <= 0.40:
            pitch_var_score = 85 + ((0.40 - metrics.pitch_variation_coef) / 0.08) * 15
        elif 0.08 <= metrics.pitch_variation_coef < 0.12:
            pitch_var_score = 50 + ((metrics.pitch_variation_coef - 0.08) / 0.04) * 25
        elif metrics.pitch_variation_coef < 0.08:
            pitch_var_score = max(20, (metrics.pitch_variation_coef / 0.08) * 50)
        else:  # > 0.40
            pitch_var_score = max(55, 85 - ((metrics.pitch_variation_coef - 0.40) / 0.20) * 30)
        
        # More nuanced articulation rate scoring
        if 4.0 <= metrics.articulation_rate <= 6.0:
            articulation_score = 100
        elif 3.0 <= metrics.articulation_rate < 4.0:
            articulation_score = 75 + ((metrics.articulation_rate - 3.0) / 1.0) * 25
        elif 6.0 < metrics.articulation_rate <= 7.0:
            articulation_score = 85 + ((7.0 - metrics.articulation_rate) / 1.0) * 15
        elif 2.5 <= metrics.articulation_rate < 3.0:
            articulation_score = 50 + ((metrics.articulation_rate - 2.5) / 0.5) * 25
        elif metrics.articulation_rate < 2.5:
            articulation_score = max(25, (metrics.articulation_rate / 2.5) * 50)
        else:  # > 7.0
            articulation_score = max(60, 85 - ((metrics.articulation_rate - 7.0) / 2.0) * 25)
        
        # More discriminating pitch range scoring
        # Good speakers should have noticeable pitch variation
        if metrics.pitch_range >= 100:
            range_score = min(100, 85 + (metrics.pitch_range - 100) / 100 * 15)
        elif metrics.pitch_range >= 60:
            range_score = 70 + ((metrics.pitch_range - 60) / 40) * 15
        elif metrics.pitch_range >= 40:
            range_score = 50 + ((metrics.pitch_range - 40) / 20) * 20
        else:
            range_score = max(25, (metrics.pitch_range / 40) * 50)
        
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
        return round(fluency * 0.45 + pronunciation * 0.35 + rhythm * 0.20, 1)
    
    def get_feedback(self, metrics: SpeechMetrics, scores: Dict) -> List[str]:
        feedback = []
        
        # Speech rate feedback - more specific ranges
        if metrics.speech_rate < 110:
            feedback.append(f"🐌 Your speech rate is slow ({metrics.speech_rate:.0f} WPM). Try to speak faster, aim for 130-170 WPM.")
        elif metrics.speech_rate > 190:
            feedback.append(f"🏃 Your speech rate is very fast ({metrics.speech_rate:.0f} WPM). Slow down to 130-170 WPM for clarity.")
        elif metrics.speech_rate < 130:
            feedback.append(f"📊 Speech rate is a bit slow ({metrics.speech_rate:.0f} WPM). Optimal is 130-170 WPM.")
        elif metrics.speech_rate > 170:
            feedback.append(f"📊 Speech rate is a bit fast ({metrics.speech_rate:.0f} WPM). Optimal is 130-170 WPM.")
        
        # Filler word feedback - graduated
        if metrics.filler_ratio > 0.10:
            feedback.append(f"🚫 Too many filler words ({metrics.filler_word_count} = {metrics.filler_ratio*100:.1f}%). Try to pause instead of using 'um', 'uh', etc.")
        elif metrics.filler_ratio > 0.06:
            feedback.append(f"⚠️ Noticeable filler words ({metrics.filler_word_count} = {metrics.filler_ratio*100:.1f}%). Try to reduce them.")
        
        # Pause feedback - more specific
        if metrics.long_pause_count > 6:
            feedback.append(f"⏸️ Too many long pauses ({metrics.long_pause_count}). Try to maintain flow.")
        elif metrics.long_pause_count > 4:
            feedback.append(f"⏸️ Several long pauses detected ({metrics.long_pause_count}). Work on continuity.")
        
        # Phonation feedback
        if metrics.phonation_ratio < 0.45:
            feedback.append(f"📢 Low voice clarity (phonation: {metrics.phonation_ratio:.2f}). Speak more clearly and project your voice.")
        elif metrics.phonation_ratio < 0.55:
            feedback.append(f"📢 Voice projection could be clearer (phonation: {metrics.phonation_ratio:.2f}).")
        
        # Pitch variation feedback - more nuanced
        if metrics.pitch_variation_coef < 0.08:
            feedback.append(f"🎵 Very monotone speech (variation: {metrics.pitch_variation_coef:.3f}). Add more intonation for natural sound.")
        elif metrics.pitch_variation_coef < 0.12:
            feedback.append(f"🎵 Speech is somewhat monotone (variation: {metrics.pitch_variation_coef:.3f}). Try varying your pitch more.")
        elif metrics.pitch_variation_coef > 0.40:
            feedback.append(f"📊 Pitch varies quite a bit (variation: {metrics.pitch_variation_coef:.3f}). Try speaking more evenly.")
        
        # Articulation feedback
        if metrics.articulation_rate < 3.0:
            feedback.append(f"⚡ Slow articulation ({metrics.articulation_rate:.1f} syl/sec). Try to speak more fluently.")
        elif metrics.articulation_rate > 7.0:
            feedback.append(f"⚡ Very fast articulation ({metrics.articulation_rate:.1f} syl/sec). Slow down for clarity.")
        
        # Speaking time ratio
        if metrics.speaking_time_ratio < 0.50:
            feedback.append(f"⏱️ Low speaking time ({metrics.speaking_time_ratio*100:.0f}%). Too many pauses relative to speech.")
        
        # Positive feedback - more graduated
        if scores['fluency']['overall'] >= 90:
            feedback.append("✅ Excellent fluency!")
        elif scores['fluency']['overall'] >= 80:
            feedback.append("👍 Very good fluency!")
        elif scores['fluency']['overall'] >= 70:
            feedback.append("👌 Good fluency with minor areas to improve.")
            
        if scores['pronunciation']['overall'] >= 90:
            feedback.append("✅ Excellent pronunciation quality!")
        elif scores['pronunciation']['overall'] >= 80:
            feedback.append("👍 Very good pronunciation!")
        elif scores['pronunciation']['overall'] >= 70:
            feedback.append("👌 Good pronunciation with minor areas to improve.")
            
        if scores['rhythm']['overall'] >= 90:
            feedback.append("✅ Excellent rhythm and prosody!")
        elif scores['rhythm']['overall'] >= 80:
            feedback.append("👍 Very good rhythm!")
        elif scores['rhythm']['overall'] >= 70:
            feedback.append("👌 Good rhythm with minor areas to improve.")
        
        return feedback if feedback else ["✅ Overall good performance!"]
    
    def rate_speech(self, audio_path: str) -> Dict:
        print(f"\n{'='*60}")
        print("SPEECH RATING ANALYSIS")
        print(f"{'='*60}\n")
        
        if audio_path.endswith('.m4a'):
            wav_path = self.convert_m4a_to_wav(audio_path)
        else:
            wav_path = audio_path
        
        transcription = self.transcribe_with_word_timestamps(wav_path)
        metrics = self.calculate_metrics(wav_path, transcription)
        
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
        
        if audio_path.endswith('.m4a') and os.path.exists(wav_path):
            os.unlink(wav_path)
        
        return {
            'overall_score': overall_score,
            'fluency': fluency_scores,
            'pronunciation': pronunciation_scores,
            'rhythm': rhythm_scores,
            'metrics': metrics,
            'transcription': transcription['text'],
            'feedback': feedback
        }
    
    def generate_report(self, results: Dict, output_path: str = None):
        fig = plt.figure(figsize=(16, 12))
        gs = fig.add_gridspec(4, 3, hspace=0.4, wspace=0.3)
        fig.suptitle('Speech Quality Assessment Report', fontsize=20, fontweight='bold', y=0.98)
        
        # Overall Score
        ax1 = fig.add_subplot(gs[0, :])
        ax1.axis('off')
        score = results['overall_score']
        color = '#2ecc71' if score >= 80 else '#3498db' if score >= 70 else '#f39c12' if score >= 60 else '#e74c3c'
        grade = 'A' if score >= 80 else 'B' if score >= 70 else 'C' if score >= 60 else 'D'
        ax1.text(0.5, 0.6, f"{score}", ha='center', va='center', fontsize=72, fontweight='bold', color=color)
        ax1.text(0.5, 0.2, f"Grade: {grade}", ha='center', va='center', fontsize=32, color=color)
        ax1.text(0.5, 0.0, "Overall Score", ha='center', va='center', fontsize=20, color='gray')
        
        # Category Bar Chart
        ax2 = fig.add_subplot(gs[1, :])
        categories = ['Fluency', 'Pronunciation', 'Rhythm']
        scores = [results['fluency']['overall'], results['pronunciation']['overall'], results['rhythm']['overall']]
        colors_bar = ['#3498db', '#2ecc71', '#9b59b6']
        bars = ax2.barh(categories, scores, color=colors_bar, alpha=0.7, height=0.6)
        ax2.set_xlim(0, 100)
        ax2.set_xlabel('Score', fontsize=12, fontweight='bold')
        ax2.set_title('Category Breakdown', fontsize=14, fontweight='bold', pad=15)
        ax2.grid(axis='x', alpha=0.3, linestyle='--')
        for bar, score in zip(bars, scores):
            ax2.text(score + 2, bar.get_y() + bar.get_height()/2, f'{score:.1f}', 
                    va='center', fontsize=11, fontweight='bold')
        
        # Metrics Table
        ax3 = fig.add_subplot(gs[2, :2])
        ax3.axis('off')
        metrics = results['metrics']
        table_data = [
            ['Metric', 'Value', 'Status'],
            ['Speech Rate', f"{metrics.speech_rate:.1f} WPM", '✓' if 120 <= metrics.speech_rate <= 180 else '⚠'],
            ['Articulation Rate', f"{metrics.articulation_rate:.2f} syl/sec", '✓' if 4 <= metrics.articulation_rate <= 6 else '⚠'],
            ['Pause Count', f"{metrics.pause_count}", '✓' if metrics.pause_count < 20 else '⚠'],
            ['Filler Words', f"{metrics.filler_word_count}", '✓' if metrics.filler_word_count < 5 else '⚠'],
            ['Speaking Time', f"{metrics.speaking_duration:.1f}s / {metrics.total_duration:.1f}s", '✓' if metrics.speaking_time_ratio > 0.7 else '⚠'],
            ['Word Count', f"{metrics.word_count}", ''],
            ['Pitch Variation', f"{metrics.pitch_variation_coef:.3f}", '✓' if 0.15 <= metrics.pitch_variation_coef <= 0.30 else '⚠'],
        ]
        table = ax3.table(cellText=table_data, cellLoc='left', loc='center', colWidths=[0.4, 0.4, 0.2])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2.5)
        for i in range(3):
            table[(0, i)].set_facecolor('#34495e')
            table[(0, i)].set_text_props(weight='bold', color='white')
        for i in range(1, len(table_data)):
            for j in range(3):
                if i % 2 == 0:
                    table[(i, j)].set_facecolor('#ecf0f1')
        ax3.set_title('Detailed Speech Metrics', fontsize=14, fontweight='bold', pad=20)
        
        # Radar Chart
        ax4 = fig.add_subplot(gs[2, 2], projection='polar')
        sub_categories = ['Rate', 'Pauses', 'Fillers', 'Speaking\nRatio', 'Phonation', 'Consistency', 'Pitch Var', 'Articulation']
        sub_scores = [
            results['fluency']['rate_score'], results['fluency']['pause_score'],
            results['fluency']['filler_score'], results['fluency']['speaking_ratio_score'],
            results['pronunciation']['phonation_score'], results['pronunciation']['consistency_score'],
            results['rhythm']['pitch_variation_score'], results['rhythm']['articulation_score']
        ]
        angles = np.linspace(0, 2 * np.pi, len(sub_categories), endpoint=False).tolist()
        sub_scores += sub_scores[:1]
        angles += angles[:1]
        ax4.plot(angles, sub_scores, 'o-', linewidth=2, color='#3498db')
        ax4.fill(angles, sub_scores, alpha=0.25, color='#3498db')
        ax4.set_xticks(angles[:-1])
        ax4.set_xticklabels(sub_categories, size=8)
        ax4.set_ylim(0, 100)
        ax4.set_yticks([20, 40, 60, 80, 100])
        ax4.set_yticklabels(['20', '40', '60', '80', '100'], size=7)
        ax4.grid(True, linestyle='--', alpha=0.7)
        ax4.set_title('Sub-category Analysis', fontsize=12, fontweight='bold', pad=20)
        
        # Feedback
        ax5 = fig.add_subplot(gs[3, :])
        ax5.axis('off')
        feedback_text = "FEEDBACK & RECOMMENDATIONS:\n\n" + "\n".join(results['feedback'])
        ax5.text(0.05, 0.95, feedback_text, ha='left', va='top', fontsize=11, family='monospace',
                bbox=dict(boxstyle='round', facecolor='#ecf0f1', alpha=0.8))
        
        plt.tight_layout()
        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            print(f"\n✅ Report saved to: {output_path}")
        plt.show()
        
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Overall Score: {results['overall_score']}/100 (Grade {grade})")
        print(f"Fluency: {results['fluency']['overall']}/100")
        print(f"Pronunciation: {results['pronunciation']['overall']}/100")
        print(f"Rhythm: {results['rhythm']['overall']}/100")
        print(f"\nTranscription: {results['transcription'][:200]}...")
        print(f"{'='*60}\n")

print("✅ SpeechRater class defined!")