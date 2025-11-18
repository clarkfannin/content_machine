## Pipeline Breakdown

1. Generate the base performer image

Run the image generation workflow in ComfyUI.

Save the resulting image (ComfyUI_XXXX.png) → this becomes the input for Clip 1.

Example function:

def generate_image(prompt_text): ...
return image_path

2. Generate the first video

Call the video generation workflow using the image from step 1 as input.

After generation, extract the last frame (like you’re already doing).

Example function:

def generate_video(input_image, prompt_text): ...
return video_path, final_frame_path

3. Generate the second (transformation) video

Same workflow, but use the final frame from clip 1 as input.

Adjust the prompt dynamically (“…begins transforming into…”).

Extract its final frame again.

4. Generate the third (ending) video

Use the last frame from clip 2 as input.

Adjust the prompt for the “return to normal” look or 2nd transformation.