# app.py
import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date, timedelta
from pathlib import Path

# =========================
# Konfigurasi halaman
# =========================
st.set_page_config(page_title="Cleansing & Pencocokan Anggota (NIK)", layout="wide")
st.title("Cleansing & Pencocokan Anggota (NIK)")
st.caption("Unggah dua file (Excel/CSV), atur (opsional) filter tanggal, lalu unduh hasilnya — tanpa coding.")

# =========================
# Util fungsi
# =========================
REQUIRED_COLS = ["MemberNo", "IdentityNo", "CreateDate"]

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Simpan DataFrame ke bytes Excel (untuk download_button)."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buf.seek(0)
    return buf.getvalue()

def ensure_required_columns(df: pd.DataFrame, name: str):
    """Pastikan kolom wajib tersedia; hentikan app bila tidak lengkap."""
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        st.error(f"File **{name}** tidak memiliki kolom wajib: {', '.join(missing)}")
        st.stop()

def normalize_nik_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Pastikan kolom NIK berformat string dan di-trim spasi."""
    df = df.copy()
    for c in ["MemberNo", "IdentityNo"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    return df

def is_valid_nik_len16_awal3(value) -> bool:
    """Validasi NIK: 16 digit dan dimulai '3'."""
    s = str(value)
    return s.isdigit() and len(s) == 16 and s.startswith("3")

def filter_nik_len16_awal3(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hanya pertahankan baris yang setidaknya SALAH SATU dari kolom (MemberNo/IdentityNo)
    merupakan NIK valid (16 digit & mulai '3').
    """
    df = df.copy()
    m_valid = df["MemberNo"].apply(is_valid_nik_len16_awal3)
    i_valid = df["IdentityNo"].apply(is_valid_nik_len16_awal3)
    return df[m_valid | i_valid].copy()

def apply_date_filter(df: pd.DataFrame, start_d: date, end_d: date) -> pd.DataFrame:
    """Filter baris berdasarkan rentang tanggal (inklusif) pada kolom CreateDate."""
    df = df.copy()
    df["CreateDate"] = pd.to_datetime(df["CreateDate"], errors="coerce")
    df["date"] = df["CreateDate"].dt.date
    return df[(df["date"] >= start_d) & (df["date"] <= end_d)].copy()

def format_count(n: int) -> str:
    return f"{n:,}".replace(",", ".")

def load_file(uploaded_file):
    """Baca file Excel/CSV menjadi DataFrame."""
    if uploaded_file is None:
        return None
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            # Coba auto-detect delimiter; jika perlu bisa tambahkan parameter sep
            df = pd.read_csv(uploaded_file)
        elif name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        else:
            st.error(f"Ekstensi file {uploaded_file.name} tidak didukung. Gunakan .csv, .xlsx, atau .xls")
            st.stop()
    except Exception as e:
        st.error(f"Gagal membaca {uploaded_file.name}: {e}")
        st.stop()
    return df

# =========================
# Sidebar: Upload & opsi
# =========================
st.sidebar.header("1) Unggah File Excel/CSV")
f1 = st.sidebar.file_uploader("File A (Dispusipda)", type=["xlsx", "xls", "csv"], key="a")
f2 = st.sidebar.file_uploader("File B (Sumedang)", type=["xlsx", "xls", "csv"], key="b")

st.sidebar.header("2) Opsi Filter Tanggal (Opsional)")
use_date_filter = st.sidebar.checkbox("Aktifkan filter tanggal penerapan NIK", value=False)

today = date.today()
default_end = today - timedelta(days=1) if today.day == 1 else today
if use_date_filter:
    st.sidebar.subheader("Rentang tanggal untuk File A (Dispusipda)")
    start_a = st.sidebar.date_input("Start A", value=date(2023, 8, 1))
    end_a   = st.sidebar.date_input("End A",   value=default_end)

    st.sidebar.subheader("Rentang tanggal untuk File B (Sumedang)")
    start_b = st.sidebar.date_input("Start B", value=date(2025, 1, 1))
    end_b   = st.sidebar.date_input("End B",   value=default_end)
else:
    start_a = end_a = start_b = end_b = None

process = st.sidebar.button("Proses Data")

