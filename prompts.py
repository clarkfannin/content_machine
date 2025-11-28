import logging
from ollama import chat
import json
import os
import re

example_prompts = [
    "A full-body shot of an extremely old, frail man with thin white hair, standing alone on the massive glossy America's Got Talent stage. Bright blue and purple stage lights beam down, dramatic shadows on star-patterned floor. Ultra-realistic, 8k detail, cinematic composition.",
    "The old man facing the camera begins a grotesque transformation into a frail turkey-human hybrid. His face elongates into a beak, red wattle droops from his chin and neck, patchy brown and white feathers sprout, arms become thin wing-like appendages. Eerie stage lights, cinematic horror-comedy style.",
    "The turkey-human hybrid transforms into a magnificent golden phoenix with a human face. Flowing golden feathers, large wings spread wide, expressive contemporary dance routine, spinning gracefully. Purple and blue stage lights, glossy stage floor reflecting radiant movement, 8k photorealistic, cinematic magical realism.",
    "The phoenix performs a breathtaking finale: spinning, arms flowing, radiant golden feathers trailing, dynamic motion blur, joyful human-like expression, dramatic lighting, full cinematic wide shot, ultra-detailed 8k photorealistic finish."
]

HISTORY_FILE = "recent_creatures.json"
MAX_HISTORY = 50  # Increased to track more concepts

def load_recent_creatures():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                content = f.read().strip()
                if not content:
                    print("History file is empty, starting fresh...")
                    return []
                data = json.loads(content)
                # Handle old format (list of strings) by clearing it
                if data and isinstance(data[0], str):
                    print("Detected old format history file, resetting...")
                    return []
                return data
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error reading history file: {e}. Starting fresh...")
            return []
    return []

def save_recent_creatures(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-MAX_HISTORY:], f, indent=2)

def extract_key_concepts(prompts):
    """
    Extracts:
    - starting_character (from prompt 1)
    - transformations (from prompts 3 and 4 only)
    - key_themes (keyword scanning)
    """
    concepts = {
        "starting_character": None,
        "transformations": [],
        "key_themes": []
    }

    # ----------------------------------------------------------------------------
    # 1. STARTING CHARACTER (Prompt 1 only)
    # ----------------------------------------------------------------------------
    p1 = prompts[0].lower()

    # Look for "a/an/the <adjectives> <core noun>"
    start_match = re.search(
        r"(?:a|an|the)?\s*([a-z\-\s]{3,}?\b(?:man|woman|person|creature|being|figure|child|boy|girl))",
        p1
    )

    if start_match:
        start = start_match.group(1).strip()
        start = re.sub(r'^(a|an|the)\s+', '', start)
        concepts["starting_character"] = start

    # ----------------------------------------------------------------------------
    # 2. TRANSFORMATIONS (Prompts 3 and 4 only)
    # ----------------------------------------------------------------------------
    CREATURE_NAMES = [
    "phoenix","dragon","unicorn","griffin","pegasus","chimera","hydra",
    "jellyfish","octopus","squid","mermaid","centaur","minotaur",
    "owl","eagle","hawk","raven","crow","dove","parrot","turkey",
    "lion","tiger","bear","wolf","fox","deer","elephant","giraffe",
    "ghost","skeleton","zombie","vampire","werewolf","angel","demon",
    "fairy","elf","goblin","troll","sprite","basilisk","kraken","leviathan",
    "wyvern","gargoyle","banshee","wraith","golem","cyclops","satyr","dryad",
    "nymph","kelpie","selkie","harpy","sphinx","manticore","cerberus","yeti",
    "sasquatch","chupacabra","thunderbird","roc","qilin","kitsune","tanuki","tengu",
    "oni","kappa","naga","lamia","siren","boggart","imp","djinn",
    "efreet","rakshasa","asura","deva","valkyrie","frost giant","fire giant","stone giant",
    "hobgoblin","kobold","orc","lizardfolk","merfolk","sea serpent","plesiosaur","pterosaur",
    "sabertooth cat","dire wolf","mammoth","giant spider","giant scorpion","cockatrice","hippogriff","bogeyman",
    "phantom","poltergeist","revenant","shadow beast","nightmare horse","hellhound","barghest","skinwalker",
    "wendigo","jackalope","mothman","jersey devil","merrow","undine","sylph","salamander",
    "firebird","ice wolf","thunder wolf","storm lion","crystal serpent","sand wyrm","dune drake","obsidian golem",
    "iron golem","clay golem","clockwork automaton","homunculus","mimic","beholder","mind flayer","aboleth",
    "deep one","sea hag","night hag","forest guardian","tree ent","barkling","bog witch","swamp beast",
    "marsh lurker","frost wraith","ice elemental","water elemental","earth elemental","air elemental","fire elemental","storm elemental",
    "sun bird","moon stag","star serpent","void wraith","abyssal fiend","shadow cat","rune wolf","ember fox",
    "frost boar","thunder ram","dune jackal","obsidian hawk","iron raven","crystal owl","ember dragon","frost dragon",
    "storm dragon","celestial lion","astral wolf","spectral horse","ghost bear","phantom fox","spirit elk","dream serpent",
    "nightmare stag","cosmic jellyfish","abyssal octopus","radiant unicorn","void griffin","molten golem","glacier giant","sand sprite",
    "ember sprite","frost sprite","storm sprite","lunar fairy","solar angel","void demon","chaos serpent","order guardian",
    "blood wolf","ashen hound","crystal golem","star phoenix","shadow drake","ember wyrm","echo spirit","mist phantom",
    "brine serpent","rift beast","time wraith","storm roc","iron basilisk","marrow ghoul","ashen revenant","golden stag",
    "obsidian lion","frozen harpy","ashen troll","storm kobold","ember minotaur","lunar dryad","solar nymph","rift dragon",
    "storm chimera","ancient sphinx","ashen griffin","thunder manticore","glow sprite","crystal mermaid","ashen satyr","rift golem"
        ]

    # Helper: safe word-boundary match
    def contains_creature(text):
        found = []
        words = re.findall(r"[a-z]+", text.lower())
        for c in CREATURE_NAMES:
            if c in words:  # prevents owl -> towards
                found.append(c)
        return found

    # Helper: extract phrase after "transforms into ..."
    def extract_full_transformation(text):
        m = re.search(
            r"transforms?\s+into\s+(?:a\s+)?(.+?)(?=(\s+with|\s+as|\s+while|,|\.))",
            text.lower()
        )
        if m:
            return m.group(1).strip()
        return None

    # Process prompts 3 and 4 only
    for prompt in prompts[2:]:
        pl = prompt.lower()

        # First: look for a well-formed "transforms into" phrase
        phr = extract_full_transformation(pl)
        if phr:
            concepts["transformations"].append(phr)
            continue

        # Fallback: Scan for creature names in a word-bounded way
        found_creatures = contains_creature(pl)
        for c in found_creatures:
            concepts["transformations"].append(c)

    # ----------------------------------------------------------------------------
    # 3. KEY THEMES (scan full text)
    # ----------------------------------------------------------------------------
    theme_keywords = [
        "magical", "horror", "comedy", "dramatic", "ethereal", "mystical",
        "mechanical", "organic", "celestial", "infernal", "aquatic", "aerial",
        "golden", "silver", "crystal", "shadowy", "radiant", "dark", "victorian",
        "futuristic", "ancient", "modern", "steampunk", "cyberpunk"
    ]

    full_text = " ".join(prompts).lower()

    for kw in theme_keywords:
        if kw in full_text:
            concepts["key_themes"].append(kw)

    return concepts


