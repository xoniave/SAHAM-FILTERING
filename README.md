# IDX Decision Dashboard v4

## Fokus v4
- Scanner tidak lagi hilang saat detail saham dibuka atau saat scan ulang berjalan.
- Scan ulang berjalan di background dan menampilkan persen progres.
- Chart detail menggunakan TradingView Lightweight Charts™: zoom, pan, crosshair, skala harga interaktif.
- Support/Resistance dinamis tampil sebagai price line; HH/HL/LH/LL, breakout/breakdown, dan candlestick/chart pattern menjadi marker.
- UI umum Bahasa Indonesia; istilah teknikal tetap dipertahankan.
- Provider REAL EOD dapat memeriksa sesi IDX terbaru otomatis saat server hidup.
- Jika dashboard sempat tidak dibuka beberapa hari, completed-session summary di antara snapshot lama dan baru dicoba di-backfill ke cache history yang sudah ada.

## Penting: EOD bukan LIVE
REAL EOD berarti analisis menggunakan sesi perdagangan yang sudah selesai, bukan transaksi intraday yang sedang bergerak. Sebelum 18:00 WIB provider sengaja mencari sesi sebelumnya supaya candle hari berjalan tidak diperlakukan sebagai candle final.

True LIVE tetap membutuhkan provider/broker/licensed market-data feed yang mendukung programmatic access.

## Upgrade dari v3.1
Gunakan paket UPDATE v4 dan extract langsung ke folder project v3.1 yang sekarang. Pilih Replace/Overwrite jika Windows bertanya. Paket UPDATE tidak berisi `app/data`, sehingga history, symbols, scanner snapshot, dan database portofolio lokal tetap dipertahankan.

Setelah overwrite:
1. Stop server lama dengan Ctrl+C.
2. Jalankan RUN.bat lagi.
3. Hard refresh browser dengan Ctrl+F5.

Tidak perlu menjalankan SYNC_REAL_DATA.bat ulang jika v3.1 kamu sudah memiliki universe/history lengkap.

## Chart
- Scroll wheel: zoom horizontal.
- Drag chart: geser timeline.
- Drag skala harga kanan: ubah zoom/posisi vertikal.
- Tombol 6 Bulan / 1 Tahun / Semua / Fit.
- Perbesar Chart untuk fokus chart hampir seluruh drawer.

Chart interaktif memakai TradingView Lightweight Charts™ 5.0.1 melalui jsDelivr CDN, sehingga browser perlu internet saat membuka chart.

## v4.1 — Entry Timing Guard
- Pattern entry hanya dianggap fresh maksimal `ENTRY_PATTERN_MAX_AGE_BARS` candle (default 3).
- Pattern lama tetap tampil di chart/panel sebagai histori, tetapi tidak boleh menjadi trigger entry baru.
- Buy on Retracement / Buy on Weakness sekarang melewati Location Gate.
- Jika harga sudah terlalu dekat Resistance atau ruang ke Resistance terlalu kecil dibanding jarak ke Support, status berubah menjadi `JANGAN KEJAR`.
- Buy on Breakout juga memiliki expiry jika harga sudah terlalu jauh dari level breakout.
- Semua threshold berada di `.env` / `app/config.py` agar bisa dikalibrasi dari chart historis.
