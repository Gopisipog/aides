import os
import json
import random
from openai import OpenAI


class ProactiveLearningEngine:
    """Generates questions and action items from YouTube video content with cross-video insights."""

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.insights_path = "data/processed/video_insights.json"
        self._load_or_initialize_insights()

    def _load_or_initialize_insights(self):
        """Load existing video insights or initialize new file."""
        if os.path.exists(self.insights_path):
            with open(self.insights_path, "r") as f:
                self.insights = json.load(f)
        else:
            self.insights = {
                "videos": {},
                "cross_video_themes": [],
                "expert_patterns": [],
            }
            self._save_insights()

    def _save_insights(self):
        """Save video insights to file."""
        os.makedirs(os.path.dirname(self.insights_path), exist_ok=True)
        with open(self.insights_path, "w") as f:
            json.dump(self.insights, f, indent=2)

    def extract_cross_video_patterns(self, nodes, relationships, corpus_segments):
        """Extract patterns that connect to other leadership YouTube content."""
        if not self.client:
            return self._default_patterns()

        nodes_summary = "\n".join([f"- {n['name']} ({n['type']})" for n in nodes])
        rels_summary = "\n".join(
            [
                f"- {r.get('from_node', '')} --[{r['relation']}]--> {r.get('to_node', '')}"
                for r in relationships
            ]
        )

        transcript_excerpts = "\n".join(
            [
                f"- [{s['start_time']:.1f}s] {s['transcript'][:200]}"
                for s in corpus_segments[:8]
            ]
        )

        prompt = f"""
Analyze this YouTube leadership video and identify cross-video patterns that connect to OTHER leadership YouTube content.

**Current Video Knowledge Graph:**
Nodes: {nodes_summary}
Relationships: {rels_summary}

**Transcript Excerpts:**
{transcript_excerpts}

Based on your knowledge of popular leadership YouTube content (like TED talks, leadership channels, etc.), identify:

1. **Cross-Video Themes**: How do these concepts connect to themes discussed in OTHER leadership YouTube videos?
2. **Expert Patterns**: What patterns from other leadership YouTubers (Simon Sinek, Brené Brown, etc.) align with this content?
3. **Common Discussions**: What do other YouTube leadership content creators say about these topics?
4. **Differing Views**: What alternative perspectives do other YouTube leaders present on these concepts?

Return JSON:
{{
    "cross_video_themes": [
        {{
            "theme": "Theme name",
            "other_content_reference": "What other YouTube leadership content says about this",
            "connection_explanation": "How it connects to this video"
        }}
    ],
    "expert_patterns": [
        {{
            "expert": "Expert name (e.g., Simon Sinek, Brené Brown)",
            "pattern": "What they teach that aligns",
            "video_connection": "How it relates to this content"
        }}
    ],
    "alternative_views": [
        {{
            "view": "Alternative perspective from other YouTube content",
            "source_context": "The context where this view is commonly discussed"
        }}
    ]
}}

Return ONLY valid JSON.
"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a leadership content analyst with knowledge of YouTube leadership content.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            return json.loads(content)
        except Exception as e:
            print(f"Error extracting patterns: {e}")
            return self._default_patterns()

    def _default_patterns(self):
        """Fallback patterns if LLM fails."""
        return {
            "cross_video_themes": [
                {
                    "theme": "Leadership Impact",
                    "other_content_reference": "Many leadership YouTubers emphasize the compound effect of small actions",
                    "connection_explanation": "This video's 'lollipop moments' aligns with this broader theme",
                }
            ],
            "expert_patterns": [
                {
                    "expert": "Leadership Experts",
                    "pattern": "Leadership is about influence, not authority",
                    "video_connection": "Connected to redefining leadership concept",
                }
            ],
            "alternative_views": [
                {
                    "view": "Some argue leadership cannot be taught, only learned through experience",
                    "source_context": "Debates in leadership development YouTube content",
                }
            ],
        }

    def generate_questions(
        self, nodes, relationships, corpus_segments, num_questions=5
    ):
        """Generate reflective questions specific to the YouTube video with cross-video bias."""
        if not corpus_segments:
            return self._default_questions(nodes)

        if not self.client:
            return self._default_questions(nodes)

        nodes_summary = "\n".join([f"- {n['name']} ({n['type']})" for n in nodes])
        rels_summary = "\n".join(
            [
                f"- {r.get('from_node', '')} --[{r['relation']}]--> {r.get('to_node', '')}"
                for r in relationships
            ]
        )

        transcript_excerpts = "\n".join(
            [
                f"- [{s['start_time']:.1f}s] {s['transcript'][:200]}..."
                for s in corpus_segments[:10]
            ]
        )

        # Get cross-video patterns
        patterns = self.extract_cross_video_patterns(
            nodes, relationships, corpus_segments
        )

        cross_themes = "\n".join(
            [
                f"- {t['theme']}: {t['other_content_reference']}"
                for t in patterns.get("cross_video_themes", [])[:3]
            ]
        )

        expert_patterns = "\n".join(
            [
                f"- {p['expert']}: {p['pattern']}"
                for p in patterns.get("expert_patterns", [])[:3]
            ]
        )

        prompt = f"""
