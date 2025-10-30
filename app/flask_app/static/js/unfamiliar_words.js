/**
 * Unfamiliar Words Manager
 * Allows users to highlight and add words to their unfamiliar words list
 */

class UnfamiliarWordsManager {
    constructor() {
        this.isSelectionMode = false;
        console.log('[UnfamiliarWords] Initializing manager...');
        this.init();
    }

    init() {
        // Add selection mode toggle button to pages
        this.addToggleButton();

        // Listen for text selection events
        document.addEventListener('mouseup', (e) => {
            if (this.isSelectionMode) {
                this.handleSelection(e);
            }
        });

        // Add click handlers for all selectable text areas
        this.makeSelectableAreas();

        console.log('[UnfamiliarWords] Manager initialized successfully');
    }

    addToggleButton() {
        // Skip on login/register pages
        const path = window.location.pathname;
        console.log('[UnfamiliarWords] Current path:', path);

        if (path === '/login' || path === '/register' || path === '/logout') {
            console.log('[UnfamiliarWords] Skipping button on auth page');
            return;
        }

        // Check if user is logged in by looking for user menu
        const userMenu = document.querySelector('.navbar .text-muted');
        if (!userMenu) {
            console.log('[UnfamiliarWords] User not logged in, skipping button');
            return; // Not logged in
        }

        console.log('[UnfamiliarWords] Creating toggle button...');

        // Always show the button on authenticated pages
        // It will work on any page with text content
        const toggleBtn = document.createElement('button');
        toggleBtn.id = 'unfamiliar-words-toggle';
        toggleBtn.className = 'unfamiliar-toggle-btn';
        toggleBtn.innerHTML = `
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
            </svg>
            <span class="toggle-text">Mark Words</span>
        `;
        toggleBtn.title = 'Toggle word selection mode - Click to start marking unfamiliar words';

        toggleBtn.addEventListener('click', () => {
            console.log('[UnfamiliarWords] Button clicked');
            this.toggleSelectionMode();
        });

        document.body.appendChild(toggleBtn);
        console.log('[UnfamiliarWords] Button added to page');
    }

    toggleSelectionMode() {
        this.isSelectionMode = !this.isSelectionMode;
        const btn = document.getElementById('unfamiliar-words-toggle');

        if (this.isSelectionMode) {
            btn.classList.add('active');
            btn.innerHTML = `
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M20 6L9 17l-5-5"/>
                </svg>
                <span class="toggle-text">Done</span>
            `;
            this.showToast('Click any word to mark it as unfamiliar', 'info');
        } else {
            btn.classList.remove('active');
            btn.innerHTML = `
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                </svg>
                <span class="toggle-text">Mark Words</span>
            `;
        }
    }

    makeSelectableAreas() {
        // Make all text content in specific areas word-selectable
        const selectors = [
            '.reading-content',
            '.exercise-content',
            '.vocab-content',
            '.passage-text',
            '.paragraph-text',
            '.sentence-text',
            '.quiz-content',
            '.card',
            'article',
            'main',
            '.container',
            'p',
            'div'
        ];

        // Elements to exclude from word selection
        const excludeSelectors = [
            'button',
            'input',
            'select',
            'textarea',
            'a',
            '.btn',
            '.record-button',
            '.unfamiliar-toggle-btn'
        ];

        selectors.forEach(selector => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => {
                // Skip if element is or contains excluded elements
                let shouldExclude = false;
                excludeSelectors.forEach(excludeSelector => {
                    if (el.matches(excludeSelector) || el.querySelector(excludeSelector)) {
                        shouldExclude = true;
                    }
                });

                if (!shouldExclude) {
                    el.classList.add('word-selectable');
                }
            });
        });
    }

    handleSelection(event) {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();

        if (!selectedText) {
            return;
        }

        // Extract single word (remove punctuation and whitespace)
        const word = selectedText.replace(/[^\w\s]/g, '').trim().split(/\s+/)[0];

        if (!word || word.length < 2) {
            return;
        }

        // Get context (the sentence containing the word)
        const context = this.getContext(selection);

        // Clear selection
        selection.removeAllRanges();

        // Add word to unfamiliar list
        this.addWord(word, context, event);
    }

    getContext(selection) {
        try {
            const range = selection.getRangeAt(0);
            const container = range.commonAncestorContainer;

            // Try to get the sentence containing the selection
            let textNode = container.nodeType === Node.TEXT_NODE ? container : container.textContent;
            let text = container.textContent || container.innerText || '';

            // Get up to 200 characters around the selection
            const selectedText = selection.toString();
            const index = text.indexOf(selectedText);

            if (index !== -1) {
                const start = Math.max(0, index - 100);
                const end = Math.min(text.length, index + selectedText.length + 100);
                text = text.substring(start, end);

                if (start > 0) text = '...' + text;
                if (end < container.textContent.length) text = text + '...';
            }

            return text.trim();
        } catch (e) {
            return '';
        }
    }

    async addWord(word, context, event) {
        // Get source from page
        const source = this.detectSource();

        try {
            const response = await fetch('/api/unfamiliar-words', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    word: word.toLowerCase(),
                    context: context,
                    source: source
                })
            });

            const data = await response.json();

            if (response.ok) {
                this.showToast(`Added "${word}" to unfamiliar words`, 'success');
                this.highlightWord(word, event);
            } else if (response.status === 200 && data.message.includes('already')) {
                this.showToast(`"${word}" is already in your list`, 'info');
            } else {
                this.showToast(data.error || 'Failed to add word', 'error');
            }
        } catch (error) {
            console.error('Error adding word:', error);
            this.showToast('Network error. Please try again.', 'error');
        }
    }

    highlightWord(word, event) {
        // Add a temporary highlight effect at the click position
        const highlight = document.createElement('div');
        highlight.className = 'word-added-indicator';
        highlight.textContent = '+';
        highlight.style.position = 'fixed';
        highlight.style.left = event.clientX + 'px';
        highlight.style.top = event.clientY + 'px';

        document.body.appendChild(highlight);

        setTimeout(() => {
            highlight.remove();
        }, 1000);
    }

    detectSource() {
        // Detect what part of the app the user is in
        const path = window.location.pathname;

        if (path.includes('/reading/practice/passage')) return 'reading_passage';
        if (path.includes('/reading/practice/paragraph')) return 'reading_paragraph';
        if (path.includes('/reading/practice/sentence')) return 'reading_sentence';
        if (path.includes('/reading/question-types')) return 'question_types';
        if (path.includes('/exercises/reading')) return 'reading_immersion';
        if (path.includes('/exercises/gap-fill')) return 'gap_fill';
        if (path.includes('/exercises/synonym')) return 'synonym_showdown';
        if (path.includes('/session')) return 'vocab_session';

        return 'unknown';
    }

    showToast(message, type = 'info') {
        // Remove any existing toasts
        const existingToast = document.querySelector('.unfamiliar-toast');
        if (existingToast) {
            existingToast.remove();
        }

        // Create toast notification
        const toast = document.createElement('div');
        toast.className = `unfamiliar-toast toast-${type}`;
        toast.textContent = message;

        document.body.appendChild(toast);

        // Animate in
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);

        // Remove after 3 seconds
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.unfamiliarWordsManager = new UnfamiliarWordsManager();
    });
} else {
    window.unfamiliarWordsManager = new UnfamiliarWordsManager();
}
