# Reading Practice Redirect Fix

## Issue
After successfully generating 5 reading practice sets, the frontend stayed on the reading dashboard page instead of automatically redirecting to the practice page.

## Root Cause
The `reading_practice` route was checking for `current_app._reading_batches`, but this attribute wasn't persisting across requests. The issue was:

1. `generate_reading_batch` stored data in `current_app._reading_batches` 
2. Browser made a new request to `reading_practice`
3. In the new request context, `hasattr(current_app, '_reading_batches')` returned `False`
4. Route redirected back to dashboard with a "No batch found" message

## Solution
Changed from using `current_app._reading_batches` (request-scoped) to `app._reading_batches` (application-scoped):

1. **Initialized at startup** (app.py:73-74):
   ```python
   if not hasattr(app, '_reading_batches'):
       app._reading_batches = {}
   ```

2. **Store using `app._reading_batches`** instead of `current_app._reading_batches` in:
   - `generate_reading_batch()` - stores the batch
   - `reading_practice()` - retrieves the batch
   - `navigate_reading_batch()` - navigates through items

## Key Difference
- `current_app`: Proxy to the current request's application context (not persistent)
- `app`: The actual Flask application object (persistent across requests)

## Result
- Batches now persist across requests
- Redirect works correctly after generation
- Users see the practice page immediately after generation completes
- No more "No batch found" redirects

## Files Modified
- `/workspace/TOEFL/app/flask_app/app.py`
  - Lines 73-74: Initialize `app._reading_batches`
  - Line 1027: Use `app._reading_batches` in generate
  - Line 1173: Use `app._reading_batches` in display
  - Line 1227: Use `app._reading_batches` in navigate
