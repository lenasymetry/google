import streamlit as st
from google.oauth2 import service_account
from google.cloud import vision
import json
import os
from PIL import Image
import io
import fitz  # PyMuPDF pour PDF
import unicodedata

# ------------------ 🔐 Authentification Google Vision ------------------

# Charger le JSON string et le parser
json_str = st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]
credentials_info = json.loads(json_str)

# Créer les credentials
credentials = service_account.Credentials.from_service_account_info(credentials_info)

# Créer le client Vision (à utiliser partout)
client = vision.ImageAnnotatorClient(credentials=credentials)

# ------------------ 🧠 Fonctions d’analyse OCR ------------------

EMOJI_DOC = {
    "Carte d'identité": "🪪",
    "Passeport": "🛂",
    "Titre de séjour": "📄",
    "Justificatif de domicile": "🏠",
    "RIB": "💳",
}

def normalize_text(text):
    nfkd_form = unicodedata.normalize('NFKD', text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()

def detect_carte_id(texte):
    t = texte.lower()
    return ("république" in t or "republique" in t) and ("française" in t or "francaise" in t) and ("carte" in t or "identité" in t)

def detect_passeport(texte):
    t = texte.lower()
    return "passeport" in t and not ("titre" in t or "séjour" in t)

def detect_titre_sejour(texte):
    mots = ["résidence", "permit", "residence", "titre", "sejour", "séjour"]
    t = texte.lower()
    return sum(1 for mot in mots if mot in t) >= 2

def detect_justif_domicile(texte):
    mots = [
        "justificatif de domicile", "adresse", "nom du titulaire", "domicile", "quittance de loyer",
        "facture", "facture d'électricité", "facture edf", "facture engie", "facture gdf",
        "facture d'eau", "suez", "veolia", "facture de gaz", "attestation d'hébergement",
        "assurance habitation", "bail", "contrat de location", "date d’émission", "avis d'échéance", "quittance", "loyer", "loyers", "montants", "avis d'echeance"
    ]
    t = texte.lower()
    return sum(1 for mot in mots if mot in t) >= 2

def detect_rib(texte):
    mots = [
        "relevé d'identité bancaire", "rib", "iban", "bic", "code banque", "code guichet",
        "numéro de compte", "clé rib", "titulaire du compte", "nom de la banque"
    ]
    t = texte.lower()
    return sum(1 for mot in mots if mot in t) >= 2

def texte_contient_nom_prenom(texte, prenom, nom):
    t_norm = normalize_text(texte)
    prenom_norm = normalize_text(prenom)
    nom_norm = normalize_text(nom)
    return prenom_norm in t_norm and nom_norm in t_norm

def detect_type_doc(texte, options, prenom=None, nom=None):
    def valide_detection(detect_func):
        if prenom and nom:
            return detect_func(texte) and texte_contient_nom_prenom(texte, prenom, nom)
        else:
            return detect_func(texte)

    if options.get("passeport") and valide_detection(detect_passeport):
        return "Passeport"
    if options.get("carte_id") and valide_detection(detect_carte_id):
        return "Carte d'identité"
    if options.get("titre_sejour") and valide_detection(detect_titre_sejour):
        return "Titre de séjour"
    if options.get("justif_domicile") and valide_detection(detect_justif_domicile):
        return "Justificatif de domicile"
    if options.get("rib") and valide_detection(detect_rib):
        return "RIB"
    return None

def ocr_google_vision(file_bytes, is_pdf=False, client=None):
    texte_total = ""

    if is_pdf:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num in range(min(1, len(doc))):  # une seule page suffit
            page = doc.load_page(page_num)
            pix = page.get_pixmap()
            img_bytes = pix.tobytes("png")
            image = vision.Image(content=img_bytes)
            response = client.text_detection(image=image)
            if response.error.message:
                continue
            texte_total += response.full_text_annotation.text + "\n"
    else:
        image = vision.Image(content=file_bytes)
        response = client.text_detection(image=image)
        if response.error.message:
            return ""
        texte_total = response.full_text_annotation.text

    return texte_total

# ------------------ 🚀 Interface Streamlit ------------------

def main():
    st.set_page_config(page_title="OCR Détection Documents", layout="wide")

    # Charger le logo pour récupérer sa largeur
    logo = Image.open('mon_logo.png')
    largeur_originale = logo.width

    # Afficher le logo avec largeur divisée par 2
    st.image(logo, width=largeur_originale // 2)

    st.title("🔍 OCR Détection de documents officiels")

    with st.sidebar:
        st.header("🔧 Options")
        doc_types = {
            "passeport": st.checkbox("🛂 Passeport", value=True),
            "carte_id": st.checkbox("✅ Carte d'identité", value=True),
            "titre_sejour": st.checkbox("📄 Titre de séjour", value=True),
            "justif_domicile": st.checkbox("🏠 Justificatif de domicile", value=True),
            "rib": st.checkbox("💳 RIB", value=True),
        }

        st.header("🧍 Identité")
        prenom = st.text_input("Prénom").strip()
        nom = st.text_input("Nom").strip()

        st.header("📂 Fichiers")
        uploaded_files = st.file_uploader("Importer fichiers (PDF ou images)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

        analyse = st.button("🔍 Lancer l’analyse")

    if analyse:
        if not uploaded_files:
            st.warning("Merci d'importer au moins un fichier.")
            return
        if not prenom or not nom:
            st.warning("Merci de saisir prénom et nom.")
            return

        resultats = []
        for file in uploaded_files:
            file_bytes = file.read()
            is_pdf = file.type == "application/pdf"
            texte = ocr_google_vision(file_bytes, is_pdf, client)
            type_doc = detect_type_doc(texte, doc_types, prenom=prenom, nom=nom)

            if type_doc:
                resultats.append({
                    "nom_fichier": file.name,
                    "type_doc": type_doc,
                    "file_bytes": file_bytes,
                    "is_pdf": is_pdf
                })

        if resultats:
            st.sidebar.markdown("---")
            st.sidebar.header("📋 Résultats")
            for r in resultats:
                emoji = EMOJI_DOC.get(r["type_doc"], "📄")
                st.sidebar.write(f"{emoji} {r['type_doc']} de **{prenom} {nom}**")

            st.header("📑 Détails des documents trouvés")
            for r in resultats:
                st.markdown(f"### {EMOJI_DOC.get(r['type_doc'], '📄')} {r['type_doc']} de **{prenom} {nom}**")
                if r["is_pdf"]:
                    doc = fitz.open(stream=r["file_bytes"], filetype="pdf")
                    page = doc.load_page(0)
                    pix = page.get_pixmap()
                    img_bytes = pix.tobytes("png")
                    image = Image.open(io.BytesIO(img_bytes))
                    st.image(image, caption=f"{r['nom_fichier']} - Page 1")
                else:
                    image = Image.open(io.BytesIO(r["file_bytes"]))
                    st.image(image, caption=r["nom_fichier"])
        else:
            st.error("❌ Aucun document officiel trouvé parmi les fichiers importés.")

if __name__ == "__main__":
    main()