def concepts_are_too_similar(new_concepts, history_concepts, threshold=0.6):
    """
    Compare new concepts against recent history.
    Returns True if concepts are too similar (should be rejected).
    """
    if not history_concepts:
        return False
    
    for hist in history_concepts[-15:]:  # Check last 15 generations
        similarity_score = 0
        comparisons = 0
        
        # Compare starting characters
        if new_concepts["starting_character"] and hist["starting_character"]:
            comparisons += 1
            if new_concepts["starting_character"] == hist["starting_character"]:
                similarity_score += 1
        
        # Compare transformations
        new_trans = set(new_concepts["transformations"])
        hist_trans = set(hist["transformations"])
        if new_trans and hist_trans:
            comparisons += 1
            overlap = len(new_trans & hist_trans) / len(new_trans | hist_trans)
            similarity_score += overlap
        
        # Compare themes
        new_themes = set(new_concepts["key_themes"])
        hist_themes = set(hist["key_themes"])
        if new_themes and hist_themes:
            comparisons += 1
            overlap = len(new_themes & hist_themes) / len(new_themes | hist_themes)
            similarity_score += overlap * 0.5  # Themes weighted less
        
        if comparisons > 0:
            avg_similarity = similarity_score / comparisons
            if avg_similarity >= threshold:
                return True
    
    return False

