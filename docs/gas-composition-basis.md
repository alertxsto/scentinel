# Scentinel — Basis Komposisi Gas & Sumber Emisi

**Versi:** 0.2.2 · **Terakhir diperbarui:** 2026-09-19
**Status:** dokumen riset — dasar keputusan, belum sepenuhnya diimplementasikan

Dokumen ini mencatat **dasar ilmiah** untuk komposisi gas yang disimulasikan
Scentinel: apa yang bisa dikutip, apa yang diturunkan, dan apa yang tidak boleh
ditebak. Tujuannya agar keakuratan data dan hasil dapat diperiksa ulang oleh
siapa pun — termasuk pengawas — tanpa harus mempercayai kode.

Dokumen terkait: [references.md](references.md) (provenansi nilai yang sudah
dipakai), [ARCHITECTURE.md](ARCHITECTURE.md) (alur data).

---

## 1. Masalah yang ditemukan

Scentinel memodelkan **bak truk pengangkut sampah** — sampah segar, baru
beberapa jam sejak dibuang.

Namun seluruh angka komposisi gasnya berasal dari **AP-42 Ch.2.4: MSW
Landfills** — sistem anaerobik dengan sampah berumur minggu sampai tahun.

AP-42 sendiri menyatakan perbedaannya secara eksplisit:

> "When MSW is first deposited in a landfill, it undergoes an **aerobic**
> decomposition stage when **little methane is generated**. Then, typically
> within **less than 1 year**, anaerobic conditions are established and
> methane-producing bacteria begin to decompose the waste and generate methane."
> — EPA LMOP, *Basic Information about Landfill Gas*

Akibatnya, nilai andalan aplikasi ini — CH₄ **500 000 ppmv** — tidak berlaku
untuk bak truk segar. Metanogen memerlukan waktu berminggu-minggu; fasa awal
sampah segar bersifat aerobik dan menghasilkan CO₂, bukan CH₄.

**Konsekuensi:** komposisi gas yang dipakai saat ini cocok untuk *landfill*,
bukan untuk *kendaraan pengangkut*. Ini kesalahan pemilihan basis, bukan
kesalahan angka.

---

## 2. Empat fasa dekomposisi (AP-42 Ch.2.4 §2.4.4)

AP-42 membagi pembentukan gas menjadi empat fasa:

| Fasa | Kondisi | Gas utama |
|---|---|---|
| I | Aerobik (O₂ tersedia) | **CO₂**; N₂ tinggi; CH₄ sangat sedikit |
| II | O₂ habis, anaerobik | CO₂ dalam jumlah besar + **H₂** |
| III | Metanogenik awal | **CH₄ mulai terbentuk**, CO₂ menurun |
| IV | Steady state | CH₄, CO₂, N₂ stabil |

Sumber: AP-42 Ch.2.4, §2.4.4, halaman 2.4-2 (`docs/data/c2s4_2024_final.pdf`).

Bak truk pengangkut berada di **Fasa I**. Landfill yang sudah matang berada di
**Fasa IV**.

### Komposisi steady-state (Fasa IV)

> "When gas generation reaches steady state conditions, LFG consists of
> approximately **40% by volume CO₂, 55% CH₄, 5% N₂** (and other gases), and
> trace amounts of NMOCs."
> — AP-42 Ch.2.4, halaman 2.4-3

Angka ini adalah **plafon fisik**. Tidak ada jalur dekomposisi sampah yang
menghasilkan 85% CH₄ — nitrogen dan CO₂ selalu menjadi bagian dari gas.

---

## 3. Model metana resmi: 40 CFR 98.343 Equation HH-1

Model generasi metana yang dipakai EPA untuk pelaporan gas rumah kaca. Ini
model **first-order decay**, bukan penskalaan linear.

```
G_CH4 = Σ_x [ W_x × MCF × DOC × DOC_F × F × (16/12) × (e^(-k(T-x-1)) - e^(-k(T-x))) ]
```

