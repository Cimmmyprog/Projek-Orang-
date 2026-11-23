import html
import re
import socket

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_POPULAR

_original_getaddrinfo = socket.getaddrinfo


def _getaddrinfo_prefer_ipv4(*args, **kwargs):
    results = _original_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 or results


socket.getaddrinfo = _getaddrinfo_prefer_ipv4

app = FastAPI()
templates = Jinja2Templates(directory="templates")
downloader = YoutubeCommentDownloader()

class VideoRequest(BaseModel):
    url: str
    limit: int = 20

KATA_POSITIF = {
    "bagus", "keren", "mantap", "bermanfaat", "sukses", "hebat", "suka",
    "terbaik", "jelas", "mudah", "membantu", "inspiratif", "luar biasa",
    "semangat", "terima kasih", "makasih", "good", "nice", "love", "kerenn"
    ,"anjay",""
}

KATA_NEGATIF = {
    "jelek", "buruk", "gagal", "susah", "ribet", "sampah", "kecewa",
    "bohong", "hoax", "palsu", "kurang", "lambat", "rugi", "benci",
    "bad", "boring", "skip", "clickbait", "menyesal", "parah","Tidak Mampu",
    "sok Keren", "sok iye","Lebay",""
}

STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "untuk", "dengan",
    "adalah", "pada", "juga", "saya", "aku", "kamu", "dia", "kita", "ada",
    "bisa", "ya", "aja", "kok", "sih", "deh", "dong", "nya"
}


def bersihkan_teks(teks: str) -> str:
    # 1. Case folding (huruf kecil semua)
    teks = teks.lower();
    # 2. Hapus URL/tautan
    teks = re.sub(r'http\S+|www\S+|https\S+', '', teks, flags=re.MULTILINE)
    # 3. Hapus tanda baca, angka, dan emoji (sisakan huruf dan spasi)
    teks = re.sub(r'[^a-z\s]', ' ', teks)
    # 4. Hapus spasi berlebih dan stopword
    kata_list = [k for k in teks.split() if k not in STOPWORDS and len(k) > 1]
    return " ".join(kata_list)

def analisis_sentimen(teks_bersih: str) -> str:
    kata_list = teks_bersih.split()
    skor = 0
    for kata in kata_list:
        if kata in KATA_POSITIF:
            skor += 1
        elif kata in KATA_NEGATIF:
            skor -= 1

    if skor > 0:
        return "Positif"
    elif skor < 0:
        return "Negatif"
    return "Netral"

def ambil_judul_video(url: str) -> str:
    response = downloader.session.get(url, timeout=15)
    match = re.search(r'property="og:t mujmitle"\s+content="([^"]+)"', response.text)
    if match:
        return html.unescape(match.group(1)).strip()
    match = re.search(r"<title>([^<]+)</title>", response.text)
    if match:
        judul = html.unescape(match.group(1)).strip()
        return re.sub(r"\s*-\s*YouTube\s*$", "", judul).strip()
    return "Judul tidak ditemukan"

@app.get("/", response_class=HTMLResponse)
async def halaman_utama(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.post("/api/analisis")
async def proses_analisis(data: VideoRequest):
    try:
        judul_video = ambil_judul_video(data.url)
        generator = downloader.get_comments_from_url(data.url, sort_by=SORT_BY_POPULAR)

        hasil_komentar = []
        ringkasan = {"Positif": 0, "Negatif": 0, "Netral": 0}

        for idx, komentar in enumerate(generator):
            if idx >= data.limit:
                break

            teks_asli = komentar.get("text", "")
            teks_bersih = bersihkan_teks(teks_asli)
            label = analisis_sentimen(teks_bersih)

            ringkasan[label] += 1
            hasil_komentar.append({
                "penulis": komentar.get("author", "Anonim"),
                "asli": teks_asli,
                "bersih": teks_bersih if teks_bersih else "(kosong setelah pembersihan)",
                "sentimen": label
            })

        return {
            "status": "sukses",
            "judul": judul_video,
            "total": len(hasil_komentar),
            "ringkasan": ringkasan,
            "data": hasil_komentar
        }
    except Exception as e:
        return {"status": "error", "pesan": f"Gagal mengambil komentar: {str(e)}"}