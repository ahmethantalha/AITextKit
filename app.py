import os
import json
import datetime
import logging
import atexit
from flask import Flask, g, render_template, request as flask_request, jsonify, send_from_directory, request
from werkzeug.utils import secure_filename
from services.data_processor import DataProcessor
from services.gemini_api import GeminiAPI
from database.db import (
    close_db, get_processing_logs, get_saved_results, init_db, get_db,
    get_custom_prompt_types, log_processing, save_custom_prompt_type,
    delete_custom_prompt_type, get_setting, save_result, toggle_log_star,
    update_log_notes, update_setting, backup_database
)
import requests
from services.llama_api import LlamaAPI
from services.imagen_api import ImagenAPI

# Loglama ayarları
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)
app.config.from_pyfile('config.py')
DATABASE = app.config['DATABASE']

# Global service instances
data_processor = None
gemini_api = None
llama_api = None
imagen_api = None

def init_services():
    """Initialize service instances"""
    global data_processor, gemini_api, llama_api, imagen_api
    
    if data_processor is None:
        data_processor = DataProcessor()
    
    if gemini_api is None:
        gemini_api = GeminiAPI(app.config.get('GEMINI_API_KEY', app.config.get('DEFAULT_API_KEY', '')))
    
    if llama_api is None:
        llama_api = LlamaAPI(
            base_url=app.config.get('LLAMA_API_URL', 'http://localhost:3001'),
            api_key=app.config.get('LLAMA_API_KEY', '')
        )
        
    if imagen_api is None:
        imagen_api = ImagenAPI(app.config.get('GEMINI_API_KEY', app.config.get('DEFAULT_API_KEY', '')))

# AJAX isteklerini loglama
@app.before_request
def log_request_info():
    if flask_request.path.startswith('/api/'):
        app.logger.info('Gelen API isteği: %s %s', flask_request.method, flask_request.path)
        if flask_request.is_json:
            app.logger.info('JSON içeriği: %s', flask_request.get_json())

# Hata yakalama
@app.errorhandler(500)
def internal_error(error):
    app.logger.error('Sunucu hatası: %s', error)
    return jsonify({
        'success': False,
        'message': 'Sunucu hatası: ' + str(error)
    }), 500

@app.errorhandler(404)
def not_found_error(error):
    app.logger.warning('Sayfa bulunamadı: %s', flask_request.path)
    return jsonify({
        'success': False,
        'message': 'Sayfa bulunamadı'
    }), 404

# Initialize database and services
with app.app_context():
    # Ensure directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
    db_dir = os.path.dirname(app.config['DATABASE'])
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    # Initialize database without preserving old data
    init_db(preserve_settings=False, preserve_logs=False)
    
    try:
        # Load settings from database
        db = get_db()
        db.execute('CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)')
        
        # Load API key
        app.config['GEMINI_API_KEY'] = get_setting('gemini_api_key', app.config.get('DEFAULT_API_KEY'))
        
        # Load max file size
        max_file_size = get_setting('max_file_size')
        if max_file_size:
            try:
                max_size = int(max_file_size)
                app.config['MAX_CONTENT_LENGTH'] = max_size * 1024 * 1024
            except (ValueError, TypeError):
                app.logger.error("Invalid max file size value, using default")
        
        # Load default model
        app.config['DEFAULT_MODEL'] = get_setting('default_model', 'gemini')

# Initialize services
        init_services()
        
    except Exception as e:
        app.logger.error(f"Error loading settings: {str(e)}")

# Model seçimini yöneten yardımcı fonksiyon
def get_model_api(model_name):
    """Get the appropriate API based on model name"""
    init_services()  # Ensure services are initialized
    if model_name == 'llama':
        return llama_api
    return gemini_api  # default to gemini

@app.route('/')
def index():
    """Render the main application page"""
    # Dosya boyutunu MB olarak döndür (bytlardan)
    max_file_size = app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024) // (1024 * 1024)
    
    # İzin verilen dosya türlerini daha kullanıcı dostu bir formatta al
    allowed_extensions = app.config.get('ALLOWED_EXTENSIONS', {})
    allowed_file_types = []
    
    for file_type, extensions in allowed_extensions.items():
        exts = [ext.lstrip('.').upper() for ext in extensions]
        allowed_file_types.append(f"{file_type.capitalize()} ({', '.join(exts)})")
    
    allowed_file_types_str = "; ".join(allowed_file_types)
    
    return render_template('index.html', 
                          max_file_size=max_file_size,
                          allowed_file_types=allowed_file_types_str)

