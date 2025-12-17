"""
Image OCR and essay analysis service.
Extracts text from handwritten essay images and analyzes content.
"""
from __future__ import annotations

import base64
import os
import re
from typing import Dict, Optional, Tuple
from pathlib import Path
from uuid import uuid4

from flask import current_app
import requests

from .gemini_client import get_gemini_client


class ImageAnalyzer:
    """Analyze handwritten essay images and extract text."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_gemini_client()
        return self._client

    def analyze_essay_image(
        self,
        image_path: str,
        task_type: str = 'independent',
        topic: str = ''
    ) -> Dict:
        """
        Extract text from essay image and assess image quality.

        Args:
            image_path: Path to uploaded image file
            task_type: 'integrated' or 'independent' or 'discussion'
            topic: The essay topic/prompt for context

        Returns:
            {
                'success': bool,
                'extracted_text': str,          # OCR text extraction
                'ocr_confidence': float,        # 0-1 confidence score
                'image_quality': str,           # 'excellent', 'good', 'fair', 'poor'
                'legibility_score': float,      # 0-1
                'analysis': str,                # AI assessment of image
                'recommendations': [str],       # Suggestions for user
                'error': str or None           # Error message if failed
            }
        """
        if not os.path.exists(image_path):
            return {
                'success': False,
                'error': f'Image file not found: {image_path}',
                'extracted_text': '',
                'ocr_confidence': 0.0
            }

        # Read and encode image
        try:
            with open(image_path, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')
        except Exception as e:
            current_app.logger.error(f"Failed to read image: {e}")
            return {
                'success': False,
                'error': f'Failed to read image: {str(e)}',
                'extracted_text': '',
                'ocr_confidence': 0.0
            }

        # Determine image MIME type
        mime_type = self._get_mime_type(image_path)

        # Extract text via Gemini Vision API
        extraction_result = self._extract_text_with_gemini(image_data, mime_type, topic)

        if not extraction_result['success']:
            return extraction_result

        # Assess image quality
        quality_assessment = self._assess_image_quality(
            image_data,
            mime_type,
            extraction_result['extracted_text']
        )

        return {
            'success': True,
            'extracted_text': extraction_result['extracted_text'],
            'ocr_confidence': extraction_result['confidence'],
            'image_quality': quality_assessment['quality'],
            'legibility_score': quality_assessment['legibility_score'],
            'analysis': quality_assessment['analysis'],
            'recommendations': quality_assessment['recommendations'],
            'error': None
        }

    def _get_mime_type(self, file_path: str) -> str:
        """Determine MIME type from file extension."""
        ext = Path(file_path).suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.pdf': 'application/pdf'
        }
        return mime_types.get(ext, 'image/jpeg')

    def _extract_text_with_gemini(
        self,
        image_data: str,
        mime_type: str,
        topic: str = ''
    ) -> Dict:
        """Extract text from image using Gemini Vision API."""
        if not self.client or not self.client.is_configured:
            return {
                'success': False,
                'error': 'Gemini API not configured',
                'extracted_text': '',
                'confidence': 0.0
            }

        topic_context = f"\n\nCONTEXT: The essay topic is: {topic}" if topic else ""

        prompt = f"""You are an expert at reading handwritten essays and extracting text.

TASK: Carefully read the handwritten essay in this image and extract ALL the text.{topic_context}

REQUIREMENTS:
1. Extract the COMPLETE text from the handwritten essay
2. Preserve line breaks and paragraph structure where visible
3. For illegible words, indicate with [ILLEGIBLE] or best guess with [?word?]
4. Do NOT add any commentary, just the pure text
5. Preserve all punctuation and formatting
6. Correct any obvious spelling mistakes while preserving the author's intent
7. Fix any grammar mistakes (capitalization, punctuation, etc.)

