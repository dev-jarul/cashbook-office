import streamlit as st
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
    # ==================== KONEKSI GOOGLE SHEETS VIA GSPREAD ====================
    def dapatkan_koneksi_spreadsheet():
        try:
            kredensial_mentah = st.secrets["connections"]["gsheets"]["service_account"]
            spreadsheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            kredensial_json = json.loads(kredensial_mentah, strict=False)
            
            gc = gspread.service_account_from_dict(kredensial_json)
            sh = gc.open_by_url(spreadsheet_url)
            return sh
        except Exception as e:
            st.error(f"❌ Masalah Koneksi Google Sheets: {e}")
            st.stop()

    KAMUS_HARI = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"
    }

    def ambil_hari_ini():
        hari_inggris = datetime.now().strftime("%A")
        return KAMUS_HARI.get(hari_inggris, hari_inggris)

    # Ambil Dokumen Spreadsheet Utama
    sh = dapatkan_koneksi_spreadsheet()
    
    # Ambil seluruh nama sheet (tab) yang tersedia untuk pilihan Dropdown
    daftar_sheet = [ws.title for ws in sh.worksheets()]
    
    # Deteksi rekomendasi nama sheet baru berdasarkan waktu saat ini (Format: "Juli_2026")
    BULAN_INDO = {
        "January": "Januari", "February": "Februari", "March": "Maret", "April": "April",
        "May": "Mei", "June": "Juni", "July": "Juli", "August": "Agustus",
        "September": "September", "October": "Oktober", "November": "November", "December": "Desember"
    }
    bulan_inggris = datetime.now().strftime("%B")
    bulan_lokal = BULAN_INDO.get(bulan_inggris, bulan_inggris)
    tahun_sekarang = datetime.now().strftime("%Y")
    rekomendasi_sheet_baru = f"{bulan_lokal}_{tahun_sekarang}"

    # --- Pilihan Dropdown Sheet Aktif di Navigasi Atas ---
    st.title("📱 Cashbook Kantor (Cloud)")
    sheet_aktif = st.selectbox("📂 Pilih Tab / Bulan Kerja Saat Ini:", options=daftar_sheet)
    st.write("---")

    # Membaca data dari sheet yang dipilih
    ws_aktif = sh.worksheet(sheet_aktif)
    semua_data = ws_aktif.get_all_records()

    if len(semua_data) == 0:
        df_master = pd.DataFrame(columns=["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"])
    else:
        df_master = pd.DataFrame(semua_data)
        df_master = df_master[df_master["Tanggal"] != "Tanggal"]

    # Cari Saldo Terakhir Global (Mencari dari sheet aktif saat ini)
    if not df_master.empty and "Saldo" in df_master.columns:
        df_master["Debit"] = pd.to_numeric(df_master["Debit"], errors='coerce').fillna(0).astype(int)
        df_master["Kredit"] = pd.to_numeric(df_master["Kredit"], errors='coerce').fillna(0).astype(int)
        df_master["Saldo"] = pd.to_numeric(df_master["Saldo"], errors='coerce').fillna(0).astype(int)
        saldo_terakhir_aktif = int(df_master.iloc[-1]["Saldo"])
        total_pengeluaran = int(df_master["Debit"].sum())
        total_pemasukan = int(df_master["Kredit"].sum())
    else:
        saldo_terakhir_aktif = 0
        total_pengeluaran = 0
        total_pemasukan = 0

    # Tampilan Ringkasan Berdasarkan Tab Terpilih
    st.metric(label=f"Sisa Saldo Kas di Tab ({sheet_aktif})", value=f"Rp {saldo_terakhir_aktif:,}")
    col_met1, col_met2 = st.columns(2)
    col_met1.metric(label="Total Keluar Tab Ini", value=f"Rp {total_pengeluaran:,}")
    col_met2.metric(label="Total Masuk Tab Ini", value=f"Rp {total_pemasukan:,}")
    st.write("---")

    # ==================== FITUR TAMBAH SHEET BARU (ESTAFET SALDO) ====================
    with st.expander("➕ Menu Tambah Sheet / Tab Baru"):
        st.write("Fitur ini akan membuat tab bulanan baru di Google Sheets Anda dan mengestafetkan sisa saldo terakhir.")
        nama_baru = st.text_input("Nama Sheet Baru:", value=rekomendasi_sheet_baru)
        
        if st.button("🚀 Buat dan Pindahkan Saldo Terakhir", use_container_width=True):
            if nama_baru in daftar_sheet:
                st.warning(f"⚠️ Tab '{nama_baru}' sudah ada di Google Sheets Anda!")
            else:
                try:
                    # 1. Buat Sheet Baru di Google Sheets
                    ws_baru = sh.add_worksheet(title=nama_baru, rows="1000", cols="20")
                    # 2. Tulis Header
                    ws_baru.append_row(["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"])
                    # 3. Tulis Baris Pertama bawaan sisa saldo terakhir dari tab sebelumnya
                    baris_awal = [
                        datetime.now().strftime("%Y-%m-%d"),
                        ambil_hari_ini(),
                        f"Estafet Saldo Akhir dari {sheet_aktif}",
                        "-",
                        0,
                        0,
                        int(saldo_terakhir_aktif)
                    ]
                    ws_baru.append_row(baris_awal)
                    st.success(f"🎉 Tab '{nama_baru}' berhasil dibuat dengan saldo awal Rp {saldo_terakhir_aktif:,}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal membuat sheet baru: {e}")

    st.write("---")

    # ==================== FORM INPUT TRANSAKSI HARIAN ====================
    with st.form("form_transaksi_gspread", clear_on_submit=True):
        st.subheader(f"📝 Tambah Data Ke Tab: {sheet_aktif}")
        deskripsi = st.text_input("Deskripsi / Keperluan:")
        tipe = st.selectbox("Jenis Transaksi:", options=["Kredit (Pemasukan / Uang Masuk)", "Debit (Pengeluaran)"])
        jumlah = st.number_input("Jumlah Uang (Rp):", min_value=0, value=0, step=5000)
        cb_nota = st.checkbox("Ada Bukti Nota Fisik")
        
        if st.form_submit_button("Simpan ke Google Sheets", type="primary", use_container_width=True):
            if deskripsi and jumlah > 0:
                status_nota = "Ada" if cb_nota else "Tidak Ada"
                debit = jumlah if "Debit" in tipe else 0
                kredit = jumlah if "Kredit" in tipe else 0
                
                saldo_baru = (saldo_terakhir_aktif - debit) if debit > 0 else (saldo_terakhir_aktif + kredit)
                
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
                    ws_aktif.append_row(baris_data)
                    st.success(f"Berhasil disimpan ke Tab {sheet_aktif}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal menulis data: {e}")
            else:
                st.warning("⚠️ Mohon isi deskripsi dan nominal uang dengan benar!")

    # ==================== TABEL DATA SINKRON (RATA TENGAH / AUTO-CENTER) ====================
    if not df_master.empty:
        st.write("---")
        st.subheader(f"📊 Tabel Data Terkini - Tab {sheet_aktif}")
        
        # Mengubah style seluruh kolom di dataframe agar teks dan angka menjadi RATA TENGAH (CENTER)
        df_tampil = df_master.copy()
        df_tampil["Debit"] = df_tampil["Debit"].apply(lambda x: f"Rp {x:,}")
        df_tampil["Kredit"] = df_tampil["Kredit"].apply(lambda x: f"Rp {x:,}")
        df_tampil["Saldo"] = df_tampil["Saldo"].apply(lambda x: f"Rp {x:,}")
        
        # Logika CSS untuk meratakan seluruh kolom ke tengah
        st.markdown(
            """
            <style>
            .dataframe th { text-align: center !important; }
            .dataframe td { text-align: center !important; }
            </style>
            """, 
            unsafe_allow_html=True
        )
        
        # Menampilkan dataframe statis yang bersih dan rapi di layar HP
        st.dataframe(df_tampil, use_container_width=True, hide_index=True)

        # ==================== FITUR DOWNLOAD PER TAB BULANAN ====================
        st.write("---")
        st.subheader("📥 Download File Excel Tab Ini")
        
        if st.button("🔍 Siapkan File Excel untuk Diunduh", use_container_width=True):
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_master.to_excel(writer, index=False, sheet_name=sheet_aktif)
                
            st.download_button(
                label=f"📥 KLIK UNTUK UNDUH FILE ({sheet_aktif}.xlsx)",
                data=buffer.getvalue(),
                file_name=f"Laporan_Cashbook_{sheet_aktif}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # ==================== FITUR RESET (ZONA UJI COBA GLOBAL) ====================
    st.write("---")
    st.subheader("⚙️ Zona Bahaya (Pembersihan Data)")
    
    # Fitur Hapus Baris Terakhir pada Tab Terpilih
    if not df_master.empty:
        if st.button(f"⚠️ Hapus 1 Baris Transaksi Terakhir di Tab {sheet_aktif}", use_container_width=True):
            try:
                total_baris_fisik = len(ws_aktif.get_all_values())
                if total_baris_fisik > 1: # Pastikan tidak menghapus baris judul (header)
                    ws_aktif.delete_rows(total_baris_fisik)
                    st.success("Baris terakhir di tab ini berhasil dihapus!")
                    st.rerun()
                else:
                    st.warning("Tab sudah kosong, tidak ada data transaksi yang bisa dihapus.")
            except Exception as e:
                st.error(f"Gagal menghapus baris: {e}")
                
    st.write("")
    konfirmasi_reset = st.checkbox("Saya mengerti dan ingin mengosongkan SELURUH DATA DI SEMUA SHEET secara total")
    if st.button("🚨 RESET TOTAL SEMUA DATA (SELURUH SHEET)", type="primary", use_container_width=True, disabled=not konfirmasi_reset):
        try:
            # Melakukan perulangan (looping) ke semua sheet yang ada di Google Sheets
            for ws in sh.worksheets():
                ws.clear() # Kosongkan isi sheet sepenuhnya
                ws.append_row(["Tanggal", "Hari", "Deskripsi", "Nota", "Debit", "Kredit", "Saldo"]) # Tulis ulang header
            st.success("💥 Sukses! Seluruh data di semua sheet telah dihapus dan dibersihkan kembali ke nol!")
            st.rerun()
        except Exception as e:
            st.error(f"Gagal melakukan reset multi-sheet: {e}")
