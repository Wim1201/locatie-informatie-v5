# Nederlandse Locatie Informatie Portaal

Een webapplicatie die uitgebreide informatie toont over Nederlandse locaties, inclusief demografische gegevens, BAG informatie, ruimtelijke plannen, en meer.

## Features
- Adreszoekfunctie met kaartweergave
- BAG gegevens (Basisregistratie Adressen en Gebouwen)
- Ruimtelijke plannen informatie
- Weer- en klimaatgegevens
- Demografische gegevens
- AI-gegenereerde samenvatting van locatie-eigenschappen

## Installatie
1. Clone deze repository
2. Installeer de benodigdheden: `pip install -r requirements.txt`
3. Maak een `.env` bestand met de volgende API-sleutels:
   - OPENAI_API_KEY
   - ANTHROPIC_API_KEY
   - RUIMTELIJKE_PLANNEN_API_KEY
   - BAG_API_KEY
4. Start de applicatie: `python app.py`

## Gebruik
Open een webbrowser en ga naar http://localhost:5000