You are a leadership coach analyzing a SPECIFIC YouTube video.

IMPORTANT: Generate questions that reference THIS video's content AND how it connects to OTHER leadership YouTube content.

**Current Video Transcript:**
{transcript_excerpts}

**Current Video Knowledge Graph:**
Nodes: {nodes_summary}
Relationships: {rels_summary}

**Cross-Video Context (Other YouTube Leadership Content):**
{cross_themes}

**Expert Patterns from Other YouTube Content:**
{expert_patterns}

Generate {num_questions} questions that:
1. Reference SPECIFIC concepts from THIS video
2. Connect to themes discussed in OTHER leadership YouTube videos
3. Ask how the user's view aligns with or differs from other YouTube perspectives
4. Challenge users to reconcile multiple YouTube leadership perspectives

For each question include:
- Direct reference to this video's content
- Connection to other YouTube leadership content
- How other YouTube leaders might answer this differently
- A perspective from the broader leadership YouTube community

Return JSON:
[
  {{
    "id": 1,
    "question": "Specific question referencing this video AND other YouTube content",
    "related_concept": "Concept from this video",
    "type": "reflection|action|assessment",
    "video_reference": "Direct quote from this video",
    "cross_video_connection": "How other YouTube leadership content addresses this",
    "alternative_perspective": "What other YouTube leaders might say differently",
    "explanation": "Why this matters in context of YouTube leadership discussions",
    "options": ["Option A", "Option B", "Option C", "Option D"]
  }}
]

