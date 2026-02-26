import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import datetime
import pandas as pd

# ----------------- KULLANICI ENVANTERİ -----------------
TAKIMLAR = {
    "1. Takım (Light)": "Shimano Bassterra LRF + İnce İp (Sakin su, hassas levrek)",
    "2. Takım (Aji)": "Major Craft Aji-do + Ester Misina (Durgun su, istavrit)",
    "3. Takım (Spin)": "NS Black Hole + Shimano Ultegra 4000 (Fırtına, Lodos, uzak atış)"
}

# ----------------- GENİŞLETİLMİŞ MARMARA MERALARI -----------------
MERALAR = {
    "İstanbul - Tuzla Medcezir": {"lat": 40.8250, "lon": 29.3000, "hedef": "Levrek"},
    "İstanbul - Maltepe Dragos": {"lat": 40.9123, "lon": 29.1566, "hedef": "İstavrit"},
    "İstanbul - Çatladıkapı": {"lat": 41.0020, "lon": 28.9750, "hedef": "İstavrit"},
    "İstanbul - Büyükçekmece": {"lat": 41.0150, "lon": 28.5600, "hedef": "Levrek"},
    "İstanbul - Sarayburnu": {"lat": 41.0155, "lon": 28.9848, "hedef": "İstavrit/Lüfer"},
    "İstanbul - Şile Ağlayankaya": {"lat": 41.1765, "lon": 29.6136, "hedef": "Levrek"},
    "Bursa - Mudanya İskele": {"lat": 40.3753, "lon": 28.8820, "hedef": "İstavrit"},
    "Bursa - Eşkel Kayalıkları": {"lat": 40.3800, "lon": 28.6650, "hedef": "Levrek/Eşkina"},
    "Yalova - Çınarcık Sahil": {"lat": 40.6405, "lon": 29.1170, "hedef": "İstavrit"},
    "Tekirdağ - Şarköy Liman": {"lat": 40.6125, "lon": 27.1120, "hedef": "Levrek"},
    "Edirne - Enez Liman Arkası": {"lat": 40.7100, "lon": 26.0500, "hedef": "Levrek"}
}