| Simbol | Arti | Nilai default | Sumber |
|---|---|---|---|
| `W_x` | Massa sampah tahun ke-x | — (input) | pengukuran timbangan |
| `MCF` | Methane correction factor | 1.0 (landfill terkelola) | Table HH-1 |
| `DOC` | Degradable organic carbon | lihat §3.1 | Table HH-1 |
| `DOC_F` | Fraksi DOC yang terurai | **0.5** | 40 CFR 98.343(a)(1) |
| `F` | Fraksi volume CH₄ dalam LFG | **0.5** | 40 CFR 98.343(a)(1) |
| `16/12` | Rasio massa CH₄/C | — | stoikiometri |
| `k` | Konstanta laju peluruhan | lihat §3.1 | Table HH-1 |

Sumber: 40 CFR §98.343(a)(1), Equation HH-1. Teks lengkap tersedia di
`https://www.law.cornell.edu/cfr/text/40/98.343`.

### 3.1 Nilai DOC dan k (Table HH-1, revisi 89 FR 31940, efektif 1 Jan 2025)

**Bulk waste option**

| Parameter | Nilai | Satuan |
|---|---|---|
| DOC (bulk waste) | 0.20 | fraksi berat, basis basah |
| k (presipitasi <20 in/tahun) | 0.02 | yr⁻¹ |
| k (presipitasi 20–40 in/tahun) | 0.038 | yr⁻¹ |
| k (presipitasi >40 in/tahun) | 0.057 | yr⁻¹ |

**Modified bulk MSW option**

| Parameter | Nilai | Satuan |
|---|---|---|
| DOC (bulk MSW, tanpa inert & C&D) | 0.31 | fraksi berat, basis basah |
| DOC (inert: kaca, plastik, logam, beton) | 0.00 | fraksi berat, basis basah |
| DOC (C&D waste) | 0.08 | fraksi berat, basis basah |
| k (bulk MSW) | 0.02 – 0.057 | yr⁻¹ |
| k (C&D waste) | 0.02 – 0.04 | yr⁻¹ |

**Waste composition option** — ini yang membuat komposisi sampah menjadi input nyata

| Material | DOC | k [yr⁻¹] |
|---|---|---|
| Sisa makanan (food waste) | 0.15 | 0.06 – 0.185 |
| Sampah taman (garden) | 0.20 | 0.05 – 0.10 |
| Kertas (paper) | 0.40 | 0.04 – 0.06 |
| Kayu & jerami (wood/straw) | 0.43 | 0.02 – 0.03 |
| Tekstil (textiles) | 0.24 | — |
| Popok (diapers) | 0.24 | — |
| Sludge IPAL (sewage sludge) | 0.05 | — |
| Inert (kaca, plastik, logam, semen) | 0.00 | — |

Sumber: Table HH-1 to Subpart HH of Part 98, `CFR-2024-title40-vol23`, halaman
1016. Nilai DOC per material berasal dari IPCC *Guidelines for National
Greenhouse Gas Inventories*.

**Catatan penting:** kolom `k` adalah laju orde-satu terhadap **waktu dalam
satuan tahun**. Untuk bak truk dengan waktu tinggal beberapa jam, faktor
`(e^(-k·Δt))` mendekati nol — artinya generasi metana praktis **belum mulai**.

Perhitungan fraksi potensi metana yang tercapai, `1 - e^(-k·Δt)`, untuk
beberapa waktu tinggal:

| Waktu tinggal | k=0.185 (sisa makanan) | k=0.06 (makanan, bawah) | k=0.02 (kertas, bawah) |
|---|---|---|---|
| 2 jam | 0.004% | 0.001% | 0.0005% |
| 8 jam | 0.017% | 0.006% | 0.002% |
| 24 jam | 0.051% | 0.016% | 0.006% |
| 3 hari | 0.152% | 0.049% | 0.016% |
| 1 minggu | 0.354% | 0.115% | 0.038% |
| 1 bulan | 1.51% | 0.49% | 0.16% |
| 6 bulan | 8.84% | 2.96% | 1.00% |
| 1 tahun | 16.9% | 5.82% | 1.98% |

Untuk bak truk (≤24 jam), fraksi yang tercapai **di bawah 0.06%** bahkan untuk
sampah makanan yang paling cepat terurai. Inilah bukti kuantitatif bahwa CH₄
tidak relevan untuk sampah segar — dan sekaligus alasan mengapa `age` harus
menjadi input, bukan diasumsikan.

### 3.2 Pemeriksaan kewajaran: potensi metana ultimate

Untuk 1 Mg sampah dengan DOC = 0.31 (modified bulk MSW):

