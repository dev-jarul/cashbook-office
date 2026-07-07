import streamlit as st
from streamlit_gsheets import GSheetsConnection
import gspread
import json
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
    # Menggunakan gsheets bawaan untuk MEMBACA (karena ada fitur cache otomatis)
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # Fungsi koneksi yang sudah dilengkapi pembersih karakter eror otomatis
    def dapatkan_koneksi_gspread():
        # Mengambil data kredensial langsung dari Streamlit Secrets Anda
        kredensial_mentah = st.secrets["connections"]["gsheets"]["service_account"]
        spreadsheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        
        # --- PROSES PEMBERSIHAN KARAKTER (ANTI-INVALID CONTROL CHARACTER) ---
        # Menghapus karakter spasi/enter aneh di ujung teks
        kredensial_bersih = kredensial_mentah.strip()
        # Mengganti baris patah tersembunyi agar aman dibaca oleh json.loads
        kredensial_bersih = kredensial_bersih.replace('\n', '\\n').replace('\r', '\\r')
        
        # Coba konversi teks bersih ke objek JSON murni
        try:
            kredensial_json = json.loads(kredensial_bersih)
        except json.JSONDecodeError:
            # Jika cara pertama gagal karena masalah backslash pada private_key, gunakan cara alternatif ini
            kredensial_json = json.loads(kredensial_mentah, strict=False)
        
        gc = gspread.service_account_from_dict(kredensial_json)
        sh = gc.open_by_url(spreadsheet_url)
        return sh.get_worksheet(0) # Mengambil sheet pertama (Sheet1)
    KAMUS_HARI = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"
    }

    def ambil_hari_ini():
        hari_inggris = datetime.now().strftime("%A")
        return KAMUS_HARI.get(hari_inggris, hari_inggris)

    bulan_aktif = datetime.now().strftime("%Y-%m")
    nama_bulan_ini = datetime.now().strftime("%B %Y")

    # Membaca data dari Google Sheets
    try:
        df_master = conn.read(ttl="2s")
        if df_master.empty or "Saldo" not in df_master.columns:
            kolom = ["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"]
            df_master = pd.DataFrame(columns=kolom)
    except Exception:
        kolom = ["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"]
        df_master = pd.DataFrame(columns=kolom)

    # Pastikan tipe data angka benar
    if not df_master.empty:
        df_master["Debit"] = pd.to_numeric(df_master["Debit"], errors='coerce').fillna(0).astype(int)
        df_master["Kredit"] = pd.to_numeric(df_master["Kredit"], errors='coerce').fillna(0).astype(int)
        df_master["Saldo"] = pd.to_numeric(df_master["Saldo"], errors='coerce').fillna(0).astype(int)
        saldo_global_terakhir = int(df_master.iloc[-1]["Saldo"])
    else:
        saldo_global_terakhir = 0

    # ==================== WEB INTERFACE ====================
    st.title("📱 Cashbook Kantor (Cloud)")
    st.caption(f"📅 Menampilkan Transaksi Bulan: **{nama_bulan_ini}**")
    st.write("---")

    # Filter data khusus bulan ini saja untuk tampilan
    if not df_master.empty:
        df_bulan_ini = df_master[df_master["Tanggal"].str.startswith(bulan_aktif, na=False)]
        total_pengeluaran_bulan_ini = int(df_bulan_ini["Debit"].sum())
        total_pemasukan_bulan_ini = int(df_bulan_ini["Kredit"].sum())
    else:
        df_bulan_ini = pd.DataFrame()
        total_pengeluaran_bulan_ini = 0
        total_pemasukan_bulan_ini = 0

    # Tampilan Ringkasan Berdasarkan Saldo Kumulatif
    st.metric(label="Sisa Saldo Kas Saat Ini", value=f"Rp {saldo_global_terakhir:,}")
    
    col_met1, col_met2 = st.columns(2)
    col_met1.metric(label="Pengeluaran Bulan Ini", value=f"Rp {total_pengeluaran_bulan_ini:,}")
    col_met2.metric(label="Pemasukan Bulan Ini", value=f"Rp {total_pemasukan_bulan_ini:,}")

    st.write("---")
    
    # Form Input Transaksi Harian
    with st.form("form_transaksi_master", clear_on_submit=True):
        st.subheader("📝 Catat Transaksi Baru")
        deskripsi = st.text_input("Deskripsi / Keperluan:")
        tipe = st.selectbox("Jenis Transaksi:", options=["Kredit (Pemasukan / Uang Masuk)", "Debit (Pengeluaran)"])
        jumlah = st.number_input("Jumlah Uang (Rp):", min_value=0, value=0, step=5000)
        cb_nota = st.checkbox("Ada Bukti Nota Fisik")
        
        if st.form_submit_button("Simpan ke Google Sheets", type="primary", use_container_width=True):
            if deskripsi and jumlah > 0:
                status_nota = "Ada" if cb_nota else "Tidak Ada"
                debit = jumlah if "Debit" in tipe else 0
                kredit = jumlah if "Kredit" in tipe else 0
                
                saldo_baru = (saldo_global_terakhir - debit) if debit > 0 else (saldo_global_terakhir + kredit)
                
                # Baris baru yang akan ditambahkan ke Google Sheets
                baris_data = [
                    datetime.now().strftime("%Y-%m-%d"),
                    ambil_hari_ini(),
                    deskripsi,
                    status_nota,
                    int(debit),
                    int(kredit),
                    int(saldo_baru)
                ]
                
                try:
                    sheet_target = dapatkan_koneksi_gspread()
                    # Jika sheet kosong, tulis baris judul kolom terlebih dahulu
                    if df_master.empty:
                        sheet_target.append_row(["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"])
                    
                    # Tambahkan baris baru ke paling bawah sheet menggunakan gspread
                    sheet_target.append_row(baris_data)
                    st.success("Berhasil disimpan ke Google Sheets!")
                    st.toast("Data Tersinkronisasi!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal menulis ke Google Sheets. Eror: {e}")
            else:
                st.warning("⚠️ Mohon isi deskripsi dan nominal uang dengan benar!")

    # ==================== FITUR DOWNLOAD LAPORAN ====================
    if not df_master.empty:
        st.write("---")
        st.subheader("📥 Fitur Download Laporan")
        df_master["TahunBulan"] = df_master["Tanggal"].str.slice(0, 7)
        pilihan_bulan = df_master["TahunBulan"].unique().tolist()
        bulan_pilihan = st.selectbox("Pilih bulan laporan yang ingin diunduh:", options=pilihan_bulan)
        
        if st.button("🔍 Siapkan File Excel untuk Diunduh", use_container_width=True):
            df_download = df_master[df_master["Tanggal"].str.startswith(bulan_pilihan, na=False)].drop(columns=["TahunBulan"])
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_download.to_excel(writer, index=False, sheet_name=f"Rekap_{bulan_pilihan}")
                
            st.download_button(
                label=f"📥 KLIK DI SINI UNTUK UNDUH FILE ({bulan_pilihan}.xlsx)",
                data=buffer.getvalue(),
                file_name=f"Laporan_Cashbook_{bulan_pilihan}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # ==================== FITUR RESET (ZONA UJI COBA) ====================
    if not df_master.empty:
        st.write("---")
        st.subheader("⚙️ Zona Bahaya (Pembersihan Data)")
        
        konfirmasi_reset = st.checkbox("Saya ingin mengosongkan SELURUH DATA Google Sheets")
        if st.button("🚨 RESET TOTAL SEMUA DATA", type="primary", use_container_width=True, disabled=not konfirmasi_reset):
            try:
                sheet_target = dapatkan_koneksi_gspread()
                sheet_target.clear() # Menghapus total isi Google Sheets
                sheet_target.append_row(["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"])
                st.success("Sistem Berhasil Direset ke Nol!")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal melakukan reset: {e}")

        # Tampilkan Riwayat Transaksi khusus bulan aktif ini saja
        if not df_bulan_ini.empty:
            st.write("---")
            st.subheader("📜 Riwayat Transaksi Bulan Ini")
            for index, row in df_bulan_ini.iloc[::-1].iterrows():
                with st.container():
                    warna = "🔴" if int(row['Debit']) > 0 else "🟢"
                    nominal = row['Debit'] if int(row['Debit']) > 0 else row['Kredit']
                    st.markdown(f"**{warna} {row['Deskripsi']}**")
                    st.caption(f"📅 {row['Tanggal']} ({row['Hari']}) | Nota: {row['Nota']}")
                    st.markdown(f"Nominal: **Rp {int(nominal):,}** | Sisa Kas: *Rp {int(row['Saldo']):,}*")
                    st.write("---")
