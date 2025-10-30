# Question Type Practice - Infinite Loop Fix

## Problem
When clicking a question type in the reading exercise lab, Gemini was being called repeatedly and validation was failing 3 times, resulting in errors.

## Root Causes Identified

### 1. **JSON Schema Mismatch** (PRIMARY ISSUE)
The prompt asked for "FIVE questions" but the JSON schema example only showed **1 question** in the array:
```json
"questions": [
  {
    "question_text": "The question...",
    ...
  }
]
```
This confused Gemini, causing it to generate only 1 question despite the instructions.

### 2. **Insufficient Token Budget**
- **Before**: 2048 tokens
- **Problem**: 5 questions with full explanations need ~300-400 tokens each = 1500-2000 tokens + passage
- **After**: 4096 tokens (doubled)

### 3. **Passage Too Short**
- **Before**: 180-220 words
- **Problem**: Not enough content to support 5 distinct questions of the same type
- **After**: 350-450 words with multiple paragraphs

### 4. **Validation Too Strict**
- **Before**: Required exactly 5 questions or reject completely
- **Problem**: If Gemini generated 4 questions, entire response was rejected
- **After**: Accept 3-5 questions, with warning if < 5

### 5. **Insufficient Logging**
- **Before**: Only said "invalid data"
- **Problem**: Couldn't diagnose what was wrong
- **After**: Detailed logging showing exactly what failed and how many questions were returned

## Changes Made

### `/workspace/TOEFL/app/flask_app/services/question_types.py`

1. **Updated Prompt** (line 345-354)
   - Changed passage length from "180-220 words" to "350-450 words with multiple paragraphs"
   - Added "IMPORTANT: Generate exactly 5 questions. Each question should test different parts of the passage."

2. **Increased Token Limit** (line 293)
   ```python
   max_output_tokens=4096,  # Was 2048
   ```

3. **Fixed JSON Schema** (line 442-510)
   - Now shows all 5 question objects in the example
   - Added "CRITICAL: The questions array MUST contain exactly 5 question objects"

4. **Improved Validation** (line 515-538)
   - Accept 3-5 questions instead of requiring exactly 5
   - Added detailed error logging for each validation failure
   - Log warnings when < 5 questions but still accept

5. **Enhanced Logging** (line 296-323)
   - Log how many questions Gemini returned
   - Log specific validation failures
   - Log final attempt details

### `/workspace/TOEFL/app/flask_app/app.py`

1. **Updated Validation** (line 1463-1467)
   - Changed from requiring 5 to requiring minimum 3
   - Better error messages showing actual count

2. **Added Navigation Endpoint** (line 1512-1541)
   - `/reading/api/question-types/<id>/navigate` for prev/next navigation
   - Updates session state without regenerating

### `/workspace/TOEFL/app/flask_app/templates/reading/question_type_practice.html`

1. **Added Question Counter** (line 40-42)
   - Shows "问题 1 / 5", "问题 2 / 5", etc.

2. **Added Navigation Buttons** (line 135-144)
   - Previous (上一题) and Next (下一题) buttons
   - Disabled at boundaries

3. **Client-Side Question Management** (line 160-424)
   - All 5 questions loaded in browser
   - Navigation happens instantly without server calls
   - Each question maintains its own state

## Expected Behavior Now

1. ✅ User clicks a question type
2. ✅ Loading screen appears
3. ✅ **ONE Gemini API call** generates 5 questions (or 3-5 if model struggles)
4. ✅ User practices all questions by clicking Next/Previous
5. ✅ **No additional API calls** until user clicks "重新生成新题组"
6. ✅ If generation fails, detailed logs explain why

## Testing

Try the question type practice now. Watch the logs:
- Should see: `Gemini returned 5 questions for 'negative_factual'`
- Should see: `Question type drill generation for 'negative_factual' succeeded on attempt 1`
- Should NOT see: Repeated validation failures

If you still see validation failures, the logs will now tell you:
- How many questions were returned
- Which specific field is missing or invalid
- Whether it's a passage issue, questions array issue, or individual question issue

## Model Behavior Notes

The validation now accepts **3-5 questions** because:
- Some question types might be harder to generate 5 distinct questions for
- It's better to accept 3-4 good questions than reject everything
- The user still gets a useful practice session
- Logs warn when < 5 so we can monitor success rates

## Summary

The infinite loop was caused by:
1. Gemini generating 1 question instead of 5 (due to confusing schema)
2. Validation rejecting it
3. System retrying 3 times
4. All 3 attempts failing the same way

Now fixed by showing Gemini exactly what 5 questions look like in the schema example.
