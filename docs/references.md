# Scentinel Data Sources & References

Semua data default di Scentinel berasal dari sumber publik yang terverifikasi.
Dokumen ini mencatat setiap angka, asal-usulnya, dan tingkat kepercayaannya.

> **Catatan basis:** dokumen ini mencatat nilai yang **sudah dipakai**. Untuk
> dasar ilmiah pemilihan basis komposisi gas — termasuk temuan bahwa basis
> AP-42 landfill tidak cocok untuk bak truk segar, dan model 40 CFR 98.343
> HH-1 yang diusulkan sebagai gantinya — lihat
> [gas-composition-basis.md](gas-composition-basis.md).

Terakhir diperbarui: 2026-09-19

---

## 1. Komposisi Landfill Gas (LFG)

### 1.1 Komposisi utama

| Komponen | Nilai | Sumber | Catatan |
|---|---|---|---|
| CH4 | ~50% by volume | EPA LMOP, *Basic Information about Landfill Gas* | Kisaran umum LFG |
| CO2 + uap air | ~50% by volume | EPA LMOP, idem | |
| CH4 (steady-state) | ~55% by volume | EPA AP-42 Ch.2.4 (Aug 2024), hal. 2.4-3 | Kondisi steady-state |
| CO2 (steady-state) | ~40% by volume | EPA AP-42 Ch.2.4, idem | |
| N2 + gas lain | ~5% by volume | EPA AP-42 Ch.2.4, idem | |
| NMOC | <1% by volume | EPA LMOP FAQ | Termasuk VOC dan HAP |

**Catatan penting:** AP-42 Ch.2.4 menyatakan bahwa pada steady-state, LFG
terdiri dari ~55% CH4, 40% CO2, dan 5% N2. EPA LMOP menggunakan angka umum
~50/50. Scentinel memakai 50% sebagai default konservatif dan menyediakan
55% sebagai alternatif.

### 1.2 Konsentrasi spesifik (ppmv, uncontrolled)

| Komponen | Konsentrasi | Sumber | Rating EPA |
|---|---|---|---|
| CO | 105 ppmv | AP-42 Final Factors (ref 98) | Minimally representative |
| NMOC (as hexane), MSW-only 1992+ | 550 ppmv | AP-42 Table 2.4-2 | Moderately representative |
| NMOC (as hexane), co-disposal | 2400 ppmv | AP-42 Table 2.4-2 | D |
| H2S | 36 ppmv | AP-42 Table 2.4-1 | B |
| Ethane | 890 ppmv | AP-42 Table 2.4-1 | C |
| Vinyl chloride | 7.3 ppmv | AP-42 Table 2.4-1 | B |
| Methyl mercaptan | 2.5 ppmv | AP-42 Table 2.4-1 | C |
| Dimethyl sulfide | 7.8 ppmv | AP-42 Table 2.4-1 | C |
| Benzene (no/unknown co-disposal) | 1.9 ppmv | AP-42 Table 2.4-2 | B |
| Benzene (co-disposal) | 11 ppmv | AP-42 Table 2.4-2 | D |
| Toluene (no/unknown co-disposal) | 39 ppmv | AP-42 Table 2.4-2 | A |
| Toluene (co-disposal) | 170 ppmv | AP-42 Table 2.4-2 | D |

Rating EPA (A–E) menunjukkan kualitas data: A = excellent, E = poor.
Lihat AP-42 Table 2.4-1 dan 2.4-2 untuk daftar lengkap ~45 komponen trace.

**Catatan co-disposal:** hanya benzene, NMOC, dan toluene yang dipecah AP-42
menurut riwayat co-disposal. Gas lain — termasuk semua baris Table 2.4-1 —
hanya punya satu nilai default, sehingga pada aliran co-disposal gas tersebut
memakai nilai dasarnya, bukan nilai alternatif yang tidak ada.

Ammonia tidak disertakan: workbook AP-42 Ch.2.4 tidak memuat baris ammonia,
sehingga tidak ada nilai yang bisa dikutip.

### 1.3 Nilai kalori LFG

| Parameter | Nilai | Sumber |
|---|---|---|
| Heating value | 350–600 Btu/ft³ | EPA LMOP FAQ |

---

## 2. Properti Fisika Gas (25°C, 1 atm)