```
CH₄ = 1000 kg × MCF × DOC × DOC_F × F × (16/12)
    = 1000 × 1.0 × 0.31 × 0.5 × 0.5 × 1.3333
    = 103.3 kg CH₄ per Mg sampah
```

Setara ≈ **144 m³ CH₄/Mg** pada kondisi standar (ρ_CH₄ = 0.716 kg/m³).

Default AP-42 untuk `L₀` adalah **100 m³ CH₄/Mg**. Kedua nilai berada dalam
faktor ≈1.4 satu sama lain — konsisten, dan selisihnya berasal dari pilihan
DOC (0.31 modified bulk vs 0.20 bulk). Ini menegaskan bahwa model HH-1 dapat
dipakai sebagai pengganti penskalaan ad-hoc.

Angka ini adalah potensi **ultimate** (seluruh karbon terurai, waktu tak
terbatas). Yang menentukan untuk bak truk adalah faktor peluruhan
`(e^(-k·Δt))`, yang dibahas di §3.1.

---

## 4. Komposisi trace (AP-42 Ch.2.4)

### 4.1 Table 2.4-1 — default concentration

Tabel 45+ senyawa trace dengan MW dan konsentrasi default. Sudah diekstrak ke
`src/scentinel/core/gas_defaults.py` (`AP42_TRACE_COMPOUNDS`).

Senyawa pembawa halogen dan sulfur yang dipakai untuk perhitungan beban Cl/S:

| Senyawa | ppmv | Atom Cl | Atom S |
|---|---|---|---|
| Dichlorodifluoromethane | 16 | 2 | 0 |
| Dichloromethane (methylene chloride) | 14 | 2 | 0 |
| Perchloroethylene | 3.7 | 4 | 0 |
| Vinyl chloride | 7.3 | 1 | 0 |
| Hydrogen sulfide | 36 | 0 | 1 |
| Dimethyl sulfide | 7.8 | 0 | 1 |
| Methyl mercaptan | 2.5 | 0 | 1 |
| Carbon disulfide | 0.58 | 0 | 2 |

Konversi ppmv → mg/Nm³ pada 25 °C, 1 atm:

```
mg/Nm³ = ppmv × (jumlah atom) × (massa atom) / 24.45
```

dengan 24.45 L/mol adalah volume molar. Satu m³ berisi 1000/24.45 mol, sehingga
faktor konversinya ≈ 40.9 mol/m³ — bukan 1 mol/m³.

### 4.2 Table 2.4-2 — bergantung riwayat pembuangan

| Polutan | No/unknown co-disposal | Co-disposal |
|---|---|---|
| NMOC (as hexane), 1992+ | **550 ppmv** (rating B) | 2400 ppmv (rating D) |
| NMOC (as hexane), pre-1992 | 600 ppmv (rating B) | 2400 ppmv (rating D) |
| Benzene | 1.9 ppmv (rating B) | 11 ppmv (rating D) |
| Toluene | 39 ppmv (rating A) | 170 ppmv (rating D) |

### 4.3 Nilai NMOC alternatif

AP-42 juga menyebut **4000 ppmv** sebagai regulatory default untuk total NMOC
(LandGEM), yang ditujukan untuk kepatuhan regulasi, bukan estimasi terbaik.

---

## 5. Celah untuk sampah segar

Bagian ini mencatat apa yang **belum** dapat dikutip dari dokumen yang sudah
ada di repo. Kejujuran di sini lebih penting daripada angka yang terlihat rapi.

### 5.1 Yang belum tersedia di repo

Sumber-sumber berikut teridentifikasi relevan tetapi **nilainya belum
diekstrak** dan karenanya belum boleh dipakai:

| Sumber | Relevansi | Status |
|---|---|---|
| *Emission characteristics and variation of volatile odorous compounds in the initial decomposition stage of MSW* — Waste Management, 2017, 68:677-687, DOI `10.1016/j.wasman.2017.07.015` | Komposisi VOC fasa dekomposisi awal MSW — persis kasus bak truk | Belum diekstrak |
| Statheropoulos et al., 2005 — *A study of VOCs evolved in urban waste disposal bins*, Atmos. Environ. | VOC di dalam bin sampah kota | Belum diekstrak |
| Salinas et al., 2026 — *Odour and Composition Assessment of MSW* | Pengaruh komposisi & tingkat pengisian terhadap emisi bau | Belum diekstrak |
| NIOSH NMAM Method 3900 | Daftar analyte yang diukur di udara sampah (termasuk α-pinene, d-limonene) | Metode analitik, bukan nilai |

