import easyocr
print("Loading EasyOCR (CPU)...")
reader = easyocr.Reader(['en'], gpu=False)
print("EasyOCR Loaded.")
