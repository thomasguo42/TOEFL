# Question Type Practice - Complete Fix Summary

## Issues Found in Logs

### Issue 1: Gemini Returning None
```
ERROR in question_types: Gemini returned non-dict payload: <class 'NoneType'>
```

**Causes:**
- JSON parsing failure
- API timeout or error
- Empty response from Gemini
- Response too large (truncated)

### Issue 2: Session Cookie Size Exceeded
```
The 'session' cookie is too large: the value was 9102 bytes but the header required 79 extra bytes. 
The final size was 9181 bytes but the limit is 4093 bytes.
```

**Cause:** Storing 5 complete questions with all data in session cookie exceeded browser limits.

## All Fixes Applied

### 1. Server-Side Storage (Cookie Size Fix) ✅

**Problem:** Session cookie limit is 4KB, but 5 questions = 9KB

**Solution:** Use server-side cache (like `_reading_batches`)

**Changes in `app.py`:**
```python
# Added server-side cache
if not hasattr(app, '_question_drills'):
    app._question_drills = {}

# Store drill in cache, only ID in session
drill_id = f"drill_{question_type_id}_{user.id}_{int(time.time())}"
cache[drill_id] = drill
session[session_key] = drill_id  # Only ~50 bytes instead of 9KB
```

**Benefits:**
- ✅ Session cookie: ~50 bytes (was 9181 bytes)
- ✅ No browser warnings
- ✅ Supports unlimited drill size
- ✅ Works like existing `_reading_batches` system

### 2. Enhanced Error Logging ✅

**Added in `gemini_client.py`:**
```python
# Log when text is empty
current_app.logger.error(
    "Gemini response contained empty text. Finish reason: %s, Candidates count: %s, Full response: %s",
    finish_reason, len(candidates), str(data)[:500]
)

# Log when JSON parsing fails
if parsed is None:
    current_app.logger.error(
        "Gemini JSON parsing failed. Text length: %s, First 500 chars: %s",
        len(text), text[:500]
    )
```

**Added in `question_types.py`:**
```python
# Log when Gemini returns None
if payload is None:
    current_app.logger.error(
        f"Gemini returned None for '{question_type_id}' on attempt {attempt + 1}. "
        f"Possible causes: API error, JSON parsing failure, or empty response."
    )
```

### 3. Increased Token Budget ✅

**Changed:** `max_output_tokens=8192` (was 2048, then 4096, now 8192)

**Reasoning:**
- 1 question ≈ 400-600 tokens with full explanations
- 5 questions = 2000-3000 tokens
- Passage = 800-1200 tokens
- Total needed ≈ 3000-4500 tokens
- 8192 provides comfortable buffer

### 4. Fixed JSON Schema Example ✅

**Before:**
```json
"questions": [
  {
    "question_text": "The question...",
    ...
  }
]  // Only showed 1 question!
```

**After:**
```json
"questions": [
  {
    "question_text": "First question...",
    ...
  },
  {
    "question_text": "Second question...",
    ...
  },
  // ... shows all 5 questions
]
```

### 5. Improved Validation ✅

**Changed:** Accept 3-5 questions (was requiring exactly 5)

```python
if num_questions < 3:
    current_app.logger.error(f"Validation failed: only {num_questions} questions (need at least 3)")
    return False

if num_questions < 5:
    current_app.logger.warning(f"Generated {num_questions} questions instead of 5, but accepting")
```

### 6. Longer Passage Support ✅

**Changed:** 350-450 words (was 180-220)

**Reasoning:** Need enough content to support 5 distinct questions

## File Changes Summary

### `/workspace/TOEFL/app/flask_app/app.py`
- ✅ Added `_question_drills` server-side cache (line 81-85)
- ✅ Modified `question_type_practice()` to use drill_id from cache (line 1402-1446)
- ✅ Modified `generate_question_type_drill_async()` to store in cache (line 1507-1525)
- ✅ Modified `navigate_question_type_drill()` to use cache (line 1539-1575)
- ✅ Modified `regenerate_question_type_drill()` to clear cache (line 1578-1603)

### `/workspace/TOEFL/app/flask_app/services/question_types.py`
- ✅ Increased passage length to 350-450 words (line 345)
- ✅ Changed max_output_tokens to 8192 (line 293)
- ✅ Fixed JSON schema to show all 5 questions (line 442-510)
- ✅ Improved validation to accept 3-5 questions (line 473-479)
- ✅ Added detailed error logging (line 297-306, 484-492)

### `/workspace/TOEFL/app/flask_app/services/gemini_client.py`
- ✅ Added logging for empty text responses (line 194-199)
- ✅ Added logging for JSON parsing failures (line 203-208)

### `/workspace/TOEFL/app/flask_app/templates/reading/question_type_practice.html`
- ✅ Added question counter (line 40-42)
- ✅ Added navigation buttons (line 135-144)
- ✅ Client-side question management (line 160-424)

## What Should Happen Now

### Expected Success Flow:
1. ✅ User clicks question type
2. ✅ Loading screen appears
3. ✅ **ONE Gemini call** generates 5 questions (15-30 seconds)
4. ✅ Drill stored in server cache with unique ID
5. ✅ Only drill ID (~50 bytes) stored in session cookie
6. ✅ User sees question 1/5 and can navigate
7. ✅ Next/Previous navigation is instant (no API calls)
8. ✅ "Regenerate" clears cache and generates new batch

### If Gemini Returns None:
The logs will now show:
```
ERROR: Gemini returned None for 'factual' on attempt 1. 
       Possible causes: API error, JSON parsing failure, or empty response.
ERROR: Gemini response contained empty text. Finish reason: MAX_TOKENS, Full response: {...}
OR
ERROR: Gemini JSON parsing failed. Text length: 8500, First 500 chars: {...}
```

### If Validation Fails:
The logs will show exactly what's wrong:
```
INFO: Gemini returned 3 questions for 'factual'
WARNING: Generated 3 questions instead of 5, but accepting
OR
ERROR: Validation failed: only 1 questions (need at least 3)
OR
ERROR: Validation failed: question 2 has invalid options
```

## Testing Checklist

- [ ] Navigate to question type hub
- [ ] Click any question type
- [ ] Should see loading screen for 15-30 seconds
- [ ] Should see "问题 1 / 5" or "问题 1 / 3" (if Gemini generated 3)
- [ ] Click "下一题" (Next) - should be instant
- [ ] Click "上一题" (Previous) - should be instant
- [ ] Answer questions and check feedback works
- [ ] Click "重新生成新题组" - should regenerate new batch

## Monitoring

Watch logs for:
1. **Success:** `Question type drill generation for 'X' succeeded on attempt 1`
2. **Stored:** `Stored drill drill_X_userId_timestamp with 5 questions`
3. **Cookie size:** Should NOT see cookie size warnings anymore
4. **If errors:** Detailed diagnostics will pinpoint the issue

## Recovery from Previous Issues

If you encounter old cached data or session issues:
1. Clear browser cookies for the site
2. Restart Flask server (already running)
3. Try generating a new drill

The server-side cache is in-memory and automatically clears on restart.