@app.route('/api/update-key', methods=['POST'])
def update_api_key():
    """Update the Gemini API key"""
    data = request.json
    api_key = data.get('api_key')
    
    if not api_key:
        return jsonify({'success': False, 'message': 'API anahtarı boş olamaz. Lütfen geçerli bir API anahtarı girin.'}), 400
    
    try:
        # Test the API key by initializing the API client
        gemini_api.update_api_key(api_key)
        
        # API anahtarı config'e kaydedelim
        app.config['GEMINI_API_KEY'] = api_key
        
        # API anahtarını veritabanına kaydedelim
        db = get_db()
        db.execute('CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)')
        db.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', 
                  ('gemini_api_key', api_key))
        db.commit()
        
        app.logger.info("API anahtarı başarıyla güncellendi ve veritabanına kaydedildi")
        return jsonify({
            'success': True, 
            'message': 'API anahtarı başarıyla doğrulandı ve kaydedildi. Artık Gemini AI modelini kullanabilirsiniz.'
        })
    except ValueError as ve:
        # Özel doğrulama hatası
        app.logger.error(f"API anahtarı doğrulama hatası: {str(ve)}")
        return jsonify({
            'success': False, 
            'message': f'API anahtarı doğrulanamadı: {str(ve)}'
        }), 400
    except requests.exceptions.RequestException as re:
        # Ağ/bağlantı hatası
        app.logger.error(f"API anahtarı test edilirken bağlantı hatası: {str(re)}")
        return jsonify({
            'success': False, 
            'message': f'API sunucusuna bağlanırken hata oluştu. Lütfen internet bağlantınızı kontrol edin.'
        }), 400
    except Exception as e:
        # Genel hata
        app.logger.error(f"API anahtarı güncellenirken beklenmeyen hata: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'API anahtarı güncellenirken beklenmeyen bir hata oluştu: {str(e)}'
        }), 400

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file uploads"""
    if 'files' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya yüklenmedi'}), 400
    
    files = request.files.getlist('files')
    uploaded_files = []
    
    for file in files:
        if file.filename == '':
            continue
            
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Get file type
        file_ext = os.path.splitext(filename)[1].lower()
        file_type = data_processor.get_file_type(file_ext)
        
        if file_type:
            uploaded_files.append({
                'name': filename,
                'path': file_path,
                'type': file_type
            })
        else:
            return jsonify({
                'success': False, 
                'message': f'Desteklenmeyen dosya formatı: {file_ext}'
            }), 400
    
    if not uploaded_files:
        return jsonify({'success': False, 'message': 'Hiçbir dosya yüklenemedi'}), 400
    
    return jsonify({
        'success': True,
        'message': f'{len(uploaded_files)} dosya başarıyla yüklendi',
        'files': uploaded_files
    })

@app.route('/api/process', methods=['POST'])
def process_files():
    """Process uploaded files with AI models"""
    data = request.json
    files = data.get('files', [])
    prompt_type = data.get('prompt_type', 'Soru-Cevap Üretimi')
    topic = data.get('topic', '')
    custom_prompt = data.get('custom_prompt', '')
    output_format = data.get('output_format', 'TXT')
    is_custom_type = data.get('is_custom_type', False)
    processing_mode = data.get('processing_mode', 'auto')
    
    # Model seçimi
    selected_model = data.get('model', app.config.get('DEFAULT_MODEL', 'gemini'))
    
    # Seçilen API'yi belirle
    api = get_model_api(selected_model)
    
    if not files:
        return jsonify({'success': False, 'message': 'İşlenecek dosya bulunamadı'}), 400
    
    # Build the prompt based on type
    if is_custom_type:
        prompt = custom_prompt
    else:
        prompt = data_processor.get_prompt(prompt_type, topic, custom_prompt)
    
    # Vision özellikleri
    use_vision = False
    if selected_model == 'llama':
        # AnythingLLM için vision özelliklerini kontrol et
        use_vision = app.config.get('VISION_ENABLED', False) and any(f.get('type') == 'image' for f in files)
    
    # İşlem tipini belirle
    is_summary = prompt_type == "Metin Özeti Oluştur"
    is_qa = prompt_type == "Soru-Cevap Üretimi"
    is_custom = prompt_type == "Özel Prompt" or is_custom_type
    
    # İşleme modunu belirle (auto modunda otomatik karar ver)
    if processing_mode == 'auto':
        # Özel prompt, özet veya blog/makale içeriyorsa birleştir
        if is_summary or is_custom or any(keyword in prompt.lower() for keyword in 
                                         ['blog', 'makale', 'yazı', 'kompozisyon', 'hikaye', 'deneme']):
            processing_mode = 'combined'
        else:
            processing_mode = 'separate'
            
    # Process each file
    result_data = {'success': True, 'messages': [], 'results': None}
    all_results = {"soru-cevaplar": []}
    combined_text = ""
    vision_results = []

    try:
        # Birleştirme modu için tüm içeriği topla
        if processing_mode == 'combined':
            all_content = ""
            
            for file_index, file in enumerate(files):
                file_path = file.get('path')
                file_name = file.get('name')
                file_type = file.get('type')
                
                result_data['messages'].append({
                    'type': 'info',
                    'text': f"Dosya okunuyor: {file_name}"
                })
                
                # Vision işleme veya normal metin işleme
                if use_vision and file_type == 'image':
                    vision_response = process_vision_file(file_name, file_path, api, prompt, result_data)
                    if vision_response:
                        vision_results.append(vision_response)
                        all_content += f"\n\n--- Görsel Analizi: {file_name} ---\n{vision_response['content']}\n\n"
                else:
                    text_content = process_text_file(file_name, file_path, file_type, data_processor, result_data)
                    if text_content:
                        all_content += text_content + "\n\n"
                
                update_progress(result_data, file_index, len(files))
            
            # Birleştirilmiş içeriği işle
            if all_content.strip():
                combined_text = process_combined_content(all_content, api, prompt, is_qa, is_summary, is_custom,
                              result_data, all_results)
        else:
            # Ayrı işleme modu
            for file_index, file in enumerate(files):
                process_single_file(file, file_index, files, use_vision, api, prompt,
                                  data_processor, is_summary, is_custom, is_qa,
                                  result_data, all_results, combined_text, vision_results)
        
        # Son işlemler ve sonuç oluşturma
        create_final_result(is_summary, is_custom, is_qa, combined_text, all_results,
                           vision_results, api, prompt, processing_mode, output_format,
                           app.config['RESULTS_FOLDER'], result_data)
        
        # Başarılı işlem loglaması
        if result_data['success'] and result_data.get('results'):
            log_successful_processing(files, prompt_type, result_data)

    except Exception as e:
        # Hata durumu loglaması
        log_error_and_return(e, files, prompt_type)
        return jsonify({
            'success': False,
            'message': f"İşlem sırasında hata oluştu: {str(e)}"
        }), 500

    return jsonify(result_data)

@app.route('/download/<filename>')
def download_file(filename):
    """Download a result file"""
    return send_from_directory(app.config['RESULTS_FOLDER'], filename, as_attachment=True)

# Özel İşlem Türleri Endpoint'leri
@app.route('/api/custom-prompt-types', methods=['GET'])
def get_custom_prompt_types_api():
    """Get all custom prompt types"""
    custom_types = get_custom_prompt_types()
    return jsonify({
        'success': True,
        'custom_prompt_types': custom_types
    })

@app.route('/api/custom-prompt-types', methods=['POST'])
def save_custom_prompt_type_api():
    """Save a custom prompt type"""
    data = request.json
    name = data.get('name')
    prompt_text = data.get('prompt_text')
    
    if not name or not prompt_text:
        return jsonify({
            'success': False,
            'message': 'İşlem türü adı ve prompt metni gereklidir.'
        }), 400
    
    success, message, custom_prompt_type = save_custom_prompt_type(name, prompt_text)
    
    return jsonify({
        'success': success,
        'message': message,
        'custom_prompt_type': custom_prompt_type
    }), 200 if success else 400

@app.route('/api/custom-prompt-types/<int:prompt_id>', methods=['DELETE'])
def delete_custom_prompt_type_api(prompt_id):
    """Delete a custom prompt type"""
    success, message = delete_custom_prompt_type(prompt_id)
    
    return jsonify({
        'success': success,
        'message': message,
        'deleted_id': prompt_id if success else None
    }), 200 if success else 400

@app.route('/settings')
def settings():
    """Render the settings page"""
    # Mevcut ayarları alıp sayfaya gönderin
    current_api_key = app.config.get('GEMINI_API_KEY', '')
    
    # Dosya boyutunu MB olarak döndür (bytlardan)
    max_file_size = app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024) // (1024 * 1024)
    
    default_model = app.config.get('DEFAULT_MODEL', 'gemini')
    
    return render_template('settings.html', 
                          current_api_key=current_api_key,
                          max_file_size=max_file_size,
                          default_model=default_model)

@app.route('/api/update-settings', methods=['POST'])
def update_settings():
    """Update application settings"""
    data = request.json
    updates = []
    all_success = True
    
    # Gemini API key
    if 'gemini_api_key' in data:
        api_key = data.get('gemini_api_key')
        try:
            # Test the API key
            gemini_api.update_api_key(api_key)
            
            # API anahtarını veritabanına ve config'e kaydet
            db = get_db()
            db.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', 
                     ('gemini_api_key', api_key))
            db.commit()
            
            app.config['GEMINI_API_KEY'] = api_key
            updates.append({
                'key': 'gemini_api_key', 
                'success': True, 
                'message': 'API anahtarı başarıyla doğrulandı ve kaydedildi'
            })
        except ValueError as ve:
            all_success = False
            updates.append({
                'key': 'gemini_api_key', 
                'success': False, 
                'message': f'API anahtarı doğrulanamadı: {str(ve)}'
            })
        except requests.exceptions.RequestException:
            all_success = False
            updates.append({
                'key': 'gemini_api_key', 
                'success': False, 
                'message': 'API sunucusuna bağlanırken hata oluştu. Lütfen internet bağlantınızı kontrol edin.'
            })
        except Exception as e:
            all_success = False
            updates.append({
                'key': 'gemini_api_key', 
                'success': False, 
                'message': f'API anahtarı güncellenirken beklenmeyen bir hata oluştu: {str(e)}'
            })
    
    # Max file size
    if 'max_file_size' in data:
        try:
            max_size = int(data.get('max_file_size', 16))
            
            if max_size <= 0:
                all_success = False
                updates.append({
                    'key': 'max_file_size', 
                    'success': False, 
                    'message': 'Maksimum dosya boyutu pozitif bir sayı olmalıdır'
                })
            elif max_size > 100:
                # Uyarı ekle ama başarılı say
                updates.append({
                    'key': 'max_file_size', 
                    'success': True, 
                    'message': f'Maksimum dosya boyutu {max_size} MB olarak ayarlandı (yüksek değerler performans sorunlarına neden olabilir)'
                })
                
                # Dosya boyutunu veritabanına ve config'e kaydet
                db = get_db()
                db.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', 
                         ('max_file_size', str(max_size)))
                db.commit()
                
                # Aktif konfigürasyonu güncelle (bytlara çevirerek)
                app.config['MAX_CONTENT_LENGTH'] = max_size * 1024 * 1024
            else:
                # Dosya boyutunu veritabanına ve config'e kaydet
                db = get_db()
                db.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', 
                         ('max_file_size', str(max_size)))
                db.commit()
                
                # Aktif konfigürasyonu güncelle (bytlara çevirerek)
                app.config['MAX_CONTENT_LENGTH'] = max_size * 1024 * 1024
                
                updates.append({
                    'key': 'max_file_size', 
                    'success': True, 
                    'message': f'Maksimum dosya boyutu {max_size} MB olarak ayarlandı'
                })
        except (ValueError, TypeError):
            all_success = False
            updates.append({
                'key': 'max_file_size', 
                'success': False, 
                'message': 'Geçersiz dosya boyutu değeri. Lütfen pozitif bir sayı girin.'
            })
        except Exception as e:
            all_success = False
            updates.append({
                'key': 'max_file_size', 
                'success': False, 
                'message': f'Dosya boyutu ayarlanırken beklenmeyen bir hata oluştu: {str(e)}'
            })
    
    # Default model
    if 'default_model' in data:
        default_model = data.get('default_model')
        supported_models = ['gemini']  # Şu an için sadece Gemini destekleniyor
        
        if default_model in supported_models:
            try:
                db = get_db()
                db.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', 
                         ('default_model', default_model))
                db.commit()
                
                app.config['DEFAULT_MODEL'] = default_model
                updates.append({
                    'key': 'default_model', 
                    'success': True, 
                    'message': f'Varsayılan model {default_model} olarak ayarlandı'
                })
            except Exception as e:
                all_success = False
                updates.append({
                    'key': 'default_model', 
                    'success': False, 
                    'message': f'Varsayılan model ayarlanırken bir hata oluştu: {str(e)}'
                })
        else:
            all_success = False
            updates.append({
                'key': 'default_model', 
                'success': False, 
                'message': f'Desteklenmeyen model: {default_model}. Şu an için sadece Gemini desteklenmektedir.'
            })
    
    # Sonuç mesajı
    if all_success:
        message = 'Tüm ayarlar başarıyla güncellendi'
    else:
        message = 'Bazı ayarlar güncellenirken sorun oluştu'
    
    return jsonify({
        'success': all_success,
        'message': message,
        'updates': updates
    })

# Chat sayfası route'u
@app.route('/chat')
def chat_page():
    """Render the chat page"""
    current_time = datetime.datetime.now().strftime('%H:%M')
    return render_template('chat.html', current_time=current_time)

# Chat API endpoint'i
@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat messages with Gemini API"""
    data = request.json
    user_message = data.get('message', '')
    chat_history = data.get('history', [])
    
    if not user_message:
        return jsonify({
            'success': False,
            'message': 'Mesaj boş olamaz'
        }), 400
    
    try:
        # Sohbet geçmişinden bağlam oluştur
        context = ""
        if chat_history:
            for msg in chat_history[-5:]:  # Son 5 mesajı kullan
                if msg['sender'] == 'user':
                    context += f"Kullanıcı: {msg['message']}\n"
                else:
                    context += f"Gemini: {msg['message']}\n"
        
        # Bağlam ve kullanıcı mesajını birleştir
        prompt = f"{context}\nKullanıcı: {user_message}\nGemini:"
        
        # Gemini API'ye istek at
        api_response = gemini_api.generate_response(prompt, "")
        
        if api_response.get('success'):
            ai_response = api_response.get('content')
            
            return jsonify({
                'success': True,
                'response': ai_response
            })
        else:
            return jsonify({
                'success': False,
                'message': api_response.get('message', 'API yanıt vermedi')
            })
    except Exception as e:
        app.logger.error(f"Chat sırasında hata: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Mesaj işlenirken hata oluştu: {str(e)}"
        }), 500
    
