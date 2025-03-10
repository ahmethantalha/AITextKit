import os
import sqlite3
from flask import Flask

app = Flask(__name__)
app.config.from_pyfile('config.py')
DATABASE = app.config['DATABASE']

def cleanup_database():
    try:
        print("Veritabanı temizleme işlemi başlatılıyor...")
        
        # Veritabanına bağlan
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        db = conn.cursor()
        
        # Mevcut kayıt sayılarını göster
        print("\nTemizlik öncesi kayıt sayıları:")
        db.execute("SELECT COUNT(*) FROM processing_logs")
        print(f"İşlem kayıtları: {db.fetchone()[0]}")
        
        db.execute("SELECT COUNT(*) FROM saved_results")
        print(f"Kayıtlı sonuçlar: {db.fetchone()[0]}")
        
        db.execute("SELECT COUNT(*) FROM custom_prompt_types")
        print(f"Özel prompt türleri: {db.fetchone()[0]}")
        
        # Tekrarlanan kayıtları temizle
        print("\nTekrarlanan kayıtlar temizleniyor...")
        
        # saved_results tablosundaki tekrarları temizle
        db.execute("""
        DELETE FROM saved_results 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM saved_results 
            GROUP BY title, description, content, result_type
        )
        """)
        print(f"Silinen tekrarlanan sonuç sayısı: {db.rowcount}")
        
        # processing_logs tablosundaki tekrarları temizle
        db.execute("""
        DELETE FROM processing_logs 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM processing_logs 
            GROUP BY files, prompt_type, result_file
        )
        """)
        print(f"Silinen tekrarlanan log sayısı: {db.rowcount}")
        
        # İşlemi kaydet
        conn.commit()
        
        # Temizlik sonrası kayıt sayılarını göster
        print("\nTemizlik sonrası kayıt sayıları:")
        db.execute("SELECT COUNT(*) FROM processing_logs")
        print(f"İşlem kayıtları: {db.fetchone()[0]}")
        
        db.execute("SELECT COUNT(*) FROM saved_results")
        print(f"Kayıtlı sonuçlar: {db.fetchone()[0]}")
        
        db.execute("SELECT COUNT(*) FROM custom_prompt_types")
        print(f"Özel prompt türleri: {db.fetchone()[0]}")
        
        # Bağlantıyı kapat
        conn.close()
        
        print("\nVeritabanı temizleme işlemi başarıyla tamamlandı!")
        return True
        
    except Exception as e:
        print(f"\nHATA: Veritabanı temizleme işlemi sırasında bir hata oluştu: {str(e)}")
        return False

if __name__ == '__main__':
    with app.app_context():
        cleanup_database() 