After extraction, provide a JSON response with:
{{
    "extracted_text": "full extracted text here",
    "confidence": 0.95,
    "illegible_words_count": 2,
    "corrections_made": ["list of corrections made"],
    "notes": "any relevant notes about handwriting clarity"
}}"""

        try:
            # Use Gemini Vision API directly via generateContent
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": image_data
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.1,  # Low temperature for accuracy
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 8192
                }
            }

            # Call API
            api_key = self.client.api_key
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}"

            response = requests.post(
                api_url,
                json=payload,
                timeout=60
            )

            if response.status_code != 200:
                current_app.logger.error(f"Gemini Vision API error: {response.text}")
                return {
                    'success': False,
                    'error': f'Vision API error: {response.status_code}',
                    'extracted_text': '',
                    'confidence': 0.0
                }

            result = response.json()

            # Parse response
            if 'candidates' in result and result['candidates']:
                content = result['candidates'][0]['content']['parts'][0]['text']

                # Try to parse JSON
                import json
                try:
                    parsed = json.loads(content)
                    extracted_text = parsed.get('extracted_text', '')
                    corrections = parsed.get('corrections_made', [])

                    # Log corrections made
                    if corrections:
                        current_app.logger.info(f"OCR corrections made: {corrections}")

                    return {
                        'success': True,
                        'extracted_text': extracted_text,
                        'confidence': parsed.get('confidence', 0.7),
                        'corrections_made': corrections
                    }
                except json.JSONDecodeError:
                    # Fallback: return raw text
                    return {
                        'success': True,
                        'extracted_text': content,
                        'confidence': 0.6,
                        'corrections_made': []
                    }

            return {
                'success': False,
                'error': 'No content in API response',
                'extracted_text': '',
                'confidence': 0.0
            }

        except Exception as e:
            current_app.logger.error(f"Vision API call failed: {e}")
            return {
                'success': False,
                'error': f'Vision API failed: {str(e)}',
                'extracted_text': '',
                'confidence': 0.0
            }

    def _assess_image_quality(
        self,
        image_data: str,
        mime_type: str,
        extracted_text: str
    ) -> Dict:
        """Assess handwriting legibility and image quality."""
        if not self.client or not self.client.is_configured:
            return {
                'quality': 'unknown',
                'legibility_score': 0.5,
                'analysis': 'Could not assess image quality',
                'recommendations': []
            }

        prompt = f"""Analyze the handwriting legibility and image quality in this essay image.

Evaluate:
1. Handwriting legibility (clear vs. messy)
2. Image brightness and contrast
3. Whether image is straight or tilted
4. Overall readability
5. Estimated percentage of text that can be confidently read

Provide JSON response:
{{
    "legibility_score": 0.85,  # 0-1, how clear the handwriting is
    "image_quality": "good",   # excellent/good/fair/poor
    "brightness": "adequate",  # too_dark/adequate/too_bright
    "contrast": "good",        # low/adequate/good
    "tilt_angle": 0,           # degrees from horizontal
    "readable_percentage": 95, # % of text estimated readable
    "analysis": "Clear, neat handwriting with good contrast. Easy to read.",
    "recommendations": ["Ensure lighting is bright", "Keep image straight"]
}}"""

        try:
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": image_data
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 1024
                }
            }

            api_key = self.client.api_key
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}"

            response = requests.post(
                api_url,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    content = result['candidates'][0]['content']['parts'][0]['text']
                    try:
                        import json
                        parsed = json.loads(content)
                        return {
                            'quality': parsed.get('image_quality', 'unknown'),
                            'legibility_score': parsed.get('legibility_score', 0.5),
                            'analysis': parsed.get('analysis', 'Unable to assess'),
                            'recommendations': parsed.get('recommendations', [])
                        }
                    except:
                        pass

            # Fallback based on extracted text length
            if extracted_text and len(extracted_text.strip()) > 50:
                return {
                    'quality': 'good',
                    'legibility_score': 0.75,
                    'analysis': 'Image appears readable',
                    'recommendations': []
                }

            return {
                'quality': 'fair',
                'legibility_score': 0.5,
                'analysis': 'Image quality is marginal',
                'recommendations': ['Try uploading a clearer image']
            }

        except Exception as e:
            current_app.logger.error(f"Quality assessment failed: {e}")
            return {
                'quality': 'unknown',
                'legibility_score': 0.5,
                'analysis': 'Could not assess image quality',
                'recommendations': []
            }


def get_image_analyzer() -> ImageAnalyzer:
    """Singleton getter for image analyzer."""
    if not hasattr(current_app, 'image_analyzer'):
        current_app.image_analyzer = ImageAnalyzer()
    return current_app.image_analyzer
