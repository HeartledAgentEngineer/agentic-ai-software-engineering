# ==============================================================================
# Script      : main.py
# Author      : der Betreiber
# Date        : 2026-07-11
# Version     : 1.0
# Description : FastAPI-Server für das RAG-System. Stellt API-Endpunkte für den
#               Chatbot und den manuellen PDF-Upload bereit.
# ==============================================================================

import html
import os
import shutil
import psycopg2
import markdown
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Importiere Such- und Ingest-Funktionalität aus unseren Skripten
from query_db import search_db, generate_answer
from ingest import ingest_file

# .env laden
load_dotenv()

SUPABASE_CONNECTION_STRING = os.getenv("SUPABASE_CONNECTION_STRING")
PCLOUD_DIR = os.getenv("RAG_DOCUMENTS_DIR", r"P:\RAG_Documents")
ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".json"}

app = FastAPI(title="Persönlicher RAG Wissensassistent")

# CORS auf localhost begrenzen (lokaler Single-User-Server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def _safe_doc_path(file_name: str, base_dir: str = PCLOUD_DIR) -> str:
    """Stellt sicher, dass der Dateiname keinen Pfad-Ausbruch (../) enthält und im Dokumentenordner liegt."""
    raw = (file_name or "").strip()
    safe_name = os.path.basename(raw)
    if not safe_name or safe_name != raw or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname.")
    base_real = os.path.realpath(base_dir)
    target_real = os.path.realpath(os.path.join(base_real, safe_name))
    if os.path.commonpath([base_real, target_real]) != base_real or target_real == base_real:
        raise HTTPException(status_code=400, detail="Pfad liegt außerhalb des Dokumentenordners.")
    return target_real

