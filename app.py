from flask import Flask, render_template, request
import os

from config import (
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    BAG_API_KEY,
    RUIMTELIJKE_PLANNEN_API_KEY,
)

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/result", methods=["POST"])
def result():
    adres = request.form.get("adres")
    vraag = request.form.get("vraag")
    # Vereenvoudigd voorbeeld
    resultaat = {
        "adres": adres,
        "vraag": vraag,
        "antwoord": "Voorbeeldantwoord op basis van API-gegevens en AI-analyse.",
        "openai_toelichting": "Analyse door GPT (voorbeeld).",
        "anthropic_toelichting": "Analyse door Claude (voorbeeld).",
    }
    return render_template("results.html", **resultaat)

if __name__ == "__main__":
    app.run(debug=True)
