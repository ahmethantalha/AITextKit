import json
import time
import re
import requests

class GeminiAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.max_retries = 3
        self.retry_delay = 5
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    def update_api_key(self, api_key):
        """Update the API key and test its validity"""
        if not api_key or len(api_key) < 10:  # Simple validation
            raise ValueError("Geçersiz API anahtarı formatı")
            
        # Test the API key with a simple request
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }
        
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": "Merhaba"}
                    ]
                }
            ]
        }
        
        response = requests.post(
            self.api_url,
            headers=headers,
            json=data
        )
        
        if response.status_code != 200:
            raise ValueError(f"API anahtarı geçersiz: {response.status_code} - {response.text}")
            
        self.api_key = api_key
    
    def generate_response(self, prompt, text):
        """Generate a response from the Gemini API"""
        for attempt in range(self.max_retries):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key
                }
                
                data = {
                    "contents": [
                        {
                            "parts": [
                                {"text": f"{prompt}\n\nMetin: {text}"}
                            ]
                        }
                    ]
                }
                
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=data
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    
                    if not response_data.get('candidates'):
                        return {
                            'success': False,
                            'message': "API boş yanıt döndürdü"
                        }
                    
                    content = response_data['candidates'][0]['content']['parts'][0]['text']
                    return {
                        'success': True,
                        'content': content
                    }
                else:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                    else:
                        return {
                            'success': False,
                            'message': f"API hatası: {response.status_code} - {response.text}"
                        }
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    return {
                        'success': False,
                        'message': f"API çağrısı sırasında hata: {str(e)}"
                    }
        
        return {
            'success': False,
            'message': f"{self.max_retries} deneme sonrası API yanıtı alınamadı"
        }
    
    def generate_chat_response(self, prompt):
        """Generate a chat response from the Gemini API (without text parameter)"""
        for attempt in range(self.max_retries):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key
                }
                
                data = {
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt}
                            ]
                        }
                    ]
                }
                
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=data
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    
                    if not response_data.get('candidates'):
                        return {
                            'success': False,
                            'message': "API boş yanıt döndürdü"
                        }
                    
                    content = response_data['candidates'][0]['content']['parts'][0]['text']
                    return {
                        'success': True,
                        'content': content
                    }
                else:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                    else:
                        return {
                            'success': False,
                            'message': f"API hatası: {response.status_code} - {response.text}"
                        }
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    return {
                        'success': False,
                        'message': f"API çağrısı sırasında hata: {str(e)}"
                    }
        
        return {
            'success': False,
            'message': f"{self.max_retries} deneme sonrası API yanıtı alınamadı"
        }
    
    def extract_json(self, text):
        """Extract JSON from the API response text"""
        try:
            # Try to find JSON using regex
            json_match = re.search(r'({.*})', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            
            # If regex fails, try finding the starting and ending brackets
            start_idx = text.find('{')
            end_idx = text.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = text[start_idx:end_idx]
                return json.loads(json_str)
            
            return None
        except Exception as e:
            raise Exception(f"JSON çıkarma hatası: {str(e)}")