@app.route('/api/check-llama', methods=['POST'])
def check_llama_connection():
    """Check connection to AnythingLLM API"""
    data = request.json
    api_url = data.get('api_url', app.config.get('LLAMA_API_URL'))
    api_key = data.get('api_key', app.config.get('LLAMA_API_KEY'))
    
    app.logger.info(f"Checking connection to AnythingLLM API at {api_url} with key: {'provided' if api_key else 'not provided'}")
    
    # Geçici LlamaAPI nesnesi oluştur
    test_api = LlamaAPI(base_url=api_url, api_key=api_key)
    
    try:
        # Bağlantıyı test et
        is_available = test_api.test_connection()
        app.logger.info(f"AnythingLLM connection test result: {is_available}")
        
        if is_available:
            # Başarılıysa, ayarları güncelle
            db = get_db()
            db.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', 
                      ('llama_api_url', api_url))
            
            # API anahtarı boş değilse kaydet
            if api_key:
                db.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', 
                          ('llama_api_key', api_key))
            
            db.commit()
            
            # Uygulama yapılandırmasını güncelle
            app.config['LLAMA_API_URL'] = api_url
            app.config['LLAMA_API_KEY'] = api_key
            
            # Llama API nesnesini güncelle
            llama_api.base_url = api_url
            llama_api.api_key = api_key
        
        return jsonify({
            'success': True,
            'available': is_available,
            'message': 'Bağlantı başarılı' if is_available else 'Bağlantı başarısız'
        })
    except Exception as e:
        app.logger.error(f"Error during AnythingLLM connection test: {str(e)}")
        return jsonify({
            'success': False,
            'available': False,
            'message': str(e)
        })
    
