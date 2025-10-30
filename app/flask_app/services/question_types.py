"""Question Type Strategy Lab - TOEFL Reading Question Type Practice System."""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from flask import current_app

from .gemini_client import GeminiClient, get_gemini_client

# Question Type Metadata
QUESTION_TYPES = {
    # Category 1: Local Questions
    "factual": {
        "id": "factual",
        "name_en": "Factual Information",
        "name_cn": "事实信息题",
        "category": "local",
        "category_cn": "局部信息题",
        "description_cn": "定位并理解文中直接陈述的具体细节",
        "identification": "According to the passage..., It is stated that...",
        "strategy_title": "Locate & Match Method",
        "strategy_steps": [
            "找出问题中的关键词",
            "扫描文章，找到这些关键词",
            "仔细阅读周围的上下文",
            "将信息与正确选项匹配"
        ],
        "common_traps": [
            "选项可能是文章其他部分的真实陈述，但不回答这个具体问题",
            "混淆相似但不同的细节"
        ],
        "icon": "fa-search",
        "color": "teal"
    },
    "negative_factual": {
        "id": "negative_factual",
        "name_en": "Negative Factual Information",
        "name_cn": "事实否定信息题",
        "category": "local",
        "category_cn": "局部信息题",
        "description_cn": "识别哪条信息未被提及或不正确（排除法）",
        "identification": "Keywords: NOT, EXCEPT (all caps)",
        "strategy_title": "Find the Three Truths Method",
        "strategy_steps": [
            "将此题视为三个迷你事实题",
            "逐一检查每个选项，在文中确认是否被提及",
            "如果找到，说明它是错误答案，排除它",
            "无法在文中找到的那个选项就是正确答案"
        ],
        "common_traps": [
            "最大的陷阱是匆忙选择第一个找到的真实陈述，忘记了 'NOT' 条件",
            "混淆未提及和明确否定的信息"
        ],
        "icon": "fa-ban",
        "color": "rose"
    },
    "vocabulary": {
        "id": "vocabulary",
        "name_en": "Vocabulary-in-Context",
        "name_cn": "词汇题",
        "category": "local",
        "category_cn": "局部信息题",
        "description_cn": "从上下文推断单词的含义",
        "identification": "The word 'X' in the passage is closest in meaning to...",
        "strategy_title": "Substitution Method",
        "strategy_steps": [
            "定位目标单词",
            "阅读它所在的句子",
            "将四个选项逐一代入句子",
            "选择最能保持句子原意和逻辑的选项"
        ],
        "common_traps": [
            "'常见含义'陷阱：选项是该词的正确定义，但不是这个特定学术语境中使用的含义",
            "忽略上下文，仅凭词典意思选择"
        ],
        "icon": "fa-book",
        "color": "amber"
    },
    "reference": {
        "id": "reference",
        "name_en": "Reference",
        "name_cn": "指代题",
        "category": "local",
        "category_cn": "局部信息题",
        "description_cn": "识别代词或指代短语所指的对象",
        "identification": "The word 'X' in the passage refers to...",
        "strategy_title": "Look Back Method",
        "strategy_steps": [
            "定位代词",
            "先行词（它指代的名词）几乎总是出现在代词之前",
            "通常在同一句或紧接着的前一句",
            "将候选名词代入句子，看哪个在语法和逻辑上合理"
        ],
        "common_traps": [
            "选择距离更近但单复数不一致的名词",
            "忽略语法一致性（单复数、人称）"
        ],
        "icon": "fa-link",
        "color": "emerald"
    },
    # Category 2: Global Questions
    "inference": {
        "id": "inference",
        "name_en": "Inference",
        "name_cn": "推断题",
        "category": "global",
        "category_cn": "全局理解题",
        "description_cn": "理解隐含但未明确陈述的内容",
        "identification": "Keywords: infer, imply, suggest",
        "strategy_title": "What Must Be True Method",
        "strategy_steps": [
            "定位文中的相关信息",
            "理解其字面含义",
            "正确的推断是基于所提供事实的直接、合理结论",
            "不要做大幅度的逻辑跳跃"
        ],
        "common_traps": [
            "'极端推断'：选项可能为真但文中没有直接支持",
            "过度解读或添加文中未提及的信息"
        ],
        "icon": "fa-lightbulb",
        "color": "purple"
    },
    "rhetorical_purpose": {
        "id": "rhetorical_purpose",
        "name_en": "Rhetorical Purpose",
        "name_cn": "修辞目的题",
        "category": "global",
        "category_cn": "全局理解题",
        "description_cn": "理解作者为何包含某个特定信息",
        "identification": "Why does the author mention X?, The author discusses Y in order to...",
        "strategy_title": "Function, Not Fact Method",
        "strategy_steps": [
            "定位具体细节",
            "阅读其前一句，理解该段落这部分的主要观点",
            "问自己：'这个细节与主要观点有什么关系？'",
            "判断其功能：例子？对比？解释？"
        ],
        "common_traps": [
            "选择关于该细节的真实事实，但不能解释其在论证中的目的",
            "混淆内容和目的"
        ],
        "icon": "fa-question-circle",
        "color": "indigo"
    },
    "sentence_simplification": {
        "id": "sentence_simplification",
        "name_en": "Sentence Simplification",
        "name_cn": "句子简化题",
        "category": "global",
        "category_cn": "全局理解题",
        "description_cn": "识别最能重述复杂句核心含义的选项",
        "identification": "Which option best expresses the essential information...",
        "strategy_title": "Deconstruct & Eliminate Method",
        "strategy_steps": [
            "解构原句，找出主要的主语、动词、宾语（核心含义）",
            "识别其主要逻辑关系（如：因果关系）",
            "排除改变核心含义、遗漏关键部分或逻辑错误的选项"
        ],
        "common_traps": [
            "选择保留了所有细节但改变了主要意思的选项",
            "选择意思接近但逻辑关系错误的选项"
        ],
        "icon": "fa-compress",
        "color": "cyan"
    },
    "insert_text": {
        "id": "insert_text",
        "name_en": "Insert Text",
        "name_cn": "句子插入题",
        "category": "global",
        "category_cn": "全局理解题",
        "description_cn": "找到段落中插入新句子的最合理位置",
        "identification": "Place the sentence at one of the black squares [■]",
        "strategy_title": "Find the Clues Method",
        "strategy_steps": [
            "首先阅读要插入的句子",
            "寻找'线索词'：转折词（However, Therefore）或代词（this, these, they）",
            "这些线索告诉你前一句必须包含什么",
            "阅读每个方框周围的文本，找到逻辑和语法连接完美的唯一位置"
        ],
        "common_traps": [
            "仅基于话题相似性而非逻辑连接",
            "忽略代词和转折词的指示作用"
        ],
        "icon": "fa-level-down-alt",
        "color": "orange"
    },
    # Category 3: Passage-Level Questions
    "prose_summary": {
        "id": "prose_summary",
        "name_en": "Prose Summary",
        "name_cn": "文章内容小结题",
        "category": "passage",
        "category_cn": "篇章理解题",
        "description_cn": "识别整篇文章的主要观点",
        "identification": "Select 3 of 6 options to summarize the passage (final question)",
        "strategy_title": "Main Idea Filter Method",
        "strategy_steps": [
            "重读提供的主题句",
            "回忆整篇文章的主要观点",
            "逐一检查6个选项，积极排除：(a) 次要细节 (b) 事实错误 (c) 未提及",
            "剩余的3个选项应构成连贯的摘要"
        ],
        "common_traps": [
            "选择虽然正确但属于次要细节的选项",
            "选择过于笼统或过于具体的选项"
        ],
        "icon": "fa-list-ul",
        "color": "blue"
    },
    "fill_table": {
        "id": "fill_table",
        "name_en": "Fill in a Table",
        "name_cn": "表格题",
        "category": "passage",
        "category_cn": "篇章理解题",
        "description_cn": "将文章的主要观点和支持细节组织到类别中",
        "identification": "A table with 2-3 categories and answer choices",
        "strategy_title": "Categorize & Match Method",
        "strategy_steps": [
            "仔细阅读表格中的类别标题，理解每个类别应包含什么类型的信息",
            "阅读答案选项，将每个视为'迷你事实'",
            "对于每个选项，扫描文章定位它，并决定它属于哪个类别",
            "将选项拖放到正确的列中"
        ],
        "common_traps": [
            "虽然真实但根本不属于表格的次要细节",
            "将信息放入错误的类别"
        ],
        "icon": "fa-table",
        "color": "green"
    }
}

