# Gözlemevi yazı tipleri

Üç aile, yerel woff2 — `@font-face` tanımları `frontend/css/fontlar-gozlemevi.css`'te.
Her aile değişken font; `latin` ve `latin-ext` ayrı dosya, `unicode-range` ile seçilir.

| Dosya | Aile | Stil | Alt küme | Bayt | sha256 (ilk 16) |
|---|---|---|---|---|---|
| `fraunces-italik-latinext.woff2` | Fraunces | italic | latin-ext | 40528 | `877bcc2fd1be299c` |
| `fraunces-italik-latin.woff2` | Fraunces | italic | latin | 45656 | `bceec2ef4d549efb` |
| `fraunces-latinext.woff2` | Fraunces | normal | latin-ext | 33584 | `a21ecfbf41fbc393` |
| `fraunces-latin.woff2` | Fraunces | normal | latin | 36620 | `7f9d191d999336d3` |
| `figtree-latinext.woff2` | Figtree | normal | latin-ext | 10280 | `bf7828e2c258cffc` |
| `figtree-latin.woff2` | Figtree | normal | latin | 20156 | `4ba7d3d096695818` |
| `martian-mono-latinext.woff2` | Martian Mono | normal | latin-ext | 24660 | `21fce7e290a2395b` |
| `martian-mono-latin.woff2` | Martian Mono | normal | latin | 38492 | `f9c1655c2c9d1ed5` |

Toplam 249 976 bayt. Eksenler: Fraunces wght 400-700 · Figtree wght 400-700 · Martian Mono wdth 75-112,5 + wght 400-800.

## Kaynak
Google Fonts css2 (woff2):
- `https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400..700;1,400..700&display=swap`
- `https://fonts.googleapis.com/css2?family=Figtree:wght@400..700&family=Martian+Mono:wdth,wght@75..112.5,400..800&display=swap`

Yenilemek: aynı adresi çek, `/* latin */` ve `/* latin-ext */` bloklarındaki woff2'leri bu adlarla kaydet,
`fontlar-gozlemevi.css`'teki `unicode-range`'i güncelle, bağlayan sayfadaki `?v=`'yi artır.

## Lisans
Üçü de SIL Open Font License 1.1: `OFL-fraunces.txt` (github.com/undercasetype/Fraunces) ·
`OFL-figtree.txt` · `OFL-martian-mono.txt` (github.com/google/fonts).
