import base64
import requests
import json
import os
import io
import datetime
from PIL import Image

class ImagenAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        # Yeni Gemini API endpoint'i
        self.base_url = "https://generativelanguage.googleapis.com/v1"
    
    def generate_image(self, prompt, num_images=1, aspect_ratio="1:1"):
        """Generate images using Google's Gemini API"""
        if not self.api_key or len(self.api_key) < 10:
            return {
                'success': False,
                'message': 'Geçersiz API anahtarı'
            }
        
        try:
            # Gemini için yeni endpoint ve parametreleri 
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key
            }
            
            # Aspect ratio'yu ayarla
            ar_width, ar_height = 1, 1
            if aspect_ratio == "16:9":
                ar_width, ar_height = 16, 9
            elif aspect_ratio == "9:16":
                ar_width, ar_height = 9, 16
            elif aspect_ratio == "4:3":
                ar_width, ar_height = 4, 3
            elif aspect_ratio == "3:4":
                ar_width, ar_height = 3, 4
            
            # Gemini-1.5 Pro model kullanma
            url = f"{self.base_url}/models/gemini-1.5-pro:generateContent"
            
            data = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "isGenerating": True
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.4,
                    "topP": 1,
                    "topK": 32,
                    "maxOutputTokens": 2048
                }
            }
            
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                result = response.json()
                images = []
                
                # API yanıtından görsel verilerini çıkar
                if "candidates" in result and len(result["candidates"]) > 0:
                    # Her bir adaydan görsel bilgilerini al
                    for candidate in result["candidates"]:
                        for part in candidate.get("content", {}).get("parts", []):
                            if part.get("inlineData") and part["inlineData"].get("data"):
                                image_b64 = part["inlineData"]["data"]
                                image_bytes = base64.b64decode(image_b64)
                                images.append(image_bytes)
                
                return {
                    'success': True,
                    'images': images,
                    'count': len(images)
                }
            else:
                return {
                    'success': False,
                    'message': f"API hatası: {response.status_code} - {response.text}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Görsel oluşturma sırasında hata: {str(e)}"
            }
    
    def save_generated_images(self, images, output_dir, prefix="generated_image"):
        """Save generated images to disk"""
        saved_paths = []
        
        os.makedirs(output_dir, exist_ok=True)
        
        for i, img_bytes in enumerate(images):
            try:
                img = Image.open(io.BytesIO(img_bytes))
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"{prefix}_{timestamp}_{i+1}.png"
                file_path = os.path.join(output_dir, filename)
                
                img.save(file_path)
                saved_paths.append(file_path)
            except Exception as e:
                print(f"Error saving image {i}: {str(e)}")
                
        return saved_paths