# System prompts for generating question type drills
QUESTION_TYPE_SYSTEM_PROMPT = """You are Gemini 2.5 Flash-Lite acting as an expert TOEFL Reading instructor specializing in question type strategies.

You will generate focused practice materials for specific TOEFL reading question types. Your materials must:
1. Follow the exact JSON schema provided
2. Create passages and questions that authentically replicate TOEFL difficulty and style
3. Provide detailed strategic analysis in Simplified Chinese
4. Design distractors that represent common mistakes students make for this question type
5. Return strict JSON only, no markdown fences

CRITICAL REQUIREMENT: You MUST generate exactly 5 questions. No more, no less. If you generate fewer than 5 questions, the system will fail and you will need to try again. Always count your questions before responding to ensure there are exactly 5."""


def _calculate_backoff_time(attempt: int, is_rate_limit: bool = False) -> float:
    """Calculate exponential backoff time with special handling for rate limits."""
    base_backoff = 2 ** attempt
    multiplier = 3 if is_rate_limit else 1
    return base_backoff * multiplier


def generate_question_type_drill(
    question_type_id: str,
    client: Optional[GeminiClient] = None,
    max_retries: int = 2
) -> Optional[Dict[str, Any]]:
    """Generate a focused drill for a specific question type.

    Args:
        question_type_id: The ID of the question type (e.g., 'factual', 'inference')
        client: Optional GeminiClient instance
        max_retries: Number of retries on failure

    Returns:
        Dictionary containing passage and questions, or None on failure
    """
    client = client or get_gemini_client()

    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured - cannot generate question type drill")
        return None

    if question_type_id not in QUESTION_TYPES:
        current_app.logger.error(f"Unknown question type: {question_type_id}")
        return None

    q_type = QUESTION_TYPES[question_type_id]

    # Build type-specific prompt
    prompt = _build_question_type_prompt(question_type_id, q_type)

    # Retry logic with exponential backoff
    for attempt in range(max_retries + 1):
        try:
            payload = client.generate_json(
                prompt,
                temperature=0.7,
                system_instruction=QUESTION_TYPE_SYSTEM_PROMPT,
                max_output_tokens=8192,
            )

            # Log what we received for debugging
            if payload is None:
                current_app.logger.error(
                    f"Gemini returned None for '{question_type_id}' on attempt {attempt + 1}. "
                    f"Possible causes: API error, JSON parsing failure, or empty response."
                )
            elif isinstance(payload, dict):
                num_questions = len(payload.get('questions', []))
                current_app.logger.info(f"Gemini returned {num_questions} questions for '{question_type_id}'")
            else:
                current_app.logger.error(f"Gemini returned non-dict payload: {type(payload)}")

            if isinstance(payload, dict) and _validate_drill_payload(payload, question_type_id):
                current_app.logger.info(
                    f"Question type drill generation for '{question_type_id}' succeeded on attempt {attempt + 1}"
                )
                # Add metadata
                payload['question_type_id'] = question_type_id
                payload['question_type_meta'] = q_type
                return payload

            if attempt < max_retries:
                backoff_time = _calculate_backoff_time(attempt, is_rate_limit=False)
                current_app.logger.warning(
                    f"Question type drill for '{question_type_id}' returned invalid data on attempt {attempt + 1}, "
                    f"retrying in {backoff_time}s..."
                )
                time.sleep(backoff_time)
            else:
                current_app.logger.error(
                    f"Question type drill for '{question_type_id}' failed after {max_retries + 1} attempts. "
                    f"Last payload had {len(payload.get('questions', [])) if isinstance(payload, dict) else 0} questions"
                )

        except Exception as exc:
            if attempt < max_retries:
                is_rate_limit = "429" in str(exc) or "Too Many Requests" in str(exc)
                backoff_time = _calculate_backoff_time(attempt, is_rate_limit=is_rate_limit)
                current_app.logger.warning(
                    f"Question type drill attempt {attempt + 1} failed: {exc}, "
                    f"retrying in {backoff_time}s..."
                )
                time.sleep(backoff_time)
            else:
                current_app.logger.error(
                    f"Question type drill for '{question_type_id}' failed after {max_retries + 1} attempts: {exc}"
                )

    return None


