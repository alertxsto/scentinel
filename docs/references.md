# Scentinel Data Sources & References

Semua data default di Scentinel berasal dari sumber publik yang terverifikasi.
Dokumen ini mencatat setiap angka, asal-usulnya, dan tingkat kepercayaannya.

Terakhir diperbarui: 2026-09-18

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
| Benzene (no co-disposal) | 1.9 ppmv | AP-42 Table 2.4-2 | B |
| Benzene (co-disposal) | 11 ppmv | AP-42 Table 2.4-2 | D |
| Toluene (no co-disposal) | 39 ppmv | AP-42 Table 2.4-2 | A |
| Toluene (co-disposal) | 170 ppmv | AP-42 Table 2.4-2 | D |
| Ethane | 890 ppmv | AP-42 Table 2.4-1 | C |
| Vinyl chloride | 7.3 ppmv | AP-42 Table 2.4-1 | B |
| Methyl mercaptan | 2.5 ppmv | AP-42 Table 2.4-1 | C |

Rating EPA (A-E) menunjukkan kualitas data: A = excellent, E = poor.
Lihat AP-42 Table 2.4-1 dan 2.4-2 untuk daftar lengkap ~45 komponen trace.

### 1.3 Nilai kalori LFG

| Parameter | Nilai | Sumber |
|---|---|---|
| Heating value | 350–600 Btu/ft³ | EPA LMOP FAQ |

---

## 2. Properti Fisika Gas (25°C, 1 atm)

| Gas | MW (g/mol) | Difusivitas di udara (m²/s) | Sumber difusivitas |
|---|---|---|---|
| CO | 28.01 | 2.0 × 10⁻⁵ | Nilai standar literatur |
| CH4 | 16.04 | 2.2 × 10⁻⁵ | Nilai standar literatur |
| VOC (hexane proxy) | 86.18 | 8.7 × 10⁻⁶ | Nilai standar literatur |
| H2S | 34.08 | 1.6 × 10⁻⁵ | Nilai standar literatur |

Difusivitas gas biner pada 1 atm dapat dihitung dengan korelasi Fuller-Schettler-Giddings.
Nilai di atas adalah aproksimasi pada 25°C yang cukup untuk simulasi screening.

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