### 5.2 Yang secara fisika tidak mungkin (kondisi sebelum W0; diperbaiki)

Model linear lama dapat menghasilkan komposisi yang melanggar batas fisik.
Diverifikasi langsung dari kode pada waktu itu:

| Waste type | CH₄ hasil model lama | Batas fisik (55% = 550 000 ppmv) |
|---|---|---|
| mixed-msw | 500 000 ppmv (50%) | ok |
| co-disposal | 550 000 ppmv (55%) | tepat di batas |
| organic-rich | 800 000 ppmv (**80%**) | **melanggar** |
| green-waste | 850 000 ppmv (**85%**) | **melanggar** |
| rdf-feedstock | 250 000 ppmv (25%) | ok |
| dry-recyclables | 100 000 ppmv (10%) | ok |

Penskalaan linear `organic_fraction / 0.50` tidak memiliki dasar dalam
dokumentasi mana pun — tidak ada sitasi di `docs/`, tidak ada di literatur yang
ditemukan. Bentuk yang benar adalah peluruhan orde-satu (§3), bukan
perkalian linear.

**Status 0.2.2:** penskalaan linear dihapus (T-103); kekuatan sumber dihitung
dari Eq. HH-1. CH₄ dan CO₂ kini mengikuti pembagian `F = 0.5` regulasi (§6.2b),
jadi tidak ada komposisi yang melampaui plafon 55%.

### 5.3 Parameter yang saat ini tidak berfungsi

`moisture_fraction` tersimpan di proyek, tercatat di manifest, dan tampil di
UI — tetapi **tidak pernah masuk ke perhitungan kekuatan sumber**. Verifikasi:

```
$ python -c "import inspect; from scentinel.core.scenario import auto_concentration_ppmv; \
  print('moisture' in inspect.getsource(auto_concentration_ppmv))"
False
```

Padahal AP-42 menyatakan kelembapan **memang** faktor yang mengubah laju:

> "The waste degradation decay rate is a function of waste type, age of waste,
> and **waste moisture**. Waste moisture might be changed by leachate
> recirculation and rainfall rates."
> — AP-42 Ch.2.4, halaman 2.4-5

Artinya kelembapan seharusnya memengaruhi `k` (atau pilihan `k`), bukan menjadi
input mati.

---

## 6. Model yang diusulkan: simulation-driven

Prinsip: **komposisi sampah adalah input; gas adalah output yang dihitung.**
Pengguna tidak memilih gas — pengguna mendeskripsikan sampah, dan model
menentukan gas apa yang relevan beserta kekuatannya.

### 6.1 Komposisi material (input)

Ganti `waste_type` tunggal dengan komposisi fraksi massa per kategori Table HH-1:

| Kategori | Fraksi massa | DOC | k [yr⁻¹] |
|---|---|---|---|
| Sisa makanan | `f_food` | 0.15 | 0.06 – 0.185 |
| Taman | `f_garden` | 0.20 | 0.05 – 0.10 |
| Kertas | `f_paper` | 0.40 | 0.04 – 0.06 |
| Kayu/jerami | `f_wood` | 0.43 | 0.02 – 0.03 |
| Tekstil | `f_textile` | 0.24 | — |
| Popok | `f_diaper` | 0.24 | — |
| Inert | `f_inert` | 0.00 | — |

Kendala: `Σ f = 1`. Ini yang membuat "variasi tumpukan sampah" benar-benar
mengubah hasil, bukan sekadar mencentang checkbox.

### 6.2 Umur sampah (input) — pembeda fasa

Ini parameter yang hilang dan paling menentukan:

| Parameter | Arti | Kasus |
|---|---|---|
| `age_h` | waktu sejak pembuangan [jam] | bak truk: 0–24 jam; landfill: tahun |

Fasa ditentukan dari umur, mengikuti AP-42 §2.4.4:

- **Fasa I (aerobik, jam–hari):** CO₂ dominan, CH₄ ≈ 0
- **Fasa II–III (hari–bulan):** CO₂ + H₂, CH₄ mulai
- **Fasa IV (bulan–tahun):** steady state 55% CH₄

