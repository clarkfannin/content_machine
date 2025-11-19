from ollama import chat
import json

example_prompts = [
    "A full-body shot of an extremely old, frail man with thin white hair, standing alone on the massive glossy America's Got Talent stage. Bright blue and purple stage lights beam down, dramatic shadows on star-patterned floor. Ultra-realistic, 8k detail, cinematic composition.",
    "The old man facing the camera begins a grotesque transformation into a frail turkey-human hybrid. His face elongates into a beak, red wattle droops from his chin and neck, patchy brown and white feathers sprout, arms become thin wing-like appendages. Eerie stage lights, cinematic horror-comedy style.",
    "The turkey-human hybrid transforms into a magnificent golden phoenix with a human face. Flowing golden feathers, large wings spread wide, expressive contemporary dance routine, spinning gracefully. Purple and blue stage lights, glossy stage floor reflecting radiant movement, 8k photorealistic, cinematic magical realism.",
    "The phoenix performs a breathtaking finale: spinning, arms flowing, radiant golden feathers trailing, dynamic motion blur, joyful human-like expression, dramatic lighting, full cinematic wide shot, ultra-detailed 8k photorealistic finish."
]

def generate_prompts_with_ollama(example_prompts):
    """
    Uses Ollama to generate 4 new prompts based on 4 example prompts.
    Returns a list of 4 strings: [image_prompt, video1_prompt, video2_prompt, video3_prompt]
    """
    user_prompt = f"""
    You are a creative visual AI prompt generator. Generate exactly 4 detailed prompts as a JSON array. 
    The first prompt should describe a full-body image of a single person standing on the America's Got Talent stage, ultra-realistic, cinematic lighting. 
    The second prompt (first video prompt) should depict the same person simply idling, smiling, or waving to the camera on the AGT stage, without any transformation, in cinematic detail, 8k photorealism, and stage lighting with reflections on the glossy floor. 
    The third and fourth prompts (video prompts) should describe dramatic transformations or performances of that person, with cinematic detail, 8k photorealism, stage lighting, reflections on the stage floor, and camera-facing perspective. 
    Every person must have one extreme characteristic (e.g., extremely tall, beautiful, old, wealthy, poor, unusual hair, bizarre clothing). 
    Return only valid JSON with no extra text or commentary. Each prompt should be a single string. Ensure consistency so the same person is depicted across all 4 prompts. 



    Examples:
    1. {example_prompts[0]}
    2. {example_prompts[1]}
    3. {example_prompts[2]}
    4. {example_prompts[3]}

    Return your output as a JSON array of 4 strings only.
    """

    response = chat(
        model='gemma3',
        messages=[{'role': 'user', 'content': user_prompt}]
    )

    # Parse JSON array from Ollama output
    resp_text = response.message.content

    # Strip triple backticks and optional "json" if present
    if resp_text.startswith("```"):
        lines = resp_text.splitlines()
        # Remove first line (```json or ```) and last line (```)
        resp_text = "\n".join(lines[1:-1])

    prompts = json.loads(resp_text)

    if not isinstance(prompts, list) or len(prompts) != 4:
        raise ValueError("Ollama did not return a valid array of 4 prompts.")
    
    return prompts