Difusivitas setiap gas **dihitung**, bukan disalin dari literatur, memakai
korelasi Fuller-Schettler-Giddings:

$$D_{AB}\ [\text{cm}^2/\text{s}] = \frac{0.00143\,T^{1.75}}{P\sqrt{M_{AB}}\left(V_A^{1/3} + V_B^{1/3}\right)^2},
\qquad M_{AB} = \frac{2}{1/M_A + 1/M_B}$$

dengan $T = 298.15$ K, $P = 1.01325$ bar, dan udara sebagai komponen B
($M_B = 28.96$ g/mol, $V_B = 19.7$). Volume difusi atomik dari Reid, Prausnitz &
Poling, *The Properties of Gases and Liquids*, 4th ed., Table 11-1: C 15.9,
H 2.31, O 6.11, N 12.7, F 16.5, Cl 21.0, Br 26.7, I 32.9, S 20.1; setiap cincin
aromatik dikurangi 18.3. Satu korelasi untuk semua gas menjaga tabel tetap
konsisten — nilai publikasi per gas berasal dari kumpulan pengukuran berbeda,
sehingga mencampurnya akan membuat perbedaan antar gas mencerminkan perbedaan
metode, bukan perbedaan molekul.

| Gas | MW (g/mol) | V (cm³) | Difusivitas di udara (m²/s) |
|---|---|---|---|
| CO | 28.01 | 22.01 | 1.87 × 10⁻⁵ |
| CH4 | 16.04 | 25.14 | 2.10 × 10⁻⁵ |
| VOC (hexane proxy) | 86.18 | 127.74 | 7.66 × 10⁻⁶ |
| H2S | 34.08 | 24.72 | 1.71 × 10⁻⁵ |
| Ethane | 30.07 | 45.66 | 1.41 × 10⁻⁵ |
| Benzene | 78.11 | 90.96 | 8.96 × 10⁻⁶ |
| Toluene | 92.13 | 111.48 | 8.06 × 10⁻⁶ |
| Vinyl chloride | 62.50 | 59.73 | 1.10 × 10⁻⁵ |
| Methyl mercaptan | 48.11 | 45.24 | 1.28 × 10⁻⁵ |
| Dimethyl sulfide | 62.13 | 65.76 | 1.06 × 10⁻⁵ |

Nilai acuan untuk memeriksa korelasi: CO ≈ 1.9 × 10⁻⁵, H2S ≈ 1.7 × 10⁻⁵, dan
hexane ≈ 7.4 × 10⁻⁶ m²/s. Semua gas memakai metode yang sama, dan difusivitas
per gas inilah yang ditulis ke `scalarTransport` di `system/functions` serta
dicatat di blok `applied_physics`.

---

## 3. Dokumentasi OpenFOAM

Semua dari OpenFOAM v13 User Guide (Greenshields, 2025):

| Topik | Bagian | Dipakai untuk |
|---|---|---|
| Solver modules | §3.5 | `foamRun` + `incompressibleFluid` |
| Scalar transport | §7.3.15 | Transport CO/CH4/VOC sebagai passive scalar |
| Probes | §7.3.12 | Sampling di titik sensor |
| Sampling & monitoring | §7.4 | Plot time-series, `foamMonitor` |
| Cut plane & streamlines | §7.3.16, §7.3.17 | Visualisasi field |
| Boundary conditions | §6 | Inlet/outlet/wall setup |
| Turbulence models | §8.2 | k-epsilon RANS |

Salinan teks tersimpan di `docs/references/of_*.txt` (hasil scrape).

---

## 4. Paper Referensi

Semua metadata dari Crossref API, terverifikasi dengan DOI.

### 4.1 Sensor placement & CFD