def _build_question_type_prompt(question_type_id: str, q_type: Dict[str, Any]) -> str:
    """Build a specialized prompt for generating a specific question type drill."""

    base_prompt = f"""Generate a focused TOEFL reading practice drill for the "{q_type['name_en']}" ({q_type['name_cn']}) question type.

Question Type Details:
- Identification: {q_type['identification']}
- Strategy: {q_type['strategy_title']}
- Common Traps: {', '.join(q_type['common_traps'])}

*** CRITICAL REQUIREMENT: You MUST generate EXACTLY 5 questions. Not 3, not 4, but EXACTLY 5 questions. ***

Generate:
1. One academic passage (350-450 words) on a TOEFL-appropriate topic with multiple paragraphs
2. EXACTLY FIVE (5) distinct questions of this specific type with 4 options each
3. For each question, provide:
   - Strategic analysis (策略分析) in Simplified Chinese explaining how to apply the strategy
   - Brief explanation for why each distractor is wrong
   - Text evidence location (which paragraph/sentence)

IMPORTANT: Generate exactly 5 questions. Each question should test different parts of the passage. Count your questions before responding to ensure there are 5.

"""

    # Type-specific instructions
    type_instructions = {
        "factual": """
For Factual Information questions:
- Questions should ask about specific details explicitly stated in the passage
- Use phrases like "According to the passage..." or "The passage states that..."
- Distractors should be plausible but factually incorrect or from different parts of the passage
- Strategy analysis should emphasize the "Locate & Match" method""",

        "negative_factual": """
For Negative Factual questions:
- Use "NOT" or "EXCEPT" in all caps in the question
- Three options must be supported by the passage, one must not be mentioned or be incorrect
- Strategy analysis should emphasize the elimination process
- Show how to confirm each true statement in the passage""",

        "vocabulary": """
For Vocabulary-in-Context questions:
- Choose words that have multiple meanings or academic usage
- Include the sentence context in the question
- Distractors should include: (1) common dictionary meaning, (2) similar but wrong meaning
- Strategy analysis should show the substitution method""",

        "reference": """
For Reference questions:
- Use pronouns like "it", "they", "this", "these", "such"
- Antecedent should be in preceding sentence or same sentence
- Distractors should include nearby nouns that don't agree in number/logic
- Strategy analysis should demonstrate the "Look Back" method""",

        "inference": """
For Inference questions:
- Use "infer", "imply", or "suggest" in the question
- Correct answer must be logically derivable but not explicitly stated
- Distractors should include: (1) too extreme, (2) contradicts passage, (3) beyond text
- Strategy analysis should show the logical connection from text to inference""",

        "rhetorical_purpose": """
For Rhetorical Purpose questions:
- Ask "Why does the author mention X?" or "The author discusses Y in order to..."
- Correct answer should describe the function (example, contrast, explanation)
- Distractors should describe content rather than purpose
- Strategy analysis should connect the detail to the main point""",

        "sentence_simplification": """
For Sentence Simplification questions:
- Original sentence should be 25-35 words with complex structure
- Correct answer preserves core meaning and logical relationships
- Distractors should: (1) change meaning, (2) omit key info, (3) alter logic
- Strategy analysis should identify the core components (subject, verb, object, logic)""",

        "insert_text": """
For Insert Text questions:
- Provide a sentence to insert with clear transitional or referential clues
- Four possible positions [■] in the paragraph
- Only one position should make logical and grammatical sense
- Strategy analysis should identify the clue words and their connections""",

        "prose_summary": """
For Prose Summary questions:
- Provide 6 statements: 3 are main ideas, 3 are minor details/incorrect
- User must select the 3 main ideas
- Strategy analysis should explain how to distinguish main ideas from details
- Show the hierarchical structure of the passage
- JSON schema for prose_summary is DIFFERENT: use "options" (6 items) and "correct_answers" (array of 3 correct options)""",

        "fill_table": """
For Fill in a Table questions:
- Create 2-3 categories based on the passage structure
- Provide 5-7 answer choices: some belong in categories, some don't belong at all
- Strategy analysis should explain category criteria
- Show how to match information to categories
- JSON schema for fill_table is DIFFERENT: use "categories" (list of category objects) and "answer_choices" (list of statements)"""
    }

    prompt = base_prompt + type_instructions.get(question_type_id, "")

    # Add JSON schema - different for special question types
    if question_type_id == "prose_summary":
        prompt += """

Return STRICT JSON with this schema for PROSE SUMMARY (must include 5 questions):
{
  "passage": "The full passage text...",
  "topic": "Brief topic description",
  "questions": [
    {
      "question_text": "An introductory sentence for a summary...",
      "options": ["Option 1", "Option 2", "Option 3", "Option 4", "Option 5", "Option 6"],
      "correct_answers": ["Option 1", "Option 3", "Option 5"],
      "strategy_analysis_cn": "如何区分主要观点和次要细节...",
      "distractor_explanations": {
        "Option 2": "为什么这是次要细节...",
        "Option 4": "为什么这是次要细节...",
        "Option 6": "为什么这是次要细节..."
      }
    },"""
    elif question_type_id == "fill_table":
        prompt += """

Return STRICT JSON with this schema for FILL TABLE (must include 5 questions):
{
  "passage": "The full passage text...",
  "topic": "Brief topic description",
  "questions": [
    {
      "question_text": "Complete the table below...",
      "categories": [
        {"name": "Category 1", "correct_choices": ["Choice A", "Choice C"]},
        {"name": "Category 2", "correct_choices": ["Choice B", "Choice D"]}
      ],
      "answer_choices": ["Choice A", "Choice B", "Choice C", "Choice D", "Choice E", "Choice F", "Choice G"],
      "strategy_analysis_cn": "如何区分类别和匹配信息...",
      "category_explanations": {
        "Category 1": "这个类别的特征...",
        "Category 2": "这个类别的特征..."
      }
    },"""
    else:
        # Standard 4-option format
        prompt += """

Return STRICT JSON with this schema (must include 5 questions):
{
  "passage": "The full passage text...",
  "topic": "Brief topic description",
  "questions": [
    {
      "question_text": "First question...",
      "options": ["A...", "B...", "C...", "D..."],
      "correct_answer": "A...",
      "strategy_analysis_cn": "如何应用策略的详细分析...",
      "text_evidence": "Paragraph 1",
      "distractor_explanations": {
        "B...": "为什么这个选项错误...",
        "C...": "为什么这个选项错误...",
        "D...": "为什么这个选项错误..."
      }
    },
    {
      "question_text": "Second question...",
      "options": ["A...", "B...", "C...", "D..."],
      "correct_answer": "B...",
      "strategy_analysis_cn": "策略分析...",
      "text_evidence": "Paragraph 2",
      "distractor_explanations": {
        "A...": "错误原因...",
        "C...": "错误原因...",
        "D...": "错误原因..."
      }
    },
    {
      "question_text": "Third question...",
      "options": ["A...", "B...", "C...", "D..."],
      "correct_answer": "C...",
      "strategy_analysis_cn": "策略分析...",
      "text_evidence": "Paragraph 3",
      "distractor_explanations": {
        "A...": "错误原因...",
        "B...": "错误原因...",
        "D...": "错误原因..."
      }
    },
    {
      "question_text": "Fourth question...",
      "options": ["A...", "B...", "C...", "D..."],
      "correct_answer": "D...",
      "strategy_analysis_cn": "策略分析...",
      "text_evidence": "Paragraph 4",
      "distractor_explanations": {
        "A...": "错误原因...",
        "B...": "错误原因...",
        "C...": "错误原因..."
      }
    },
    {
      "question_text": "Fifth question...",
      "options": ["A...", "B...", "C...", "D..."],
      "correct_answer": "A...",
      "strategy_analysis_cn": "策略分析...",
      "text_evidence": "Paragraph 5",
      "distractor_explanations": {
        "B...": "错误原因...",
        "C...": "错误原因...",
        "D...": "错误原因..."
      }
    }
  ]
}

*** CRITICAL REQUIREMENTS ***:
1. The questions array MUST contain EXACTLY 5 question objects (not 3, not 4, but EXACTLY 5)
2. Return only the JSON object, no markdown fences or additional text
3. Before you respond, count the questions in your JSON to verify there are exactly 5
4. If you generate fewer than 5 questions, the entire response will be rejected and you'll need to regenerate

DO NOT FORGET: You must generate EXACTLY 5 questions. This is not optional."""

    return prompt


