import sys
from pathlib import Path

import pytest
from flask import Flask

# Ensure repository root is importable when pytest changes working dir
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.flask_app.services.writing_analyzer import WritingAnalyzer


@pytest.fixture(autouse=True)
def app_context():
    app = Flask(__name__)
    with app.app_context():
        yield


def test_normalize_feedback_handles_nested_integrated_payload():
    analyzer = WritingAnalyzer()
    raw_feedback = {
        "scores": {
            "overall_score_5": "4.5",
            "content_development": "4",
            "organization": 3,
            "vocabulary": "3.5",
            "grammar": None,
        },
        "annotations": [
            {
                "type": "Task",
                "text": "targeted campaigns",
                "comment": "Lecture never mentions campaigns.",
                "start_index": "0",
                "end_index": 18,
            },
            {
                "type": "grammar",
                "text": "",
                "comment": "Skip - missing text.",
                "start_index": 5,
                "end_index": 5,
            },
        ],
        "overall_feedback": {"coach_summary": {"text": "Focused revision on lecture details."}},
        "feedback": {
            "positives": ["Clear thesis", {"text": "Logical transitions"}],
            "areas_for_improvement": ["Tighten source summary", "Quote accurately"],
            "grammar_notes": [{"text": "Subject-verb agreement"}],
            "lexical_suggestions": "Use more academic verbs; Avoid repetition",
            "structure_notes": None,
            "content_notes": "",
        },
        "content_accuracy": {
            "content_accuracy": "Captures lecture stance but misses one refutation.",
            "point_coverage": [
                {"text": "Point 1: Inefficient funding - Addressed"},
                "Point 2: Volunteer retention - Missing detail",
            ],
            "example_accuracy": "Misquotes the retention statistic.",
            "paraphrase_quality": "Mostly paraphrased with occasional copying.",
            "source_integration": "Links reading and lecture but reverses one causal claim.",
        },
    }

    normalized = analyzer._normalize_feedback(raw_feedback, task_type="integrated")

    assert normalized["overall_score"] == pytest.approx(18.0)
    assert normalized["content_development_score"] == pytest.approx(3.0)
    assert normalized["annotations"] == [
        {
            "type": "task",
            "text": "targeted campaigns",
            "comment": "Lecture never mentions campaigns.",
            "start_index": 0,
            "end_index": 18,
        }
    ]
    assert normalized["coach_summary"] == "Focused revision on lecture details."
    assert normalized["strengths"] == ["Clear thesis", "Logical transitions"]
    assert normalized["improvements"] == ["Tighten source summary", "Quote accurately"]
    assert normalized["grammar_issues"] == ["Subject-verb agreement"]
    assert normalized["vocabulary_suggestions"] == ["Use more academic verbs", "Avoid repetition"]
    assert normalized["content_accuracy"] == "Captures lecture stance but misses one refutation."
    assert normalized["point_coverage"] == [
        "Point 1: Inefficient funding - Addressed",
        "Point 2: Volunteer retention - Missing detail",
    ]
    assert normalized["example_accuracy"] == "Misquotes the retention statistic."
    assert normalized["paraphrase_quality"] == "Mostly paraphrased with occasional copying."
    assert normalized["source_integration"] == "Links reading and lecture but reverses one causal claim."


def test_normalize_feedback_discussion_defaults_and_strings():
    analyzer = WritingAnalyzer()
    raw_feedback = {
        "score_breakdown": {
            "overall_score_5": "NaN",
            "content_development": None,
            "organization": "bad data",
            "vocabulary": 0,
            "grammar": "2",
        },
        "annotations": "[]",
        "coach_summary": "  ",
        "strengths": "Strong intro\nClear conclusion",
        "improvements": "",
        "grammar_issues": None,
        "vocabulary_suggestions": "[\"Vary adjectives\"]",
        "organization_notes": ["Add topic sentences"],
        "content_suggestions": ["Provide concrete examples"],
    }

    normalized = analyzer._normalize_feedback(raw_feedback, task_type="discussion")

    assert normalized["overall_score"] == 0.0
    assert normalized["content_development_score"] == 0.0
    assert normalized["organization_structure_score"] == 0.0
    assert normalized["vocabulary_language_score"] == 0.0
    assert normalized["grammar_mechanics_score"] == pytest.approx(2.0)
    assert normalized["annotations"] == []
    assert normalized["coach_summary"] == ""
    assert normalized["strengths"] == ["Strong intro", "Clear conclusion"]
    assert normalized["improvements"] == []
    assert normalized["grammar_issues"] == []
    assert normalized["vocabulary_suggestions"] == ["Vary adjectives"]
    assert normalized["organization_notes"] == ["Add topic sentences"]
    assert normalized["content_suggestions"] == ["Provide concrete examples"]
    assert normalized["content_accuracy"] is None
    assert normalized["point_coverage"] == []
    assert normalized["example_accuracy"] is None
    assert normalized["paraphrase_quality"] is None
    assert normalized["source_integration"] is None