# ----------------- SAYFA AYARLARI VE GLASSMORPHISM CSS -----------------
st.set_page_config(page_title="AI Kıyı Avı Radarı PRO", page_icon="🌊", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
   .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
        color: #e2e8f0;
        font-family: 'Segoe UI', Tahoma, sans-serif;
    }
   .glass-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
        transition: transform 0.3s ease;
    }
   .glass-card:hover { transform: translateY(-5px); }
    h1, h2, h3 { color: #38bdf8!important; text-shadow: 0 0 10px rgba(56, 189, 248, 0.3); }
   .badge { padding: 4px 10px; border-radius: 8px; font-weight: bold; font-size: 0.9em; }
   .badge-levrek { background: rgba(220, 38, 38, 0.2); color: #fca5a5; border: 1px solid #fca5a5; }
   .badge-istavrit { background: rgba(59, 130, 246, 0.2); color: #93c5fd; border: 1px solid #93c5fd; }
    div { background: rgba(15, 23, 42, 0.8)!important; border-right: 1px solid rgba(255,255,255,0.1); }
</style>
""", unsafe_allow_html=True)

# ----------------- YARDIMCI FONKSİYONLAR -----------------
def get_wind_direction_name(degree):
    dirs = ["Kuzey", "Kuzeydoğu", "Doğu", "Güneydoğu", "Güney", "Güneybatı", "Batı", "Kuzeybatı"]
    return dirs[int((degree + 22.5) / 45) % 8]

def get_wind_color(speed):
    if speed < 10: return "green"
    elif speed < 25: return "orange"
    else: return "red"

def get_pressure_color(pressure):
    if pressure < 1005: return "red"      # Alçak basınç (Fırtına/Aktif balık)
    elif pressure < 1015: return "green"  # Normal
    else: return "blue"                   # Yüksek basınç (Durgun)

# ----------------- API VERİ ÇEKME (HAFTALIK) -----------------
@st.cache_data(ttl=3600)
def fetch_weather_for_spot(lat, lon):
    url_w = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=windspeed_10m,winddirection_10m,surface_pressure&timezone=Europe%2FIstanbul"
    url_m = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height&timezone=Europe%2FIstanbul"
    try:
        w_data = requests.get(url_w).json()
        m_data = requests.get(url_m).json()
        return w_data, m_data
    except:
        return None, None

def get_hourly_data(w_data, m_data, target_time_str):
    try:
        idx = w_data["hourly"]["time"].index(target_time_str)
        return {
            "wind_speed": w_data["hourly"]["windspeed_10m"][idx],
            "wind_dir": w_data["hourly"]["winddirection_10m"][idx],
            "pressure": w_data["hourly"]["surface_pressure"][idx],
            "wave": m_data["hourly"]["wave_height"][idx] if m_data.get("hourly", {}).get("wave_height") else 0.0
        }
    except:
        return {"wind_speed": 0, "wind_dir": 0, "pressure": 1015, "wave": 0}

# ----------------- ANALİZ ALGORİTMASI -----------------
def analyze_spot(hedef, data):
    score = 0
    ruzgar_yonu = get_wind_direction_name(data["wind_dir"])

    if hedef == "Levrek":
        if data["wind_speed"] > 20: score += 3
        if data["wave"] > 0.8: score += 5
        if data["pressure"] < 1010: score += 2
        takim = TAKIMLAR # Corrected: Assuming it should be TAKIMLAR based on context, previously 'TAKIMLAR if data["wave"] > 0.8 else TAKIMLAR' was redundant.

    else: # İstavrit vb.
        if "Kuzey" in ruzgar_yonu: score += 4
        if data["wave"] < 0.6: score += 6
        takim = TAKIMLAR

    return min(score, 10), takim, ruzgar_yonu

# ----------------- SİDEBAR: ZAMAN VE HARİTA KONTROLLERİ -----------------
st.sidebar.markdown("<h2>⚙️ Radar Kontrol Paneli</h2>", unsafe_allow_html=True)
st.sidebar.divider()

# Dinamik Tarih Seçimi
today = datetime.date.today()
selected_date = st.sidebar.date_input("🗓️ Tarih Seçin", value=today, min_value=today, max_value=today + datetime.timedelta(days=6))
selected_hour = st.sidebar.slider("⏰ Saat Seçin", min_value=0, max_value=23, value=datetime.datetime.now().hour, format="%02d:00")

# Hedef Zaman Stringi (API formatı: YYYY-MM-DDTHH:00)
target_time_str = f"{selected_date}T{selected_hour:02d}:00"

st.sidebar.divider()
map_type = st.sidebar.radio("🗺️ Harita Katmanı", ("🎣 Genel Av Skoru", "💨 Rüzgar ve Yön (Oklar)", "📉 Basınç Merkezleri", "🦠 Klorofil-a (Uydu)")) # Corrected: Added options for the radio button

# ----------------- VERİLERİ İŞLEME -----------------
mera_verileri = {}
en_iyi_mera = None
en_yuksek_skor = -1

for mera, bilgiler in MERALAR.items():
    w_data, m_data = fetch_weather_for_spot(bilgiler["lat"], bilgiler["lon"])
    hourly_data = get_hourly_data(w_data, m_data, target_time_str)

    skor, takim, ruzgar_str = analyze_spot(bilgiler["hedef"], hourly_data)

    mera_verileri[mera] = {
        **bilgiler, **hourly_data,
        "skor": skor, "takim": takim, "ruzgar_str": ruzgar_str
    }

    if skor > en_yuksek_skor:
        en_yuksek_skor = skor
        en_iyi_mera = mera

# ----------------- ANA EKRAN: HARİTA -----------------
st.markdown(f"<h1>Oşinografik Av Radarı</h1>", unsafe_allow_html=True)
st.markdown(f"<p style='color:#94a3b8; font-size:1.1em;'>Seçili Zaman: <b>{selected_date.strftime('%d.%m.%Y')} - {selected_hour:02d}:00</b></p>", unsafe_allow_html=True)

# Folium Haritasını Başlat (Marmara Merkezi)
m = folium.Map(location=[40.75, 28.5], zoom_start=8, tiles="CartoDB dark_matter")

# Seçilen Katmana Göre Haritayı Çiz
if map_type == "🎣 Genel Av Skoru":
    for mera, d in mera_verileri.items():
        renk = "darkgreen" if mera == en_iyi_mera else "cadetblue"
        ikon = "star" if mera == en_iyi_mera else "info-sign"
        html = f"<b>{mera}</b><br>Hedef: {d['hedef']}<br>Skor: {d['skor']}/10<br>Dalga: {d['wave']}m"
        folium.Marker([d["lat"], d["lon"]], popup=folium.Popup(html, max_width=250), icon=folium.Icon(color=renk, icon=ikon)).add_to(m)

elif map_type == "💨 Rüzgar ve Yön (Oklar)":
    for mera, d in mera_verileri.items():
        color = get_wind_color(d['wind_speed'])
        html = f"<b>{mera}</b><br>Rüzgar: {d['wind_speed']} km/s<br>Yön: {d['ruzgar_str']}"
        # Rüzgarın gittiği yönü göstermek için ok (Üçgen Marker)
        # Folium'da 0 derece Doğu'dur. Meteorolojide rüzgar yönü esilen yeri gösterir.
        angle = d['wind_dir'] - 90

        folium.RegularPolygonMarker(
            location=[d["lat"], d["lon"]],
            number_of_sides=3, radius=12, rotation=angle,
            color=color, fill=True, fill_color=color, fill_opacity=0.8,
            popup=folium.Popup(html, max_width=200), tooltip=f"{d['wind_speed']} km/s"
        ).add_to(m)

elif map_type == "📉 Basınç Merkezleri":
    for mera, d in mera_verileri.items():
        color = get_pressure_color(d['pressure'])
        # Basınç merkezlerini göstermek için iç içe dairesel dalgalar (Sözde-İzobar)
        folium.Circle(
            location=[d["lat"], d["lon"]], radius=15000,
            color=color, fill=True, fill_opacity=0.2, weight=1
        ).add_to(m)
        folium.CircleMarker(
            location=[d["lat"], d["lon"]], radius=5, color="white", fill=True,
            popup=f"<b>{mera}</b><br>Basınç: {d['pressure']} hPa", tooltip=f"{d['pressure']} hPa"
        ).add_to(m)

elif map_type == "🦠 Klorofil-a (Uydu)":
    # Sentinel Hub WMS Katmanı Entegrasyonu (Copernicus)
    # Not: Gerçek kullanımda INSTANCE_ID kısmını kendi Sentinel Hub id'nizle değiştirmelisiniz.
    INSTANCE_ID = st.secrets.get("SH_INSTANCE_ID", "ORNEK_ID")
    wms_url = f"https://services.sentinel-hub.com/ogc/wms/{INSTANCE_ID}"

    folium.raster_layers.WmsTileLayer(
        url=wms_url,
        layers='CHLOROPHYLL', # Sentinel Hub üzerindeki konfigüre edilmiş katman adı
        transparent=True,
        control=True,
        fmt='image/png',
        name='Sentinel-3 Klorofil-a',
        overlay=True,
        show=True,
        attr='Copernicus Sentinel Data'
    ).add_to(m)

    # Meraları siyah noktalarla işaretle
    for mera, d in mera_verileri.items():
        folium.CircleMarker([d["lat"], d["lon"]], radius=4, color="white", popup=mera).add_to(m)

st_folium(m, width=1200, height=500)

# ----------------- TOP MERALAR (KARTLAR) -----------------
st.markdown("<h3>🎯 Seçilen Saatteki En İyi Fırsatlar</h3>", unsafe_allow_html=True)

# Meraları skora göre sırala
sirali_meralar = sorted(mera_verileri.items(), key=lambda x: x[1]['skor'], reverse=True)[:3]

cols = st.columns(3)
for idx, (mera, d) in enumerate(sirali_meralar):
    with cols[idx]:
        badge_class = "badge-levrek" if d['hedef'] == "Levrek" else "badge-istavrit"
        st.markdown(f"""
        <div class="glass-card">
            <h4>{mera}</h4>
            <span class="badge {badge_class}">{d['hedef']}</span>
            <span style="float:right; font-weight:bold; color:#38bdf8;">Skor: {d['skor']}/10</span>
            <hr style="border-color: rgba(255,255,255,0.1);">
            <p>🌊 <b>Dalga:</b> {d['wave']} m</p>
            <p>💨 <b>Rüzgar:</b> {d['wind_speed']} km/s <i>({d['ruzgar_str']})</i></p>
            <p>📉 <b>Basınç:</b> {d['pressure']} hPa</p>
            <hr style="border-color: rgba(255,255,255,0.1);">
            <p style="font-size:0.9em; color:#cbd5e1;"><b>Takım:</b> {d['takim']}</p>
        </div>
        """, unsafe_allow_html=True)
