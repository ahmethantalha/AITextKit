import requests
import json
import time
import base64
from io import BytesIO
from PIL import Image

class LlamaAPI:
    def __init__(self, base_url="http://localhost:3001", api_key=None):
        """
        Initialize the AnythingLLM API client for Llama 3.2
        
        Args:
            base_url (str): AnythingLLM API endpoint (default: http://localhost:3001)
            api_key (str): API key if required
        """
        # Browser Extension API formatı (http://localhost:3001/api|brx-XXXX) ise parse edelim
        if '|' in base_url:
            parts = base_url.split('|')
            self.base_url = parts[0]
            if len(parts) > 1 and not api_key:
                self.api_key = parts[1]
            else:
                self.api_key = api_key
        else:
            self.base_url = base_url
            self.api_key = api_key
        
        # URL sonunda "/" karakteri kontrolü
        if self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]
            
        self.max_retries = 3
        self.retry_delay = 5
        print(f"LlamaAPI initialized with base_url: {self.base_url}, api_key: {'***' if self.api_key else 'None'}")
    
    def _get_headers(self):
        """Get headers for API requests"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            if self.api_key.startswith('brx-'):
                # Browser extension key formatı
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                # Developer API key formatı
                headers["x-api-key"] = self.api_key
        return headers
        
    def generate_response(self, prompt, text):
        """Generate text response using AnythingLLM's API"""
        for attempt in range(self.max_retries):
            try:
                # Prompt ve text'i birleştir
                if text:
                    full_prompt = f"{prompt}\n\nMetin: {text}"
                else:
                    full_prompt = prompt
                
                # AnythingLLM'in doğru endpoint'i (dokümantasyona göre)
                endpoint = f"{self.base_url.split('|')[0]}/v1/workspace/chatting/chat"
                
                print(f"[LlamaAPI] Sending request to {endpoint}")
                
                # API anahtarı formatını düzelt - dokümantasyona göre x-api-key header'ı kullanılmalı
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key
                }
                
                # Doğru request format
                payload = {
                    "message": full_prompt,
                    "mode": "chat"  # chat veya query modunu belirtin
                }
                
                print(f"[LlamaAPI] Payload: {json.dumps(payload)[:200]}")
                print(f"[LlamaAPI] Headers: {headers}")
                
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                print(f"[LlamaAPI] Response status: {response.status_code}")
                
                if response.status_code == 200:
                    response_data = response.json()
                    print(f"[LlamaAPI] Response data: {json.dumps(response_data)[:200]}")
                    
                    # API'nin döndürdüğü yanıt formatına göre uyum sağla
                    if "textResponse" in response_data:
                        return {
                            'success': True,
                            'content': response_data["textResponse"]
                        }
                    else:
                        print(f"[LlamaAPI] Invalid response format: {json.dumps(response_data)}")
                        return {
                            'success': False,
                            'message': "Geçersiz yanıt formatı"
                        }
                else:
                    error_text = response.text[:500] if hasattr(response, 'text') else "No response text"
                    print(f"[LlamaAPI] Error response: {error_text}")
                    
                    if attempt < self.max_retries - 1:
                        print(f"[LlamaAPI] Retrying after error ({attempt+1}/{self.max_retries})")
                        time.sleep(self.retry_delay)
                    else:
                        return {
                            'success': False,
                            'message': f"API hatası: {response.status_code} - {error_text}"
                        }
            except Exception as e:
                print(f"[LlamaAPI] Exception: {str(e)}")
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

    def generate_vision_response(self, prompt, image_path):
        """Generate text response from vision model based on an image"""
        try:
            # Görüntüyü base64'e çevir
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            # OpenAI uyumlu endpoint
            endpoint = f"{self.base_url}/v1/openai/chat/completions"
            
            # OpenAI Vision formatında payload
            payload = {
                "model": "llama",
                "messages": [
                    {"role": "system", "content": "Sen görüntüleri analiz edebilen yardımcı bir asistansın."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}}
                    ]}
                ],
                "temperature": 0.7,
                "max_tokens": 1024
            }
            
            print(f"[LlamaAPI] Sending vision request to {endpoint}")
            
            response = requests.post(
                endpoint,
                headers=self._get_headers(),
                json=payload,
                timeout=120
            )
            
            print(f"[LlamaAPI] Vision response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    generated_text = response_data["choices"][0]["message"]["content"]
                    return {
                        'success': True,
                        'content': generated_text
                    }
                else:
                    print(f"[LlamaAPI] Invalid vision response format: {json.dumps(response_data)[:200]}")
                    return {
                        'success': False,
                        'message': "Geçersiz yanıt formatı"
                    }
            else:
                error_text = response.text[:200] if hasattr(response, 'text') else "No response text"
                print(f"[LlamaAPI] Vision API error: {response.status_code} - {error_text}")
                return {
                    'success': False,
                    'message': f"Vision API hatası: {response.status_code} - {error_text}"
                }
        except Exception as e:
            print(f"[LlamaAPI] Vision exception: {str(e)}")
            return {
                'success': False,
                'message': f"Vision API çağrısı sırasında hata: {str(e)}"
            }
    
    def extract_json(self, text):
        """Extract JSON from the API response text (compatible with Gemini API)"""
        try:
            import re
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
            print(f"[LlamaAPI] JSON extraction error: {str(e)}")
            raise Exception(f"JSON çıkarma hatası: {str(e)}")
    
    def test_connection(self):
        """Test the connection to AnythingLLM API"""
        try:
            # API anahtarı formatını düzelt
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key
            }
            
            # Doğrudan auth endpoint'ini kullan
            endpoint = f"{self.base_url.split('|')[0]}/v1/auth"
            
            print(f"[LlamaAPI] Testing connection to {endpoint}")
            print(f"[LlamaAPI] Headers: {headers}")
            
            response = requests.get(
                endpoint,
                headers=headers,
                timeout=5
            )
            
            print(f"[LlamaAPI] Auth response: {response.status_code} - {response.text}")
            
            # 403 hatası "No valid api key found" ise, API anahtarı formatı yanlış
            if response.status_code == 403 and "No valid api key found" in response.text:
                print("[LlamaAPI] API key format is incorrect")
                return False
                
            return response.status_code == 200
        except Exception as e:
            print(f"[LlamaAPI] Connection test exception: {str(e)}")
            return False