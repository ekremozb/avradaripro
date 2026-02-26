import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import datetime
import math

# ----------------- KULLANICI ENVANTERİ -----------------
TAKIMLAR = {
    "Sessiz LRF": "Shimano Bassterra LRF + İnce İp (Durgun su levreği)",
    "Aji (İstavrit)": "Major Craft Aji-do + Ester Misina (Durgun deniz, gece avı)",
    "Spin (Fırtına)": "NS Black Hole 10-36g + Shimano Ultegra 4000 (Sert lodos, uzak erim)"
}

# ----------------- MARMARA GENELİ MERALAR VE KIYI YÖNELİMLERİ (0m İzohips) -----------------
# 'shore_facing': Kıyının denize baktığı yön (Derece). Örn: Güney'e bakan kıyı 180 derecedir.
# Rüzgar yönü ile shore_facing eşleşirse (±45 derece), rüzgar "kıyıya dik (onshore)" esiyor demektir.
MERALAR = {
    "İstanbul - Tuzla/Mercan": {"lat": 40.825, "lon": 29.300, "hedef": "Levrek", "shore_facing": 180},
    "İstanbul - Maltepe Sahil": {"lat": 40.912, "lon": 29.156, "hedef": "İstavrit", "shore_facing": 180},
    "İstanbul - Sarayburnu": {"lat": 41.015, "lon": 28.984, "hedef": "İstavrit", "shore_facing": 90},
    "İstanbul - Büyükçekmece": {"lat": 40.995, "lon": 28.560, "hedef": "Levrek", "shore_facing": 180},
    "İstanbul - Silivri": {"lat": 41.070, "lon": 28.240, "hedef": "Levrek", "shore_facing": 180},
    "Tekirdağ - Merkez": {"lat": 40.970, "lon": 27.510, "hedef": "Levrek", "shore_facing": 135},
    "Tekirdağ - Şarköy": {"lat": 40.610, "lon": 27.110, "hedef": "Levrek", "shore_facing": 135},
    "Çanakkale - Gelibolu": {"lat": 40.400, "lon": 26.660, "hedef": "Levrek", "shore_facing": 135},
    "Çanakkale - Karabiga": {"lat": 40.400, "lon": 27.300, "hedef": "Levrek", "shore_facing": 0},
    "Balıkesir - Erdek": {"lat": 40.390, "lon": 27.790, "hedef": "Levrek", "shore_facing": 315},
    "Bursa - Mudanya": {"lat": 40.370, "lon": 28.880, "hedef": "İstavrit", "shore_facing": 0},
    "Yalova - Çınarcık": {"lat": 40.640, "lon": 29.110, "hedef": "İstavrit", "shore_facing": 0}
}

# ----------------- UI / UX TASARIMI (GLASSMORPHISM) -----------------
st.set_page_config(page_title="Marmara Av Radarı PRO", page_icon="🌊", layout="wide")
st.markdown("""
<style>
    /* Derin Deniz Arkaplanı */
   .stApp { background: linear-gradient(135deg, #020617 0%, #0f172a 100%); color: #f8fafc; font-family: 'Inter', sans-serif; }
    h1, h2, h3 { color: #38bdf8!important; font-weight: 700; }
    /* Şeffaf Cam Kartlar */
   .glass-card { background: rgba(30, 41, 59, 0.6); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); 
                  border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: 0.3s; }
   .glass-card:hover { transform: translateY(-5px); border-color: #38bdf8; }
   .text-highlight { color: #f43f5e; font-weight: 800; }
   .score-high { color: #10b981; font-weight: 900; font-size: 1.2em; }
   .score-low { color: #ef4444; font-weight: 900; font-size: 1.2em; }
</style>
""", unsafe_allow_html=True)

# ----------------- MATEMATİKSEL VE METEOROLOJİK FONKSİYONLAR -----------------
def get_wind_direction_name(degree):
    dirs =
    return dirs[int((degree + 22.5) / 45) % 8]

def is_onshore_wind(wind_dir, shore_facing):
    # Rüzgarın geliş yönü ile kıyının baktığı yön arasındaki açı farkı 45 dereceden küçükse rüzgar kıyıya dik esiyordur.
    diff = abs(wind_dir - shore_facing)
    min_diff = min(diff, 360 - diff)
    return min_diff <= 45

