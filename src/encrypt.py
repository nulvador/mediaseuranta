"""Raportin salaus web-julkaisua varten.

Salaa HTML-tiedoston AES-256-GCM:llä (avain johdetaan salasanasta PBKDF2:lla).
Tuloksena on itsenäinen HTML-sivu, joka kysyy salasanan ja purkaa sisällön
selaimessa WebCrypto-rajapinnalla. Ilman salasanaa sisältöä ei voi lukea —
ei edes julkisen GitHub-repon kautta.

Käyttö:  python -m src.encrypt <input.html> <output.html>
Salasana luetaan REPORT_PASSWORD-ympäristömuuttujasta (.env).
Paluukoodit: 0 = salattu, 3 = salasanaa ei ole asetettu, 1 = virhe.
"""
import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import config  # noqa: F401 — lataa .env:n ympäristömuuttujiin

ITERATIONS = 600_000

_TEMPLATE = """<!DOCTYPE html>
<html lang="fi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Golfliiton mediakatsaus</title>
<style>
body{font-family:-apple-system,'Segoe UI',sans-serif;background:#f4f6f4;display:flex;
     align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{background:#fff;border-radius:12px;padding:36px 40px;box-shadow:0 2px 12px rgba(0,0,0,.08);
     max-width:340px;text-align:center}
h1{color:#003F20;font-size:1.15rem;margin:0 0 6px}
p{color:#667;font-size:.85rem;margin:0 0 18px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #ccc;
      border-radius:8px;font-size:.95rem;margin-bottom:10px}
button{width:100%;padding:10px;border:none;border-radius:8px;background:#003F20;
       color:#fff;font-size:.95rem;font-weight:600;cursor:pointer}
button:disabled{opacity:.6}
#err{color:#c1121f;font-size:.82rem;min-height:1.2em;margin:10px 0 0}
</style></head><body>
<div class="box">
  <h1>&#128274; Golfliiton mediakatsaus</h1>
  <p>T&auml;m&auml; sivu on suojattu. Sy&ouml;t&auml; salasana.</p>
  <form id="f">
    <input type="password" id="pw" autofocus autocomplete="current-password" placeholder="Salasana">
    <button id="btn">Avaa raportti</button>
    <div id="err"></div>
  </form>
</div>
<script>
var PAYLOAD="__PAYLOAD__", ITER=__ITER__;
function b64(s){var r=atob(s),a=new Uint8Array(r.length);
  for(var i=0;i<r.length;i++)a[i]=r.charCodeAt(i);return a;}
document.getElementById("f").addEventListener("submit",async function(e){
  e.preventDefault();
  var err=document.getElementById("err"),btn=document.getElementById("btn");
  err.textContent="";btn.disabled=true;btn.textContent="Avataan\\u2026";
  try{
    var data=b64(PAYLOAD),salt=data.slice(0,16),iv=data.slice(16,28),ct=data.slice(28);
    var enc=new TextEncoder();
    var km=await crypto.subtle.importKey("raw",
      enc.encode(document.getElementById("pw").value),"PBKDF2",false,["deriveKey"]);
    var key=await crypto.subtle.deriveKey(
      {name:"PBKDF2",salt:salt,iterations:ITER,hash:"SHA-256"},
      km,{name:"AES-GCM",length:256},false,["decrypt"]);
    var pt=await crypto.subtle.decrypt({name:"AES-GCM",iv:iv},key,ct);
    var html=new TextDecoder().decode(pt);
    document.open();document.write(html);document.close();
  }catch(_){
    err.textContent="V\\u00e4\\u00e4r\\u00e4 salasana";
    btn.disabled=false;btn.textContent="Avaa raportti";
  }
});
</script></body></html>"""


def encrypt_html(html: bytes, password: str) -> str:
    salt = os.urandom(16)
    iv = os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=salt, iterations=ITERATIONS)
    key = kdf.derive(password.encode("utf-8"))
    ciphertext = AESGCM(key).encrypt(iv, html, None)
    payload = base64.b64encode(salt + iv + ciphertext).decode("ascii")
    return _TEMPLATE.replace("__PAYLOAD__", payload).replace("__ITER__", str(ITERATIONS))


def main() -> int:
    if len(sys.argv) != 3:
        print("käyttö: python -m src.encrypt <input.html> <output.html>", file=sys.stderr)
        return 1
    password = os.environ.get("REPORT_PASSWORD", "").strip()
    if not password:
        return 3

    src_path, dst_path = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        result = encrypt_html(src_path.read_bytes(), password)
        tmp = dst_path.with_suffix(".tmp")
        tmp.write_text(result, encoding="utf-8")
        tmp.replace(dst_path)
    except Exception as e:  # noqa: BLE001
        print(f"salaus epäonnistui: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
