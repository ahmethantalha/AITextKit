# Katkıda Bulunma Rehberi

Metin Analiz Uygulaması'na katkıda bulunmak istediğiniz için teşekkür ederiz! Bu belge, projeye nasıl katkıda bulunabileceğiniz konusunda rehberlik sağlamak için hazırlanmıştır.

## Nasıl Katkıda Bulunabilirsiniz?

Projeye aşağıdaki şekillerde katkıda bulunabilirsiniz:

1. **Hata Raporları**: Bulduğunuz hataları GitHub Issues üzerinden bildirebilirsiniz
2. **Özellik Önerileri**: Yeni özellik fikirlerinizi paylaşabilirsiniz
3. **Kod Katkıları**: Yeni özellikler ekleyebilir veya hataları düzeltebilirsiniz
4. **Dokümantasyon**: Belgelendirme ve açıklamaları iyileştirebilirsiniz
5. **Testler**: Birim testleri veya entegrasyon testleri yazabilirsiniz

## Geliştirme Ortamının Kurulumu

1. Repoyu klonlayın:
git clone https://github.com/kullaniciadi/metin-analiz-uygulamasi.git

consolede (Cmd veya powershell Windows için)
cd metin-analiz-uygulamasi

2. Sanal ortam oluşturun ve etkinleştirin:
python -m venv venv

Windows
venv\Scripts\activate
Linux/macOS
source venv/bin/activate

3. Gerekli paketleri yükleyin:
pip install -r requirements.txt

4. `.env.example` dosyasını `.env` olarak kopyalayın ve gerekli API anahtarlarını ekleyin

5. Dizin yapısını oluşturun:
mkdir -p uploads results database/backups

6. Veritabanını başlatın:
python -c "from app import init_db; init_db()"

7. Uygulamayı başlatın:
python app.py

## Katkı İş Akışı

1. Projeyi forklayın ve kendi kopyanızı oluşturun
2. Yeni bir branch oluşturun: `git checkout -b feature/yeni-ozellik` veya `fix/hata-duzeltme`
3. Değişikliklerinizi yapın ve kodunuzu test edin
4. Değişikliklerinizi commit edin: `git commit -am 'Özellik: Yeni özellik eklendi'`
5. Branch'inizi GitHub'a gönderin: `git push origin feature/yeni-ozellik`
6. GitHub üzerinden bir Pull Request oluşturun

## Kodlama Standartları

Projede aşağıdaki kodlama standartlarına uyulması beklenmektedir:

1. **Python Kodu**:
- PEP 8 kurallarına uygun kod yazımı
- Belirli bir işlevi olan fonksiyonlar ve sınıflar için docstring kullanımı
- Anlamlı değişken ve fonksiyon isimleri

2. **JavaScript**:
- ESLint veya benzeri bir kod biçimlendirici kullanılması
- Fonksiyonların üzerine açıklamalar yazılması
- Modern JavaScript özellikleri (ES6+) kullanımı

3. **HTML/CSS**:
- Semantik HTML kullanımı
- Responsive tasarım prensiplerine uygun yapı
- CSS sınıfları için anlamlı isimler (BEM metodolojisi tercih edilir)

## Sürüm Kontrolü

- Semantic Versioning (SemVer) kullanıyoruz: MAJOR.MINOR.PATCH
- Commit mesajları için "conventional commits" formatını kullanıyoruz:
- `feat:` - Yeni özellikler
- `fix:` - Hata düzeltmeleri
- `docs:` - Sadece dokümantasyon değişiklikleri
- `style:` - Kodun anlamını değiştirmeyen formatlamalar
- `refactor:` - Hata düzeltmeyen ve yeni özellik eklemeyen kod değişiklikleri
- `perf:` - Performans iyileştirmeleri
- `test:` - Test ekleme veya düzeltme
- `chore:` - Bakım değişiklikleri

## API Anahtarları ve Hassas Bilgiler

- Asla API anahtarlarını veya gizli bilgileri kodunuza eklemeyin
- Çevre değişkenleri veya `.env` dosyası kullanın
- Örnekler için sansürlenmiş anahtar değerleri kullanın: `YOUR_API_KEY`

## Testler

Yeni bir özellik eklediğinizde veya hata düzelttiğinizde, uygun testler yazmanız beklenmektedir. 

```python
# test_example.py
def test_yeni_ozellik():
 # Test kodunuz burada
 assert sonuc == beklenen_deger

Yardım Alma
Eğer katkıda bulunma sürecinde yardıma ihtiyacınız olursa:

GitHub Issues üzerinden soru sorabilirsiniz
GitHub Discussions sayfasını ziyaret edebilirsiniz

Katkılarınız için şimdiden teşekkür ederiz!