@app.route('/api/test-llama-chat', methods=['POST'])
def test_llama_chat():
    """Test AnythingLLM chat capabilities"""
    data = request.json
    prompt = data.get('prompt', 'Merhaba, nasılsın?')
    
    app.logger.info(f"Testing AnythingLLM chat with prompt: {prompt}")
    
    try:
        # Basit bir mesaj gönder
        response = llama_api.generate_response(prompt, "")
        
        app.logger.info(f"AnythingLLM response: {response}")
        
        return jsonify({
            'success': response.get('success', False),
            'content': response.get('content', ''),
            'message': response.get('message', '')
        })
    except Exception as e:
        app.logger.error(f"Error during AnythingLLM chat test: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })
    
@app.route('/api/custom-prompt-types/<int:prompt_id>', methods=['PUT'])
def update_custom_prompt_type_api(prompt_id):
    """Update a custom prompt type"""
    data = request.json
    name = data.get('name')
    prompt_text = data.get('prompt_text')
    
    if not name or not prompt_text:
        return jsonify({
            'success': False,
            'message': 'İşlem türü adı ve prompt metni gereklidir.'
        }), 400
    
    try:
        db = get_db()
        
        # İlgili prompt türünün var olup olmadığını kontrol et
        prompt_exists = db.execute('SELECT id FROM custom_prompt_types WHERE id = ?', (prompt_id,)).fetchone()
        if not prompt_exists:
            return jsonify({
                'success': False,
                'message': 'Düzenlenecek işlem türü bulunamadı.'
            }), 404
        
        # İsim unique olmalı, bu yüzden diğer kayıtlarla çakışma kontrolü yap
        name_exists = db.execute('SELECT id FROM custom_prompt_types WHERE name = ? AND id != ?', 
                              (name, prompt_id)).fetchone()
        if name_exists:
            return jsonify({
                'success': False,
                'message': f'"{name}" adında başka bir işlem türü zaten var.'
            }), 400
        
        # Güncelleme işlemi
        db.execute(
            'UPDATE custom_prompt_types SET name = ?, prompt_text = ? WHERE id = ?',
            (name, prompt_text, prompt_id)
        )
        db.commit()
        
        # Güncellenmiş veriyi döndür
        updated_prompt = {
            'id': prompt_id,
            'name': name,
            'prompt_text': prompt_text
        }
        
        return jsonify({
            'success': True,
            'message': 'İşlem türü başarıyla güncellendi.',
            'updated_prompt': updated_prompt
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'İşlem türü güncellenirken bir hata oluştu: {str(e)}'
        }), 500
    

@app.route('/api/saved-results')
def get_results_api():
    """Get saved results with optional filtering"""
    result_type = request.args.get('type')
    search_query = request.args.get('query')
    limit = int(request.args.get('limit', 50))
    
    # Sonuçları al
    results = get_saved_results(limit=limit, result_type=result_type, search_query=search_query)
    
    # Benzersiz sonuçları filtrele (aynı içeriğe sahip olanları kaldır)
    unique_results = []
    seen_contents = set()
    
    for result in results:
        # İçeriği string'e çevir (dict olabilir)
        content_str = str(result['content'])
        
        # Bu içeriği daha önce görmediyse, listeye ekle
        if content_str not in seen_contents:
            seen_contents.add(content_str)
            unique_results.append(result)
    
    app.logger.info(f"Toplam sonuç sayısı: {len(results)}, Benzersiz sonuç sayısı: {len(unique_results)}")
    
    return jsonify({
        'success': True,
        'results': unique_results
    })

@app.route('/api/save-result', methods=['POST'])
def save_result_api():
    """Save a result to the database"""
    data = request.json
    title = data.get('title')
    description = data.get('description', '')
    result_type = data.get('result_type')
    content = data.get('content')
    source_file = data.get('source_file')
    processing_log_id = data.get('processing_log_id')
    tags = data.get('tags', [])
    
    if not title or not result_type:
        return jsonify({
            'success': False,
            'message': 'Başlık ve sonuç türü alanları gereklidir.'
        }), 400
    
    # İçerik yoksa varsayılan bir değer belirle
    if content is None:
        # İşlem ID'si varsa, o işlemin dosyasından içeriği almaya çalış
        if processing_log_id:
            db = get_db()
            log = db.execute('SELECT result_file FROM processing_logs WHERE id = ?', 
                           (processing_log_id,)).fetchone()
            if log and log['result_file']:
                try:
                    # Dosyayı oku ve içeriği al
                    file_path = os.path.join(app.config['RESULTS_FOLDER'], log['result_file'])
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception as e:
                    app.logger.error(f"Dosya okuma hatası: {str(e)}")
                    content = "İçerik alınamadı"
            else:
                content = "Boş içerik"
        else:
            content = "Boş içerik"
    
    try:
        # İçerik zaten kaydedilmiş mi kontrol et
        db = get_db()
        existing = db.execute(
            'SELECT id FROM saved_results WHERE title = ? AND content = ?',
            (title, content)
        ).fetchone()
        
        # Eğer aynı başlık ve içerikle kayıt varsa, onun ID'sini döndür
        if existing:
            return jsonify({
                'success': True,
                'message': 'Bu sonuç zaten kaydedilmiş.',
                'result_id': existing['id']
            })
        
        # Yeni kayıt ekle
        result_id = save_result(
            title, description, result_type, 
            content,
            source_file, processing_log_id, tags
        )
        
        return jsonify({
            'success': True,
            'message': 'Sonuç başarıyla kaydedildi.',
            'result_id': result_id
        })
    except Exception as e:
        app.logger.error(f"Sonuç kaydedilirken hata oluştu: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Sonuç kaydedilirken hata oluştu: {str(e)}'
        }), 500