Return ONLY valid JSON.
"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a leadership coach. Generate questions referencing this video AND other YouTube leadership content.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            return json.loads(content)
        except Exception as e:
            print(f"Error generating questions: {e}")
            return self._default_questions(nodes)

    def _default_questions(self, nodes):
        """Fallback questions if LLM fails."""
        competencies = [n["name"] for n in nodes if n.get("type") == "Competency"]
        concepts = [n["name"] for n in nodes if n.get("type") == "Concept"]

        questions = [
            {
                "id": 1,
                "question": f"Based on THIS video, how does '{competencies[0] if competencies else 'leadership'}' compare to how other YouTube leaders define it?",
                "related_concept": competencies[0] if competencies else "Leadership",
                "type": "reflection",
                "video_reference": "From this video's content",
                "cross_video_connection": "Other YouTube leadership channels discuss various leadership definitions",
                "alternative_perspective": "Some leaders emphasize authority, others influence",
                "explanation": "Comparing perspectives across YouTube leadership content deepens understanding",
                "options": [
                    "Aligns with my view",
                    "Different from my view",
                    "I need more context",
                    "Unsure",
                ],
            },
            {
                "id": 2,
                "question": f"How can you apply '{concepts[0] if concepts else 'this concept'}' from this video, given what other YouTube leaders teach about implementation?",
                "related_concept": concepts[0] if concepts else "Impact",
                "type": "action",
                "video_reference": "This video's approach to the concept",
                "cross_video_connection": "Other YouTubers share their frameworks for applying concepts",
                "alternative_perspective": "Some emphasize mindset, others emphasize action",
                "explanation": "Combining insights from multiple sources improves application",
                "options": [
                    "Start today",
                    "Next week",
                    "Research more first",
                    "Need a mentor",
                ],
            },
            {
                "id": 3,
                "question": "What surprised you about THIS video compared to other leadership YouTube content you've watched?",
                "related_concept": "Perspective",
                "type": "reflection",
                "video_reference": "Unexpected insights from this video",
                "cross_video_connection": "Leadership YouTube has diverse perspectives",
                "alternative_perspective": "Each creator brings unique experiences",
                "explanation": "Recognizing differences across sources builds critical thinking",
                "options": [
                    "The approach was unique",
                    "The examples resonated",
                    "The research was different",
                    "It aligned with others",
                ],
            },
            {
                "id": 4,
                "question": "How confident are you applying THIS video's teachings vs other leadership YouTube advice you've encountered?",
                "related_concept": "Implementation",
                "type": "assessment",
                "video_reference": "This video's practical recommendations",
                "cross_video_connection": "Multiple YouTube sources offer different implementation paths",
                "alternative_perspective": "Some prioritize quick wins, others long-term growth",
                "explanation": "Confidence varies based on alignment with existing knowledge",
                "options": [
                    "Very confident",
                    "Somewhat confident",
                    "Unsure",
                    "Conflicting with other sources",
                ],
            },
            {
                "id": 5,
                "question": "Which leadership YouTube creator's views most align with THIS video's message?",
                "related_concept": "Community Context",
                "type": "reflection",
                "video_reference": "This video's core message",
                "cross_video_connection": "Comparing this to Simon Sinek, Brené Brown, etc.",
                "alternative_perspective": "Different creators emphasize different aspects",
                "explanation": "Finding alignment across sources validates the concept",
                "options": [
                    "Simon Sinek style",
                    "Brené Brown style",
                    "Traditional leadership",
                    "Completely unique",
                ],
            },
        ]
        return questions[:5]

    def generate_action_items(self, questions, answers, corpus_segments):
        """Generate action items with cross-video YouTube insights."""
        if not self.client:
            return self._default_action_items(answers)

        qa_pairs = []
        for q, a in zip(questions, answers):
            qa_pairs.append(
                f"Q: {q['question']}\n"
                f"A: {a['answer']} (Selected: {a['selected_option']})\n"
                f"Video: {q.get('video_reference', 'N/A')}\n"
                f"Other YouTube: {q.get('cross_video_connection', 'N/A')}"
            )

        qa_text = "\n\n".join(qa_pairs)

        transcript_summary = (
            "\n".join([s["transcript"][:150] for s in corpus_segments[:5]])
            if corpus_segments
            else "General leadership content"
        )

        prompt = f"""
Based on user's responses to questions about THIS YouTube video AND other leadership YouTube content, generate action items.

**User's Q&A:**
{qa_text}

**This Video's Content:**
{transcript_summary}

Generate 3-5 action items that:
1. Reference THIS video's specific content
2. Incorporate insights from OTHER leadership YouTube content
3. Help user reconcile multiple YouTube perspectives
4. Provide a balanced approach combining multiple sources

For each action item include:
- Specific action tied to this video
- How other YouTube leaders would support this action
- Alternative approaches from different YouTube perspectives
- Timeline and success metric

Return JSON:
[
  {{
    "id": 1,
    "action": "Specific action from this video context",
    "video_connection": "Specific reference to this YouTube video",
    "cross_video_support": "How OTHER YouTube leadership content supports this",
    "alternative_approach": "What different YouTube leaders might suggest",
    "balanced_perspective": "How to reconcile multiple YouTube sources",
    "timeline": "This week" or "This month",
    "success_metric": "How to measure"
  }}
]

Return ONLY valid JSON.
"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a leadership coach. Generate action items referencing this YouTube video AND other leadership YouTube content.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            return json.loads(content)
        except Exception as e:
            print(f"Error generating action items: {e}")
            return self._default_action_items(answers)

    def _default_action_items(self, answers):
        """Fallback action items if LLM fails."""
        items = [
            {
                "id": 1,
                "action": "Watch another YouTube leadership video on a similar theme and compare perspectives",
                "video_connection": "Based on this video's topic",
                "cross_video_support": "Many YouTube leaders offer complementary views",
                "alternative_approach": "Some focus on theory, others on practice",
                "balanced_perspective": "Combining multiple YouTube sources gives well-rounded understanding",
                "timeline": "This week",
                "success_metric": "Watch 1-2 additional videos and note differences",
            },
            {
                "id": 2,
                "action": "Apply this video's key concept and track your results",
                "video_connection": "Specific practice from this YouTube content",
                "cross_video_support": "Other YouTubers emphasize the importance of practice",
                "alternative_approach": "Some recommend journaling, others recommend action",
                "balanced_perspective": "Use both reflection and action",
                "timeline": "This week",
                "success_metric": "Apply concept and note the outcome",
            },
            {
                "id": 3,
                "action": "Share this video's insight with someone who might benefit",
                "video_connection": "This video's message worth spreading",
                "cross_video_support": "YouTube leaders encourage knowledge sharing",
                "alternative_approach": "Some recommend 1-on-1, others recommend wider sharing",
                "balanced_perspective": "Start small and scale based on response",
                "timeline": "This week",
                "success_metric": "Have at least one meaningful conversation",
            },
        ]
        return items

    def get_video_stats(self):
        """Get statistics about processed videos."""
        return {
            "videos_processed": len(self.insights.get("videos", {})),
            "cross_themes": len(self.insights.get("cross_video_themes", [])),
            "expert_patterns": len(self.insights.get("expert_patterns", [])),
        }