def _validate_drill_payload(payload: Dict[str, Any], question_type_id: str) -> bool:
    """Validate that the generated drill has all required fields."""
    if not isinstance(payload, dict):
        current_app.logger.error(f"Validation failed: payload is not a dict")
        return False

    if "passage" not in payload or not payload["passage"]:
        current_app.logger.error(f"Validation failed: missing or empty passage")
        return False

    if "questions" not in payload or not isinstance(payload["questions"], list):
        current_app.logger.error(f"Validation failed: missing or invalid questions list")
        return False

    num_questions = len(payload["questions"])
    if num_questions < 5:
        current_app.logger.error(f"Validation failed: only {num_questions} questions (need exactly 5)")
        return False

    # Validate each question
    for idx, q in enumerate(payload["questions"]):
        if not isinstance(q, dict):
            current_app.logger.error(f"Validation failed: question {idx} is not a dict")
            return False

        # Different question types have different structures
        if question_type_id == "prose_summary":
            # Prose summary questions have 6 options (choose 3)
            if "options" not in q or not isinstance(q["options"], list) or len(q["options"]) != 6:
                current_app.logger.error(f"Validation failed: prose_summary question {idx} needs 6 options")
                return False
            if "correct_answers" not in q or not isinstance(q["correct_answers"], list) or len(q["correct_answers"]) != 3:
                current_app.logger.error(f"Validation failed: prose_summary question {idx} needs 3 correct answers")
                return False
        elif question_type_id == "fill_table":
            # Fill table questions have categories and answer choices
            if "categories" not in q or not isinstance(q["categories"], list):
                current_app.logger.error(f"Validation failed: fill_table question {idx} needs categories")
                return False
            if "answer_choices" not in q or not isinstance(q["answer_choices"], list):
                current_app.logger.error(f"Validation failed: fill_table question {idx} needs answer_choices")
                return False
        else:
            # Standard 4-option questions
            required_fields = ["question_text", "options", "correct_answer"]
            if not all(field in q for field in required_fields):
                current_app.logger.error(f"Validation failed: question {idx} missing required fields")
                return False
            if not isinstance(q["options"], list) or len(q["options"]) != 4:
                current_app.logger.error(f"Validation failed: question {idx} has invalid options (need 4, got {len(q['options']) if isinstance(q.get('options'), list) else 'N/A'})")
                return False

    return True