@app.route('/api/log/update-notes', methods=['POST'])
def update_log_notes_api():
    """Update notes for a processing log"""
    data = request.json
    log_id = data.get('log_id')
    notes = data.get('notes', '')
    
    if not log_id:
        return jsonify({
            'success': False,
            'message': 'İşlem ID gereklidir.'
        }), 400
    
    try:
        update_log_notes(log_id, notes)
        return jsonify({
            'success': True,
            'message': 'Notlar başarıyla güncellendi.'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Notlar güncellenirken hata oluştu: {str(e)}'
        }), 500

@app.route('/api/log/toggle-star', methods=['POST'])
def toggle_log_star_api():
    """Toggle starred status for a log"""
    data = request.json
    log_id = data.get('log_id')
    
    if not log_id:
        return jsonify({
            'success': False,
            'message': 'İşlem ID gereklidir.'
        }), 400
    
    try:
        new_status = toggle_log_star(log_id)
        if new_status is not None:
            return jsonify({
                'success': True,
                'message': f'İşlem {"yıldızlandı" if new_status == 1 else "yıldızı kaldırıldı"}.',
                'starred': new_status == 1
            })
        else:
            return jsonify({
                'success': False,
                'message': 'İşlem bulunamadı.'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'İşlem yıldız durumu değiştirilirken hata oluştu: {str(e)}'
        }), 500
    
@app.route('/history')
def history_page():
    """Render the history page"""
    try:
        logs = get_processing_logs(100)  # Son 100 işlemi göster
        app.logger.info(f"Retrieved {len(logs)} logs from database")
        
        # Detaylı hata ayıklama için log içeriğini kontrol et
        if len(logs) > 0:
            app.logger.info(f"First log: {logs[0]}")
        else:
            app.logger.warning("No logs found in database")
            
        # Timestamp formatını kontrol et
        for log in logs:
            if not isinstance(log['timestamp'], datetime.datetime):
                app.logger.error(f"Invalid timestamp format for log {log['id']}: {type(log['timestamp'])}")
                # Timestamp'i datetime formatına dönüştür
                try:
                    if isinstance(log['timestamp'], str):
                        log['timestamp'] = datetime.datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00'))
                except Exception as e:
                    app.logger.error(f"Failed to convert timestamp: {str(e)}")
        
        return render_template('history.html', logs=logs)
    except Exception as e:
        app.logger.error(f"Error in history_page: {str(e)}")
        # Boş log listesi ile devam et
        return render_template('history.html', logs=[])

# Uygulama başladığında veritabanı varlığını kontrol et
def check_database():
    if not os.path.exists(DATABASE):
        app.logger.warning(f"Veritabanı dosyası bulunamadı: {DATABASE}")
        # Yoksa yeni veritabanı oluştur
        with app.app_context():
            init_db(preserve_settings=False)
    else:
        app.logger.info(f"Veritabanı dosyası bulundu: {DATABASE}")

@app.teardown_appcontext
def close_db_connection(exception):
    """Ensure database connection is properly closed"""
    close_db()

# Uygulamayı kapatmadan önce veritabanını kaydet
def save_db_before_exit():
    """Ensure database is saved before application exit"""
    try:
        with app.app_context():
            if 'db' in g:
                db = g.db
                db.commit()
                app.logger.info("Database committed before exit")
    except Exception as e:
        app.logger.error(f"Error saving database before exit: {str(e)}")

# Uygulama kapatılırken veritabanını kaydet
atexit.register(save_db_before_exit)

