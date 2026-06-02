import os
import json
from openai import OpenAI

class SemanticEntityRecognizer:
    """Uses LLM to identify Nodes and relationships from text segments."""

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com",
        ) if self.api_key else None
        
    def extract_triplets(self, text_segment):
        """
        Extracts (Subject, Relation, Object) from a text segment using few-shot prompting.
        Returns a list of dictionaries representing the graph edges.
        """
        if not self.client:
            print("Warning: OPENAI_API_KEY not found. Returning empty triplets.")
            return []

        print(f"Extracting triplets from: {text_segment[:50]}...")
        
        prompt = f"""
        You are a Knowledge Graph extraction engine specialized in Leadership Education.
        Analyze the following text segment and extract entity relationships as a JSON array of triplets.

        Valid Node Types: Competency, Concept, Strategy, Tactic, Path, Object, Personality, Outcome.

        Node Type Guidance:
        - Competency: A learnable leadership skill or capability (e.g. "Active Listening", "Decision Making")
        - Concept: An abstract idea or principle (e.g. "Psychological Safety", "Growth Mindset")
        - Strategy: A high-level approach to achieving a goal (e.g. "Transformational Leadership", "Servant Leadership")
        - Tactic: A specific, actionable technique or practice (e.g. "Daily Stand-up", "One-on-One Meetings", "SMART Goals")
        - Path: An ordered sequence or learning journey (e.g. "Leadership Development Path", "Conflict Resolution Path")
        - Outcome: A measurable result (e.g. "Team Performance", "Employee Retention")
        - Personality: A personality trait or style (e.g. "Empathy", "Resilience")
        - Object: A concrete artifact, tool, or resource

        Valid Relations:
        - DEVELOPS_SKILL: Subject builds or develops the object skill/competency
        - IS_EXAMPLE_OF: Subject is a concrete instance of the object concept
        - SEMANTICALLY_RELATED: Subject and object share semantic proximity
        - HAS_STRATEGY: A competency or concept is pursued via this strategy
        - HAS_TACTIC: A strategy is implemented using this specific tactic
        - LEADS_TO: Subject is a step or cause that leads to the object outcome or next concept
        - ENABLES: Subject enables or unlocks the object capability
        - REQUIRES: Subject requires the object as a prerequisite
        - IS_PART_OF: Subject is a component or sub-element of the object path or concept

        Instructions:
        1. Extract all clearly stated relationships first, then infer implicit ones from context.
        2. If a strategy is mentioned, link it to its parent competency via HAS_STRATEGY.
        3. If a specific technique or practice is mentioned, classify it as Tactic and link to its strategy via HAS_TACTIC.
        4. If a causal or sequential flow is implied, use LEADS_TO.
        5. Return at least one triplet per clear concept present.

        Input Text: "{text_segment}"

        Output JSON Format:
        [
          {{
            "subject": "Entity Name 1",
            "subject_type": "Node Type",
            "relation": "VALID_RELATION",
            "object": "Entity Name 2",
            "object_type": "Node Type"
          }}
        ]
        """
        
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a specialized triple extraction API matching a predefined schema. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            # Strip markdown formatting if present
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
                
            return json.loads(content)
        except Exception as e:
            print(f"Error extracting triplets: {e}")
            return []

    def map_to_dbpedia(self, entity_str):
        """Cross-references entity with DBpedia URIs to standardize terminology."""
        # Simple heuristic matching for common leadership terms
        # In a full production system, this would make an external HTTP call to DBpedia Spotlight
        standardized_maps = {
            # Core leadership concepts
            "strategic planning": "http://dbpedia.org/resource/Strategic_management",
            "conflict": "http://dbpedia.org/resource/Conflict_resolution",
            "listening": "http://dbpedia.org/resource/Active_listening",
            "empathy": "http://dbpedia.org/resource/Empathy",
            # Strategies
            "transformational leadership": "http://dbpedia.org/resource/Transformational_leadership",
            "servant leadership": "http://dbpedia.org/resource/Servant_leadership",
            "situational leadership": "http://dbpedia.org/resource/Situational_leadership_theory",
            "coaching": "http://dbpedia.org/resource/Coaching",
            "mentoring": "http://dbpedia.org/resource/Mentorship",
            "delegation": "http://dbpedia.org/resource/Delegation",
            # Competencies
            "decision making": "http://dbpedia.org/resource/Decision-making",
            "communication": "http://dbpedia.org/resource/Communication",
            "emotional intelligence": "http://dbpedia.org/resource/Emotional_intelligence",
            "team building": "http://dbpedia.org/resource/Team_building",
            "motivation": "http://dbpedia.org/resource/Motivation",
            "negotiation": "http://dbpedia.org/resource/Negotiation",
            "feedback": "http://dbpedia.org/resource/Feedback",
            "trust": "http://dbpedia.org/resource/Trust_(social_science)",
            "accountability": "http://dbpedia.org/resource/Accountability",
            "vision": "http://dbpedia.org/resource/Strategic_vision",
            # Tactics
            "smart goals": "http://dbpedia.org/resource/SMART_criteria",
            "one-on-one": "http://dbpedia.org/resource/One-on-one_(management)",
            "stand-up": "http://dbpedia.org/resource/Stand-up_meeting",
            "retrospective": "http://dbpedia.org/resource/Retrospective",
            "brainstorming": "http://dbpedia.org/resource/Brainstorming",
            # Outcomes
            "employee retention": "http://dbpedia.org/resource/Employee_retention",
            "team performance": "http://dbpedia.org/resource/Team_effectiveness",
            "psychological safety": "http://dbpedia.org/resource/Psychological_safety",
            "growth mindset": "http://dbpedia.org/resource/Mindset#Fixed_and_growth_mindset",
        }
        
        lower_entity = entity_str.lower()
        for key, uri in standardized_maps.items():
            if key in lower_entity:
                return uri
                
        return entity_str
