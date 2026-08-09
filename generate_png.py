import io
import base64
try:
    from PIL import Image
except ImportError:
    import os
    os.system('pip install Pillow')
    from PIL import Image

# Create a 500x500 image, which will be > 500 bytes
img = Image.new('RGB', (500, 500), color = 'red')
buffer = io.BytesIO()
img.save(buffer, format="PNG")
img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
with open('dummy.png.b64', 'w') as f:
    f.write(img_str)
print("Created dummy.png.b64")