def get_question_types_by_category() -> List[Dict[str, Any]]:
    """Get all question types organized by category.

    Returns a list of category objects with name, description, and types.
    """
    # Category metadata
    category_info = {
        "local": {
            "name_en": "Local Questions",
            "name_cn": "局部信息题",
            "description": "Focus on specific information within the passage"
        },
        "global": {
            "name_en": "Global Questions",
            "name_cn": "全局理解题",
            "description": "Require understanding connections and broader context"
        },
        "passage": {
            "name_en": "Passage-Level Questions",
            "name_cn": "篇章理解题",
            "description": "Test holistic understanding of entire passage"
        }
    }

    # Organize question types by category
    categories_dict = {
        "local": [],
        "global": [],
        "passage": []
    }

    for q_id, q_data in QUESTION_TYPES.items():
        category = q_data.get("category", "local")
        if category in categories_dict:
            categories_dict[category].append({
                "id": q_id,
                **q_data
            })

    # Convert to list format expected by template
    result = []
    for cat_key in ["local", "global", "passage"]:
        if cat_key in category_info and categories_dict[cat_key]:
            result.append({
                "category_key": cat_key,
                "name_en": category_info[cat_key]["name_en"],
                "name_cn": category_info[cat_key]["name_cn"],
                "description": category_info[cat_key]["description"],
                "types": categories_dict[cat_key]
            })

    return result


def get_question_type_metadata(question_type_id: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific question type."""
    return QUESTION_TYPES.get(question_type_id)