def generate_full_video_metadata(example_prompts=example_prompts, max_retries=3):
    recent_concepts = load_recent_creatures()
    
    # Build avoidance guidance from recent concepts
    avoid_items = []
    if recent_concepts:
        for concept in recent_concepts[-10:]:
            if concept.get("starting_character"):
                avoid_items.append(concept["starting_character"])
            avoid_items.extend(concept.get("transformations", [])[:2])
    
    avoid_text = ", ".join(set(avoid_items)) if avoid_items else "none"

    user_prompt = f"""
You are a creative visual AI prompt generator generating prompts for videos of an America's Got Talent performance.

AVOID using these recently used concepts: {avoid_text}

Generate exactly this JSON structure:

{{
  "prompts": ["prompt1", "prompt2", "prompt3", "prompt4"],
  "title": "string",
  "description": "string",
  "tags": ["tag1", "tag2", "tag3", "..."]
}}

IMPORTANT:
- Characters should NEVER be children.
- Characters should never be depicted nude or semi-nude.
- Characters should always have a realistic appearance. No cartoons. The prompts should specifically mention realistic animals or people.
- The starting character, in the first and second videos, should ALWAYS be a human.
- All human characters should have a specific race/ethnicity.
- Stage light should always be bright blue.
- Avoid characters with neon colored hair or skin. Humans should always appear realistic before the transformation.
- All characters MUST be generated in a photorealistic, REALISM style with ultra-detailed 8k resolution.
- Characters should ALWAYS have some extreme or exaggerated characteristic (e.g., extremely old, extremely tall, extremely colorful).
- Each prompt must describe a single character performing on the America's Got Talent stage, facing the camera directly.
- Follow the example prompts below for style, composition, and cinematic detail.
- Character must always be facing the camera directly in all prompts.
- Prompt 1: full-body, extreme characteristic.
- Prompt 2: idle/simple action, NO transformation.
- Prompts 3 & 4: dramatic, elaborate, visually impressive transformations.
- Avoid simple fade-ins/fade-outs. Include dynamic motion, props, magical effects, or costume changes.
- TITLE: viral YouTube Short style, 6–10 words, only 1-2 words fully CAPITALIZED.
- DESCRIPTION: 1–2 punchy sentences.
- TAGS: 10–15 content-related tags describing the story, theme, or audience. Never include apostrophes in tags. Just omit the apostrophes.

EXAMPLES (style reference):
1. {example_prompts[0]}
2. {example_prompts[1]}
3. {example_prompts[2]}
4. {example_prompts[3]}

Return only valid JSON.
"""

    for attempt in range(max_retries):
        response = chat(
            model='gemma3',
            messages=[{'role': 'user', 'content': user_prompt}]
        )

        resp_text = response.message.content
        if resp_text.startswith("```"):
            lines = resp_text.splitlines()
            resp_text = "\n".join(lines[1:-1])

        # Clean up response - remove markdown code blocks and extra text
        resp_text = resp_text.strip()

        # Remove markdown code blocks if present
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].split("```")[0].strip()

        # Try to find JSON object boundaries if there's extra text
        if not resp_text.startswith("{"):
            # Look for first { and last }
            start = resp_text.find("{")
            end = resp_text.rfind("}") + 1
            if start != -1 and end > start:
                resp_text = resp_text[start:end]

        try:
            data = json.loads(resp_text)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON. Raw response:\n{resp_text}")
            raise

        if ("prompts" not in data or
            not isinstance(data["prompts"], list) or
            len(data["prompts"]) != 4):
            raise ValueError("Ollama did not return a valid prompts array.")

        # Extract concepts from this generation
        new_concepts = extract_key_concepts(data["prompts"])
        
        # Check for similarity with recent generations
        if not concepts_are_too_similar(new_concepts, recent_concepts):
            # Append tags to description
            if "tags" in data and data["tags"]:
                hashtags = " ".join(f"#{tag.replace(' ', '')}" for tag in data["tags"])
                data["description"] += "\n\n" + hashtags

            # Save concepts to history
            recent_concepts.append(new_concepts)
            save_recent_creatures(recent_concepts)
            
            # Print the generated prompts
            print(f"\nGenerated Title: {data['title']}")
            print("Generated Prompts:")
            print("-" * 80)
            for i, prompt in enumerate(data['prompts'], 1):
                print(f"\nPrompt {i}:")
                print(prompt)
            print("-" * 80 + "\n")
            
            return data
        
        print(f"Attempt {attempt + 1}: Concept too similar to recent generations, retrying...")
    
    # If all retries failed, return the last generation anyway with a warning
    print("Warning: Could not generate sufficiently unique concept after retries. Using last attempt.")
    
    if "tags" in data and data["tags"]:
        hashtags = " ".join(f"#{tag.replace(' ', '')}" for tag in data["tags"])
        data["description"] += "\n\n" + hashtags
    
    new_concepts = extract_key_concepts(data["prompts"])
    recent_concepts.append(new_concepts)
    save_recent_creatures(recent_concepts)
    
    return data


if __name__ == "__main__":
    print("Generating video metadata...\n")
    result = generate_full_video_metadata()
    
    print(f"Title: {result['title']}")
    print(f"Description: {result['description']}\n")
    print("Generated Prompts:")
    print("-" * 80)
    for i, prompt in enumerate(result['prompts'], 1):
        print(f"\nPrompt {i}:")
        print(prompt)
    print("-" * 80)