# =========================
# Main logic
# =========================
if process:
    if not f1 or not f2:
        st.warning("Silakan unggah **dua** file terlebih dahulu.")
        st.stop()

    # Baca file
    df1 = load_file(f1)
    df2 = load_file(f2)

    # Validasi kolom
    ensure_required_columns(df1, f1.name)
    ensure_required_columns(df2, f2.name)

    # (Opsional) Filter tanggal
    if use_date_filter:
        df1 = apply_date_filter(df1, start_a, end_a)
        df2 = apply_date_filter(df2, start_b, end_b)

    # Normalisasi + filter NIK valid
    df1 = normalize_nik_columns(df1)
    df2 = normalize_nik_columns(df2)

    df1_filteredNIK = filter_nik_len16_awal3(df1)
    df2_filteredNIK = filter_nik_len16_awal3(df2)

    # Set NIK untuk pencocokan
    nik_set_A = set(df1_filteredNIK["MemberNo"]).union(set(df1_filteredNIK["IdentityNo"]))
    nik_set_B = set(df2_filteredNIK["MemberNo"]).union(set(df2_filteredNIK["IdentityNo"]))

    # B → Tambah (baris di B yang tidak ada di A pada kedua kolom NIK)
    df2_not_in_A = df2_filteredNIK[
        (~df2_filteredNIK["MemberNo"].isin(nik_set_A)) &
        (~df2_filteredNIK["IdentityNo"].isin(nik_set_A))
    ].copy()

    # A → Tambah (baris di A yang NIK '3211' & tidak ada di B)
    def is_valid_3211_not_in_B(nik: str) -> bool:
        s = str(nik)
        return s.startswith("3211") and (s not in nik_set_B)

    df1_3211_not_in_B = df1_filteredNIK[
        df1_filteredNIK["MemberNo"].apply(is_valid_3211_not_in_B) |
        df1_filteredNIK["IdentityNo"].apply(is_valid_3211_not_in_B)
    ].copy()

    # =========================
    # Ringkasan & Preview
    # =========================
    st.subheader("Ringkasan")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Baris A (setelah filter NIK)", format_count(len(df1_filteredNIK)))
    col2.metric("Baris B (setelah filter NIK)", format_count(len(df2_filteredNIK)))
    col3.metric("B → Tambah (Tidak ada di A)", format_count(len(df2_not_in_A)))
    col4.metric("A → Tambah (NIK 3211 & tdk ada di B)", format_count(len(df1_3211_not_in_B)))

    with st.expander("Preview A (setelah filter NIK)"):
        st.dataframe(df1_filteredNIK.head(50), use_container_width=True)
    with st.expander("Preview B (setelah filter NIK)"):
        st.dataframe(df2_filteredNIK.head(50), use_container_width=True)
    with st.expander("Preview B → Tambah (tidak ada di A)"):
        st.dataframe(df2_not_in_A.head(50), use_container_width=True)
    with st.expander("Preview A → Tambah (NIK 3211 & tidak ada di B)"):
        st.dataframe(df1_3211_not_in_B.head(50), use_container_width=True)

    # =========================
    # Unduh hasil
    # =========================
    st.subheader("Unduh Hasil")

    colA, colB = st.columns(2)
    with colA:
        st.download_button(
            label="Unduh A (setelah filter NIK)",
            data=to_excel_bytes(df1_filteredNIK),
            file_name="output_filtered_df1.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.download_button(
            label="Unduh A → Tambah (NIK 3211 & tdk ada di B)",
            data=to_excel_bytes(df1_3211_not_in_B),
            file_name="output_member_dispusipda.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with colB:
        st.download_button(
            label="Unduh B (setelah filter NIK)",
            data=to_excel_bytes(df2_filteredNIK),
            file_name="output_filtered_df2.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.download_button(
            label="Unduh B → Tambah (tidak ada di A)",
            data=to_excel_bytes(df2_not_in_A),
            file_name="output_member_sumedang.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.info(
        "Logika utama:\n"
        "- Pertahankan baris dengan **NIK valid (16 digit, mulai '3')** di `MemberNo` **atau** `IdentityNo`.\n"
        "- **B → Tambah**: baris di B yang **tidak muncul** di A pada kedua kolom NIK.\n"
        "- **A → Tambah**: baris di A yang NIK-nya **mulai '3211'** dan **tidak ada** di B."
    )
else:
    st.markdown(
        """
        **Cara pakai singkat:**
        1. Unggah dua file (Excel/CSV) di sidebar — *File A* (Dispusipda) & *File B* (Sumedang).
        2. (Opsional) Aktifkan *Filter Tanggal* dan atur rentang untuk masing-masing file.
        3. Klik **Proses Data** → periksa ringkasan & preview.
        4. Klik tombol **Unduh** untuk menyimpan hasil (Excel).
        """
    )

# =========================
# Footer kecil
# =========================
st.caption("© 2025 — Utility cleansing anggota. Pastikan kolom: MemberNo, IdentityNo, CreateDate.")