def test_normalize_feedback_discussion_maps_specific_fields():
    analyzer = WritingAnalyzer()
    raw_feedback = {
        "scores": {
            "overall_score_5": 3.5,
            "content_development": 3,
            "organization": 3,
            "vocabulary": 3,
            "grammar": 3,
        },
        "thread_alignment": "Directly answers the professor but overlooks the final question.",
        "participant_references": [
            "Mentions Alex's concern about lab space.",
            "Fails to address Priya's funding idea.",
        ],
        "new_contribution": "Suggests creating a shared booking app but lacks detail.",
        "tone_style": "Tone is collaborative but slips into casual phrasing.",
        "evidence_precision": "Examples are general and need concrete data.",
    }

    normalized = analyzer._normalize_feedback(raw_feedback, task_type="discussion")

    assert normalized["content_accuracy"] == "Directly answers the professor but overlooks the final question."
    assert normalized["point_coverage"] == [
        "Mentions Alex's concern about lab space.",
        "Fails to address Priya's funding idea.",
    ]
    assert normalized["example_accuracy"] == "Suggests creating a shared booking app but lacks detail."
    assert normalized["paraphrase_quality"] == "Tone is collaborative but slips into casual phrasing."
    assert normalized["source_integration"] == "Examples are general and need concrete data."


def test_apply_score_strictness_penalizes_off_topic_integrated():
    analyzer = WritingAnalyzer()
    raw_feedback = {
        "scores": {
            "overall_score_5": 4.5,
            "content_development": 4.0,
            "organization": 4.0,
            "vocabulary": 4.0,
            "grammar": 4.0,
        },
        "annotations": [
            {
                "type": "task",
                "text": "this essay",
                "comment": "Off-topic relative to lecture.",
                "start_index": 0,
                "end_index": 20,
            },
            {
                "type": "task",
                "text": "irrelevant example",
                "comment": "Does not match lecture evidence.",
                "start_index": 40,
                "end_index": 60,
            },
        ],
        "coach_summary": "The response is mostly off-topic and not relevant to the lecture.",
        "improvements": [
            "Address the professor's points; current essay is irrelevant.",
            "Reference the lecture's evidence instead of fabricated examples.",
        ],
        "content_accuracy": "Essay is off-topic and fails to address professor's arguments.",
        "point_coverage": [
            "Point 1: Climate data - Missing",
            "Point 2: Mitigation evidence - Not addressed",
        ],
    }

    normalized = analyzer._normalize_feedback(raw_feedback, task_type="integrated")

    assert normalized["content_development_score"] <= 1.0
    assert normalized["overall_score"] <= 6.0
    assert normalized["organization_structure_score"] <= 1.0


def test_apply_score_strictness_penalizes_discussion_that_ignores_classmates():
    analyzer = WritingAnalyzer()
    raw_feedback = {
        "scores": {
            "overall_score_5": 4.0,
            "content_development": 4.0,
            "organization": 4.0,
            "vocabulary": 4.0,
            "grammar": 4.0,
        },
        "annotations": [
            {
                "type": "task",
                "text": "response",
                "comment": "Does not engage with classmates.",
                "start_index": 0,
                "end_index": 8,
            },
            {
                "type": "task",
                "text": "new idea",
                "comment": "Fails to add new perspective.",
                "start_index": 10,
                "end_index": 18,
            },
        ],
        "coach_summary": "Off-topic response that ignores classmates and repeats the question.",
        "improvements": [
            "Address the professor and classmates directly; current post is irrelevant.",
            "Introduce a new idea instead of repeating the prompt.",
        ],
        "content_suggestions": [
            "No reference to classmates' arguments.",
        ],
        "organization_notes": [
            "Fails to connect to the discussion thread.",
        ],
        "strengths": [],
    }

    normalized = analyzer._normalize_feedback(raw_feedback, task_type="discussion")

    assert normalized["content_development_score"] <= 1.5
    assert normalized["overall_score"] <= analyzer._convert_to_30_scale(1.5)
    assert normalized["organization_structure_score"] <= 2.0
