# Paraphrase Evaluation: Gemini is Now Mandatory

## Changes Made

### Problem
The paraphrase evaluation was falling back to `SequenceMatcher` (local scoring) instead of using Gemini AI because:
1. The sentence wasn't being stored in the session when the practice page loaded
2. The code had a fallback mechanism that would silently use local scoring

### Solution

#### 1. Store Sentence in Session (app.py)
**Lines 1185-1188**: When displaying a sentence practice page, store the current sentence in the session:
```python
# Store current sentence in session for paraphrase evaluation
if practice_type == 'sentence' and current_item:
    session['reading_last_sentence'] = current_item
    session.modified = True
```

**Lines 1238-1240**: When navigating to next/previous sentence, update the session:
```python
# Store current sentence in session for paraphrase evaluation
if practice_type == 'sentence' and item:
    session['reading_last_sentence'] = item
```

#### 2. Remove Fallback Logic (reading_content.py)
Removed the `_fallback_score()` and `_ensure_fallback()` functions completely. Now if Gemini fails, it returns a clear error message instead of silently falling back.

**Before**: Used `SequenceMatcher` for similarity scoring as fallback
**After**: Returns error with helpful message in Chinese

#### 3. Better Error Messages
Changed all fallback scenarios to return explicit error messages:

- **Sentence not found**: `"无法找到句子信息，请刷新页面重试。"`
- **API not configured**: `"AI 评估服务暂时不可用，请联系管理员。"`
- **Gemini error**: `"AI 评估服务出现错误，请稍后重试。"`

#### 4. Enhanced Logging
Added clear logging to track Gemini usage:
```python
current_app.logger.info(f"Calling Gemini 2.5 Flash-Lite for paraphrase evaluation of sentence_id={sentence_id}")
# ... API call ...
current_app.logger.info(f"Gemini 2.5 Flash-Lite response received for sentence_id={sentence_id}")
```

## How to Verify Gemini is Being Used

### Check Logs
Look for these log messages:
- ✅ **Success**: `"Calling Gemini 2.5 Flash-Lite for paraphrase evaluation"`
- ✅ **Success**: `"Gemini 2.5 Flash-Lite response received"`
- ❌ **Error**: `"Paraphrase evaluation failed: sentence_id=X not found"` (sentence not in session)
- ❌ **Error**: `"Gemini client unavailable - API key not configured!"` (API key missing)
- ❌ **Error**: `"Gemini paraphrase evaluation failed: X"` (API error)

### Check Response
The API response at `/reading/api/paraphrase` should include:
```json
{
  "score": 0.85,
  "category": "good",
  "feedback": "你的改写保留了主要意思...",
  "detailedFeedback": "该改写覆盖了关键信息，语法正确。",  // ← This is Gemini's feedback
  "missing": ["提示：某个要点"],
  "modelAnswer": "Reference paraphrase..."
}
```

The `detailedFeedback` field contains Gemini's Chinese comment.

## Model Used
- **Model**: `gemini-2.5-flash-lite`
- **Temperature**: 0.2 (consistent evaluation)
- **Max tokens**: 768
- **Cost**: Most cost-effective 2.5 model
- **Speed**: Optimized for low latency

## Files Modified
1. `/workspace/TOEFL/app/flask_app/app.py`
   - Store sentence in session when displaying practice page
   - Store sentence in session when navigating

2. `/workspace/TOEFL/app/flask_app/services/reading_content.py`
   - Removed `_fallback_score()` and `_ensure_fallback()` functions
   - Changed fallback returns to explicit error messages
   - Added detailed logging for Gemini calls
   - Removed dependency on `SequenceMatcher` for paraphrase evaluation

3. `/workspace/TOEFL/run_flask.sh`
   - Verified API key is set: `AIzaSyAJrbPs_fr5hUqt08qUAporCHztsoZgFzE`

## Testing Steps
1. Restart Flask app
2. Navigate to Sentence Practice
3. Generate 5 sentences
4. Submit a paraphrase
5. Check logs for "Calling Gemini 2.5 Flash-Lite"
6. Verify response includes `detailedFeedback` field with Chinese text from Gemini
7. Should NOT see: "Paraphrase evaluation fallback triggered"

## Expected Behavior
- ✅ Every paraphrase submission calls Gemini
- ✅ Clear error messages if Gemini unavailable
- ✅ Detailed Chinese feedback from AI
- ❌ NO silent fallbacks to local scoring
- ❌ NO SequenceMatcher used for evaluation