**Penting — fasa adalah interpretasi, bukan saklar.** Batas 48 jam / 90 hari /
365 hari adalah narasi AP-42 yang dinyatakan sebagai aturan keputusan; AP-42
sendiri menyatakan durasinya "bervariasi" dan tidak memberi angka pasti. Karena
itu fasa **tidak boleh** mematikan atau menyalakan gas: jumlah gas dihitung oleh
kurva peluruhan orde-satu yang kontinu pada setiap umur, dan fasa hanya
menafsirkan umur itu. Model yang lama memakai fasa sebagai saklar, sehingga
CH₄ meloncat dari 0 menjadi campuran landfill tepat di batas 90 hari — itu
artefak, bukan fisika. Lihat §6.6.

### 6.2b Campuran gas yang dihasilkan (F = 0.5)

Gas yang dihasilkan dibagi oleh **default metana regulasi itu sendiri**,
`F = 0.5` (40 CFR §98.343 Tabel HH-1) — bukan oleh campuran AP-42 55/40/5.
Alasannya:

- 55/40/5 adalah **hasil pengukuran landfill matang**; menerapkannya pada sampah
  berumur jam-an adalah kesalahan basis yang sama yang memicu seluruh dokumen ini.
- Regulasi yang sama yang memberi persamaan HH-1 juga memberi `F = 0.5` sebagai
  default, jadi campurannya satu basis dengan lajunya.
- Dengan `F = 0.5`, karbon yang terdegradasi terbagi rata: sekitar separuh mol
  menjadi CH₄, separuh menjadi CO₂. N₂ **bukan** produk peluruhan (ia udara
  terperangkap) sehingga tidak dilaporkan.
- Yang berubah karena umur adalah **jumlah** gas (kumulatif, kg) dan **lajunya**
  (kg/jam), bukan persentasenya. Ini yang membuat umur benar-benar menggerakkan
  simulasi, bukan hanya angka di layar.

Campuran 55/40/5 tetap disimpan sebagai **plafon dan pembanding** (gas landfill
matang), bukan sebagai input model.

### 6.3 Gas yang dihitung (output)

**Fasa I (bak truk):**

| Gas | Sumber nilai | Status |
|---|---|---|
| CO₂ | Fasa I aerobik — AP-42 §2.4.4 | bentuk tersedia, nilai perlu ekstraksi |
| H₂S | Table 2.4-1: 36 ppmv | **tersedia & relevan** |
| Merkaptan (metil, etil) | Table 2.4-1: 2.5 / 2.3 ppmv | **tersedia & relevan** |
| Dimetil sulfida | Table 2.4-1: 7.8 ppmv | **tersedia & relevan** |
| NH₃ | **tidak ada di AP-42** — perlu sumber lain | belum tersedia |
| VOC oksigenat (etanol, aseton) | Table 2.4-1 punya nilai | perlu validasi fasa |
| Terpena (limonena, pinena) | **tidak ada di AP-42** | belum tersedia |
| CH₄ | ≈ 0 untuk jam-jam pertama | dihitung dari `age_h` |

**Fasa IV (landfill/aged):**

| Gas | Sumber nilai |
|---|---|
| CH₄ | Equation HH-1 (§3) dengan `f`, `DOC`, `k`, dibagi `F = 0.5` (§6.2b) |
| CO₂ | Neraca karbon HH-1; sisa karbon setelah CH₄, perbandingan massa molar 44.009/12.011 |
| NMOC | Table 2.4-2, regime co-disposal |
| Trace | Table 2.4-1 |

### 6.4 Yang tetap tidak boleh ditebak

| Besaran | Alasan |
|---|---|
| NCV (net calorific value) | Properti bahan bakar; butuh analisis laboratorium material |
| Ash content | Butuh analisis laboratorium |
| Cl sebagai % massa kering | Fasa gas tidak mengetahui massa bahan bakar |
| Kelas RDF (EN 15359 / ISO 21640) | Turunan dari ketiga di atas |

Ketiganya tetap dilaporkan sebagai **"butuh karakterisasi laboratorium"** —
tidak pernah diestimasi dari fasa gas.

### 6.5 Pemisahan what-if

Skenario sensitivitas ("bagaimana jika emisi 2× lebih besar?") tetap sah untuk
perencanaan penempatan sensor, tetapi harus **eksplisit dan terpisah**:

