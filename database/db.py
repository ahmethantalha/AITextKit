import json
import os
import sqlite3
import datetime
from flask import g, current_app

def get_db():
    """Connect to the database with improved durability settings"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None  # otomatik commit
        )
        g.db.row_factory = sqlite3.Row
        
        # Daha sıkı senkronizasyon modu ayarla
        g.db.execute('PRAGMA synchronous=FULL')
        g.db.execute('PRAGMA journal_mode=WAL')
    
    return g.db

def close_db(e=None):
    """Close the database connection"""
    db = g.pop('db', None)
    
    if db is not None:
        db.close()

def init_db(preserve_settings=True, preserve_logs=True):
    """Initialize the database schema with option to preserve settings and logs"""
    db = get_db()
    
    # Ayarları ve logları korumak istiyorsak, önce mevcut verileri alalım
    saved_settings = {}
    saved_logs = []
    saved_custom_prompts = []
    saved_results = []
    
    if preserve_settings or preserve_logs:
        try:
            # app_settings tablosunu kontrol et
            if preserve_settings:
                settings_exist = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'").fetchone()
                if settings_exist:
                    settings = db.execute('SELECT key, value FROM app_settings').fetchall()
                    saved_settings = {setting['key']: setting['value'] for setting in settings}
            
            # processing_logs ve saved_results tablolarını kontrol et
            if preserve_logs:
                logs_exist = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processing_logs'").fetchone()
                if logs_exist:
                    logs = db.execute('SELECT * FROM processing_logs').fetchall()
                    saved_logs = [dict(log) for log in logs]
                
                results_exist = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='saved_results'").fetchone()
                if results_exist:
                    results = db.execute('SELECT * FROM saved_results').fetchall()
                    saved_results = [dict(result) for result in results]
                
                prompts_exist = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custom_prompt_types'").fetchone()
                if prompts_exist:
                    prompts = db.execute('SELECT * FROM custom_prompt_types').fetchall()
                    saved_custom_prompts = [dict(prompt) for prompt in prompts]
        except Exception as e:
            print(f"Mevcut verileri okuma hatası: {str(e)}")
            saved_settings = {}
            saved_logs = []
            saved_custom_prompts = []
            saved_results = []
    
    # Schema'yı uygula (tabloları yeniden oluşturur)
    with current_app.open_resource('database/schema.sql') as f:
        db.executescript(f.read().decode('utf8'))
    
    try:
        # Ayarları geri yükle
        if preserve_settings and saved_settings:
            db.executemany('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', 
                         [(k, v) for k, v in saved_settings.items()])
        
        # Custom prompt tiplerini yükle
        if saved_custom_prompts:
            for prompt in saved_custom_prompts:
                keys = [k for k in prompt.keys() if k != 'id']
                placeholders = ', '.join(['?'] * len(keys))
                columns = ', '.join(keys)
                values = [prompt[k] for k in keys]
                db.execute(f'INSERT OR IGNORE INTO custom_prompt_types ({columns}) VALUES ({placeholders})', values)
        
        # Logları yükle
        if saved_logs:
            for log in saved_logs:
                keys = [k for k in log.keys() if k != 'id']
                placeholders = ', '.join(['?'] * len(keys))
                columns = ', '.join(keys)
                values = [log[k] for k in keys]
                db.execute(f'INSERT OR IGNORE INTO processing_logs ({columns}) VALUES ({placeholders})', values)
        
        # Sonuçları yükle
        if saved_results:
            for result in saved_results:
                keys = [k for k in result.keys() if k != 'id']
                placeholders = ', '.join(['?'] * len(keys))
                columns = ', '.join(keys)
                values = [result[k] for k in keys]
                db.execute(f'INSERT OR IGNORE INTO saved_results ({columns}) VALUES ({placeholders})', values)
        
        # Tüm değişiklikleri tek seferde commit et
        db.commit()
        
    except Exception as e:
        print(f"Veritabanı yükleme hatası: {str(e)}")
        # Hata durumunda rollback yap
        db.rollback()
        raise

def log_processing(file_names, prompt_type, success, result_file=None):
    """Log a processing job to the database"""
    db = get_db()
    timestamp = datetime.datetime.now()
    
    db.execute(
        'INSERT INTO processing_logs (timestamp, files, prompt_type, success, result_file) VALUES (?, ?, ?, ?, ?)',
        (timestamp, ', '.join(file_names), prompt_type, 1 if success else 0, result_file)
    )
    db.commit()

def get_processing_logs(limit=50):
    """Get recent processing logs"""
    db = get_db()
    try:
        logs = db.execute(
            'SELECT * FROM processing_logs ORDER BY timestamp DESC LIMIT ?',
            (limit,)
        ).fetchall()
        
        result = []
        for log in logs:
            # JSON formatındaki etiketleri parse et
            tags = []
            if log['tags']:
                try:
                    tags = json.loads(log['tags'])
                except:
                    pass  # Geçersiz JSON formatı
            
            # Tüm alanları içeren bir sözlük oluştur
            log_dict = {
                'id': log['id'],
                'timestamp': log['timestamp'],
                'files': log['files'],
                'prompt_type': log['prompt_type'],
                'success': bool(log['success']),
                'result_file': log['result_file'],
                'notes': log['notes'] or '',
                'tags': tags,
                'starred': bool(log['starred'] or 0)
            }
            result.append(log_dict)
        
        return result
    except Exception as e:
        print(f"Error in get_processing_logs: {str(e)}")
        return []

def save_custom_prompt_type(name, prompt_text):
    """Save a custom prompt type to the database"""
    db = get_db()
    try:
        cursor = db.execute(
            'INSERT INTO custom_prompt_types (name, prompt_text) VALUES (?, ?)',
            (name, prompt_text)
        )
        db.commit()
        
        # Yeni eklenen kaydın ID'sini al
        new_id = cursor.lastrowid
        
        # Yeni eklenen kaydı döndür
        new_prompt = {
            'id': new_id,
            'name': name,
            'prompt_text': prompt_text,
            'created_at': datetime.datetime.now().isoformat()
        }
        
        return True, "Özel işlem türü başarıyla kaydedildi.", new_prompt
    except sqlite3.IntegrityError:
        # Name already exists, try to update instead
        try:
            db.execute(
                'UPDATE custom_prompt_types SET prompt_text = ? WHERE name = ?',
                (prompt_text, name)
            )
            db.commit()
            
            # Güncellenen kaydı bul
            updated_prompt = db.execute(
                'SELECT id, name, prompt_text, created_at FROM custom_prompt_types WHERE name = ?',
                (name,)
            ).fetchone()
            
            updated_prompt_dict = {
                'id': updated_prompt['id'],
                'name': updated_prompt['name'],
                'prompt_text': updated_prompt['prompt_text'],
                'created_at': updated_prompt['created_at']
            }
            
            return True, "Özel işlem türü başarıyla güncellendi.", updated_prompt_dict
        except Exception as e:
            return False, f"Özel işlem türü güncellenirken hata oluştu: {str(e)}", None
    except Exception as e:
        return False, f"Özel işlem türü kaydedilirken hata oluştu: {str(e)}", None

def get_custom_prompt_types():
    """Get all custom prompt types from the database"""
    db = get_db()
    custom_types = db.execute(
        'SELECT id, name, prompt_text, created_at FROM custom_prompt_types ORDER BY name'
    ).fetchall()
    
    return [{
        'id': ct['id'],
        'name': ct['name'],
        'prompt_text': ct['prompt_text'],
        'created_at': ct['created_at']
    } for ct in custom_types]

def delete_custom_prompt_type(prompt_id):
    """Delete a custom prompt type from the database"""
    db = get_db()
    try:
        db.execute('DELETE FROM custom_prompt_types WHERE id = ?', (prompt_id,))
        db.commit()
        return True, "Özel işlem türü başarıyla silindi."
    except Exception as e:
        return False, f"Özel işlem türü silinirken hata oluştu: {str(e)}"
    
def update_setting(key, value):
    """Update or insert a setting in the database"""
    db = get_db()
    try:
        db.execute(
            'INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)',
            (key, value)
        )
        db.commit()
        return True, f"Ayar '{key}' başarıyla güncellendi."
    except Exception as e:
        return False, f"Ayar güncellenirken hata oluştu: {str(e)}"

def get_setting(key, default=None):
    """Get a setting from the database"""
    db = get_db()
    setting = db.execute(
        'SELECT value FROM app_settings WHERE key = ?',
        (key,)
    ).fetchone()
    
    if setting:
        return setting['value']
    return default

def update_custom_prompt_type(prompt_id, name, prompt_text):
    """Update a custom prompt type in the database"""
    db = get_db()
    try:
        # Check if name already exists for another prompt type
        existing = db.execute(
            'SELECT id FROM custom_prompt_types WHERE name = ? AND id != ?',
            (name, prompt_id)
        ).fetchone()
        
        if existing:
            return False, f'"{name}" adında başka bir işlem türü zaten var.'
        
        db.execute(
            'UPDATE custom_prompt_types SET name = ?, prompt_text = ? WHERE id = ?',
            (name, prompt_text, prompt_id)
        )
        db.commit()
        return True, "Özel işlem türü başarıyla güncellendi."
    except Exception as e:
        return False, f"Özel işlem türü güncellenirken hata oluştu: {str(e)}"
    

def save_result(title, description, result_type, content, source_file=None, processing_log_id=None, tags=None):
    """Save a result to the database"""
    db = get_db()
    created_at = datetime.datetime.now()
    
    cursor = db.execute(
        'INSERT INTO saved_results (title, description, result_type, content, source_file, created_at, updated_at, processing_log_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (title, description, result_type, content, source_file, created_at, created_at, processing_log_id)
    )
    db.commit()
    
    # İşlem kaydı varsa, tags'i güncelle
    if processing_log_id and tags:
        tags_json = json.dumps(tags)
        db.execute('UPDATE processing_logs SET tags = ? WHERE id = ?', (tags_json, processing_log_id))
        db.commit()
    
    return cursor.lastrowid

def get_saved_results(limit=50, result_type=None, search_query=None):
    """Get saved results with optional filtering"""
    db = get_db()
    try:
        query = 'SELECT * FROM saved_results'
        params = []
        
        # Filtreleri uygula
        conditions = []
        if result_type:
            conditions.append('result_type = ?')
            params.append(result_type)
        
        if search_query:
            conditions.append('(title LIKE ? OR description LIKE ? OR content LIKE ?)')
            search_term = f'%{search_query}%'
            params.extend([search_term, search_term, search_term])
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        # Benzersiz sonuçları al (aynı içeriğe sahip olanlardan sadece birini)
        query += ' GROUP BY content'
        
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)
        
        print(f"SQL Query: {query}, Params: {params}")  # Debug için
        results = db.execute(query, params).fetchall()
        
        result_list = []
        for res in results:
            # İlgili işlem kaydından etiketleri al
            tags = []
            if res['processing_log_id']:
                log = db.execute('SELECT tags FROM processing_logs WHERE id = ?', 
                               (res['processing_log_id'],)).fetchone()
                if log and log['tags']:
                    try:
                        tags = json.loads(log['tags'])
                    except:
                        pass  # Geçersiz JSON formatı
            
            # Eğer content JSON formatında ise, parse et
            content = res['content']
            if content and isinstance(content, str):
                try:
                    if (content.startswith('{') or content.startswith('[')):
                        content = json.loads(content)
                except Exception as e:
                    print(f"JSON parse error: {e}")
                    # JSON olarak parse edilemiyorsa, string olarak devam et
            
            result_dict = {
                'id': res['id'],
                'title': res['title'],
                'description': res['description'],
                'result_type': res['result_type'],
                'content': content,
                'source_file': res['source_file'],
                'created_at': res['created_at'],
                'updated_at': res['updated_at'],
                'processing_log_id': res['processing_log_id'],
                'tags': tags
            }
            result_list.append(result_dict)
        
        return result_list
    except Exception as e:
        print(f"Error in get_saved_results: {str(e)}")
        return []

def update_log_notes(log_id, notes):
    """Update notes for a processing log"""
    db = get_db()
    db.execute('UPDATE processing_logs SET notes = ? WHERE id = ?', (notes, log_id))
    db.commit()
    return True

def toggle_log_star(log_id):
    """Toggle starred status for a log"""
    db = get_db()
    current = db.execute('SELECT starred FROM processing_logs WHERE id = ?', (log_id,)).fetchone()
    if current:
        new_status = 1 if current['starred'] == 0 else 0
        db.execute('UPDATE processing_logs SET starred = ? WHERE id = ?', (new_status, log_id))
        db.commit()
        return new_status
    return None

def backup_database():
    """Backup the database to ensure data persistence"""
    try:
        db_path = current_app.config['DATABASE']
        backup_dir = os.path.join(os.path.dirname(db_path), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = os.path.join(backup_dir, f'text_analysis_backup_{timestamp}.db')
        
        # Veritabanı kopyalama
        import shutil
        shutil.copy2(db_path, backup_path)
        
        # Eski yedekleri temizle (son 5 yedek kalsın)
        backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) 
                         if f.startswith('text_analysis_backup_')])
        
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                os.remove(old_backup)
                
        return True
    except Exception as e:
        current_app.logger.error(f"Veritabanı yedekleme hatası: {str(e)}")
        return False