import os
from PIL import Image

logo_path = r"a:\TVS_1\frontend\public\tvs_logo.png"
out_dir = r"a:\TVS_1\frontend\public"

try:
    # Open the original wide logo
    img = Image.open(logo_path).convert("RGBA")
    w, h = img.size
    
    # Create a square canvas of size w x w with transparent background
    square_size = max(w, h)
    square_img = Image.new("RGBA", (square_size, square_size), (0, 0, 0, 0))
    
    # Paste the original logo in the center
    paste_x = (square_size - w) // 2
    paste_y = (square_size - h) // 2
    square_img.paste(img, (paste_x, paste_y))
    
    # Generate 192x192 icon
    icon_192 = square_img.resize((192, 192), Image.Resampling.LANCZOS)
    icon_192.save(os.path.join(out_dir, "tvs_logo_192.png"), "PNG")
    print("Created tvs_logo_192.png successfully.")
    
    # Generate 512x512 icon
    icon_512 = square_img.resize((512, 512), Image.Resampling.LANCZOS)
    icon_512.save(os.path.join(out_dir, "tvs_logo_512.png"), "PNG")
    print("Created tvs_logo_512.png successfully.")
    
except Exception as e:
    print(f"Error generating PWA icons: {e}")
