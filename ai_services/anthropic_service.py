import os
import anthropic
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def generate_claude_analysis(adresgegevens, pandgegevens, demodata, bestemmingsinfo, vraag=None):
    """
    Genereert een analyse met Claude 3 op basis van locatiegegevens.
    """

    prompt = f"""
Je bent een ervaren vastgoedanalist. Analyseer de onderstaande locatiegegevens op een duidelijke, gestructureerde en begrijpelijke manier.

🗺️ Adresgegevens:
- Straat en nummer: {adresgegevens.get("straat", "onbekend")}
- Postcode: {adresgegevens.get("postcode", "onbekend")}
- Plaats: {adresgegevens.get("plaats", "onbekend")}
- Gemeente: {adresgegevens.get("gemeente", "onbekend")}
- Provincie: {adresgegevens.get("provincie", "onbekend")}

🏠 Pandgegevens:
- Bouwjaar: {pandgegevens.get("bouwjaar", "onbekend")}
- Oppervlakte: {pandgegevens.get("oppervlakte", "onbekend")} m²
- Gebruiksdoel: {pandgegevens.get("gebruiksdoel", "onbekend")}
- Status: {pandgegevens.get("status", "onbekend")}

📊 Demografie gemeente:
- Inwoners: {demodata.get("inwoners", "onbekend")}
- Gemiddeld inkomen: €{demodata.get("inkomen", "onbekend")} per jaar

📐 Bestemmingsplan:
- Functie: {bestemmingsinfo.get("functie", "onbekend")}
- Bouwhoogte toegestaan: {bestemmingsinfo.get("bouwhoogte", "onbekend")}
- Status plan: {bestemmingsinfo.get("status", "onbekend")}

"""

    if vraag:
        prompt += f"\n🔎 Vraag van gebruiker: {vraag}\n"

    try:
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=800,
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"Er trad een fout op bij het genereren van Claude's analyse: {e}"
