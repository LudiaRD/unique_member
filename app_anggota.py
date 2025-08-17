# app.py
import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime, date

st.set_page_config(page_title="Cleansing Anggota – Dispusipda & Sumedang", layout="wide")

st.title("Cleansing & Pencocokan Anggota (NIK)")
st.caption("Unggah dua file Excel, pilih filter tanggal bila perlu, lalu unduh hasilnya (tanpa coding).")

# =========================
# Util fungsi
# =========================
REQUIRED_COLS = ["MemberNo", "IdentityNo", "CreateDate"]

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buf.seek(0)
    return buf.getvalue()

def ensure_required_columns(df: pd.DataFrame, name: str):
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        st.error(f"File **{name}** tidak memiliki kolom wajib: {', '.join(missing)}")
        st.stop()

def normalize_nik_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Pastikan string & trim
    for c in ["MemberNo", "IdentityNo"]:
        df[c] = df[c].astype(str).str.strip()
    return df

def is_valid_nik_len16_awal3(value) -> bool:
    value = str(value)
    return value.isdigit() and len(value) == 16 and value.startswith("3")

def filter_nik_len16_awal3(df: pd.DataFrame) -> pd.DataFrame:
    # Buang baris yang kedua kolom NIK-nya tidak valid (hanya keep yang salah satu valid)
    mask_invalid_both = (~df["MemberNo"].apply(is_valid_nik_len16_awal3)) & \
                        (~df["IdentityNo"].apply(is_valid_nik_len16_awal3))
    return df[~mask_invalid_both].copy()

def apply_date_filter(df: pd.DataFrame, start_d: date, end_d: date) -> pd.DataFrame:
    df = df.copy()
    df["CreateDate"] = pd.to_datetime(df["CreateDate"], errors="coerce")
    df["date"] = df["CreateDate"].dt.date
    # keep antara start dan end (inklusif)
    return df[(df["date"] >= start_d) & (df["date"] <= end_d)].copy()

def format_count(n):
    return f"{n:,}".replace(",", ".")

# =========================
# Sidebar: Upload & opsi
# =========================
st.sidebar.header("1) Unggah File Excel")
f1 = st.sidebar.file_uploader("File A (Dispusipda)", type=["xlsx", "xls"])
f2 = st.sidebar.file_uploader("File B (Sumedang)", type=["xlsx", "xls"])

st.sidebar.header("2) Opsi Filter Tanggal (Opsional)")
use_date_filter = st.sidebar.checkbox("Aktifkan filter tanggal penerapan NIK", value=False)

today = date.today()
if use_date_filter:
    st.sidebar.subheader("Rentang tanggal untuk File A (Dispusipda)")
    start_a = st.sidebar.date_input("Start A", value=date(2023, 8, 1))
    end_a   = st.sidebar.date_input("End A",   value=date(today.year, min(today.month, 12), min(today.day, 28)))

    st.sidebar.subheader("Rentang tanggal untuk File B (Sumedang)")
    start_b = st.sidebar.date_input("Start B", value=date(2025, 1, 1))
    end_b   = st.sidebar.date_input("End B",   value=date(today.year, min(today.month, 12), min(today.day, 28)))
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

    # Baca excel
    try:
        df1 = pd.read_excel(f1, header=0, engine="openpyxl")
        df2 = pd.read_excel(f2, header=0, engine="openpyxl")
    except Exception as e:
        st.error(f"Gagal membaca Excel: {e}")
        st.stop()

    ensure_required_columns(df1, f1.name)
    ensure_required_columns(df2, f2.name)

    # (Opsional) Filter tanggal
    if use_date_filter:
        df1 = apply_date_filter(df1, start_a, end_a)
        df2 = apply_date_filter(df2, start_b, end_b)

    # Filter NIK valid (16 digit, mulai '3') untuk keduanya
    df1_filteredNIK = filter_nik_len16_awal3(df1)
    df2_filteredNIK = filter_nik_len16_awal3(df2)

    # Normalisasi kolom NIK -> string/trim
    df1_filteredNIK = normalize_nik_columns(df1_filteredNIK)
    df2_filteredNIK = normalize_nik_columns(df2_filteredNIK)

    # ===== Pencocokan 1: Tambahan untuk Sumedang (baris di B yang TIDAK ada di A) =====
    nik_set_A = set(df1_filteredNIK["MemberNo"]).union(set(df1_filteredNIK["IdentityNo"]))
    df2_not_in_A = df2_filteredNIK[
        (~df2_filteredNIK["MemberNo"].isin(nik_set_A)) &
        (~df2_filteredNIK["IdentityNo"].isin(nik_set_A))
    ].copy()

    # ===== Pencocokan 2: Tambahan untuk Dispusipda (baris di A yang NIK '3211' dan TIDAK ada di B) =====
    nik_set_B = set(df2_filteredNIK["MemberNo"]).union(set(df2_filteredNIK["IdentityNo"]))

    def is_valid_3211_not_in_B(nik: str) -> bool:
        nik = str(nik)
        return nik.startswith("3211") and (nik not in nik_set_B)

    df1_3211_not_in_B = df1_filteredNIK[
        df1_filteredNIK["MemberNo"].apply(is_valid_3211_not_in_B) |
        df1_filteredNIK["IdentityNo"].apply(is_valid_3211_not_in_B)
    ].copy()

    # =========================
    # Ringkasan & Preview
    # =========================
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

    # Catatan untuk user
    st.info(
        "Logika utama:\n"
        "- Hanya baris dengan **NIK valid (16 digit, mulai '3')** yang dipertahankan.\n"
        "- **B → Tambah**: baris di B yang `MemberNo` **dan** `IdentityNo`-nya tidak muncul di A.\n"
        "- **A → Tambah**: baris di A yang `MemberNo` **atau** `IdentityNo`-nya **mulai '3211'** dan **tidak ada** di B."
    )
else:
    st.markdown(
        """
        **Cara pakai singkat:**
        1. Unggah dua file Excel di sidebar (Dispusipda sebagai *File A*, Sumedang sebagai *File B*).
        2. (Opsional) Aktifkan *Filter Tanggal* dan atur rentang untuk masing-masing file.
        3. Klik **Proses Data** → lihat ringkasan & preview.
        4. Klik tombol **Unduh** untuk menyimpan hasil.
        """
    )
