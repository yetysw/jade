# -*- mode: python ; coding: utf-8 -*-
"""Build PyInstaller du backend Jade (onedir, fenêtré).

Sortie : dist/Jade/Jade.exe + _internal/ — backend API pur, lancé en sidecar
par l'application native Flutter. Le .env n'est PAS dans le bundle (écrit par
l'assistant d'installation) ; les modèles sont téléchargés au premier lancement
dans %PROGRAMDATA%\\Jade\\models.
"""

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    "ragagent",
    # importés paresseusement (dans des fonctions) — sécurise l'analyse
    # jwt : import différé dans licensing.py (vérification EdDSA de la licence)
    "jwt",
    "docx", "openpyxl", "xlrd", "extract_msg", "odf", "odf.opendocument",
    "odf.text", "odf.teletype", "pypdf", "pypdfium2", "rank_bm25",
    "winreg", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
]

# paquets avec données/binaires embarqués (moteurs ONNX, migrations SQL, JS,
# polices reportlab pour la création de PDF...)
# pptx embarque un modèle de présentation par défaut (default.pptx) : collect_all
# indispensable, sinon la création PowerPoint plante dans l'exe (comme reportlab)
# NB : plus de rapidocr/opencv (OCR, ~125 Mo) ni webview/.NET (ancienne UI) —
# l'interface est Flutter et l'OCR dégrade proprement (ocr.available() -> False).
# cryptography : bindings OpenSSL (EdDSA de la licence) — collecte complète pour
# embarquer les modules binaires de manière fiable dans l'exe gelé
for pkg in ("chromadb", "fastembed", "onnxruntime",
            "tokenizers", "reportlab", "pptx", "cryptography"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["jade_launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "IPython", "jupyter", "pytest",
        "kubernetes",  # dépendance optionnelle de chromadb, inutile en local
        # OCR retiré (OpenCV ~112 Mo) : dégrade proprement via ocr.available()
        "cv2", "rapidocr_onnxruntime",
        # ancienne UI WebView remplacée par Flutter : runtime .NET inutile
        "webview", "pywebview", "clr_loader", "pythonnet", "Python.Runtime",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Jade",
    icon="installer/jade.ico",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # application fenêtrée : pas de console noire
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Jade",
)