- Nilai hasil hitungan model disimpan sebagai `computed`
- Nilai yang diubah pengguna disimpan sebagai `perturbation` dengan pengali
  dan alasannya
- Manifest mencatat keduanya secara terpisah, sehingga tidak ada konsumen yang
  salah membaca nilai what-if sebagai nilai kutipan

### 6.6 Tiga kuantitas yang tidak boleh dicampur

Versi 0.2.2 melabeli massa kumulatif gas sebagai "gas yang dihasilkan sekarang".
Itu keliru: tiga besaran berbeda disatukan dalam satu angka.

| Kuantitas | Simbol | Satuan | Sifat |
|---|---|---|---|
| Potensi pamungkas | `ultimate_ch4_kg` | kg | Properti komposisi + tonase; tidak bergantung umur |
| Gas kumulatif | `ch4_cumulative_kg` | kg | Monoton naik terhadap umur; nol di umur nol |
| Laju pembentukan | `ch4_rate_kg_per_h` | kg/jam | Turunan eksak kurva kumulatif |

Laju **adalah turunan** dari kumulatif:
`d/dt [C_ult · (1 − e^(−k·t))] = C_ult · k · e^(−k·t)`, sehingga keduanya tidak
dapat saling bertentangan. Uji mengasertifkan ini secara numerik.

---

## 7. Dampak implementasi

Perubahan ini mengubah angka secara besar dan **membatalkan kompatibilitas
manifest lama**:

| Item | Dampak |
|---|---|
| `Scenario.waste_type` | Digantikan komposisi material + `age_h` |
| `auto_concentration_ppmv()` | Digantikan model HH-1 untuk CH₄/CO₂ |
| Manifest | Naik versi; manifest lama tidak dapat dibaca sebagai komposisi baru |
| `gas_defaults.py` | Perlu gas baru (CO₂, NH₃, terpena) dengan sumber baru |
| Dokumentasi | `references.md` perlu tabel fasa dan model HH-1 |

### Urutan pengerjaan yang disarankan

1. **Ekstrak nilai** dari tiga sumber §5.1 — tanpa angka, fasa I tidak dapat
   diisi secara jujur
2. **Implementasi model HH-1** untuk fasa IV (data sudah lengkap di dokumen ini)
3. **Tambah `age_h`** dan pemilihan fasa
4. **Ganti penskalaan linear** dengan DOC berbobot komposisi
5. **Naikkan versi manifest** dan migrasikan

Langkah 2 sudah dapat dikerjakan sekarang; langkah 1 dan 3 memerlukan ekstraksi
data dari literatur.

---

## 8. Ringkasan status kutipan

| Komponen | Status | Sumber |
|---|---|---|
| Komposisi steady-state LFG (55/40/5) | **Terkutip** (plafon/pembanding, bukan input) | AP-42 Ch.2.4 hlm 2.4-3 |
| Empat fasa dekomposisi | **Terkutip** | AP-42 Ch.2.4 hlm 2.4-2 |
| Persamaan HH-1 | **Terkutip** | 40 CFR §98.343(a)(1) |
| DOC & k per material | **Terkutip** | Table HH-1 Subpart HH |
| DOC_F = 0.5, F = 0.5 | **Terkutip** | 40 CFR §98.343(a)(1) |
| Rasio massa CO₂/C = 44.009/12.011 | **Derived** | Massa molar |
| Konsentrasi trace (45+ senyawa) | **Terkutip** | AP-42 Table 2.4-1 |
| NMOC/Benzene/Toluene per regime | **Terkutip** | AP-42 Table 2.4-2 |
| Kelembapan memengaruhi laju | **Terkutip** | AP-42 Ch.2.4 hlm 2.4-5 |
| Komposisi VOC fasa awal MSW | **Belum diekstrak** | Waste Manag. 2017 (DOI di §5.1) |
| VOC dalam bin sampah | **Belum diekstrak** | Statheropoulos 2005 |
| NH₃ | **Tidak ada sumber** | — |
| Terpena (limonena, pinena) | **Tidak ada sumber** | — |
| NCV, ash, Cl% bahan bakar | **Butuh laboratorium** | — |

Aturan yang berlaku: **nilai tanpa sitasi tidak boleh masuk ke model.** Baris
"belum diekstrak" berarti pekerjaan ekstraksi, bukan izin mengira-ngira.
