import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# === Load dan preprocessing data ===
df = pd.read_csv("Data/data_supplier.csv")

# Konversi harga dari USD ke IDR
usd_to_idr = 16000
df['Unit_Price'] = df['Unit_Price'] * usd_to_idr
df['Negotiated_Price'] = df['Negotiated_Price'] * usd_to_idr

# Ubah kolom tanggal menjadi format datetime
df['Order_Date'] = pd.to_datetime(df['Order_Date'])
df['Delivery_Date'] = pd.to_datetime(df['Delivery_Date'])

# Hitung Lead Time (untuk yang lengkap dulu)
df['Lead_Time'] = (df['Delivery_Date'] - df['Order_Date']).dt.days
mean_lead_time = df.dropna(subset=['Delivery_Date']).groupby('Supplier')['Lead_Time'].mean()

# Imputasi nilai kosong pada Delivery_Date
def isi_delivery_date(row):
    if pd.isnull(row['Delivery_Date']) and row['Supplier'] in mean_lead_time:
        return row['Order_Date'] + pd.to_timedelta(round(mean_lead_time[row['Supplier']]), unit='D')
    else:
        return row['Delivery_Date']

df['Delivery_Date'] = df.apply(isi_delivery_date, axis=1)

# Imputasi Defective_Units = 0 jika kosong
df['Defective_Units'] = df['Defective_Units'].fillna(0)

# Update kolom setelah imputasi
df['Lead_Time'] = (df['Delivery_Date'] - df['Order_Date']).dt.days
df['Defect_Rate'] = df.apply(
    lambda row: (row['Defective_Units'] / row['Quantity']) * 100 if row['Quantity'] != 0 else 0,
    axis=1
)
df['Price_Efficiency'] = (1 - df['Negotiated_Price'] / df['Unit_Price']) * 100

# === Fungsi Rekomendasi Supplier ===
def recommend_suppliers(item_category, max_price, max_lead_time, max_defect_rate, compliance_preference="All"):
    filtered_df = df.copy()

    if item_category != "All":
        filtered_df = filtered_df[filtered_df['Item_Category'].str.lower() == item_category.lower()]

    if compliance_preference == "Yes":
        filtered_df = filtered_df[filtered_df['Compliance'] == 'Yes']
    elif compliance_preference == "No":
        filtered_df = filtered_df[filtered_df['Compliance'] == 'No']

    filtered_df = filtered_df[
        (filtered_df['Negotiated_Price'] <= max_price) &
        (filtered_df['Lead_Time'] <= max_lead_time) &
        (filtered_df['Defect_Rate'] <= max_defect_rate)
    ]

    if filtered_df.empty:
        return pd.DataFrame()

    group_cols = ['Supplier']
    agg_dict = {
        'Negotiated_Price': 'mean',
        'Lead_Time': 'mean',
        'Defect_Rate': 'mean',
        'Price_Efficiency': 'mean',
        'Quantity': 'sum',
        'PO_ID': 'count'
    }

    # Jika user memilih "All", tambahkan kolom ke hasil agregasi
    if item_category == "All":
        group_cols.append('Item_Category')
    if compliance_preference == "All":
        group_cols.append('Compliance')

    result = filtered_df.groupby(group_cols).agg(agg_dict).rename(columns={
        'Negotiated_Price': 'Avg_Negotiated_Price',
        'Defect_Rate': 'Defect_Rate (%)',
        'Price_Efficiency': 'Price_Efficiency (%)',
        'Quantity': 'Total_Quantity',
        'PO_ID': 'Total_Orders'
    }).reset_index()

    # Gabungkan dengan status PO (Open/Closed)
    status_counts = pd.crosstab(
        [filtered_df['Supplier']] + (
            [filtered_df['Item_Category']] if item_category == "All" else []
        ) + (
            [filtered_df['Compliance']] if compliance_preference == "All" else []
        ),
        filtered_df['Order_Status']
    ).reset_index()

    result = pd.merge(result, status_counts, on=group_cols, how='left')

    # Urutkan
    result = result.sort_values(by=['Defect_Rate (%)', 'Lead_Time', 'Avg_Negotiated_Price'])
    return result

# === STREAMLIT ANTARMUKA ===
st.title("📦 Supplier Recommendation System")
st.markdown("## Masukkan kriteria pencarian supplier:")

# Layout 1 kolom untuk input
item_categories = ["All"] + sorted(df['Item_Category'].dropna().unique().tolist())
item_category = st.selectbox("📁 Pilih kategori barang:", item_categories,
                             help="Pilih kategori barang yang ingin dicari. Pilih 'All' untuk semua kategori.")

