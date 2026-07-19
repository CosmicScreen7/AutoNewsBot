from PIL import Image
import os

# Define the images we have
images_to_use = [
    "test_single_1.jpg",
    "test_single_2.jpg",
    "test_single_3.jpg",
    "test_carousel_1.jpg"
]

# We want a 3x3 grid (9 posts) to simulate a profile.
# Let's repeat them to fill the grid.
grid_pattern = [
    images_to_use[0], images_to_use[1], images_to_use[2],
    images_to_use[3], images_to_use[0], images_to_use[1],
    images_to_use[2], images_to_use[3], images_to_use[0]
]

GRID_SIZE = 3 # 3x3 grid
POST_SIZE = 500 # 500x500 px for each square in the grid preview
SPACING = 10 # 10px white border between posts

canvas_size = (GRID_SIZE * POST_SIZE) + ((GRID_SIZE - 1) * SPACING)
canvas = Image.new('RGB', (canvas_size, canvas_size), 'white')

def crop_center_square(img):
    width, height = img.size
    min_dim = min(width, height)
    left = (width - min_dim) / 2
    top = (height - min_dim) / 2
    right = (width + min_dim) / 2
    bottom = (height + min_dim) / 2
    return img.crop((left, top, right, bottom))

try:
    for index, image_name in enumerate(grid_pattern):
        # Calculate row and column
        row = index // GRID_SIZE
        col = index % GRID_SIZE
        
        # Open image
        img_path = os.path.join(os.getcwd(), image_name)
        if not os.path.exists(img_path):
            # Fallback if an image is missing
            img = Image.new('RGB', (POST_SIZE, POST_SIZE), '#080808')
        else:
            img = Image.open(img_path)
            # Instagram profile grid shows 1:1 squares
            img = crop_center_square(img)
            img = img.resize((POST_SIZE, POST_SIZE), Image.Resampling.LANCZOS)
        
        # Calculate position
        x = col * (POST_SIZE + SPACING)
        y = row * (POST_SIZE + SPACING)
        
        # Paste onto canvas
        canvas.paste(img, (x, y))

    output_path = os.path.join(os.getcwd(), "instagram_grid_preview.jpg")
    canvas.save(output_path, quality=95)
    print(f"[SUCCESS] Grid preview saved at: {output_path}")

except Exception as e:
    print(f"[ERROR] {e}")