# ----------------- API VERİ ÇEKİMİ VE İŞLEME -----------------
@st.cache_data(ttl=1800)
def fetch_meteo_data(lat, lon):
    url_w = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=windspeed_10m,winddirection_10m,surface_pressure&timezone=Europe%2FIstanbul"
    url_m = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height&timezone=Europe%2FIstanbul"
    try:
        w_data = requests.get(url_w).json()
        m_data = requests.get(url_m).json()
        return w_data, m_data
    except:
        return None, None

def extract_hourly_data(w_data, m_data, target_time):
    try:
        idx = w_data["hourly"]["time"].index(target_time)
        return {
            "wind_speed": w_data["hourly"]["windspeed_10m"][idx],
            "wind_dir": w_data["hourly"]["winddirection_10m"][idx],
            "pressure": w_data["hourly"]["surface_pressure"][idx],
            "wave": m_data["hourly"]["wave_height"][idx] if m_data.get("hourly", {}).get("wave_height") else 0.0
        }
    except:
        return {"wind_speed": 0, "wind_dir": 0, "pressure": 1015, "wave": 0}

# ----------------- HEDEF BALIK ALGORİTMASI -----------------
def calculate_score(hedef, data, shore_facing):
    score = 0
    tavsiye = ""
    onshore = is_onshore_wind(data["wind_dir"], shore_facing)
    
    # Sentinel Hub NDCI (Klorofil) Simülasyonu - Dalga ve rüzgara bağlı bulanıklık indeksi
    chlorophyll_level = "Yüksek (Bulanık)" if (data["wave"] > 0.8 or onshore) else "Düşük (Berrak)"

    if hedef == "Levrek":
        # Levrek Kuralları: Kıyıya dik rüzgar + 15km/h üstü rüzgar + 0.5-2m dalga + Yüksek Klorofil
        if onshore: score += 4
        if data["wind_speed"] > 15: score += 2
        if 0.5 <= data["wave"] <= 2.0: score += 3
        if chlorophyll_level == "Yüksek (Bulanık)": score += 1
        
        if score >= 7:
            tavsiye = TAKIMLAR
        else:
            tavsiye = TAKIMLAR
            
    elif hedef == "İstavrit":
        # İstavrit Kuralları: Rüzgar < 15km/h + Dalga < 0.5m (Durgun su)
        if data["wind_speed"] < 15: score += 5
        if data["wave"] < 0.5: score += 5
        tavsiye = TAKIMLAR["Aji (İstavrit)"]

    return score, tavsiye, onshore, chlorophyll_level

# ----------------- SİDEBAR: ZAMAN VE HARİTA KONTROLLERİ -----------------
st.sidebar.markdown("## ⚙️ Radar Kontrol Paneli")
today = datetime.date.today()
selected_date = st.sidebar.date_input("🗓️ Tarih", value=today, min_value=today, max_value=today + datetime.timedelta(days=6))
selected_hour = st.sidebar.slider("⏰ Saat", 0, 23, datetime.datetime.now().hour, format="%02d:00")
target_time = f"{selected_date}T{selected_hour:02d}:00"

st.sidebar.markdown("---")
map_layer = st.sidebar.radio("🗺️ Harita Katmanları", 
   )

# ----------------- VERİLERİ TOPLAMA VE İŞLEME -----------------
results = {}
for mera, info in MERALAR.items():
    w_data, m_data = fetch_meteo_data(info["lat"], info["lon"])
    h_data = extract_hourly_data(w_data, m_data, target_time)
    
    score, takim, onshore, chl = calculate_score(info["hedef"], h_data, info["shore_facing"])
    
    results[mera] = {
        **info, **h_data, "score": score, "takim": takim, 
        "onshore": onshore, "chl": chl, "ruzgar_ad": get_wind_direction_name(h_data["wind_dir"])
    }

# En iyi merayı bul
best_spot = max(results.items(), key=lambda x: x[1]['score'])

# ----------------- ANA EKRAN & HARİTA ÇİZİMİ -----------------
st.title("Marmara Denizi Av Radarı PRO")
st.markdown(f"**Seçilen Zaman:** `{selected_date.strftime('%d.%m.%Y')} - {selected_hour:02d}:00`")

m = folium.Map(location=[40.65, 28.3], zoom_start=8, tiles="CartoDB dark_matter")