@app.route('/api/log-details/<int:log_id>')
def get_log_details(log_id):
    """Get detailed information about a log"""
    try:
        db = get_db()
        log = db.execute('SELECT * FROM processing_logs WHERE id = ?', (log_id,)).fetchone()
        
        if not log:
            return jsonify({
                'success': False,
                'message': 'İşlem bulunamadı'
            }), 404
        
        # Log verilerini sözlüğe dönüştür
        log_data = dict(log)
        
        # Sonuç dosyasını oku (varsa)
        result_content = None
        if log['result_file']:
            try:
                file_path = os.path.join(app.config['RESULTS_FOLDER'], log['result_file'])
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        result_content = f.read()
                        
                    # JSON içeriği ise parse et
                    if log['result_file'].endswith('.json'):
                        try:
                            result_content = json.loads(result_content)
                        except:
                            pass
            except Exception as e:
                app.logger.error(f"Sonuç dosyası okuma hatası: {str(e)}")
        
        # Tüm detayları döndür
        return jsonify({
            'success': True,
            'log': {
                'id': log['id'],
                'timestamp': log['timestamp'],
                'files': log['files'],
                'prompt_type': log['prompt_type'],
                'success': bool(log['success']),
                'result_file': log['result_file'],
                'notes': log['notes'] or '',
                'tags': json.loads(log['tags']) if log['tags'] else [],
                'starred': bool(log['starred'])
            },
            'result_content': result_content
        })
    except Exception as e:
        app.logger.error(f"İşlem detayları alınırken hata: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'İşlem detayları alınırken bir hata oluştu: {str(e)}'
        }), 500

@app.route('/api/generate-image', methods=['POST'])
def generate_image():
    """Generate images using Gemini API"""
    data = request.json
    prompt = data.get('prompt', '')
    num_images = int(data.get('num_images', 1))
    aspect_ratio = data.get('aspect_ratio', '1:1')
    
    if not prompt:
        app.logger.warning("Empty prompt received")
        return jsonify({'success': False, 'message': 'Görsel istemi (prompt) boş olamaz'}), 400
    
    # Check API key
    api_key = app.config.get('GEMINI_API_KEY')
    if not api_key:
        app.logger.error("No API key configured")
        return jsonify({'success': False, 'message': 'Gemini API anahtarı ayarlanmamış'}), 400
    
    # Initialize services
    init_services()
    
    try:
        app.logger.info(f"Generating image with prompt: {prompt[:50]}...")
        
        # Generate images
        result = imagen_api.generate_image(prompt, num_images, aspect_ratio)
        
        if not result.get('success'):
            error_msg = result.get('message', 'Unknown error')
            app.logger.error(f"Image generation failed: {error_msg}")
            return jsonify({
                'success': False,
                'message': f"Görsel oluşturma başarısız: {error_msg}"
            }), 400
        
        if not result.get('images'):
            app.logger.error("No images generated")
            return jsonify({
                'success': False,
                'message': 'Görsel oluşturulamadı'
            }), 400
            
        # Save images
        app.logger.info(f"Saving {len(result['images'])} images")
        saved_paths = imagen_api.save_generated_images(
            result['images'],
            app.config['RESULTS_FOLDER'],
            "imagen"
        )
        
        download_urls = [f"/download/{os.path.basename(path)}" for path in saved_paths]
        
        return jsonify({
            'success': True,
            'message': f"{len(saved_paths)} görsel başarıyla oluşturuldu",
            'image_count': len(saved_paths),
            'download_urls': download_urls
        })
        
    except Exception as e:
        app.logger.error(f"Error in generate_image: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Görsel oluşturma hatası: {str(e)}"
        }), 500


def process_vision_file(file_name, file_path, api, prompt, result_data):
    """Görsel dosyasını işle"""
    result_data['messages'].append({
        'type': 'info',
        'text': f"Görüntü işleniyor: {file_name} (Vision API kullanılıyor)"
    })
    
    api_response = api.generate_vision_response(prompt, file_path)
    
    if api_response.get('success'):
        result_data['messages'].append({
            'type': 'success',
            'text': f"Görsel analizi başarıyla tamamlandı: {file_name}"
        })
        return {
            'file_name': file_name,
            'content': api_response.get('content')
        }
    else:
        result_data['messages'].append({
            'type': 'error',
            'text': f"Görsel analizi başarısız: {api_response.get('message', 'Bilinmeyen hata')}"
        })
    return None

def process_text_file(file_name, file_path, file_type, data_processor, result_data):
    """Metin dosyasını işle"""
    chunks = data_processor.process_file(file_path, file_type)
    if not chunks:
        result_data['messages'].append({
            'type': 'warning',
            'text': f"{file_name}: Metin çıkarılamadı!"
        })
        return None
    return "\n\n".join(chunks)

def update_progress(result_data, current_index, total_files):
    """İlerleme durumunu güncelle"""
    progress = ((current_index + 1) / total_files) * 100
    result_data['messages'].append({
        'type': 'info',
        'text': f"İlerleme - Dosya: %{progress:.1f}"
    })

def process_combined_content(content, api, prompt, is_qa, is_summary, is_custom, result_data, all_results):
    """Birleştirilmiş içeriği işle"""
    result_data['messages'].append({
        'type': 'info',
        'text': "Tüm içerik birleştirildi, işleniyor..."
    })
    
    api_response = api.generate_response(prompt, content)
    
    if api_response.get('success'):
        content = api_response.get('content')
        
        if is_qa:
            try:
                extracted_json = api.extract_json(content)
                if extracted_json and "soru-cevaplar" in extracted_json:
                    all_results["soru-cevaplar"] = extracted_json["soru-cevaplar"]
                    
                    result_data['messages'].append({
                        'type': 'success',
                        'text': f"{len(all_results['soru-cevaplar'])} soru-cevap eklendi"
                    })
            except Exception as e:
                result_data['messages'].append({
                    'type': 'warning',
                    'text': f"JSON çıkarma hatası: {str(e)}"
                })
        else:
            # Özet veya özel prompt için içeriği kaydet
            result_data['combined_text'] = content
            
    else:
        result_data['messages'].append({
            'type': 'error',
            'text': f"API hatası: {api_response.get('message')}"
        })
    
    # Sonucu döndür
    return content if api_response.get('success') else None

