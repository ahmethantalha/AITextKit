# Bu bir örnek yapılandırma dosyasıdır
# Kendi kullanımınız için bu dosyayı `config.py` olarak kopyalayın ve değerlerinizi güncelleyin


import os

# Application configuration
SECRET_KEY = 'your_secret_key_here'  # Üretimde değiştirin
DEBUG = True  # Üretimde False yapın

# File storage paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
RESULTS_FOLDER = os.path.join(BASE_DIR, 'results')
DATABASE = os.path.join(BASE_DIR, 'database/text_analysis.db')

# API configuration
DEFAULT_API_KEY = "YOUR_API_KEY"  # BURAYA KENDİ API KEY'İNİZİ GİRİN (https://aistudio.google.com/apikey sitesinden ücretsiz alabilirsiniz)
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', DEFAULT_API_KEY)

# AnythingLLM API configuration
LLAMA_API_KEY = os.environ.get('LLAMA_API_KEY', 'YOUR_LLAMA_API_KEY')  # BURAYA KENDİ API KEY'İNİZİ GİRİN
VISION_ENABLED = os.environ.get('VISION_ENABLED', 'true').lower() == 'true'  # Vision özellikleri aktif mi?

# Model configuration
DEFAULT_MODEL = "gemini"  # gemini, openai, claude (gelecekteki destekler için)

# File upload settings
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB file size limit
ALLOWED_EXTENSIONS = {
    'pdf': ['.pdf'],
    'image': ['.jpg', '.jpeg', '.png'],
    'text': ['.txt'],
    'word': ['.docx'],
    'json': ['.json']
}