# Dashboard Restructure - Hierarchical Navigation System

## Overview

Restructured the entire application to have a hierarchical dashboard system with better UX flow and batch generation for reading practice.

## New Dashboard Structure

```
Main Dashboard (/)
├── Vocabulary Section (/vocab/dashboard)
│   ├── Learning Session (/session)
│   ├── Exercises Hub (/exercises)
│   └── Word Browser (/words)
│
├── Reading Section (/reading/dashboard)
│   ├── Sentence Practice (/reading/practice/sentence)
│   │   └── Batch of 5 exercises with navigation
│   ├── Paragraph Practice (/reading/practice/paragraph)
│   │   └── Batch of 5 exercises with navigation
│   └── Passage Practice (/reading/practice/passage)
│       └── Batch of 5 exercises with navigation
│
├── Writing Section (Coming Soon)
├── Listening Section (Coming Soon)
├── Speaking Section (Coming Soon)
└── Mock Tests (Coming Soon)
```

## Key Features

### 1. Main Dashboard
- **Route**: `/dashboard` or `/`
- **Purpose**: Central hub showing all TOEFL sections
- **Features**:
  - Quick progress summary (words reviewed today, new/review counts)
  - Section cards for Vocabulary, Reading, Writing, Listening, Speaking, Mock Tests
  - Active sections are clickable, others show "Coming Soon"
  - Direct links to start learning or access settings

### 2. Vocabulary Dashboard
- **Route**: `/vocab/dashboard`
- **Purpose**: Detailed vocabulary analytics and access to vocab features
- **Features**:
  - Full progress stats (daily goal, streak, velocity)
  - Mastery breakdown visualization
  - 14-day review activity chart
  - Links to:
    - Learning Session (SRS-based review)
    - Exercises Hub (gap-fill, synonyms, reading)
    - Word Browser (by mastery level)
  - Back button to main dashboard

### 3. Reading Dashboard
- **Route**: `/reading/dashboard`
- **Purpose**: Choose reading practice type
- **Features**:
  - Three practice cards: Sentence Gym, Paragraph Lab, Passage Simulator
  - Each card explains what's included
  - Click to generate batch of 5 practice sets
  - Loading overlay during generation (30-60 seconds)
  - Info box explaining how it works

### 4. Batch Generation System

#### How It Works
1. User clicks a practice type (sentence/paragraph/passage)
2. Backend generates 5 sets sequentially
3. Stores batch in session with index tracker
4. Redirects to practice page

#### Practice Pages
- **Routes**:
  - `/reading/practice/sentence`
  - `/reading/practice/paragraph`
  - `/reading/practice/passage`

- **Navigation**:
  - Progress indicator: "Exercise X of 5"
  - Previous/Next buttons
  - AJAX navigation (no page reload for switching)
  - Disabled states when at start/end

- **Content Display**:
  - **Sentence**: Full analysis, focus points, paraphrase reference
  - **Paragraph**: Sentence breakdown with roles, topic sentence highlighting, transitions
  - **Passage**: Multi-paragraph text, comprehension questions with interactive options

- **Regenerate Button**:
  - Fixed position (bottom-right)
  - Generates new batch of 5
  - Confirmation dialog before regenerating
  - Shows loading spinner during generation

## New Routes

### Dashboard Routes
```python
@app.route('/dashboard')           # Main TOEFL dashboard
@app.route('/vocab/dashboard')     # Vocabulary section dashboard
@app.route('/reading/dashboard')   # Reading section dashboard
```

### Reading Practice Routes
```python
# Generate batch of 5
@app.route('/reading/practice/<practice_type>/generate', methods=['POST'])

# Display current item from batch
@app.route('/reading/practice/<practice_type>')

# Navigate through batch (next/prev)
@app.route('/reading/practice/<practice_type>/navigate', methods=['POST'])
```

## Session Management

### Batch Storage
```python
# Keys used in session
session[f'reading_{practice_type}_batch']  # List of 5 items
session[f'reading_{practice_type}_index']  # Current index (0-4)
```

### Navigation Flow
1. Generate: Create batch → store in session → set index to 0
2. Navigate: Update index → reload page
3. Regenerate: Generate new batch → reset index to 0

## Templates Created/Modified

### New Templates
- `main_dashboard.html` - Main TOEFL dashboard
- `vocab_dashboard.html` - Vocabulary section dashboard
- `reading_dashboard.html` - Reading practice selection
- `reading/sentence_practice.html` - Sentence batch practice
- `reading/paragraph_practice.html` - Paragraph batch practice
- `reading/passage_practice.html` - Passage batch practice

### Existing Templates
- `dashboard.html` - Original (kept for reference, not used anymore)
- `reading/index.html` - Original reading page (still exists, not in new flow)

## User Flow Example

### Reading Practice Flow
```
1. User logs in → Main Dashboard
2. Click "Reading" card → Reading Dashboard
3. Click "Sentence Gym" → Loading screen (30-60s)
4. Gemini generates 5 sentences → Sentence Practice page (showing #1)
5. User reads analysis, clicks "Next" → Sentence #2
6. User continues through 5 sentences
7. User clicks "Regenerate" → New batch of 5 generated
8. Back button → Reading Dashboard → Main Dashboard
```

### Vocabulary Flow
```
1. User logs in → Main Dashboard
2. Click "Vocabulary" card → Vocab Dashboard
3. See detailed analytics, progress charts
4. Click "Learning Session" → SRS review
5. Back button → Vocab Dashboard → Main Dashboard
```

## Benefits

### User Experience
- ✅ Clear hierarchical navigation
- ✅ Dedicated dashboards for each section
- ✅ Batch generation reduces waiting time (generate once, practice 5 times)
- ✅ Easy navigation between exercises
- ✅ One-click regeneration for fresh content
- ✅ Consistent back button navigation

### Technical
- ✅ Cleaner route organization
- ✅ Session-based batch storage (no database needed)
- ✅ Efficient Gemini usage (generate 5 at once vs 5 separate calls)
- ✅ Scalable structure for adding new sections

### Gemini Optimization
- ✅ Batch generation spreads API load over 5 generations
- ✅ User practices while system generates (if needed)
- ✅ Regenerate button gives user control
- ✅ Fallback to seeds if any single generation fails

## Configuration

No additional configuration needed. The system uses existing:
- Session management (Flask sessions)
- Gemini client with thinking token fixes
- Seed fallbacks for robustness

## Testing Recommendations

1. **Navigation Flow**
   - Test all dashboard → sub-dashboard → feature paths
   - Verify back buttons work correctly
   - Check breadcrumb consistency

2. **Batch Generation**
   - Generate 5 sentences → verify all 5 are unique
   - Test navigation (next/prev)
   - Test regenerate → verify new content
   - Test with Gemini failures → verify seed fallbacks work

3. **Session Persistence**
   - Navigate away and back → verify position maintained
   - Test across browser refreshes
   - Test session timeout behavior

4. **UI/UX**
   - Verify loading states
   - Check responsive design on mobile
   - Test disabled button states
   - Verify error messages are clear

## Future Enhancements

- [ ] Add "Bookmark" feature to save favorite exercises
- [ ] Track completion % for each batch
- [ ] Add difficulty levels for each practice type
- [ ] Implement topic selection for targeted practice
- [ ] Add timer for timed practice mode
- [ ] Progress tracking across batches
- [ ] Achievement badges for completing batches
