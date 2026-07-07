import streamlit as st
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import pandas as pd
import io

# --- KONFIGURASI HALAMAN WEB ---
st.set_page_config(page_title="Office Cashbook Cloud", page_icon="📱", layout="centered")

# ==================== SISTEM KEAMANAN LOGIN ====================
def cek_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.subheader("🔒 Akses Terbatas - Cashbook Kantor")
        password = st.text_input("Masukkan Password Akses:", type="password")
        if st.button("Masuk", type="primary", use_container_width=True):
            # Anda bisa mengganti password 'kantor123' di bawah ini sesuai keinginan
            if password == "kantor123": 
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Password salah!")
        return False
    return True

if cek_login():
    # ==================== KONEKSI GOOGLE SHEETS ====================
    # Otomatis membaca konfigurasi dari .streamlit/secrets.toml
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    KAMUS_HARI = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"
    }

    def ambil_hari_ini():
        hari_inggris = datetime.now().strftime("%A")
        return KAMUS_HARI.get(hari_inggris, hari_inggris)

    # Membaca data terbaru dari awan Google Sheets
    try:
        df_tampil = conn.read(ttl="5s") # Data otomatis refresh jika ada perubahan dalam 5 detik
    except Exception:
        # Jika Google Sheets masih kosong atau baru dibuat
        kolom = ["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"]
        df_tampil = pd.DataFrame(columns=kolom)

    # ==================== WEB INTERFACE (MOBILE OPTIMIZED) ====================
    st.title("📱 Cashbook Kantor (Cloud)")
    st.write("Data tersimpan otomatis dan permanen di Google Sheets Kantor.")
    st.write("---")

    # Logika Menghitung Saldo Akhir, Total Debit, Total Kredit
    if not df_tampil.empty:
        # Memastikan data dibaca sebagai angka bersih
        df_tampil["Debit"] = pd.to_numeric(df_tampil["Debit"], errors='coerce').fillna(0).astype(int)
        df_tampil["Kredit"] = pd.to_numeric(df_tampil["Kredit"], errors='coerce').fillna(0).astype(int)
        df_tampil["Saldo"] = pd.to_numeric(df_tampil["Saldo"], errors='coerce').fillna(0).astype(int)
        
        saldo_sekarang = int(df_tampil.iloc[-1]["Saldo"])
        total_pengeluaran = int(df_tampil["Debit"].sum())
        total_pemasukan = int(df_tampil["Kredit"].sum())
    else:
        saldo_sekarang = 0
        total_pengeluaran = 0
        total_pemasukan = 0

    # Tampilan Ringkasan Utama (Sangat pas untuk layar vertikal HP)
    st.metric(label="Sisa Saldo Saat Ini", value=f"Rp {saldo_sekarang:,}")
    
    col_met1, col_met2 = st.columns(2)
    col_met1.metric(label="Total Keluar (Debit)", value=f"Rp {total_pengeluaran:,}")
    col_met2.metric(label="Total Masuk (Kredit)", value=f"Rp {total_pemasukan:,}")

    # Tampilan Jika Spreadsheet Baru Pertama Kali Dipakai
    if df_tampil.empty:
        st.subheader("⚙️ Inisialisasi Saldo Awal")
        saldo_awal = st.number_input("Nominal Uang Kas Awal (Rp):", min_value=0, value=1000000)
        if st.button("🚀 Set Saldo Awal", type="primary", use_container_width=True):
            data_awal = pd.DataFrame([{
                "Tanggal": datetime.now().strftime("%Y-%m-%d"),
                "Hari": ambil_hari_ini(),
                "Deskripsi": "Saldo Awal",
                "Nota": "-",
                "Debit": 0,
                "Kredit": 0,
                "Saldo": int(saldo_awal)
            }])
            conn.update(data=data_awal)
            st.success("Saldo awal berhasil dikunci di Google Sheets!")
            st.rerun()
    else:
        # Form Input Transaksi Harian Kantor
        st.write("---")
        with st.form("form_transaksi_sheets", clear_on_submit=True):
            st.subheader("📝 Catat Transaksi Baru")
            deskripsi = st.text_input("Deskripsi / Keperluan:")
            tipe = st.selectbox("Jenis Transaksi:", options=["Debit (Pengeluaran)", "Kredit (Pemasukan)"])
            jumlah = st.number_input("Jumlah Uang (Rp):", min_value=0, value=0, step=5000)
            cb_nota = st.checkbox("Ada Bukti Nota Fisik")
            
            if st.form_submit_button("Simpan ke Google Sheets", type="primary", use_container_width=True):
                if deskripsi and jumlah > 0:
                    status_nota = "Ada" if cb_nota else "Tidak Ada"
                    debit = jumlah if tipe == "Debit (Pengeluaran)" else 0
                    kredit = jumlah if tipe == "Kredit (Pemasukan)" else 0
                    saldo_baru = (saldo_sekarang - debit) if tipe == "Debit (Pengeluaran)" else (saldo_sekarang + kredit)
                    
                    baris_baru = pd.DataFrame([{
                        "Tanggal": datetime.now().strftime("%Y-%m-%d"),
                        "Hari": ambil_hari_ini(),
                        "Deskripsi": deskripsi,
                        "Nota": status_nota,
                        "Debit": int(debit),
                        "Kredit": int(kredit),
                        "Saldo": int(saldo_baru)
                    }])
                    
                    # Menggabungkan baris data baru ke data lama
                    df_gabung = pd.concat([df_tampil, baris_baru], ignore_index=True)
                    conn.update(data=df_gabung)
                    st.success("Berhasil di-sinkronisasi ke Google Sheets!")
                    st.rerun()
                else:
                    st.warning("⚠️ Mohon isi deskripsi dan nominal uang dengan benar!")

        # ==================== FITUR EXPORT UNTUK HP ====================
        st.write("---")
        st.subheader("📥 Ekspor Rekap Bulanan")
        st.write("Teman Anda bisa mengunduh data langsung ke memori HP dalam format Excel asli:")

        # Mengubah data dari cloud menjadi file Excel virtual di memori server
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_tampil.to_excel(writer, index=False, sheet_name="Rekap_Cashbook")
            
        st.download_button(
            label="📥 UNDUH FILE EXCEL (`.xlsx`) KE HP",
            data=buffer.getvalue(),
            file_name=f"Laporan_Cashbook_{datetime.now().strftime('%d%m%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        # Fitur Hapus Transaksi Terakhir (Koreksi salah input)
        st.write("---")
        st.subheader("⚙️ Koreksi Data")
        if st.button("⚠️ Hapus Baris Transaksi Terakhir", use_container_width=True):
            if len(df_tampil) <= 1:
                st.error("Hanya tersisa Saldo Awal, tidak bisa dihapus.")
            else:
                df_kurang = df_tampil.drop(df_tampil.index[-1])
                conn.update(data=df_kurang)
                st.success("Baris terakhir berhasil dihapus dari Google Sheets!")
                st.rerun()

        # Tampilan Riwayat Berbentuk Kartu Vertikal (Sangat bersahabat untuk layar HP)
        st.write("---")
        st.subheader("📜 Riwayat Buku Kas Terkini")
        for index, row in df_tampil.iloc[::-1].iterrows():
            with st.container():
                warna = "🔴" if row['Debit'] > 0 else "🟢"
                nominal = row['Debit'] if row['Debit'] > 0 else row['Kredit']
                st.markdown(f"**{warna} {row['Deskripsi']}**")
                st.caption(f"📅 {row['Tanggal']} ({row['Hari']}) | Nota: {row['Nota']}")
                st.markdown(f"Nominal: **Rp {nominal:,}** | Sisa Kas: *Rp {row['Saldo']:,}*")
                st.write("---")