1. **Legg, S.W., Benavides-Serrano, A.J., Siirola, J.D., et al. (2012).**
   A stochastic programming approach for gas detector placement using CFD-based
   dispersion simulations. *Computers & Chemical Engineering*.
   DOI: [10.1016/j.compchemeng.2012.05.010](https://doi.org/10.1016/j.compchemeng.2012.05.010)

2. **Lang, Y., Ng, M.X.Y., Yu, K.X., et al. (2025).**
   A novel CFD-MILP-ANN approach for optimizing sensor placement, number, and
   source localization in large-scale gas dispersion from unknown locations.
   *Digital Chemical Engineering*.
   DOI: [10.1016/j.dche.2024.100216](https://doi.org/10.1016/j.dche.2024.100216)

3. **Zi, Y., Fan, L., Wu, X., et al. (2022).**
   Distributionally Robust Optimal Sensor Placement Method for Site-Scale
   Methane-Emission Monitoring. *IEEE Sensors Journal*.
   DOI: [10.1109/JSEN.2022.3214176](https://doi.org/10.1109/JSEN.2022.3214176)

4. **Abbassi, R., Dadashzadeh, M., Khan, F., et al. (2012).**
   Risk-Based Prioritisation of Indoor Air Pollution Monitoring Using
   Computational Fluid Dynamics. *Indoor and Built Environment*.
   DOI: [10.1177/1420326X11428164](https://doi.org/10.1177/1420326X11428164)

### 4.2 Landfill gas & dispersi

5. **Klise, K.A., Nicholson, B.L., Laird, C.D., et al. (2020).**
   Sensor Placement Optimization Software Applied to Site-Scale Methane-Emissions
   Monitoring. *Journal of Environmental Engineering*.
   DOI: [10.1061/(ASCE)EE.1943-7870.0001737](https://doi.org/10.1061/(ASCE)EE.1943-7870.0001737)

### 4.3 Passive scalar transport

6. **Vanderwel, C., Tavoularis, S. (2014).**
   Relative dispersion of a passive scalar plume in turbulent shear flow.
   *Physical Review E*.
   DOI: [10.1103/PhysRevE.89.041005](https://doi.org/10.1103/PhysRevE.89.041005)

### 4.4 Ventilasi waste bunker

7. **Lee, T., Moon, S., et al. (2006).**
   Improvement of the Ventilation System in the Waste Bunker of a Municipal
   Solid Waste Incineration Plant. *AIHce 2006*.
   DOI: [10.3320/1.2759094](https://doi.org/10.3320/1.2759094)

---

## 5. Buku Teks

1. **Greenshields, C. (2025).** *OpenFOAM v13 User Guide*. The OpenFOAM Foundation, London.
   https://doc.cfd.direct/openfoam/user-guide-v13

2. **Versteeg, H.K., Malalasekera, W. (2007).** *An Introduction to Computational
   Fluid Dynamics: The Finite Volume Method* (2nd ed.). Pearson.

3. **Ferziger, J.H., Perić, M., Street, R.L. (2020).** *Computational Methods for
   Fluid Dynamics* (4th ed.). Springer.

4. **Moukalled, F., Mangani, L., Darwish, M. (2016).** *The Finite Volume Method
   in Computational Fluid Dynamics*. Springer.

5. **Reid, R.C., Prausnitz, J.M., Poling, B.E. (1987).** *The Properties of Gases
   and Liquids* (4th ed.). McGraw-Hill. — Table 11-1: volume difusi atomik dan
   koreksi cincin aromatik (−18.3 cm³ per cincin) yang dipakai untuk menghitung
   seluruh difusivitas di §2.

6. **Fuller, E.N., Schettler, P.D., Giddings, J.C. (1966).** A new method for
   prediction of binary gas-phase diffusion coefficients. *Industrial &
   Engineering Chemistry*, 58(5), 18–27.
   DOI: [10.1021/ie50677a007](https://doi.org/10.1021/ie50677a007)
   — Korelasi Fuller-Schettler-Giddings yang menghasilkan difusivitas §2.

---

## 6. Regulasi & Standar

| Standar | Judul | Relevansi |
|---|---|---|
| 40 CFR Part 60 Subpart XXX | NSPS for MSW Landfills | Ambang emisi NMOC |
| 40 CFR Part 60 Subpart Cf | Emission Guidelines | Regulasi GCCS |
| ISO 21640:2021 | Solid recovered fuels — Specifications and classes | Konteks RDF/SRF |

---

## 7. Cara Reproduksi

Semua data dapat di-scrape ulang:

```bash
.venv/bin/python scripts/scrape_references.py   # ambil ulang dari sumber
.venv/bin/python scripts/build_gas_data.py      # generate gas_defaults.py
```

File mentah tersimpan di:
- `docs/data/*.xlsx`, `docs/data/*.pdf` — dokumen resmi EPA
- `docs/references/*.html` — snapshot HTML sumber
- `docs/data/scraped_references.json` — metadata terstruktur
