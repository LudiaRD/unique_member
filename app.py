import io
import re
import pandas as pd
import streamlit as st

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
    st.dataframe(df_only_a.head(50), use_container_width=True)

    csv_a = df_only_a.to_csv(index = False).encode("utf-8-sig")
    st.download_button("⬇️ Download NIK hanya di Data Dispusipda (CSV)", data = csv_a, file_name = "only_in_data_dispusipda.csv", mime = "text/csv", key = "dl_only_a_csv")
    buf_a = io.BytesIO()
    with pd.ExcelWriter(buf_a, engine = "openpyxl") as writer:
        df_only_a.to_excel(writer, index = False, sheet_name = "only_in_dispusipda")
    st.download_button("⬇️ Download NIK hanya di Data Dispusipda (XLSX)", data = buf_a.getvalue(), file_name = "only_in_data_dispusipda.xlsx", mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key = "dl_only_a_xlsx")
