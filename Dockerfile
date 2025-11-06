# Gunakan image dasar Python
FROM python:3.11-slim

# Ganti working directory di dalam container ke /app
WORKDIR /app

# Copy file requirements.txt ke container
COPY requirements.txt .

# Install semua dependency dari requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua file aplikasi (termasuk mcu.py, cistech.png, dll) ke /app di container
COPY . .

# Buat folder database dan subfolder uploads di dalam container
# Ini penting karena aplikasi lo nyimpen data dan file upload di sana
RUN mkdir -p database/uploads

# Ekspos port yang digunakan oleh Streamlit (kita ganti ke 8511)
EXPOSE 8511

# Perintah untuk menjalankan aplikasi Streamlit saat container dijalankan
# Ganti 'mcu.py' dengan nama file Python utama lo jika berbeda
# Ganti port ke 8511
CMD ["streamlit", "run", "mcu.py", "--server.port", "8511", "--server.address", "0.0.0.0"]