# Chat-Request Modell
class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Nachricht darf nicht leer sein.")
    
    try:
        # Führe Hybrid-Suche über die Top 10 Chunks aus
        chunks = search_db(request.message, match_count=10)
        
        if not chunks:
            return {
                "answer": "Es wurden keine relevanten Dokumente in der Datenbank gefunden. Bitte lade zuerst Dokumente hoch.",
                "sources": []
            }
        
        # Generiere Antwort über Gemini
        answer = generate_answer(request.message, chunks)
        
        # Quellen sammeln
        sources = []
        for chunk in chunks:
            # Quelle extrahieren
            meta = chunk["metadata"]
            if meta.get("course"):
                sources.append({
                    "name": f"{meta.get('course')} -> {meta.get('module')}",
                    "url": meta.get("url"),
                    "original_path": None,
                    "page_number": None
                })
            else:
                name = meta.get("file_name", "Unbekannt")
                page_num = meta.get("page_number")
                
                # Link-Generierung (mit page oder text fragment)
                if page_num:
                    url = f"/files/{name}#page={page_num}"
                else:
                    # Suchbegriff (Highlight) für unseren HTML-Reader erzeugen (Absatz-Erkennung)
                    chunk_content = chunk.get("content", "")
                    # Bereinige Markdown-Tags für die Text-Suche
                    clean_text = chunk_content.replace("**", "").replace("*", "").replace("__", "").replace("_", "").replace("#", "")
                    highlight_text = clean_text[:50].strip()
                    import urllib.parse
                    if highlight_text:
                        url = f"/view-doc/{name}?highlight={urllib.parse.quote(highlight_text)}"
                    else:
                        url = f"/view-doc/{name}"
                
                sources.append({
                    "name": name,
                    "url": url,
                    "original_path": meta.get("original_path") or f"P:\\RAG_Documents\\{name}",
                    "page_number": page_num
                })
        
        # Duplikate filtern
        unique_sources = []
        seen = set()
        for src in sources:
            key = (src["name"], src["url"])
            if key not in seen:
                seen.add(key)
                unique_sources.append(src)
        
        return {
            "answer": answer,
            "sources": unique_sources
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sync")
async def sync_file(file: UploadFile = File(...)):
    safe_name = os.path.basename(file.filename or "")
    # Validierung der Dateiendung
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Nur PDF-, MD-, TXT- und JSON-Dateien werden unterstützt.")
        
    # pCloud-Zielverzeichnis sicherstellen
    pcloud_dir = PCLOUD_DIR
    os.makedirs(pcloud_dir, exist_ok=True)
    
    file_path = _safe_doc_path(safe_name, pcloud_dir)
    
    try:
        # Datei direkt nach pCloud schreiben
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Ingestion-Prozess starten
        success = ingest_file(file_path)
        
        if success:
            return {"status": "success", "message": f"'{safe_name}' wurde erfolgreich indiziert."}
        else:
            raise HTTPException(status_code=500, detail=f"Fehler bei der Indizierung von {safe_name}.")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents")
async def list_documents():
    if not SUPABASE_CONNECTION_STRING:
        raise HTTPException(status_code=500, detail="SUPABASE_CONNECTION_STRING fehlt.")
    try:
        conn = psycopg2.connect(SUPABASE_CONNECTION_STRING)
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                metadata->>'file_name' as name, 
                count(*) as chunks, 
                max(metadata->>'original_path') as original_path,
                max(metadata->>'file_hash') as hash
            FROM documents 
            WHERE metadata->>'file_name' IS NOT NULL
            GROUP BY metadata->>'file_name'
            ORDER BY name;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{
            "name": row[0],
            "chunks": row[1],
            "original_path": row[2],
            "hash": row[3]
        } for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Dokumente: {str(e)}")

@app.delete("/documents/{file_name}")
async def delete_document(file_name: str):
    if not SUPABASE_CONNECTION_STRING:
        raise HTTPException(status_code=500, detail="SUPABASE_CONNECTION_STRING fehlt.")
    try:
        conn = psycopg2.connect(SUPABASE_CONNECTION_STRING)
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM documents 
            WHERE metadata->>'file_name' = %s;
        """, (file_name,))
        deleted_rows = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "deleted_chunks": deleted_rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Löschen des Dokuments: {str(e)}")

@app.post("/documents/reindex")
async def reindex_document(file_name: str):
    if not SUPABASE_CONNECTION_STRING:
        raise HTTPException(status_code=500, detail="SUPABASE_CONNECTION_STRING fehlt.")
    try:
        # 1. Finde den Originalpfad des Dokuments aus der DB heraus
        conn = psycopg2.connect(SUPABASE_CONNECTION_STRING)
        cur = conn.cursor()
        cur.execute("""
            SELECT metadata->>'original_path' 
            FROM documents 
            WHERE metadata->>'file_name' = %s 
            LIMIT 1;
        """, (file_name,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="Originalpfad der Datei nicht in der Datenbank gefunden.")
            
        original_path = row[0]
        
        # 2. Ingestierung mit force=True aufrufen (löscht alte Chunks und chunkelt neu nach Absatzmethode)
        success = ingest_file(original_path, force=True)
        if success:
            return {"status": "success", "message": f"'{file_name}' wurde erfolgreich neu indiziert (mit der neuen Absatz-Methode)."}
        else:
            raise HTTPException(status_code=500, detail=f"Fehler bei der Ingestierung von '{file_name}'.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/view-doc/{file_name}", response_class=HTMLResponse)
async def view_document_html(file_name: str):
    file_path = _safe_doc_path(file_name, PCLOUD_DIR)
    safe_title = html.escape(os.path.basename(file_path))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Datei nicht auf dem PC gefunden.")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".md":
            # Markdown in HTML übersetzen (Rohes HTML zuerst escapen)
            html_content = markdown.markdown(html.escape(content), extensions=['fenced_code', 'tables'])
        else:
            # Für txt und sonstige Textdateien
            html_content = f"<pre style='white-space: pre-wrap; word-break: break-word; font-family: monospace;'>{html.escape(content)}</pre>"
            
        # Ästhetisches Dark-Mode Reader Template (ohne f-Prefix!)
        styled_html = r"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{file_name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Outfit', sans-serif;
            background: #0f172a;
            color: #cbd5e1;
            line-height: 1.7;
            padding: 40px 24px;
            max-width: 800px;
            margin: 0 auto;
        }
        .reader-container {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(5px);
        }
        .doc-header {
            margin-bottom: 30px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 15px;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #f1f5f9;
            margin-top: 1.6em;
            margin-bottom: 0.6em;
            font-weight: 600;
        }
        h1 {
            font-size: 2rem;
            margin-top: 0;
        }
        p {
            margin-bottom: 1.2em;
        }
        a {
            color: #c084fc;
            text-decoration: underline;
        }
        pre {
            background: rgba(255, 255, 255, 0.05);
            padding: 18px;
            border-radius: 8px;
            overflow-x: auto;
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #e2e8f0;
            margin-bottom: 1.5em;
        }
        code {
            font-family: monospace;
            background: rgba(255, 255, 255, 0.1);
            padding: 2px 6px;
            border-radius: 4px;
            color: #f472b6;
        }
        blockquote {
            border-left: 4px solid #c084fc;
            margin: 0 0 1.5em 0;
            padding-left: 20px;
            color: #94a3b8;
            font-style: italic;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 1.5em;
        }
        th, td {
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 10px 12px;
            text-align: left;
        }
        th {
            background: rgba(255, 255, 255, 0.05);
            color: #f1f5f9;
        }
        .content {
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="reader-container">
        <div class="doc-header">
            <span style="font-size: 0.8rem; color: #a855f7; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Dokumenten Reader</span>
            <h1 style="margin-top: 5px; margin-bottom: 0;">{file_name}</h1>
        </div>
        <div class="content">
            {html_content}
        </div>
    </div>

    <script>
        // Custom Block-Highlighter & Auto-Scroll (100% zuverlässig, markiert den gesamten Absatz)
        const urlParams = new URLSearchParams(window.location.search);
        const highlightText = urlParams.get('highlight');
        
        if (highlightText) {
            const searchStr = highlightText.trim().toLowerCase();
            if (searchStr.length > 2) {
                const contentDiv = document.querySelector('.content');
                // Finde alle Block-Elemente im Inhaltsbereich
                const blocks = contentDiv.querySelectorAll('p, li, blockquote, h1, h2, h3, h4, h5, h6, pre, tr');
                
                let matchedElement = null;
                for (let block of blocks) {
                    const blockText = block.textContent.replace(/\s+/g, ' ').trim().toLowerCase();
                    if (blockText.includes(searchStr)) {
                        matchedElement = block;
                        break;
                    }
                }
                
                if (matchedElement) {
                    // Wende ein wunderschönes Block-Highlighting an
                    matchedElement.style.transition = 'all 0.3s ease';
                    matchedElement.style.background = 'rgba(168, 85, 247, 0.12)';
                    matchedElement.style.borderLeft = '4px solid #a855f7';
                    matchedElement.style.padding = '12px 16px';
                    matchedElement.style.borderRadius = '0 8px 8px 0';
                    matchedElement.style.boxShadow = '0 4px 15px rgba(168, 85, 247, 0.15)';
                    matchedElement.id = 'highlighted-block';
                    
                    // Sanft in die Mitte scrollen
                    setTimeout(() => {
                        matchedElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }, 200);
                }
            }
        }
    </script>
</body>
</html>""".replace("{file_name}", safe_title).replace("{html_content}", html_content)
        return HTMLResponse(content=styled_html)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/open-file")
async def open_file(path: str):
    # Nur Dateien aus dem freigegebenen Dokumentenordner mit erlaubter Endung öffnen
    file_name = os.path.basename(path or "")
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Dateityp nicht freigegeben.")
    safe_path = _safe_doc_path(file_name, PCLOUD_DIR)
    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail="Datei nicht auf dem PC gefunden.")
    try:
        # Öffnet die Datei nativ in Windows (z. B. Adobe Acrobat, VS Code, Word)
        os.startfile(safe_path)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Öffnen der Datei: {str(e)}")

@app.post("/open-folder")
async def open_folder(path: str):
    import subprocess
    file_name = os.path.basename(path or "")
    safe_path = _safe_doc_path(file_name, PCLOUD_DIR)
    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail="Datei nicht auf dem PC gefunden.")
    try:
        # Öffnet den Windows Explorer und markiert die Datei direkt (Argumentliste statt Shell-String)
        subprocess.Popen(["explorer", f"/select,{safe_path}"])
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Öffnen des Explorers: {str(e)}")

# Frontend-Ordner statisch bereitstellen (mit PyInstaller sys._MEIPASS Fallback)
import sys
if getattr(sys, 'frozen', False):
    static_dir = os.path.join(sys._MEIPASS, "static")
else:
    static_dir = os.path.join(os.path.dirname(__file__), "static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# pCloud-Verzeichnis statisch bereitstellen unter /files/
pcloud_dir = PCLOUD_DIR
if os.path.exists(pcloud_dir):
    app.mount("/files", StaticFiles(directory=pcloud_dir), name="files")

@app.get("/")
async def read_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    else:
        return {"message": "Willkommen beim RAG-Server. Frontend-Dateien unter static/ fehlen noch."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