max_price = st.number_input("💰 Harga maksimum per unit (Rp):", min_value=0, value=200000,
                            help="Masukkan harga maksimal per unit dalam Rupiah.")

max_lead_time = st.slider("⏳ Waktu pengiriman maksimum (hari):", min_value=1, max_value=30, value=10,
                          help="Batas maksimal waktu pengiriman barang (dalam hari).")

max_defect_rate = st.slider("🛠 Maksimum persentase barang cacat (%):", min_value=0.0, max_value=100.0, value=5.0, step=0.5,
                            help="Batas maksimal persentase barang cacat yang bisa diterima.")

compliance_preference = st.selectbox("✅ Preferensi compliance:", ["All", "Yes", "No"],
                                     help="Filter supplier berdasarkan kepatuhan compliance.")

st.markdown("---")

# Tombol cari dengan spinner
if st.button("🔍 Cari Supplier"):
    with st.spinner("Sedang mencari supplier terbaik..."):
        hasil = recommend_suppliers(
            item_category=item_category,
            max_price=max_price,
            max_lead_time=max_lead_time,
            max_defect_rate=max_defect_rate,
            compliance_preference=compliance_preference
        )

    if hasil.empty:
        st.warning("❌ Tidak ada supplier yang memenuhi semua kriteria.")

        # --- Rekomendasi Alternatif dalam Expander ---
        with st.expander("✅ Rekomendasi Alternatif (Hampir Memenuhi)"):
            toleransi_defect = max_defect_rate + 2
            toleransi_lead = max_lead_time + 2
            toleransi_price = max_price * 1.5

            alternatif = recommend_suppliers(
                item_category=item_category,
                max_price=toleransi_price,
                max_lead_time=toleransi_lead,
                max_defect_rate=toleransi_defect,
                compliance_preference=compliance_preference
            )

            if alternatif.empty:
                st.info("⚠️ Tidak ada alternatif yang cukup mendekati.")
            else:
                def alasan(row):
                    alasan_list = []
                    if abs(row['Defect_Rate (%)'] - max_defect_rate) <= 2:
                        alasan_list.append(f"Defect Rate mendekati batas ({row['Defect_Rate (%)']:.1f}%)")
                    elif row['Defect_Rate (%)'] > max_defect_rate:
                        alasan_list.append(f"Defect Rate {row['Defect_Rate (%)']:.1f}%")
                    if row['Avg_Negotiated_Price'] > max_price:
                        alasan_list.append(f"Harga {int(row['Avg_Negotiated_Price']):,} > {int(max_price):,}")
                    if row['Lead_Time'] > max_lead_time:
                        alasan_list.append(f"Lead Time {row['Lead_Time']} hari")
                    return ", ".join(alasan_list)

                alternatif['Catatan'] = alternatif.apply(alasan, axis=1)
                st.dataframe(alternatif[['Supplier', 'Avg_Negotiated_Price', 'Lead_Time', 'Defect_Rate (%)', 'Catatan']], use_container_width=True)

    else:
        st.success("✅ Supplier yang direkomendasikan:")
        st.dataframe(hasil, use_container_width=True)

        csv_data = hasil.to_csv(index=False)
        st.download_button(
            label="⬇️ Download Hasil Rekomendasi (CSV)",
            data=csv_data,
            file_name='hasil_rekomendasi_supplier.csv',
            mime='text/csv'
        )

        st.subheader("📊 Visualisasi Hasil Filter")

        if 'Supplier' in hasil.columns and 'Total_Quantity' in hasil.columns:
            st.markdown("**📦 Total Quantity per Supplier**")
            fig_qty, ax_qty = plt.subplots(figsize=(8,4))
            sns.barplot(
                data=hasil.sort_values('Total_Quantity', ascending=False),
                x='Total_Quantity',
                y='Supplier',
                palette="Blues_d",
                ax=ax_qty
            )
            ax_qty.set_xlabel("Total Quantity")
            ax_qty.set_ylabel("Supplier")
            st.pyplot(fig_qty)

        else:
            st.info("❌ Tidak ada hasil")

        if 'Supplier' in hasil.columns and 'Defect_Rate (%)' in hasil.columns:
            st.markdown("**📈 Rata-rata Defect Rate Tiap Supplier**")
            fig_line, ax_line = plt.subplots(figsize=(8,4))
            sns.lineplot(data=hasil, x='Supplier', y='Defect_Rate (%)', marker="o", ax=ax_line, color="#E91E63")
            ax_line.set_ylabel("Defect Rate (%)")
            ax_line.set_xticks(range(len(hasil)))
            ax_line.set_xticklabels(hasil['Supplier'], rotation=45, ha="right")
            fig_line.tight_layout()
            st.pyplot(fig_line)
        
        else:
            st.info("❌ Tidak ada hasil")