DROP TABLE IF EXISTS processing_logs;

CREATE TABLE processing_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    files TEXT NOT NULL,
    prompt_type TEXT NOT NULL,
    success BOOLEAN NOT NULL DEFAULT 0,
    result_file TEXT,
    notes TEXT,  -- Kullanıcı notları için
    tags TEXT,   -- Etiketler (JSON formatında)
    starred BOOLEAN NOT NULL DEFAULT 0  -- Yıldızlı işaretleme
);

-- Özel İşlem Türleri tablosu
CREATE TABLE IF NOT EXISTS custom_prompt_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    prompt_text TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Sonuçları saklamak için yeni tablo
CREATE TABLE IF NOT EXISTS saved_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    result_type TEXT NOT NULL,  -- 'summary', 'qa_pairs', 'custom' vb.
    content TEXT NOT NULL,      -- Sonucun içeriği (JSON veya metin)
    source_file TEXT,           -- Kaynak dosya(lar)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processing_log_id INTEGER,  -- İlgili işlem kaydına referans
    FOREIGN KEY (processing_log_id) REFERENCES processing_logs (id)
);