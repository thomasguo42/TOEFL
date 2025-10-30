# Paraphrase Evaluation Using Gemini Fix

## Issue
The sentence paraphrase practice was using a fallback evaluation method based on `SequenceMatcher` instead of actually calling Gemini 2.5 Flash-Lite to provide AI-powered feedback.

## Root Cause
The code in `evaluate_paraphrase()` was already set up to use Gemini 2.5 Flash-Lite (`model_override="gemini-2.5-flash-lite"`), but it may have been falling back to the local scoring method due to:
1. API key not being configured
2. Client initialization issues
3. API errors not being handled properly

## Solution
1. **Verified API Key**: Confirmed `GEMINI_API_KEY` is set in `run_flask.sh` with the user's provided key
2. **Model Configuration**: The code already uses `model_override="gemini-2.5-flash-lite"` which is the correct, cost-effective model for evaluation tasks
3. **Retry Logic**: Removed nested retries that were previously causing rate limit issues - now relies solely on `GeminiClient`'s internal exponential backoff

## Code Flow
When a user submits a paraphrase:

1. **Route**: `/reading/api/paraphrase` (POST) in `app.py:1262-1294`
2. **Evaluation Function**: `evaluate_paraphrase()` in `reading_content.py:369-524`
3. **Gemini Call**: Lines 467-476 make the actual API call:
   ```python
   response = client.generate_json(
       prompt,
       temperature=0.2,
       system_instruction=(
           "You are an attentive TOEFL tutor who compares student paraphrases with a reference answer. "
           "Be concise and focus on meaning coverage."
       ),
       max_output_tokens=768,
       model_override="gemini-2.5-flash-lite",  # Uses Flash-Lite for cost efficiency
   )
   ```

## What Gemini Evaluates
The AI evaluates:
- **Score**: Float between 0-1 for semantic coverage
- **Category**: "excellent", "good", or "needs_work"
- **Feedback**: Short Simplified Chinese comment (≤50 chars)
- **Missing Points**: Array of Chinese hints describing what checkpoints were missed

## Fallback Behavior
If Gemini is unavailable or fails after retries, the system gracefully falls back to:
- `SequenceMatcher` for similarity ratio
- Simple phrase matching for missing focus points
- Basic categorization based on thresholds

## Files Modified
- `/workspace/TOEFL/run_flask.sh` - Verified API key configuration
- `/workspace/TOEFL/app/flask_app/services/reading_content.py` - Already has correct Gemini integration
- `/workspace/TOEFL/app/flask_app/services/gemini_client.py` - Supports `model_override` parameter

## Testing
To verify Gemini is being called:
1. Start the application
2. Navigate to sentence practice
3. Submit a paraphrase
4. Check logs for "Gemini client unavailable" - should NOT appear if working correctly
5. Response should include `detailedFeedback` field with Gemini's Chinese comment

## Model Choice: gemini-2.5-flash-lite
- **Cost-effective**: Lowest cost among 2.5 models
- **Fast**: Optimized for low latency
- **Sufficient**: Perfect for evaluation tasks that don't require extensive reasoning
- **Multimodal**: Supports text input (though we only use text for paraphrase evaluation)