def process_single_file(file, file_index, files, use_vision, api, prompt, data_processor, 
                       is_summary, is_custom, is_qa, result_data, all_results, combined_text, vision_results):
    """Tek bir dosyayı işle"""
    file_path = file.get('path')
    file_name = file.get('name')
    file_type = file.get('type')
    
    result_data['messages'].append({
        'type': 'info',
        'text': f"Dosya işleniyor: {file_name}"
    })
    
    if use_vision and file_type == 'image':
        vision_response = process_vision_file(file_name, file_path, api, prompt, result_data)
        if vision_response:
            vision_results.append(vision_response)
            process_vision_result(vision_response, is_summary, is_custom, is_qa, 
                                combined_text, all_results, result_data, api)
    else:
        chunks = data_processor.process_file(file_path, file_type)
        if chunks:
            process_text_chunks(chunks, file_index, len(files), prompt, api, 
                              is_summary, is_custom, is_qa, combined_text, 
                              all_results, result_data)

def create_final_result(is_summary, is_custom, is_qa, combined_text, all_results, vision_results, 
                       api, prompt, processing_mode, output_format, results_folder, result_data):
    """Son işlemleri yap ve sonucu oluştur"""
    if is_summary:
        final_content = result_data.get('combined_text', combined_text)
        if final_content:
            if processing_mode != 'combined':
                api_response = api.generate_response(prompt, final_content)
                if api_response.get('success'):
                    final_content = api_response.get('content')
                else:
                    result_data['messages'].append({
                        'type': 'error',
                        'text': f"Özet oluşturma hatası: {api_response.get('message')}"
                    })
                    return
            
            filename = data_processor.save_content(final_content, output_format, results_folder)
            result_data['results'] = create_summary_result(final_content, filename, vision_results)
        
    elif is_custom:
        final_content = result_data.get('combined_text', combined_text)
        if final_content:
            filename = data_processor.save_content(final_content, "TXT", results_folder)
            result_data['results'] = create_custom_result(final_content, filename, vision_results)
        
    elif is_qa and all_results["soru-cevaplar"]:
        filename = data_processor.save_json(all_results, results_folder)
        result_data['results'] = create_qa_result(all_results, filename, vision_results)
        
    elif vision_results:
        vision_text = "\n\n".join([f"--- {vr['file_name']} Analizi ---\n{vr['content']}" 
                                  for vr in vision_results])
        filename = data_processor.save_content(vision_text, "TXT", results_folder)
        result_data['results'] = create_vision_result(vision_text, filename, vision_results)
    else:
        result_data['messages'].append({
            'type': 'warning',
            'text': "İşlenecek sonuç bulunamadı!"
        })

def log_successful_processing(files, prompt_type, result_data):
    """Başarılı işlem loglaması yap"""
    file_names = [file.get('name') for file in files]
    result_file = result_data['results'].get('filename', None)
    
    # İşlemi loglama
    log_processing(file_names, prompt_type, True, result_file)
    
    # Veritabanını yedekle
    backup_database()
    
    app.logger.info(f"Logged successful processing: {prompt_type}, files: {file_names}")
    
    # Sonucu veritabanına kaydet
    try:
        save_processing_result(result_data, prompt_type, file_names)
    except Exception as e:
        app.logger.error(f"Sonuç kaydedilirken hata: {str(e)}")

def log_error_and_return(error, files, prompt_type):
    """Hata durumunu logla"""
    file_names = [file.get('name') for file in files]
    log_processing(file_names, prompt_type, False)
    app.logger.error(f"Failed processing: {prompt_type}, files: {file_names}, error: {str(error)}")

def create_summary_result(content, filename, vision_results):
    """Özet sonucu oluştur"""
    return {
        'type': 'summary',
        'content': content,
        'filename': filename,
        'download_url': f"/download/{filename}",
        'vision_results': vision_results if vision_results else None
    }

def create_custom_result(content, filename, vision_results):
    """Özel sonuç oluştur"""
    return {
        'type': 'custom',
        'content': content,
        'filename': filename,
        'download_url': f"/download/{filename}",
        'vision_results': vision_results if vision_results else None
    }

def create_qa_result(content, filename, vision_results):
    """Soru-cevap sonucu oluştur"""
    return {
        'type': 'qa_pairs',
        'content': content,
        'filename': filename,
        'download_url': f"/download/{filename}",
        'vision_results': vision_results if vision_results else None
    }

def create_vision_result(content, filename, vision_results):
    """Görsel analizi sonucu oluştur"""
    return {
        'type': 'vision_analysis',
        'content': content,
        'filename': filename,
        'download_url': f"/download/{filename}",
        'vision_results': vision_results
    }

