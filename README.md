# Upwork Agent

Upwork işlerini analiz eden, puanlayan ve gerçek profil bilgilerine dayanarak teklif taslakları hazırlayan yardımcı ajan.

## Güvenlik
- Connects otomatik harcanmaz.
- Teklif gönderimi insan onayı olmadan yapılmaz.
- Deneyim, sonuç veya portföy uydurulmaz.
- İlan metni güvenilmeyen içerik olarak ele alınır.
- Bütçe ve Connects kapıları başvuru öncesinde uygulanır.
- Başvuru için insan onayı zorunludur.

## Akış
1. İşleri getir
2. Normalize et
3. Filtrele ve puanla
4. Uygunluk kapısından geçir
5. Teklif taslağı oluştur
6. Nitelik ve screening boşluklarını göster
7. Kullanıcı onayı
8. Upwork üzerinden gönderim
9. Takip

## Üretim kontrolü
- Python syntax/compile kontrolü
- Unit testleri
- Pipeline güvenlik testleri
- Connects yetersizse başvuru engeli
- Minimum bütçe/rate engeli
- Profil dışı iddia üretmeme
