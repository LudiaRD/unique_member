import io
import re
import pandas as pd
import streamlit as st
import difflib

st.set_page_config(page_title = "CSV/Excel Viewer + NIK Cleaner & Comparator", page_icon = "🧹", layout = "wide")
st.title("🧹 CSV/Excel Viewer + NIK Cleaner & Comparator")
st.markdown("""
         **Upload Data Dispusipda dan Data Kab/Kota (CSV/XLS/XLSX). Aplikasi akan:**
         
         (1) membersihkan NIK (16 digit, diawali '3') dari kolom *MemberNo* dan/atau *IdentityNo*,  
         (2) menampilkan data bersih, dan  
         (3) membandingkan NIK unik antar kedua data untuk menghasilkan dua output:
         <div style = "margin-left: 2em;">
           <ul>
             <li>NIK hanya di <strong>Data Kab/Kota</strong> (tidak ada di <strong>Data Dispusipda</strong>)</li>
             <li>NIK hanya di <strong>Data Dispusipda</strong> (tidak ada di <strong>Data Kab/Kota</strong>)</li>
           </ul>
         </div>
         """,
             unsafe_allow_html = True,
         )

# ---------- Utilitas ----------
def only_digits(s):
    """Ambil hanya digit (0-9) dari nilai apa pun."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    return re.sub(r"[^0-9]", "", s)

def normalize_nik(val):
    """Normalisasi ke NIK valid (16 digit dan mulai '3'); jika tidak valid -> None."""
    digits = only_digits(val)
    if len(digits) == 16 and digits.startswith("3"):
        return digits
    return None

def default_index_for(cols, target_lower: str) -> int:
    """Cari index default untuk selectbox (dengan '<Tidak Ada>' di posisi 0)."""
    lower_cols = [str(c).lower() for c in cols]
    try:
        return 1 + lower_cols.index(target_lower)  # +1 karena '<Tidak Ada>' di depan
    except ValueError:
        return 0

def load_dataframe(uploaded_file, prefix_key: str, use_header_default = True):
    """Baca CSV/XLS/XLSX dengan UI delimiter/sheet terpisah per file."""
    if uploaded_file is None:
        return None

    name = uploaded_file.name.lower()
    use_header = st.checkbox(f"[{prefix_key}] Baris pertama sebagai header", value = use_header_default, key = f"{prefix_key}_hdr")

    if name.endswith(".csv"):
        delimiter = st.selectbox(f"[{prefix_key}] Delimiter CSV", options = [",", ";", "\t", "|"], index = 0, key = f"{prefix_key}_delim")
        encodings = ["utf-8", "utf-8-sig", "cp1252", "latin1"]
        last_err = None
        df = None
        for enc in encodings:
            try:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep = delimiter, encoding = enc, header = 0 if use_header else None)
                break
            except Exception as e:
                last_err = e
        if df is None and last_err:
            st.error(f"[{prefix_key}] Gagal membaca CSV. Error terakhir: {last_err}")
            return None
        return df

    elif name.endswith(".xlsx") or name.endswith(".xls"):
        try:
            uploaded_file.seek(0)
            xl = pd.ExcelFile(uploaded_file)
            sheet = st.selectbox(f"[{prefix_key}] Pilih sheet", options = xl.sheet_names, key = f"{prefix_key}_sheet")
            df = xl.parse(sheet_name = sheet, header = 0 if use_header else None)
            return df
        except Exception as e:
            st.error(f"[{prefix_key}] Gagal membaca Excel: {e}")
            return None
    else:
        st.error(f"[{prefix_key}] Ekstensi file tidak didukung.")
        return None

def clean_with_nik(df, prefix_key: str, title: str):
    """Pilih kolom MemberNo/IdentityNo, bersihkan ke NIK valid, kembalikan df_clean + preview UI."""
    if df is None:
        return None

    st.subheader(f"{title}")
    st.caption("Baris dianggap valid jika **salah satu** kolom menghasilkan NIK yang valid "
               "(16 digit, diawali '3'). Nilai non-digit dihapus sebelum validasi.")
    st.dataframe(df.head(30), use_container_width = True)

    cols_display = ["<Tidak Ada>"] + [str(c) for c in df.columns]
    member_idx = default_index_for(df.columns, "memberno")
    identity_idx = default_index_for(df.columns, "identityno")

    member_col = st.selectbox(f"[{prefix_key}] Kolom MemberNo", options = cols_display, index = member_idx, key = f"{prefix_key}_member")
    identity_col = st.selectbox(f"[{prefix_key}] Kolom IdentityNo", options = cols_display, index = identity_idx, key = f"{prefix_key}_identity")

    do_clean = st.checkbox(f"[{prefix_key}] Aktifkan pembersihan NIK", value = True, key = f"{prefix_key}_clean")
    drop_dup = st.checkbox(f"[{prefix_key}] Hapus duplikat berdasarkan NIK (setelah bersih)", value = True, key = f"{prefix_key}_dedup")

    if not do_clean or (member_col == "<Tidak Ada>" and identity_col == "<Tidak Ada>"):
        st.info("Aktifkan pembersihan dan pilih minimal satu kolom (MemberNo/IdentityNo).")
        return None

    work = df.copy()

    # Hasil bersih per kolom
    work["MemberNo_clean"] = work[member_col].apply(normalize_nik) if member_col != "<Tidak Ada>" else None
    work["IdentityNo_clean"] = work[identity_col].apply(normalize_nik) if identity_col != "<Tidak Ada>" else None

    # Baris valid jika salah satu kolom *_clean tidak None
    mask_valid = pd.Series(False, index = work.index)
    if "MemberNo_clean" in work:
        mask_valid = mask_valid | work["MemberNo_clean"].notna()
    if "IdentityNo_clean" in work:
        mask_valid = mask_valid | work["IdentityNo_clean"].notna()

    df_clean = work.loc[mask_valid].copy()

    # Kolom NIK final (prioritas MemberNo_clean, lalu IdentityNo_clean)
    df_clean["NIK"] = df_clean.get("MemberNo_clean").combine_first(df_clean.get("IdentityNo_clean"))

    # Letakkan NIK di depan, sembunyikan *_clean
    front_cols = ["NIK"]
    other_cols = [c for c in df_clean.columns if c not in front_cols and not str(c).endswith("_clean")]
    df_clean = df_clean[front_cols + other_cols]

    if drop_dup:
        before = len(df_clean)
        df_clean = df_clean.drop_duplicates(subset = ["NIK"], keep = "first")
        removed_dups = before - len(df_clean)
    else:
        removed_dups = 0

    kept = len(df_clean)
    dropped = int(len(work) - mask_valid.sum()) + removed_dups
    c1, c2, c3 = st.columns(3)
    c1.metric(f"[{prefix_key}] Baris Valid (kept)", kept)
    c2.metric(f"[{prefix_key}] Baris Dibuang", dropped)
    c3.metric(f"[{prefix_key}] Total Awal", len(work))

    st.write(f"**Preview Data (SETELAH dibersihkan) – {prefix_key}**")
    st.dataframe(df_clean.head(30), use_container_width = True)

    # Unduh versi bersih (opsional)
    csv_bytes = df_clean.to_csv(index = False).encode("utf-8-sig")
    st.download_button(f"⬇️ Download {prefix_key} (bersih) - CSV", data = csv_bytes, file_name = f"{prefix_key.lower()}_cleaned.csv", mime = "text/csv", key = f"{prefix_key}_dl_csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine = "openpyxl") as writer:
        df_clean.to_excel(writer, index = False, sheet_name = "cleaned")
    st.download_button(f"⬇️ Download {prefix_key} (bersih) - XLSX", data = buf.getvalue(), file_name = f"{prefix_key.lower()}_cleaned.xlsx", mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key = f"{prefix_key}_dl_xlsx")

    return df_clean

# ---------- Upload kedua file ----------
st.markdown("### 1) Upload File")
colA, colB = st.columns(2)
with colA:
    file_a = st.file_uploader("📂 Data Dispusipda (CSV/XLS/XLSX)", type = ["csv", "xlsx", "xls"], key = "file_a")
with colB:
    file_b = st.file_uploader("📂 Data Kab/Kota (CSV/XLS/XLSX)", type = ["csv", "xlsx", "xls"], key = "file_b")

df_a = load_dataframe(file_a, "DataDispusipda") if file_a else None
df_b = load_dataframe(file_b, "DataKab/Kota") if file_b else None

if df_a is not None:
    st.success("Data Dispusipda berhasil dibaca ✅")
if df_b is not None:
    st.success("Data Kab/Kota berhasil dibaca ✅")

# ---------- Bersihkan masing-masing ----------
df_a_clean = clean_with_nik(df_a, "DataDispusipda", "2) Pembersihan NIK – Data Dispusipda") if df_a is not None else None
st.markdown("---")
df_b_clean = clean_with_nik(df_b, "DataKab/Kota", "3) Pembersihan NIK – Data Kab/Kota") if df_b is not None else None

# ---------- Perbandingan ----------
st.markdown("---")
st.subheader("4) Perbandingan NIK antara Data Dispusipda vs Data Kab/Kota")
if df_a_clean is None or df_b_clean is None:
    st.info("Unggah dan bersihkan **kedua** data terlebih dahulu untuk melakukan perbandingan.")
else:
    # Set NIK
    nik_a = set(df_a_clean["NIK"].dropna().astype(str).unique())
    nik_b = set(df_b_clean["NIK"].dropna().astype(str).unique())

    only_in_b = nik_b - nik_a  # NIK yang hanya ada di Data Kab/kota
    only_in_a = nik_a - nik_b  # NIK yang hanya ada di Data Dispusipda

    st.write("**Ringkasan:**")
    c1, c2, c3 = st.columns(3)
    c1.metric("NIK unik di Data Dispusipda", len(nik_a))
    c2.metric("NIK unik di Data Kab/Kota", len(nik_b))
    c3.metric("NIK sama (irisan)", len(nik_a & nik_b))

    # Data Kab/Kota TIDAK dimiliki Data Dispusipda
    st.markdown("#### ➕ NIK hanya di **Data Kab/Kota** (tidak ada di Data Dispusipda)")
    df_only_b = df_b_clean[df_b_clean["NIK"].isin(only_in_b)].copy()
    # tampilkan NIK dulu
    front_cols_b = ["NIK"]
    other_cols_b = [c for c in df_only_b.columns if c not in front_cols_b]
    df_only_b = df_only_b[front_cols_b + other_cols_b]
    st.dataframe(df_only_b.head(50), use_container_width=True)

    csv_b = df_only_b.to_csv(index = False).encode("utf-8-sig")
    st.download_button("⬇️ Download NIK hanya di Data Kab/Kota (CSV)", data = csv_b, file_name = "only_in_data_kab_kota.csv", mime = "text/csv", key = "dl_only_b_csv")
    buf_b = io.BytesIO()
    with pd.ExcelWriter(buf_b, engine = "openpyxl") as writer:
        df_only_b.to_excel(writer, index = False, sheet_name = "only_in_kab_kota")
    st.download_button("⬇️ Download NIK hanya di Data Kab/Kota (XLSX)", data = buf_b.getvalue(), file_name = "only_in_data_baru.xlsx", mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key = "dl_only_b_xlsx")

    # Data Dispusipda TIDAK dimiliki Data Kab/Kota
    st.markdown("#### ➕ NIK hanya di **Data Dispusipda** (tidak ada di Data Kab/Kota)")
    df_only_a = df_a_clean[df_a_clean["NIK"].isin(only_in_a)].copy()
    front_cols_a = ["NIK"]
    other_cols_a = [c for c in df_only_a.columns if c not in front_cols_a]
    df_only_a = df_only_a[front_cols_a + other_cols_a]
    st.dataframe(df_only_a.head(50), use_container_width = True)

    csv_a = df_only_a.to_csv(index = False).encode("utf-8-sig")
    st.download_button("⬇️ Download NIK hanya di Data Dispusipda (CSV)", data = csv_a, file_name = "only_in_data_dispusipda.csv", mime = "text/csv", key = "dl_only_a_csv")
    buf_a = io.BytesIO()
    with pd.ExcelWriter(buf_a, engine = "openpyxl") as writer:
        df_only_a.to_excel(writer, index = False, sheet_name = "only_in_dispusipda")
    st.download_button("⬇️ Download NIK hanya di Data Dispusipda (XLSX)", data = buf_a.getvalue(), file_name = "only_in_data_dispusipda.xlsx", mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key = "dl_only_a_xlsx")

# ---------- Standarisasi Tanpa Upload Mapping ----------
st.markdown("---")
st.subheader("5) Standarisasi Otomatis (sesuai template)")

# 1) Tentukan urutan & nama kolom final yang diinginkan (template)
TEMPLATE_ORDER = ["NO", "NO ANGGOTA", "NAMA", "TEMPAT LAHIR", "TANGGAL LAHIR", "ALAMAT SESUAI KTP", "KECAMATAN SESUAI KTP", "KELURAHAN SESUAI KTP", "RT SESUAI KTP", "RW SESUAI KTP", "PROPINSI SESUAI KTP", "KABUPATEN/KOTA SESUAI KTP", "ALAMAT TEMPAT TINGGAL SEKARANG", "KECAMATAN SEKARANG", "KELURAHAN SEKARANG", "RT SEKARANG", "RW SEKARANG", "PROPINSI SEKARANG", "KABUPATEN/KOTA SEKARANG", "NO. HP", "NO. TELP RUMAH", "JENIS IDENTITAS", "NO. IDENTITAS", "JENIS KELAMIN", "AGAMA", "PEKERJAAN", "IBU KANDUNG", "ALAMAT EMAIL", "JENIS ANGGOTA", "PENDIDIKAN TERAKHIR", "STATUS PERKAWINAN", "TANGGAL PENDAFTARAN", "TANGGAL AKHIR BERLAKU", "JENIS PERMOHONAN", "STATUS ANGGOTA", "NAMA INSTITUSI", "ALAMAT INSTITUSI", "NO TELP INSTITUSI", "NAMA (KEADAAN DARURAT)", "ALAMAT (KEADAAN DARURAT)", "NO TELP (KEADAAN DARURAT)", "STATUS HUBUNGAN (DARURAT)", "UNIT KERJA", "TAHUN AJARAN", "FAKULTAS", "JURUSAN", "PROGRAM STUDI", "KELAS SISWA", "PHOTO URL"]

# 2) Mapping bawaan: kolom sumber di DataBaru & DataAwal.
#    Isi sesuai kolom asli pada df_only_b (Kab/Kota) & df_only_a (Dispusipda).
#    Jika tidak ada/biarkan "", sistem akan coba sinonim & fuzzy match.
MAPPING_BUILTIN = {"NO":                             {"kab": "ID",                    "disp": "ID"},
                   "NO ANGGOTA":                     {"kab": "MemberNo",              "disp": "MemberNo"},
                   "NAMA":                           {"kab": "Fullname",              "disp": "Fullname"},
                   "TEMPAT LAHIR":                   {"kab": "PlaceOfBirth",          "disp": "PlaceOfBirth"},
                   "TANGGAL LAHIR":                  {"kab": "DateOfBirth",           "disp": "DateOfBirth"},
                   "ALAMAT SESUAI KTP":              {"kab": "Address",               "disp": "Address"},
                   "KECAMATAN SESUAI KTP":           {"kab": "Kecamatan",             "disp": "Kecamatan"},
                   "KELURAHAN SESUAI KTP":           {"kab": "Kelurahan",             "disp": "Kelurahan"},
                   "RT SESUAI KTP":                  {"kab": "RT",                    "disp": "RT"},
                   "RW SESUAI KTP":                  {"kab": "RW",                    "disp": "RW"},
                   "PROPINSI SESUAI KTP":            {"kab": "Province",              "disp": "Province"},
                   "KABUPATEN / KOTA SESUAI KTP":    {"kab": "City",                  "disp": "City"},
                   "ALAMAT TEMPAT TINGGAL SEKARANG": {"kab": "AddressNow",            "disp": "AddressNow"},
                   "KECAMATAN SEKARANG":             {"kab": "KecamatanNow",          "disp": "KecamatanNow"},
                   "KELURAHAN SEKARANG":             {"kab": "KelurahanNow",          "disp": "KelurahanNow"},
                   "RT SEKARANG":                    {"kab": "RTNow",                 "disp": "RTNow"},
                   "RW SEKARANG":                    {"kab": "RWNow",                 "disp": "RWNow"},
                   "PROPINSI SEKARANG":              {"kab": "ProvinceNow",           "disp": "ProvinceNow"},
                   "KABUPATEN / KOTA SEKARANG":      {"kab": "CityNow",               "disp": "CityNow"},
                   "NO. HP":                         {"kab": "NoHp",                  "disp": "NoHp"},
                   "NO. TELP RUMAH":                 {"kab": "Phone",                 "disp": "Phone"},
                   "JENIS IDENTITAS":                {"kab": "IdentityType_id",       "disp": "IdentityType_id"},
                   "NO. IDENTITAS":                  {"kab": "IdentityNo",            "disp": "IdentityNo"},
                   "JENIS KELAMIN":                  {"kab": "Sex_id",                "disp": "Sex_id"},
                   "AGAMA":                          {"kab": "Agama_id",              "disp": "Agama_id"},
                   "PEKERJAAN":                      {"kab": "Job_id",                "disp": "Job_id"},
                   "IBU KANDUNG":                    {"kab": "MotherMaidenName",      "disp": "MotherMaidenName"},
                   "ALAMAT EMAIL":                   {"kab": "Email",                 "disp": "Email"},
                   "JENIS ANGGOTA":                  {"kab": "JenisAnggota_id",       "disp": "JenisAnggota_id"},
                   "PENDIDIKAN TERAKHIR":            {"kab": "EducationLevel_id",     "disp": "EducationLevel_id"},
                   "STATUS PERKAWINAN":              {"kab": "MartialStatus_id",      "disp": "MartialStatus_id"},
                   "TANGGAL PENDAFTARAN":            {"kab": "RegisterDate",          "disp": "RegisterDate"},
                   "TANGGAL AKHIR BERLAKU":          {"kab": "EndDate",               "disp": "EndDate"},
                   "JENIS PERMOHONAN":               {"kab": "JenisPermohonan_id",    "disp": "JenisPermohonan_id"},
                   "STATUS ANGGOTA":                 {"kab": "StatusAnggota_id",      "disp": "StatusAnggota_id"},
                   "NAMA INSTITUSI":                 {"kab": "InstitutionName",       "disp": "InstitutionName"},
                   "ALAMAT INSTITUSI":               {"kab": "InstitutionAddress",    "disp": "InstitutionAddress"},
                   "NO TELP INSTITUSI":              {"kab": "InstitutionPhone",      "disp": "InstitutionPhone"},
                   "NAMA (KEADAAN DARURAT)":         {"kab": "NamaDarurat",           "disp": "NamaDarurat"},
                   "ALAMAT (KEADAAN DARURAT)":       {"kab": "AlamatDarurat",         "disp": "AlamatDarurat"},
                   "NO TELP (KEADAAN DARURAT)":      {"kab": "TelpDarurat",           "disp": "TelpDarurat"},
                   "STATUS HUBUNGAN (DARURAT)":      {"kab": "StatusHubunganDarurat", "disp": "StatusHubunganDarurat"},
                   "UNIT KERJA":                     {"kab": "UnitKerja_id",          "disp": "UnitKerja_id"},
                   "TAHUN AJARAN":                   {"kab": "TahunAjaran",           "disp": "TahunAjaran"},
                   "FAKULTAS":                       {"kab": "Fakultas_id",           "disp": "Fakultas_id"},
                   "JURUSAN":                        {"kab": "Jurusan_id",            "disp": "Jurusan_id"},
                   "PROGRAM STUDI":                  {"kab": "ProgramStudi_id",       "disp": "ProgramStudi_id"},
                   "KELAS SISWA":                    {"kab": "Kelas_id",              "disp": "Kelas_id"},
                   "PHOTO URL":                      {"kab": "PhotoUrl",              "disp": "PhotoUrl"}
                  }

# (opsional) kamus sinonim untuk bantu auto-pick jika mapping kosong/typo ringan
# 3) Sinonim untuk membantu auto-pemetaan (opsional — tambah sesuai kebutuhan)
SYNONYMS = {"NO":                             ["ID"],
            "NO ANGGOTA":                     ["NIK", "No KTP", "No_KTP", "IdentityNo", "MemberNo"],
            "NAMA":                           ["Nama Lengkap", "Nama", "FullName", "Name"],
            "TEMPAT LAHIR":                   ["Tempat Lahir", "Tmpt_Lahir", "BirthPlace", "PlaceOfBirth"],
            "TANGGAL LAHIR":                  ["Tanggal Lahir", "Tgl Lahir", "Tgl_Lahir", "BirthDate", "DOB", "dob"],
            "ALAMAT SESUAI KTP":              ["Alamat", "Address", "AddressKTP", "Address_KTP"],
            "KECAMATAN SESUAI KTP":           ["Kecamatan", "Kecamatan KTP", "Kecamatan_KTP"],
            "KELURAHAN SESUAI KTP":           ["Kelurahan", "Kelurahan KTP", "Kelurahan_KTP", "Desa", "Desa KTP", "Desa_KTP"],
            "RT SESUAI KTP":                  ["RT", "Rt", "rt", "RT KTP", "RT_KTP"],
            "RW SESUAI KTP":                  ["RW", "Rw", "rw", "RW KTP", "RW_KTP"],
            "PROPINSI SESUAI KTP":            ["Prov", "Provinsi", "Provinsi KTP", "Provinsi_KTP", "Propinsi", "Province", "Province KTP", "Province_KTP"],
            "KABUPATEN / KOTA SESUAI KTP":    ["Kab/Kota", "Kabupaten/Kota", "Kab / Kota", "Kabupaten / Kota", "Kabupaten", "Kota", "Kab_Kota", "City", "CityKTP", "City KTP", "City_KTP"],
            "ALAMAT TEMPAT TINGGAL SEKARANG": ["Alamat Sekarang", "AlamatSekarang", "Alamat_Sekarang", "AlamatNow", "Alamat_Now", "AddressNow", "Address_Now"],
            "KECAMATAN SEKARANG":             ["Kecamatan Sekarang", "KecamatanSekarang", "Kecamatan_Sekarang", "KecamatanNow", "Kecamatan_Now"],
            "KELURAHAN SEKARANG":             ["Kelurahan Sekarang", "KelurahanSekarang", "Kelurahan_Sekarang", "KelurahanNow", "Kelurahan_Now"],
            "RT SEKARANG":                    ["RTSekarang", "RT Sekarang", "RT_Sekarang", "RT Now", "RTNow", "RT_Now"],
            "RW SEKARANG":                    ["RWSekarang", "RW Sekarang", "RW_Sekarang", "RW Now", "RWNow", "RW_Now"],
            "PROPINSI SEKARANG":              ["ProvNow", "ProvinsiNow", "Provinsi Now", "PropinsiNow", "Propinsi Now", "ProvinceNow", "Province Now", "Prov_Now", "Provinsi_Now", "Propinsi_Now", "Province_Now"],
            "KABUPATEN / KOTA SEKARANG":      ["Kab/Kota Sekarang", "Kabupaten/Kota Sekarang", "Kab / Kota Sekarang", "Kabupaten / Kota Sekarang", "KabupatenSekarang", "KotaSekarang", "Kab_Kota_Sekarang", "City Now", "CityNow", "City_Now"],
            "NO. HP":                         ["No HP", "No. HP", "HP", "Phone", "Telp", "Mobile", "No_Telp", "No_HP"],
            "NO. TELP RUMAH":                 ["Phone", "Telp Rumah", "Telp_Rumah"],
            "JENIS IDENTITAS":                ["IdentityType_id", "Jenis_ID", "Jenis Identitas"],
            "NO. IDENTITAS":                  ["IdentityNo", "No_ID", "No. Identitas"],
            "JENIS KELAMIN":                  ["Jenis Kelamin", "Jenis_Kelamin", "JK", "Gender", "Sex"],
            "AGAMA":                          ["Agama_id", "Agama", "Religion"],
            "PEKERJAAN":                      ["Job_id", "Job", "Pekerjaan", "Pekerjaan Saat Ini"],
            "IBU KANDUNG":                    ["MotherMaidenName", "Nama Ibu Kandung"],
            "ALAMAT EMAIL":                   ["Email", "E-mail"],
            "JENIS ANGGOTA":                  ["JenisAnggota_id", "Jenis Anggota", "Jenis_Anggota"],
            "PENDIDIKAN TERAKHIR":            ["EducationLevel_id", "Pendidikan Terakhir", "Pendidikan_Terakhir"],
            "STATUS PERKAWINAN":              ["MartialStatus_id", "Status Perkawinan", "Status_Perkawinan", "Status Kawin", "Status_Kawin"],
            "TANGGAL PENDAFTARAN":            ["RegisterDate", "Tgl_Daftar"],
            "TANGGAL AKHIR BERLAKU":          ["EndDate", "Tgl_Berakhir"],
            "JENIS PERMOHONAN":               ["JenisPermohonan_id", "JenisPermohonan", "Jenis Permohonan", "Jenis_Permohonan"],
            "STATUS ANGGOTA":                 ["StatusAnggota_id", "StatusAnggota", "Status Anggota", "Status_Anggota"],
            "NAMA INSTITUSI":                 ["InstitutionName", "Institution_Name", "Nama Institusi", "Nama_Institusi"],
            "ALAMAT INSTITUSI":               ["InstitutionAddress", "Institution_Address", "Alamat Institusi", "Alamat_Institusi"],
            "NO TELP INSTITUSI":              ["InstitutionPhone", "Institution_Phone", "Telp Institusi", "Telp_Institusi"],
            "NAMA (KEADAAN DARURAT)":         ["NamaDarurat", "Nama Darurat", "Nama_Darurat", "EmergencyName", "Emergency Name", "Emergency_Name"],
            "ALAMAT (KEADAAN DARURAT)":       ["AlamatDarurat", "Alamat Darurat", "EmergencyAddress", "Emergency Address", "Emergency_Address"],
            "NO TELP (KEADAAN DARURAT)":      ["TelpDarurat", "Telp Darurat", "Telp_Darurat", "Emergency Phone", "EmergencyPhone", "Emergency_Phone"],
            "STATUS HUBUNGAN (DARURAT)":      ["StatusHubunganDarurat", "Status Hubungan Darurat", "Status_Hubungan_Darurat", "Emergency Relation", "EmergencyRelation", "Emergency_Relation"],
            "UNIT KERJA":                     ["UnitKerja_id", "UnitKerja", "Unit Kerja", "Unit_Kerja"],
            "TAHUN AJARAN":                   ["TahunAjaran", "Tahun Ajaran", "Tahun_Ajaran"],
            "FAKULTAS":                       ["Fakultas_id", "Fakultas", "Faculty"],
            "JURUSAN":                        ["Jurusan_id", "Jurusan"],
            "PROGRAM STUDI":                  ["ProgramStudi_id", "Program Studi", "ProgramStudi", "Program_Studi"],
            "KELAS SISWA":                    ["Kelas_id", "Kelas", "Class"],
            "PHOTO URL":                      ["PhotoUrl", "Foto", "Photo"]
           }

def _pick_source_col(df_src: pd.DataFrame, target_name: str, which: str):
    """Ambil kolom sumber berdasar mapping → sinonim → fuzzy."""
    # 1) mapping builtin
    src = MAPPING_BUILTIN.get(target_name, {}).get(which, "")
    if src and src in df_src.columns:
        return src

    # 2) sinonim (case-insensitive)
    lower_map = {str(c).lower(): c for c in df_src.columns}
    for cand in SYNONYMS.get(target_name, [target_name]):
        if str(cand).lower() in lower_map:
            return lower_map[str(cand).lower()]

    # 3) fuzzy (nama template ke kolom sumber)
    match = difflib.get_close_matches(target_name, [str(c) for c in df_src.columns], n = 1, cutoff = 0.85)
    return match[0] if match else None

def _standardize(df_src: pd.DataFrame, which: str):
    """Bentuk dataframe baru persis TEMPLATE_ORDER, isi NA jika tidak ditemukan."""
    out = pd.DataFrame()
    for tgt in TEMPLATE_ORDER:
        src_col = _pick_source_col(df_src, tgt, which)
        out[tgt] = df_src[src_col] if (src_col and src_col in df_src.columns) else pd.NA
    return out

if (df_a_clean is not None) and (df_b_clean is not None):
    # Lihat kolom sumber untuk memudahkan mengedit mapping sekali saja
    with st.expander("Lihat daftar kolom sumber (debug)"):
        st.write("Kolom di output Kab/Kota:", list(df_only_b.columns))
        st.write("Kolom di output Dispusipda:", list(df_only_a.columns))

    std_kab = _standardize(df_only_b, which = "kab")
    std_disp = _standardize(df_only_a, which = "disp")

    st.markdown("#### Preview Standar – Data Kab/Kota")
    st.dataframe(std_kab.head(30), use_container_width = True)
    st.markdown("#### Preview Standar – Data Dispusipda")
    st.dataframe(std_disp.head(30), use_container_width = True)

    # Unduh versi standar
    cdl1, cdl2 = st.columns(2)
    with cdl1:
        st.download_button("⬇️ Download Standar (Kab/Kota) - CSV", data = std_kab.to_csv(index = False).encode("utf-8-sig"), file_name = "only_in_data_kab_kota_standar.csv", mime = "text/csv", key = "dl_std_kab_csv")
        buf1 = io.BytesIO()
        with pd.ExcelWriter(buf1, engine = "openpyxl") as w:
            std_kab.to_excel(w, index = False, sheet_name = "standar")
        st.download_button("⬇️ Download Standar (Kab/Kota) - XLSX", data = buf1.getvalue(), file_name = "only_in_data_kab_kota_standar.xlsx", mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key = "dl_std_kab_xlsx")
    with cdl2:
        st.download_button("⬇️ Download Standar (Dispusipda) - CSV", data = std_disp.to_csv(index = False).encode("utf-8-sig"), file_name = "only_in_data_dispusipda_standar.csv", mime = "text/csv", key = "dl_std_disp_csv")
        buf2 = io.BytesIO()
        with pd.ExcelWriter(buf2, engine = "openpyxl") as w:
            std_disp.to_excel(w, index = False, sheet_name = "standar")
        st.download_button("⬇️ Download Standar (Dispusipda) - XLSX", data = buf2.getvalue(), file_name = "only_in_data_dispusipda_standar.xlsx", mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key = "dl_std_disp_xlsx")
            
# ---------- Watermark/Copyright ----------
st.markdown(
    """
    <style>
      .footer-fixed {position: fixed; left: 0; right: 0; bottom: 0; text-align: center; font-size: 12px; padding: 10px 16px; color: #6b7280; background: rgba(0,0,0,0.04); border-top: 1px solid rgba(0,0,0,0.08); z-index: 9999;}
    </style>
    <div class = "footer-fixed">© 2025 Tim IT Dispusipda Jabar</div>
    """,
    unsafe_allow_html = True,
)
st.markdown("<div style = 'height: 60px'></div>", unsafe_allow_html = True)  # spacer