def process_vision_result(vision_response, is_summary, is_custom, is_qa, combined_text, all_results, result_data):
    """Görsel analizi sonucunu işle"""
    vision_content = vision_response['content']
    
    if is_summary:
        combined_text += vision_content + "\n\n"
    elif is_custom:
        if not combined_text:
            combined_text = vision_content
        else:
            combined_text += "\n\n" + vision_content
    elif is_qa:
        try:
            # Doğrudan JSON işle
            import json
            import re
            
            # JSON formatını bulmaya çalış
            json_match = re.search(r'({.*})', vision_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                extracted_json = json.loads(json_str)
            else:
                # Başka bir yöntem dene
                start_idx = vision_content.find('{')
                end_idx = vision_content.rfind('}') + 1
                
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = vision_content[start_idx:end_idx]
                    extracted_json = json.loads(json_str)
                else:
                    extracted_json = None
            
            if extracted_json and "soru-cevaplar" in extracted_json:
                existing_questions = {qa.get("soru", "") for qa in all_results["soru-cevaplar"]}
                new_qa_pairs = []
                
                for qa in extracted_json["soru-cevaplar"]:
                    if qa.get("soru", "") not in existing_questions and qa.get("soru", "").strip():
                        new_qa_pairs.append(qa)
                
                all_results["soru-cevaplar"].extend(new_qa_pairs)
                
                result_data['messages'].append({
                    'type': 'success',
                    'text': f"{len(new_qa_pairs)} yeni soru-cevap eklendi (görsel analizi)"
                })
        except Exception as e:
            result_data['messages'].append({
                'type': 'warning',
                'text': f"Görsel analizinden JSON çıkarma hatası: {str(e)}"
            })

def process_text_chunks(chunks, file_index, total_files, prompt, api, is_summary, is_custom, is_qa, 
                       combined_text, all_results, result_data):
    """Metin parçalarını işle"""
    for chunk_index, chunk in enumerate(chunks):
        result_data['messages'].append({
            'type': 'info',
            'text': f"Bölüm {chunk_index + 1}/{len(chunks)} işleniyor... (Dosya: {file_index + 1}/{total_files})"
        })
        
        if is_summary:
            # combined_text yerine result_data kullanımı
            if 'combined_text' not in result_data:
                result_data['combined_text'] = ""
            result_data['combined_text'] += chunk + "\n\n"
        else:
            api_response = api.generate_response(prompt, chunk)
            
            if api_response.get('success'):
                content = api_response.get('content')
                
                if is_custom:
                    # combined_text yerine result_data kullanımı
                    if 'combined_text' not in result_data:
                        result_data['combined_text'] = ""
                    result_data['combined_text'] += (result_data['combined_text'] and "\n\n" or "") + content
                elif is_qa:
                    process_qa_content(content, all_results, result_data)
            else:
                result_data['messages'].append({
                    'type': 'error',
                    'text': f"API hatası: {api_response.get('message')}"
                })
        
        # Calculate progress
        file_progress = ((file_index + 1) / total_files) * 100
        chunk_progress = ((chunk_index + 1) / len(chunks)) * 100
        
        result_data['messages'].append({
            'type': 'info',
            'text': f"İlerleme - Dosya: %{file_progress:.1f}, Bölüm: %{chunk_progress:.1f}"
        })


def process_qa_content(content, all_results, result_data):
    """Soru-cevap içeriğini işle"""
    try:
        # Doğrudan JSON işle
        import json
        import re
        
        # JSON formatını bulmaya çalış
        json_match = re.search(r'({.*})', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            extracted_json = json.loads(json_str)
        else:
            # Başka bir yöntem dene
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                extracted_json = json.loads(json_str)
            else:
                extracted_json = None
        
        if extracted_json and "soru-cevaplar" in extracted_json:
            existing_questions = {qa.get("soru", "") for qa in all_results["soru-cevaplar"]}
            new_qa_pairs = []
            
            for qa in extracted_json["soru-cevaplar"]:
                if qa.get("soru", "") not in existing_questions and qa.get("soru", "").strip():
                    new_qa_pairs.append(qa)
            
            all_results["soru-cevaplar"].extend(new_qa_pairs)
            
            result_data['messages'].append({
                'type': 'success',
                'text': f"{len(new_qa_pairs)} yeni soru-cevap eklendi"
            })
    except Exception as e:
        result_data['messages'].append({
            'type': 'warning',
            'text': f"JSON çıkarma hatası: {str(e)}"
        })

def save_processing_result(result_data, prompt_type, file_names):
    """İşlem sonucunu veritabanına kaydet"""
    try:
        result_type = result_data['results'].get('type')
        content = result_data['results'].get('content')
        
        # dict tipini JSON string'e çevir
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
            
        save_result(
            title=f"{prompt_type} - {file_names[0] if file_names else 'İsimsiz'}",
            description=f"İşlem sonucu: {result_type}",
            result_type=result_type,
            content=content,
            source_file=result_data['results'].get('filename'),
            processing_log_id=None,
            tags=[]
        )
    except Exception as e:
        app.logger.error(f"Sonuç kaydedilirken hata: {str(e)}")

@app.route('/api/saved-results/<int:result_id>', methods=['GET'])
def get_saved_result(result_id):
    """Get details of a saved result"""
    try:
        db = get_db()
        result = db.execute('SELECT * FROM saved_results WHERE id = ?', (result_id,)).fetchone()
        
        if not result:
            return jsonify({
                'success': False,
                'message': 'Sonuç bulunamadı'
            }), 404
        
        # Sonuç verilerini sözlüğe dönüştür
        result_data = dict(result)
        
        # Content JSON ise parse et
        if isinstance(result_data['content'], str):
            try:
                if result_data['content'].startswith('{') or result_data['content'].startswith('['):
                    result_data['content'] = json.loads(result_data['content'])
            except json.JSONDecodeError:
                # JSON olarak parse edilemezse string olarak bırak
                pass
        
        # Etiketleri al
        tags = []
        if result_data['processing_log_id']:
            log = db.execute('SELECT tags FROM processing_logs WHERE id = ?', 
                           (result_data['processing_log_id'],)).fetchone()
            if log and log['tags']:
                try:
                    tags = json.loads(log['tags'])
                except:
                    tags = []
        
        return jsonify({
            'success': True,
            'result': {
                'id': result_data['id'],
                'title': result_data['title'],
                'description': result_data['description'],
                'result_type': result_data['result_type'],
                'content': result_data['content'],
                'source_file': result_data['source_file'],
                'created_at': result_data['created_at'],
                'updated_at': result_data['updated_at'],
                'processing_log_id': result_data['processing_log_id'],
                'tags': tags
            }
        })
    except Exception as e:
        app.logger.error(f"Sonuç detayları alınırken hata: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Sonuç detayları alınırken bir hata oluştu: {str(e)}'
        }), 500

@app.route('/api/saved-results/<int:result_id>', methods=['DELETE'])
def delete_saved_result(result_id):
    """Delete a saved result"""
    try:
        db = get_db()
        
        # Silinecek sonucu kontrol et
        result = db.execute('SELECT * FROM saved_results WHERE id = ?', (result_id,)).fetchone()
        if not result:
            return jsonify({
                'success': False,
                'message': 'Silinecek sonuç bulunamadı'
            }), 404
        
        # Sonucu sil
        db.execute('DELETE FROM saved_results WHERE id = ?', (result_id,))
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Sonuç başarıyla silindi'
        })
    except Exception as e:
        app.logger.error(f"Sonuç silinirken hata: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Sonuç silinirken bir hata oluştu: {str(e)}'
        }), 500
    
@app.route('/api/recent-processings')
def get_recent_processings():
    """Get recent processing logs"""
    try:
        limit = request.args.get('limit', default=3, type=int)
        logs = get_processing_logs(limit)
        
        return jsonify({
            'success': True,
            'logs': logs
        })
    except Exception as e:
        app.logger.error(f"Error getting recent processings: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Son işlemler alınırken bir hata oluştu: {str(e)}'
        }), 500

if __name__ == '__main__':
    # Uygulama başlamadan önce veritabanını kontrol et
    check_database()
    app.run(debug=True)


