# Upwork Agent Pro

Upwork işlerini analiz eden, fırsatları filtreleyip puanlayan ve doğrulanmış profil bilgilerine dayanarak teklif taslakları hazırlayan satışa hazır bir yardımcı ajan.

## Ürün olarak ne satılıyor?
- İş keşfi ve filtreleme
- Bütçe / Connects / ödeme doğrulama kapıları
- Fırsat puanlama
- Teklif taslağı üretimi
- Screening soruları için güvenli taslaklar
- İnsan onaylı başvuru akışı
- Testler ve GitHub Actions
- Alıcı kurulum ve satış dokümantasyonu

## Güvenlik ve sınırlar
- Connects otomatik harcanmaz.
- Teklif gönderimi insan onayı olmadan yapılmaz.
- Deneyim, sonuç, sertifika veya portföy uydurulmaz.
- Özel profil ve çalışma verileri Git'e gönderilmez.
- İlan metni güvenilmeyen içerik olarak ele alınır.
- Bütçe ve Connects kapıları başvuru öncesinde uygulanır.
- Upwork ile resmi bağlantı, ortaklık veya onay iddiası yoktur.

## Akış
1. İşleri getir
2. Normalize et
3. Filtrele ve puanla
4. Uygunluk kapısından geçir
5. Teklif ve screening taslaklarını oluştur
6. Kullanıcı incelemesi
7. Açık kullanıcı onayı
8. Yetkili entegrasyon üzerinden gönderim
9. Takip

## Ticari paketler
- Starter: $29 tek sefer
- Pro: $79 tek sefer
- Agency: $149 tek sefer

Bunlar önerilen ürün paketleridir; gelir veya iş sonucu garantisi değildir.

## Satış materyalleri
- sales/PRODUCT.md
- sales/SETUP.md
- sales/FAQ.md
- site/index.html

## Yerel kurulum
Python 3.12+ kullanın. agent/profile.example.json dosyasını agent/profile.json olarak kopyalayın ve yalnızca doğrulanmış bilgileri girin. agent/profile.json Git tarafından yok sayılır.

## Test

    python -m compileall -q agent tests
    python -m unittest discover -s tests -v

## Lisans
Bu repo ticari/proprietary lisansla dağıtılır. Ayrı bir satın alma lisansı verilmedikçe yeniden satış, yeniden dağıtım veya rakip hosted ürün olarak sunma yasaktır.
