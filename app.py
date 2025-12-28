import os
import sqlite3
import datetime
import base64
import json
from io import BytesIO

# ---------- CONFIGURAZIONE ----------
DATABASE = "/tmp/fiuggigram.db"
UPLOAD_FOLDER = "/tmp/uploads"
MAX_FILE_SIZE = 2 * 1024 * 1024
SECRET_JOIN_CODE = os.environ.get("FIUGGI_CODE", "FIUGGI2025")
PING_INTERVAL_SEC = 30
# ------------------------------------

from flask import Flask, request, redirect, url_for, send_from_directory

PIL_AVAILABLE = False

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            content TEXT,
            image_path TEXT,
            parent_id INTEGER DEFAULT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            post_id INTEGER,
            ip_hash TEXT,
            PRIMARY KEY (post_id, ip_hash)
        )
    """)
    conn.commit()
    conn.close()

def get_client_id():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    return base64.b64encode(ip.encode()).decode()[:12]

@app.route("/ping")
def ping():
    return "", 200

def render_page(posts, replies_by_post, error=""):
    theme = request.cookies.get("theme", "auto")
    theme_attr = f'data-theme="{theme}"' if theme in ("light", "dark") else ''

    def fmt_ts(ts):
        try:
            dt = datetime.datetime.fromisoformat(ts)
            now = datetime.datetime.now()
            diff = now - dt
            if diff.days == 0:
                if diff.seconds < 60:
                    return "pochi secondi fa"
                elif diff.seconds < 3600:
                    m = diff.seconds // 60
                    return f"{m} minuto{'i' if m != 1 else ''} fa"
                else:
                    h = diff.seconds // 3600
                    return f"{h} ora{'e' if h != 1 else ''} fa"
            elif diff.days == 1:
                return "ieri"
            else:
                return dt.strftime("%d %b")
        except:
            return ts

    def render_post(pid, username, content, image_path, ts, like_count, is_liked, replies, level=0):
        indent = "  " * level
        margin_left = 16 * level
        border_left = "4px solid #FFD166" if level == 0 else "2px solid #CBD5E1"
        pad_left = 16 - margin_left if level > 0 else 16

        img_html = ""

        reply_input = f'''
        <div class="reply-form mt-2" id="reply-form-{pid}" style="display:none">
          <input type="text" class="form-control form-control-sm reply-input"
                 placeholder="La tua risposta…" maxlength="200"
                 onkeypress="if(event.key==='Enter') submitReply({pid})">
          <button class="btn-reply" onclick="submitReply({pid})">➤</button>
        </div>
        '''

        replies_html = ""
        for r in replies:
            rid, runame, rcontent, rimg, rparent, rts, rlike_count = r
            is_reply_liked = request.cookies.get(f"liked_{rid}") == "1"
            replies_html += render_post(
                rid, runame, rcontent, rimg, rts, rlike_count, is_reply_liked, [], level=level+1
            )

        return f'''
        {indent}<div class="fiuggi-post" style="margin-left:{margin_left}px; border-left:{border_left}; padding-left:{pad_left}px">
          <div class="fiuggi-header">
            <div class="fiuggi-avatar">{username[0].upper()}</div>
            <div class="fiuggi-meta">
              <strong>{username}</strong>
              <span class="fiuggi-time">{fmt_ts(ts)}</span>
            </div>
            <div class="fiuggi-actions">
              <button class="fiuggi-like" data-id="{pid}" onclick="toggleLike({pid})" style="color:{'#FFD166' if is_liked else '#64748B'}">
                <i class="{'fas fa-heart' if is_liked else 'far fa-heart'}"></i> <span>{like_count}</span>
              </button>
              <button class="fiuggi-reply" onclick="toggleReply({pid})">🗨️ Rispondi</button>
            </div>
          </div>
          <div class="fiuggi-content">{content}</div>
          {img_html}
          {reply_input}
          <div class="replies" id="replies-{pid}">{replies_html}</div>
        </div>
        '''

    main_posts = [p for p in posts if p[4] is None]
    html_posts = ""
    for pid, username, content, image_path, parent_id, ts, like_count in main_posts:
        is_liked = request.cookies.get(f"liked_{pid}") == "1"
        replies = replies_by_post.get(pid, [])
        html_posts += render_post(pid, username, content, image_path, ts, like_count, is_liked, replies)

    return f'''
<!DOCTYPE html>
<html lang="it" {theme_attr}>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FiuggiGram ✨</title>
  <link href="https://fonts.googleapis.com/css2?family=Geist+Mono:ital,wght@0,300;0,400;0,500;1,400&family=ClashGrotesk:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --blue-fiuggi: #0F1B3D;
      --blue-fiuggi-light: #1E3A8A;
      --yellow-fiuggi: #FFD166;
      --yellow-fiuggi-dark: #FABF66;
      --bg-light: #F8FAFC;
      --bg-dark: #0F172A;
      --card-light: #FFFFFF;
      --card-dark: #1E293B;
      --text-light: #1E293B;
      --text-dark: #E2E8F0;
      --border-light: rgba(0,0,0,0.05);
      --border-dark: rgba(255,255,255,0.1);
    }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: 'Geist Mono', ui-monospace, system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      transition: background 0.4s ease, color 0.4s ease;
      padding: 20px 16px;
      min-height: 100vh;
    }}

    @media (prefers-color-scheme: dark) {{
      body {{ --bg: var(--bg-dark); --card: var(--card-dark); --text: var(--text-dark); --border: var(--border-dark); }}
    }}
    body[data-theme="light"] {{ --bg: var(--bg-light); --card: var(--card-light); --text: var(--text-light); --border: var(--border-light); }}
    body[data-theme="dark"]  {{ --bg: var(--bg-dark); --card: var(--card-dark); --text: var(--text-dark); --border: var(--border-dark); }}

    .container {{ max-width: 768px; margin: 0 auto; }}

    /* Logo */
    .logo {{
      font-family: 'ClashGrotesk', sans-serif;
      font-weight: 600;
      font-size: 2.6rem;
      background: linear-gradient(90deg, var(--yellow-fiuggi), #FFFFFF);
      -webkit-background-clip: text; background-clip: text; color: transparent;
      text-align: center;
      margin: 24px 0 8px;
      letter-spacing: -0.5px;
    }}
    .logo-sub {{ 
      text-align: center; 
      color: var(--text); 
      opacity: 0.75; 
      font-size: 1.05rem;
      margin-bottom: 32px;
    }}

    /* Theme toggle */
    .theme-toggle {{
      position: absolute; top: 24px; right: 24px;
      width: 52px; height: 28px;
      background: var(--border);
      border-radius: 14px;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      padding: 0 4px;
      backdrop-filter: blur(4px);
    }}
    .theme-toggle::after {{
      content: ""; width: 20px; height: 20px;
      border-radius: 50%;
      background: white;
      transition: 0.3s cubic-bezier(0.68, -0.55, 0.27, 1.55);
      transform: translateX(0);
    }}
    body[data-theme="dark"] .theme-toggle::after {{ transform: translateX(24px); }}

    /* Card */
    .fiuggi-card {{
      background: var(--card);
      border-radius: 24px;
      padding: 28px;
      margin-bottom: 32px;
      box-shadow: 0 10px 40px rgba(15, 27, 61, 0.12);
      border: 1px solid var(--border);
    }}

    /* Form */
    .form-group {{ margin-bottom: 18px; }}
    .form-control {{
      width: 100%;
      padding: 14px 18px;
      border-radius: 16px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.7); /* ✅ Sfondo chiaro */
      font-family: 'Geist Mono';
      font-size: 1.02rem;
      transition: all 0.3s;
      color: #1E293B; /* ✅ Testo nero chiaro */
    }}
    body[data-theme="dark"] .form-control {{
      background: rgba(30, 41, 59, 0.7); /* ✅ Sfondo scuro */
      color: #E2E8F0; /* ✅ Testo chiaro */
    }}
    .form-control:focus {{
      outline: none;
      border-color: var(--yellow-fiuggi);
      box-shadow: 0 0 0 3px rgba(255, 209, 102, 0.3);
    }}
    .file-input-wrapper {{
      background: rgba(255,255,255,0.4);
      border: 2px dashed var(--border);
      border-radius: 16px;
      padding: 18px;
      text-align: center;
      cursor: pointer;
      transition: all 0.3s;
      margin: 12px 0;
    }}
    .file-input-wrapper:hover {{
      border-color: var(--yellow-fiuggi);
      background: rgba(255, 209, 102, 0.08);
    }}
    .btn-fiuggi {{
      width: 100%;
      padding: 16px;
      background: linear-gradient(120deg, var(--blue-fiuggi), var(--blue-fiuggi-light));
      color: white;
      border: none;
      border-radius: 16px;
      font-family: 'ClashGrotesk';
      font-weight: 500;
      font-size: 1.1rem;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
      box-shadow: 0 4px 20px rgba(15, 27, 61, 0.2);
    }}
    .btn-fiuggi:hover {{
      transform: translateY(-3px);
      box-shadow: 0 8px 25px rgba(15, 27, 61, 0.3);
    }}

    /* Posts */
    .fiuggi-post {{
      background: var(--card);
      border-radius: 18px;
      padding: 20px;
      margin-bottom: 24px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.03);
      transition: all 0.3s;
    }}
    .fiuggi-post:hover {{
      box-shadow: 0 6px 25px rgba(0,0,0,0.06);
    }}
    .fiuggi-header {{
      display: flex;
      align-items: flex-start;
      margin-bottom: 14px;
    }}
    .fiuggi-avatar {{
      width: 42px;
      height: 42px;
      border-radius: 50%;
      background: var(--yellow-fiuggi);
      color: var(--blue-fiuggi);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 600;
      font-size: 1.1rem;
      flex-shrink: 0;
      margin-right: 14px;
    }}
    .fiuggi-meta {{
      flex: 1;
    }}
    .fiuggi-meta strong {{
      font-family: 'ClashGrotesk';
      font-weight: 500;
      font-size: 1.15rem;
      color: var(--blue-fiuggi-light);
    }}
    .fiuggi-time {{
      font-size: 0.85rem;
      opacity: 0.7;
      display: block;
      margin-top: 4px;
    }}
    .fiuggi-actions {{
      display: flex;
      gap: 12px;
      margin-left: auto;
    }}
    .fiuggi-like, .fiuggi-reply {{
      background: none;
      border: none;
      font-family: 'Geist Mono';
      font-size: 0.9rem;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 6px 10px;
      border-radius: 10px;
      transition: all 0.2s;
    }}
    .fiuggi-like:hover, .fiuggi-reply:hover {{
      background: rgba(255,209,102,0.15);
    }}
    .fiuggi-content {{
      line-height: 1.6;
      font-size: 1.05rem;
      white-space: pre-wrap;
    }}
    .fiuggi-image img {{
      width: 100%;
      border-radius: 16px;
      margin-top: 16px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }}

    /* Reply form */
    .reply-input {{
      flex: 1;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 0.95rem;
      background: rgba(255,255,255,0.7);
      color: #1E293B;
    }}
    body[data-theme="dark"] .reply-input {{
      background: rgba(30, 41, 59, 0.7);
      color: #E2E8F0;
    }}
    .btn-reply {{
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: var(--yellow-fiuggi);
      color: var(--blue-fiuggi);
      border: none;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
    }}
    .btn-reply:hover {{
      background: var(--yellow-fiuggi-dark);
      transform: scale(1.05);
    }}

    .error {{
      background: rgba(252, 211, 77, 0.15);
      border: 1px solid var(--yellow-fiuggi);
      color: #B45309;
      padding: 14px;
      border-radius: 14px;
      margin-top: 16px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    footer {{
      text-align: center;
      color: var(--text);
      opacity: 0.6;
      font-size: 0.9rem;
      margin-top: 48px;
      padding-top: 24px;
      border-top: 1px solid var(--border);
    }}
  </style>
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()"></button>
  
  <div class="container">
    <h1 class="logo">FiuggiGram</h1>
    <p class="logo-sub">✨ Uno spazio per condividere, insieme</p>

    <div class="fiuggi-card">
      <form method="POST" enctype="multipart/form-data">
        <div class="form-group">
          <input type="text" name="username" class="form-control" placeholder="Il tuo nome" maxlength="16" required autofocus>
        </div>
        <div class="form-group">
          <textarea name="content" class="form-control" rows="3" placeholder="Cosa ti va di condividere oggi?"></textarea>
        </div>
        <div class="file-input-wrapper" onclick="document.getElementById('fileInput').click()">
          <div>📎 Allega un’immagine (opzionale)</div>
          <input type="file" id="fileInput" name="image" accept="image/*" style="display:none">
        </div>
        <div class="form-group">
          <input type="password" name="code" class="form-control" placeholder="Codice Fiuggi" required>
        </div>
        <button type="submit" class="btn-fiuggi">✨ Pubblica</button>
        {"<div class='error'><i class='fas fa-exclamation-triangle'></i> Codice errato!</div>" if error else ""}
      </form>
    </div>

    <h2 style="font-family:'ClashGrotesk'; font-weight:500; font-size:1.5rem; color:var(--text); margin:32px 0 20px">📬 I vostri momenti</h2>
    
    {html_posts if html_posts else '''
    <div class="fiuggi-card" style="text-align:center; padding:50px 20px">
      <div style="font-size:4rem; margin-bottom:20px">✨</div>
      <h3 style="font-family:'ClashGrotesk'; font-weight:500; margin-bottom:12px">Nessun momento ancora</h3>
      <p style="opacity:0.8">Sii il primo a condividere qualcosa di bello.</p>
    </div>
    '''}

    <footer>
      © {datetime.datetime.now().year} FiuggiGram — creato con cura
    </footer>
  </div>

  <script src="https://kit.fontawesome.com/a076d05399.js" crossorigin="anonymous"></script>
  <script>
    setInterval(() => fetch('/ping').catch(() => {{}}), {PING_INTERVAL_SEC * 1000});

    function toggleTheme() {{
      const body = document.body;
      let t = body.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      let next = t === 'light' ? 'dark' : 'light';
      body.setAttribute('data-theme', next);
      document.cookie = "theme=" + next + "; path=/; max-age=31536000";
    }}

    function toggleLike(postId) {{
      fetch('/like/' + postId, {{ method: 'POST' }})
        .then(r => r.json())
        .then(data => {{
          if (data.success) {{
            const btn = document.querySelector(`button[data-id="${{postId}}"]`);
            const icon = btn.querySelector('i');
            const span = btn.querySelector('span');
            if (data.liked) {{
              icon.className = 'fas fa-heart';
              icon.style.color = '#FFD166';
              span.textContent = data.count;
              icon.animate([
                {{ transform: 'scale(1)' }},
                {{ transform: 'scale(1.3)' }},
                {{ transform: 'scale(1)' }}
              ], {{ duration: 400, easing: 'ease' }});
              document.cookie = "liked_" + postId + "=1; path=/";
            }} else {{
              icon.className = 'far fa-heart';
              icon.style.color = '#64748B';
              span.textContent = data.count;
              document.cookie = "liked_" + postId + "=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
            }}
          }}
        }});
    }}

    function toggleReply(postId) {{
      const form = document.getElementById('reply-form-' + postId);
      form.style.display = form.style.display === 'flex' ? 'none' : 'flex';
      form.querySelector('input').focus();
    }}

    function submitReply(postId) {{
      const input = document.querySelector(`#reply-form-${{postId}} .reply-input`);
      const content = input.value.trim();
      if (!content) return;
      
      fetch('/reply', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ post_id: postId, content: content }})
      }})
      .then(r => r.json())
      .then(data => {{
        if (data.success) {{
          input.value = '';
          const repliesDiv = document.getElementById('replies-' + postId);
          const newReply = `
            <div class="fiuggi-post" style="margin-left:16px; border-left:2px solid #CBD5E1; padding-left:16px">
              <div class="fiuggi-header">
                <div class="fiuggi-avatar">T</div>
                <div class="fiuggi-meta">
                  <strong>Tu</strong>
                  <span class="fiuggi-time">pochi secondi fa</span>
                </div>
              </div>
              <div class="fiuggi-content">${{content}}</div>
            </div>
          `;
          repliesDiv.insertAdjacentHTML('beforeend', newReply);
          toggleReply(postId);
        }}
      }});
    }}
  </script>
</body>
</html>
    '''

@app.route("/", methods=["GET", "POST"])
def home():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    if request.method == "POST":
        username = request.form.get("username", "").strip()[:16] or "Amico"
        content = request.form.get("content", "").strip()[:400]
        code = request.form.get("code", "")
        image_path = None

        if code != SECRET_JOIN_CODE:
            cursor.execute("""
                SELECT p.id, p.username, p.content, p.image_path, p.parent_id, p.timestamp,
                       (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) as like_count
                FROM posts p
                WHERE p.parent_id IS NULL
                ORDER BY p.timestamp DESC
            """)
            posts = cursor.fetchall()
            
            replies_by_post = {}
            for pid, *rest in posts:
                cursor.execute("""
                    SELECT id, username, content, image_path, parent_id, timestamp,
                           (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) as like_count
                    FROM posts p
                    WHERE p.parent_id = ?
                    ORDER BY timestamp ASC
                """, (pid,))
                replies_by_post[pid] = cursor.fetchall()
            
            conn.close()
            return render_page(posts, replies_by_post, error=True)

        cursor.execute(
            "INSERT INTO posts (username, content, image_path, parent_id) VALUES (?, ?, ?, NULL)",
            (username, content, image_path)
        )
        conn.commit()

    cursor.execute("""
        SELECT p.id, p.username, p.content, p.image_path, p.parent_id, p.timestamp,
               (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) as like_count
        FROM posts p
        WHERE p.parent_id IS NULL
        ORDER BY p.timestamp DESC
    """)
    posts = cursor.fetchall()
    
    replies_by_post = {}
    for pid, *rest in posts:
        cursor.execute("""
            SELECT id, username, content, image_path, parent_id, timestamp,
                   (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) as like_count
            FROM posts p
            WHERE p.parent_id = ?
            ORDER BY timestamp ASC
        """, (pid,))
        replies_by_post[pid] = cursor.fetchall()
    
    conn.close()
    return render_page(posts, replies_by_post)

@app.route("/reply", methods=["POST"])
def reply():
    data = request.get_json()
    post_id = data.get("post_id")
    content = (data.get("content", "")[:200]).strip()
    username = "Tu"

    if not post_id or not content:
        return {"success": False}, 400

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO posts (username, content, image_path, parent_id) VALUES (?, ?, NULL, ?)",
        (username, content, post_id)
    )
    conn.commit()
    conn.close()
    return {"success": True}

@app.route("/like/<int:post_id>", methods=["POST"])
def like_post(post_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    client_id = get_client_id()

    cursor.execute("SELECT 1 FROM likes WHERE post_id = ? AND ip_hash = ?", (post_id, client_id))
    exists = cursor.fetchone()

    if exists:
        cursor.execute("DELETE FROM likes WHERE post_id = ? AND ip_hash = ?", (post_id, client_id))
        liked = False
    else:
        cursor.execute("INSERT INTO likes (post_id, ip_hash) VALUES (?, ?)", (post_id, client_id))
        liked = True

    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", (post_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return {"success": True, "liked": liked, "count": count}

if not os.path.exists(DATABASE):
    init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"✨ FiuggiGram Evolution — Avvio su porta {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