if map_layer == "🎯 Av Verimi Haritası":
    for mera, d in results.items():
        color = "green" if d["score"] >= 8 else ("orange" if d["score"] >= 5 else "red")
        icon = folium.Icon(color=color, icon="star" if d["score"] >= 8 else "info-sign")
        html = f"<b>{mera}</b><br>Hedef: {d['hedef']}<br>Skor: {d['score']}/10"
        folium.Marker([d["lat"], d["lon"]], popup=html, icon=icon).add_to(m)

elif map_layer == "💨 Rüzgar Yön (Oklar)":
    for mera, d in results.items():
        color = "#ef4444" if d["wind_speed"] > 20 else "#10b981"
        # Rüzgar okunun (üçgen) ucunu rüzgarın estiği yöne çevir
        angle = d["wind_dir"] - 90 
        folium.RegularPolygonMarker(
            [d["lat"], d["lon"]], number_of_sides=3, radius=12, rotation=angle,
            color=color, fill_color=color, fill_opacity=0.8,
            popup=f"<b>{mera}</b><br>Hız: {d['wind_speed']} km/h<br>Yön: {d['ruzgar_ad']}"
        ).add_to(m)

elif map_layer == "📉 İzobarik Basınç Alanları":
    for mera, d in results.items():
        # Düşük basınç (Siklon/Fırtına) kırmızımsı, Yüksek basınç (Antisiklon/Durgun) mavimsi
        color = "#ef4444" if d["pressure"] < 1010 else "#3b82f6"
        # Basınç eğrisi hissi vermek için geniş dairesel dalgalar
        folium.Circle([d["lat"], d["lon"]], radius=20000, color=color, fill=True, fill_opacity=0.2, weight=1).add_to(m)
        folium.Circle([d["lat"], d["lon"]], radius=40000, color=color, fill=False, weight=0.5).add_to(m)
        folium.Marker([d["lat"], d["lon"]], icon=folium.DivIcon(html=f"<div style='color:white; font-weight:bold;'>{int(d['pressure'])} hPa</div>")).add_to(m)

elif map_layer == "🦠 Klorofil-a (Sentinel)":
    # Sentinel Hub (Copernicus) WMS Katmanı
    INSTANCE_ID = st.secrets.get("SH_INSTANCE_ID", "DEFAULT_ID")
    folium.raster_layers.WmsTileLayer(
        url=f"https://services.sentinel-hub.com/ogc/wms/{INSTANCE_ID}",
        layers='CHLOROPHYLL', transparent=True, fmt='image/png', name='Sentinel-3 Klorofil', overlay=True
    ).add_to(m)
    for mera, d in results.items():
        folium.CircleMarker([d["lat"], d["lon"]], radius=5, color="white", popup=f"Klorofil: {d['chl']}").add_to(m)

st_folium(m, width=1200, height=500)

# ----------------- DETAYLI ANALİZ KARTLARI -----------------
st.markdown("### 🏆 En İyi Av Fırsatları")

cols = st.columns(3)
sorted_spots = sorted(results.items(), key=lambda x: x[1]['score'], reverse=True)[:3]

for i, (mera, d) in enumerate(sorted_spots):
    with cols[i]:
        score_class = "score-high" if d['score'] >= 7 else "score-low"
        onshore_text = "Evet (Kıyıya Dik)" if d['onshore'] else "Hayır (Sırttan/Açıktan)"
        
        st.markdown(f"""
        <div class="glass-card">
            <h4>{mera}</h4>
            <span style="background: rgba(56, 189, 248, 0.2); padding: 3px 8px; border-radius: 5px;">Hedef: {d['hedef']}</span>
            <hr style="border-color: rgba(255,255,255,0.1);">
            <p>Skor: <span class="{score_class}">{d['score']} / 10</span></p>
            <p>🌊 <b>Dalga:</b> {d['wave']} m</p>
            <p>💨 <b>Rüzgar:</b> {d['wind_speed']} km/h <i>({d['ruzgar_ad']})</i></p>
            <p>🎯 <b>Rüzgar Yönelimi:</b> <span class="text-highlight">{onshore_text}</span></p>
            <p>📉 <b>Basınç:</b> {d['pressure']} hPa</p>
            <p>🦠 <b>Klorofil:</b> {d['chl']}</p>
            <hr style="border-color: rgba(255,255,255,0.1);">
            <p style="font-size: 0.9em; color:#94a3b8;"><b>Önerilen Takım:</b><br>{d['takim']}</p>
        </div>
        """, unsafe_allow_html=True)