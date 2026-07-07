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
            if password == "kantor123": 
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Password salah!")
        return False
    return True

if cek_login():
    # ==================== KONEKSI GOOGLE SHEETS ====================
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    KAMUS_HARI = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"
    }

    def ambil_hari_ini():
        hari_inggris = datetime.now().strftime("%A")
        return KAMUS_HARI.get(hari_inggris, hari_inggris)

    # 1. Deteksi Bulan Saat Ini untuk Nama Sheet Otomatis (Format: "July_2026")
    bulan_sekarang = datetime.now().strftime("%B_%Y")
    
    # 2. Ambil Estimasi Saldo Bulan Lalu Berdasarkan Urutan Kronologis (Jika Ada)
    def hitung_saldo_estafet():
        saldo_terakhir_bulan_lalu = 0
        try:
            df_cek = conn.read(ttl="1s")
            if not df_cek.empty and "Saldo" in df_cek.columns:
                df_cek["Saldo"] = pd.to_numeric(df_cek["Saldo"], errors='coerce').fillna(0).astype(int)
                saldo_terakhir_bulan_lalu = int(df_cek.iloc[-1]["Saldo"])
        except Exception:
            pass
        return saldo_terakhir_bulan_lalu

    # 3. Membaca Sheet Bulan Berjalan
    try:
        df_tampil = conn.read(worksheet=bulan_sekarang, ttl="2s")
        if df_tampil.empty or "Saldo" not in df_tampil.columns:
            raise Exception("Sheet Baru")
    except Exception:
        kolom = ["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"]
        df_tampil = pd.DataFrame(columns=kolom)

    # ==================== WEB INTERFACE ====================
    st.title("📱 Cashbook Kantor (Cloud)")
    st.caption(f"📂 Mengakses Tab Bulan: **{bulan_sekarang.replace('_', ' ')}**")
    st.write("---")

    # Hitung Saldo Akhir, Total Debit, Total Kredit di Sheet Aktif
    if not df_tampil.empty and "Saldo" in df_tampil.columns:
        df_tampil["Debit"] = pd.to_numeric(df_tampil["Debit"], errors='coerce').fillna(0).astype(int)
        df_tampil["Kredit"] = pd.to_numeric(df_tampil["Kredit"], errors='coerce').fillna(0).astype(int)
        df_tampil["Saldo"] = pd.to_numeric(df_tampil["Saldo"], errors='coerce').fillna(0).astype(int)
        
        saldo_sekarang = int(df_tampil.iloc[-1]["Saldo"])
        total_pengeluaran = int(df_tampil["Debit"].sum())
        total_pemasukan = int(df_tampil["Kredit"].sum())
    else:
        saldo_sekarang = hitung_saldo_estafet()
        total_pengeluaran = 0
        total_pemasukan = 0

    # Tampilan Ringkasan Utama
    st.metric(label="Sisa Saldo Saat Ini", value=f"Rp {saldo_sekarang:,}")
    
    col_met1, col_met2 = st.columns(2)
    col_met1.metric(label="Total Keluar Bulan Ini", value=f"Rp {total_pengeluaran:,}")
    col_met2.metric(label="Total Masuk Bulan Ini", value=f"Rp {total_pemasukan:,}")

    st.write("---")
    
    # Form Input Transaksi Harian
    with st.form("form_transaksi_sheets", clear_on_submit=True):
        st.subheader("📝 Catat Transaksi Baru")
        deskripsi = st.text_input("Deskripsi / Keperluan:")
        tipe = st.selectbox("Jenis Transaksi:", options=["Kredit (Pemasukan / Tambah Saldo)", "Debit (Pengeluaran)"])
        jumlah = st.number_input("Jumlah Uang (Rp):", min_value=0, value=0, step=5000)
        cb_nota = st.checkbox("Ada Bukti Nota Fisik")
        
        if st.form_submit_button("Simpan ke Google Sheets", type="primary", use_container_width=True):
            if deskripsi and jumlah > 0:
                status_nota = "Ada" if cb_nota else "Tidak Ada"
                debit = jumlah if "Debit" in tipe else 0
                kredit = jumlah if "Kredit" in tipe else 0
                
                saldo_baru = (saldo_sekarang - debit) if debit > 0 else (saldo_sekarang + kredit)
                
                baris_baru = pd.DataFrame([{
                    "Tanggal": datetime.now().strftime("%Y-%m-%d"),
                    "Hari": ambil_hari_ini(),
                    "Deskripsi": deskripsi,
                    "Nota": status_nota,
                    "Debit": int(debit),
                    "Kredit": int(kredit),
                    "Saldo": int(saldo_baru)
                }])
                
                if df_tampil.empty:
                    df_gabung = baris_baru
                else:
                    df_gabung = pd.concat([df_tampil, baris_baru], ignore_index=True)
                    
                conn.update(worksheet=bulan_sekarang, data=df_gabung)
                st.success(f"Berhasil disimpan!")
                st.rerun()
            else:
                st.warning("⚠️ Mohon isi deskripsi dan nominal uang dengan benar!")

    # ==================== FITUR REKAP & DOWNLOAD ====================
    if not df_tampil.empty:
        st.write("---")
        st.subheader("📥 Fitur Download Laporan")
        sheet_target = st.text_input("Ketik nama file/bulan yang ingin diunduh:", value=bulan_sekarang)
        
        if st.button("🔍 Siapkan File Excel untuk Diunduh", use_container_width=True):
            try:
                df_download = conn.read(worksheet=sheet_target, ttl="1s")
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_download.to_excel(writer, index=False, sheet_name=sheet_target)
                    
                st.download_button(
                    label=f"📥 KLIK DI SINI UNTUK UNDUH FILE ({sheet_target}.xlsx)",
                    data=buffer.getvalue(),
                    file_name=f"Laporan_Cashbook_{sheet_target}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception:
                st.error(f"❌ Tab '{sheet_target}' tidak ditemukan!")

        # ==================== FITUR KENDALI DATA (RESET & DELETE) ====================
        st.write("---")
        st.subheader("⚙️ Zona Bahaya (Pembersihan Data)")
        
        if st.button("⚠️ Hapus Baris Transaksi Terakhir", use_container_width=True):
            df_kurang = df_tampil.drop(df_tampil.index[-1])
            conn.update(worksheet=bulan_sekarang, data=df_kurang)
            st.success("Baris terakhir berhasil dihapus!")
            st.rerun()
            
        # TOMBOL RESET DARI AWAL UNTUK MASA UJI COBA
        st.write("")
        konfirmasi_reset = st.checkbox("Saya benar-benar ingin mengosongkan aplikasi untuk bulan ini")
        if st.button("🚨 RESET TOTAL DATA BULAN INI", type="primary", use_container_width=True, disabled=not konfirmasi_reset):
            # Membuat dataframe kosong baru untuk menimpa data asal-asalan
            kolom_kosong = ["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"]
            df_kosong = pd.DataFrame(columns=kolom_kosong)
            conn.update(worksheet=bulan_sekarang, data=df_kosong)
            st.success("Sistem Berhasil Direset! Mengulai Kembali dari Rp 0...")
            st.rerun()

        # Tampilkan Riwayat jika data bulan ini ada
        st.write("---")
        st.subheader("📜 Riwayat Transaksi Bulan Ini")
        for index, row in df_tampil.iloc[::-1].iterrows():
            with st.container():
                warna = "🔴" if int(row['Debit']) > 0 else "🟢"
                nominal = row['Debit'] if int(row['Debit']) > 0 else row['Kredit']
                st.markdown(f"**{warna} {row['Deskripsi']}**")
                st.caption(f"📅 {row['Tanggal']} ({row['Hari']}) | Nota: {row['Nota']}")
                st.markdown(f"Nominal: **Rp {int(nominal):,}** | Sisa Kas: *Rp {int(row['Saldo']):,}*")
                st.write("---")
