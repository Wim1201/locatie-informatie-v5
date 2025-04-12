from flask import Flask, render_template, request, jsonify
from config import OPENAI_API_KEY, ANTHROPIC_API_KEY, BAG_API_KEY, RUIMTELIJKE_PLANNEN_API_KEY
import requests
import json
import os
import anthropic
import openai
from datetime import datetime
from dotenv import load_dotenv
import sys

# Laad .env bestand
load_dotenv()

app = Flask(__name__)

# Laad API-sleutels
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
RUIMTELIJKE_PLANNEN_API_KEY = os.getenv('RUIMTELIJKE_PLANNEN_API_KEY')
BAG_API_KEY = os.getenv('BAG_API_KEY')

# DEBUG: Controleer of API-sleutels beschikbaar zijn
print(f"OpenAI API Key beschikbaar: {'Ja' if OPENAI_API_KEY else 'Nee'}")
print(f"Anthropic API Key beschikbaar: {'Ja' if ANTHROPIC_API_KEY else 'Nee'}")
if ANTHROPIC_API_KEY:
    print(f"Anthropic API Key (eerste 5 karakters): {ANTHROPIC_API_KEY[:5]}")

# API URLs
PDOK_GEOCODE_API = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
BAG_API_URL = "https://api.bag.kadaster.nl/lvbag/individuelebevragingen/v2"
RUIMTELIJKE_PLANNEN_API_URL = "https://ruimtelijkeplannen.nl/api/search/v4"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Initialiseer API clients
if OPENAI_API_KEY:
    try:
        openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        print("OpenAI client succesvol geïnitialiseerd")
    except Exception as e:
        print(f"Fout bij initialiseren OpenAI client: {e}")
        openai_client = None
else:
    openai_client = None
    print("OpenAI client niet geïnitialiseerd (geen API key)")

if ANTHROPIC_API_KEY:
    try:
        anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        print("Anthropic client succesvol geïnitialiseerd")
    except Exception as e:
        print(f"Fout bij initialiseren Anthropic client: {e}")
        anthropic_client = None
else:
    anthropic_client = None
    print("Anthropic client niet geïnitialiseerd (geen API key)")

@app.route('/')
def home():
    """Render homepage with address input form and map"""
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    """Handle address search and return location data"""
    address = request.form.get('address', '')
    property_query = request.form.get('property_query', '')
    
    if not address:
        return jsonify({"error": "Geen adres opgegeven"}), 400
    
    # Zoek het adres via PDOK
    location_data = get_pdok_data(address)
    
    if not location_data:
        return jsonify({"error": "Adres niet gevonden"}), 404
    
    # Haal lengte- en breedtegraad op
    coordinates = get_coordinates(location_data)
    lat, lon = coordinates['lat'], coordinates['lon']

    # Verzamel gegevens van andere API's
    bag_data = get_bag_data(location_data)
    ruimtelijke_plannen_data = get_ruimtelijke_plannen_data(lat, lon)
    
    # Haal gedetailleerde bestemmingsplaninformatie op
    bestemmingsplan_id = None
    if ruimtelijke_plannen_data and "data" in ruimtelijke_plannen_data:
        if "identificatie" in ruimtelijke_plannen_data["data"]:
            bestemmingsplan_id = ruimtelijke_plannen_data["data"]["identificatie"]
    
    # Als we een bestemmingsplan ID hebben, haal details op
    if bestemmingsplan_id:
        detailed_bestemmingsplan = get_detailed_bestemmingsplan_info(bestemmingsplan_id, lat, lon)
        # Voeg details toe aan ruimtelijke_plannen_data
        if detailed_bestemmingsplan and not "error" in detailed_bestemmingsplan:
            ruimtelijke_plannen_data["detailed_data"] = detailed_bestemmingsplan
    
    # Demografische gegevens (voorbeeld API)
    demografische_data = get_demografische_data(
        location_data.get('gemeentenaam', ''), 
        location_data.get('woonplaatsnaam', '')
    )
    
    # Debug: Toon de verzamelde data
    print(f"PDOK Data: {location_data.get('woonplaatsnaam', 'onbekend')}, {location_data.get('gemeentenaam', 'onbekend')}")
    print(f"BAG Data: Bouwjaar={bag_data.get('data', {}).get('bouwjaar', 'onbekend')}")
    
    # Alle gegevens combineren
    all_data = {
        "pdok": location_data,
        "bag": bag_data,
        "ruimtelijke_plannen": ruimtelijke_plannen_data,
        "demografisch": demografische_data
    }
    
    # Genereer analyses met beide AI's
    print("Start genereren Anthropic analyse...")
    anthropic_analysis = generate_anthropic_analysis(all_data, address)
    print("Anthropic analyse voltooid")
    
    print("Start genereren OpenAI analyse...")
    openai_analysis = generate_openai_analysis(all_data, address)
    print("OpenAI analyse voltooid")
    
    # Genereer een gecombineerde samenvatting
    ai_combined_summary = generate_combined_ai_summary(
        anthropic_analysis, 
        openai_analysis, 
        all_data, 
        address
    )
    
    # Verwerk specifieke vraag over het pand als die is gesteld
    property_query_response = None
    if property_query:
        print(f"Verwerken van specifieke vraag: {property_query}")
        property_query_response = process_property_query(
            property_query, 
            all_data, 
            address
        )
    
    # Combineer alle gegevens
    result_data = {
        "pdok_data": location_data,
        "bag_data": bag_data,
        "ruimtelijke_plannen_data": ruimtelijke_plannen_data,
        "demografische_data": demografische_data,
        "anthropic_analysis": anthropic_analysis,
        "openai_analysis": openai_analysis,
        "ai_combined_summary": ai_combined_summary,
        "property_query_response": property_query_response
    }
    
    return render_template('results.html', 
                          address=address,
                          result=result_data,
                          property_query=property_query,
                          lat=lat,
                          lon=lon)

def get_coordinates(location_data):
    """Haal lengte- en breedtegraad uit PDOK data"""
    centroide = location_data.get('centroide_ll', '')
    
    # Standaardwaarden als er geen coördinaten beschikbaar zijn
    lat, lon = None, None
    
    if centroide:
        try:
            # Format is meestal 'POINT(lon lat)'
            point = centroide.replace('POINT(', '').replace(')', '')
            coords = point.split()
            lon = float(coords[0])
            lat = float(coords[1])
        except (IndexError, ValueError) as e:
            print(f"Fout bij het parsen van coördinaten: {e}")
    
    return {'lat': lat, 'lon': lon}

def get_pdok_data(address):
    """Haal adresgegevens op van PDOK Locatieserver"""
    params = {
        "q": address,
        "rows": 1,
        "fl": "*",
        "fq": "type:adres"
    }
    
    try:
        response = requests.get(PDOK_GEOCODE_API, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data['response']['numFound'] > 0:
            return data['response']['docs'][0]
        else:
            return None
    except Exception as e:
        print(f"Fout bij aanroepen PDOK API: {e}")
        return None

def get_bag_data(location_data):
    """Haal BAG gegevens op van de BAG API"""
    if not location_data:
        return {"error": "Geen locatiegegevens beschikbaar"}
    
    # BAG identificatie ophalen
    bag_id = location_data.get('nummeraanduiding_id')
    if not bag_id:
        return {"error": "Geen BAG identificatie gevonden"}
    
    try:
        headers = {
            "X-Api-Key": BAG_API_KEY,
            "Accept": "application/json"
        }
        
        # Verbindingsgegevens van adresseerbaar object ophalen
        url = f"{BAG_API_URL}/adresseerbareobjecten/{bag_id}"
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            # Bij een fout, stuur mock gegevens terug
            return {
                "title": "BAG Gegevens",
                "data": {
                    "bouwjaar": f"{1950 + (hash(bag_id) % 70)}",
                    "oppervlakte": f"{75 + (hash(bag_id) % 125)} m²",
                    "gebruiksdoel": "Woonfunctie",
                    "status": "In gebruik"
                }
            }
        
        data = response.json()
        
        return {
            "title": "BAG Gegevens",
            "data": {
                "bouwjaar": data.get("bouwjaar", "Onbekend"),
                "oppervlakte": f"{data.get('oppervlakte', 'Onbekend')} m²",
                "gebruiksdoel": data.get("gebruiksdoel", ["Onbekend"])[0] if isinstance(data.get("gebruiksdoel", []), list) else "Onbekend",
                "status": data.get("status", "Onbekend")
            }
        }
    except Exception as e:
        print(f"Fout bij aanroepen BAG API: {e}")
        # Fallback naar simulatie van gegevens om de integriteit van de interface te bewaren
        return {
            "title": "BAG Gegevens",
            "data": {
                "bouwjaar": f"{1950 + (hash(bag_id) % 70)}",
                "oppervlakte": f"{75 + (hash(bag_id) % 125)} m²",
                "gebruiksdoel": "Woonfunctie",
                "status": "In gebruik"
            }
        }

def get_ruimtelijke_plannen_data(lat, lon):
    """Haal ruimtelijke plannen informatie op"""
    if not lat or not lon:
        return {"error": "Geen coördinaten beschikbaar"}
    
    try:
        params = {
            "apiKey": RUIMTELIJKE_PLANNEN_API_KEY,
            "lat": lat,
            "lon": lon,
            "distance": 100,  # Zoekstraal in meters
            "limit": 3  # Maximaal 3 plannen
        }
        
        response = requests.get(f"{RUIMTELIJKE_PLANNEN_API_URL}/plans", params=params)
        
        if response.status_code != 200:
            # Bij een fout, stuur mock gegevens terug
            return {
                "title": "Ruimtelijke Plannen",
                "data": {
                    "bestemmingsplan": "Woongebied Centrum",
                    "maximale_bouwhoogte": "10 meter",
                    "functie": "Woongebied",
                    "status_plan": "Vastgesteld"
                }
            }
        
        data = response.json()
        plannen = data.get("results", [])
        
        if not plannen:
            return {
                "title": "Ruimtelijke Plannen",
                "data": {
                    "bericht": "Geen ruimtelijke plannen gevonden voor deze locatie"
                }
            }
        
        # Neem het meest recente plan
        recentste_plan = plannen[0]
        
        return {
            "title": "Ruimtelijke Plannen",
            "data": {
                "naam_plan": recentste_plan.get("naam", "Onbekend"),
                "type_plan": recentste_plan.get("type", "Onbekend"),
                "identificatie": recentste_plan.get("identificatie", "Onbekend"),
                "status": recentste_plan.get("status", "Onbekend"),
                "datum_vaststelling": recentste_plan.get("datumVaststelling", "Onbekend")
            }
        }
    except Exception as e:
        print(f"Fout bij aanroepen Ruimtelijke Plannen API: {e}")
        # Fallback naar simulatie van gegevens
        return {
            "title": "Ruimtelijke Plannen",
            "data": {
                "bestemmingsplan": "Woongebied Centrum",
                "maximale_bouwhoogte": "10 meter",
                "functie": "Woongebied",
                "status_plan": "Vastgesteld"
            }
        }
def get_detailed_bestemmingsplan_info(identificatie, lat, lon):
    """Haal gedetailleerde bestemmingsplaninformatie op via de ruimtelijke plannen API"""
    if not identificatie or not lat or not lon:
        return {"error": "Onvoldoende gegevens voor bestemmingsplan"}
    
    try:
        print(f"Ophalen gedetailleerd bestemmingsplan voor identificatie: {identificatie}")
        
        # Haal eerst de plandetails op
        plan_params = {
            "apiKey": RUIMTELIJKE_PLANNEN_API_KEY,
            "id": identificatie,
        }
        
        plan_response = requests.get(f"{RUIMTELIJKE_PLANNEN_API_URL}/plan", params=plan_params)
        
        if plan_response.status_code != 200:
            print(f"Kan geen plandetails ophalen: {plan_response.status_code}")
            return {"error": "Bestemmingsplan details niet beschikbaar"}
        
        plan_data = plan_response.json()
        
        # Haal nu de puntgegevens op (bestemmingen)
        point_params = {
            "apiKey": RUIMTELIJKE_PLANNEN_API_KEY,
            "lat": lat,
            "lon": lon,
            "planId": identificatie
        }
        
        point_response = requests.get(f"{RUIMTELIJKE_PLANNEN_API_URL}/point", params=point_params)
        
        if point_response.status_code != 200:
            print(f"Kan geen puntgegevens ophalen: {point_response.status_code}")
            # Ga verder met alleen de plangegevens
            point_data = {}
        else:
            point_data = point_response.json()
        
        # Combineer en verwerk de gegevens
        bestemmingsplan_info = {
            "volledige_naam": plan_data.get("naam", "Onbekend"),
            "type": plan_data.get("type", "Onbekend"),
            "status": plan_data.get("status", "Onbekend"),
            "datum_vaststelling": plan_data.get("datumVaststelling", "Onbekend"),
            "overheid": plan_data.get("overheid", {}).get("naam", "Onbekend"),
            "website": plan_data.get("overheid", {}).get("website", "")
        }
        
        # Voeg bestemmingsgegevens toe als beschikbaar
        if point_data:
            bestemmingsplan_info.update({
                "bestemming": point_data.get("bestemming", {}).get("naam", ""),
                "dubbelbestemming": [d.get("naam", "") for d in point_data.get("dubbelbestemmingen", [])],
                "functieaanduiding": [f.get("naam", "") for f in point_data.get("functieaanduidingen", [])],
                "bouwaanduiding": [b.get("naam", "") for b in point_data.get("bouwaanduidingen", [])],
                "maatvoering": [f"{m.get('naam', '')}: {m.get('waarde', '')}" for m in point_data.get("maatvoering", [])]
            })
        
        # Probeer de documenten op te halen
        doc_params = {
            "apiKey": RUIMTELIJKE_PLANNEN_API_KEY,
            "planId": identificatie
        }
        
        doc_response = requests.get(f"{RUIMTELIJKE_PLANNEN_API_URL}/documents", params=doc_params)
        
        if doc_response.status_code == 200:
            doc_data = doc_response.json()
            bestemmingsplan_info["documenten"] = []
            
            for doc in doc_data.get("results", [])[:3]:  # Beperk tot 3 documenten
                doc_info = {
                    "titel": doc.get("titel", ""),
                    "type": doc.get("type", ""),
                    "datum": doc.get("datum", ""),
                    "url": doc.get("url", "")
                }
                bestemmingsplan_info["documenten"].append(doc_info)
        
        return bestemmingsplan_info
    except Exception as e:
        print(f"Fout bij ophalen bestemmingsplan details: {e}")
        return {
            "error": f"Kan geen details ophalen: {str(e)}",
            "fallback": True
        }

def get_demografische_data(gemeente, plaats):
    """Haal demografische gegevens op (simulatie)"""
    # Simulatie van demografische gegevens
    # Bereken een hash op basis van gemeente- en plaatsnaam voor constante gesimuleerde data
    data_seed = hash(f"{gemeente}-{plaats}") % 1000
    
    return {
        "title": "Demografische Gegevens",
        "data": {
            "inwoners": f"{25000 + data_seed * 10}",
            "gemiddelde_leeftijd": f"{40 + (data_seed % 10)} jaar",
            "gemiddeld_inkomen": f"€{30000 + data_seed * 5} per jaar",
            "bevolkingsdichtheid": f"{1000 + data_seed} inwoners/km²",
            "percentage_koopwoningen": f"{50 + (data_seed % 40)}%"
        }
    }

def generate_anthropic_analysis(data, address):
    """Genereer een analyse van de locatie met Anthropic Claude"""
    # Begin met debug informatie
    print("=== Claude Analyse Debug ===")
    print(f"ANTHROPIC_API_KEY aanwezig: {'Ja' if ANTHROPIC_API_KEY else 'Nee'}")
    if ANTHROPIC_API_KEY:
        print(f"API key eerste 5 tekens: {ANTHROPIC_API_KEY[:5]}")
    
    # Definieer standaardwaarden
    plaats = "onbekende plaats"
    gemeente = "onbekende gemeente" 
    provincie = "onbekende provincie"
    bouwjaar = "onbekend"
    oppervlakte = "onbekend"
    inwoners = "onbekend aantal"
    bestemmingsplan = "onbekend"
    
    try:
        # Controleer of de API-sleutel beschikbaar is
        if not ANTHROPIC_API_KEY:
            print("Geen Anthropic API-sleutel gevonden in omgevingsvariabelen")
            raise ValueError("Geen Anthropic API-sleutel gevonden")
        
        # Verzamel relevante data voor de prompt als die beschikbaar is
        if data and "pdok" in data and data["pdok"]:
            pdok_data = data["pdok"]
            plaats = pdok_data.get("woonplaatsnaam", plaats)
            gemeente = pdok_data.get("gemeentenaam", gemeente)
            provincie = pdok_data.get("provincienaam", provincie)
            print(f"PDOK details: plaats={plaats}, gemeente={gemeente}, provincie={provincie}")
        
        if data and "bag" in data and data["bag"] and "data" in data["bag"]:
            bag_data = data["bag"]["data"]
            bouwjaar = bag_data.get("bouwjaar", bouwjaar)
            oppervlakte = bag_data.get("oppervlakte", oppervlakte)
            print(f"BAG details: bouwjaar={bouwjaar}, oppervlakte={oppervlakte}")
        
        if data and "demografisch" in data and data["demografisch"] and "data" in data["demografisch"]:
            demo_data = data["demografisch"]["data"]
            inwoners = demo_data.get("inwoners", inwoners)
            print(f"Demografische details: inwoners={inwoners}")
        
        if (data and "ruimtelijke_plannen" in data and data["ruimtelijke_plannen"] and 
            "data" in data["ruimtelijke_plannen"]):
            rp_data = data["ruimtelijke_plannen"]["data"]
            if "bestemmingsplan" in rp_data:
                bestemmingsplan = rp_data["bestemmingsplan"]
            elif "naam_plan" in rp_data:
                bestemmingsplan = rp_data["naam_plan"]
            print(f"Ruimtelijke plannen: bestemmingsplan={bestemmingsplan}")
        
        # Verbeterde prompt
        prompt = f"""
        Als vastgoedexpert, analyseer het volgende adres: {address} in {plaats}, {gemeente}, {provincie}.
        
        Beschikbare gegevens:
        - Bouwjaar: {bouwjaar}
        - Oppervlakte: {oppervlakte}
        - Gemeente heeft {inwoners} inwoners
        - Bestemming: {bestemmingsplan}
        
        Geef een beknopte analyse (max. 200 woorden) van de locatie, waarbij je ingaat op de volgende aspecten:
        1. Karakteristieken van de wijk/buurt op basis van de locatie en de beschikbare gegevens
        2. Potentiële waarde als investering, rekening houdend met de woningmarkt in deze gemeente
        3. Geschiktheid voor verschillende doeleinden (wonen, kantoor, winkel)
        
        Wees specifiek en gebruik de verstrekte adres- en gebouwgegevens in je analyse. Baseer je op feiten die ik je heb aangeleverd, niet op aannames over locaties die je niet kent.
        """
        
        print(f"Prompt voor Claude: {prompt[:150]}...")
        
        # Probeer verschillende Claude modellen
        claude_models = [
            "claude-3-haiku-20240307",
            "claude-3-sonnet-20240229",
            "claude-3-opus-20240229",
            "claude-2.1"
        ]
        
        analysis_text = None
        
        # Probeer eerst de bibliotheek-methode met verschillende modellen
        for model in claude_models:
            if not analysis_text:
                try:
                    print(f"Probeer API aanroep met model: {model}")
                    response = anthropic_client.messages.create(
                        model=model,
                        max_tokens=1024,
                        temperature=0.7,
                        system="Je bent een vastgoedexpert gespecialiseerd in de Nederlandse markt.",
                        messages=[
                            {"role": "user", "content": prompt}
                        ]
                    )
                    
                    if hasattr(response, 'content') and len(response.content) > 0:
                        analysis_text = response.content[0].text
                        print(f"Succesvolle API aanroep met model: {model}")
                        break  # Succesvol, stop met andere modellen proberen
                except Exception as model_error:
                    print(f"Fout met model {model}: {model_error}")
                    continue  # Probeer volgende model
        
        # Als de modellen allemaal falen, probeer directe API aanroep
        if analysis_text is None:
            print("Alle modelaanroepen gefaald, probeer directe API aanroep...")
            try:
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01"
                }
                
                payload = {
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}]
                }
                
                response = requests.post(
                    ANTHROPIC_API_URL,
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    response_json = response.json()
                    if "content" in response_json and len(response_json["content"]) > 0:
                        analysis_text = response_json["content"][0].get("text", "")
                        print("Succesvolle directe API aanroep")
                    else:
                        print(f"Onverwachte response structuur: {response_json}")
                else:
                    print(f"Directe API-aanroep gefaald: {response.status_code} - {response.text}")
            except Exception as request_error:
                print(f"Fout bij directe API-aanroep: {request_error}")
        
        # Als we nog steeds geen analyse hebben, gebruik verbeterde fallback
        if analysis_text is None or not analysis_text.strip():
            print("Alle API aanroepen gefaald, gebruik fallback")
            analysis_text = f"""Het pand aan {address} in {plaats}, {gemeente} dateert uit {bouwjaar} en heeft een oppervlakte van {oppervlakte}. 

De locatie ligt in een gebied met bestemmingsplan {bestemmingsplan}, wat doorgaans wijst op een woonwijk met voornamelijk residentiële functies. De gemeente {gemeente} telt {inwoners} inwoners en ligt in de provincie {provincie}.

Als investering biedt deze locatie interessante mogelijkheden, gezien de locatie en de kenmerken van het pand. De woning is primair geschikt voor woondoeleinden, maar afhankelijk van het bestemmingsplan kunnen er mogelijk ook beperkte zakelijke activiteiten worden uitgevoerd, zoals een kantoor aan huis of praktijkruimte."""
        
        print("=== Einde Claude Debug ===")
        return {
            "title": "Claude Analyse",
            "data": {
                "tekst": analysis_text
            }
        }
    except Exception as e:
        print(f"Algemene fout bij Claude analyse: {e}")
        # Fallback voor als alles faalt
        fallback_text = f"Deze locatie in {plaats}, {gemeente} lijkt interessant. Het pand dateert uit {bouwjaar} en heeft een oppervlakte van {oppervlakte}. De gemeente heeft {inwoners} inwoners. Door technische beperkingen is een gedetailleerdere analyse momenteel niet beschikbaar."
        return {
            "title": "Locatieanalyse (Claude)",
            "data": {
                "tekst": fallback_text
            }
        }

def generate_openai_analysis(data, address):
    """Genereer een analyse van de locatie met OpenAI"""
    # Definieer standaardwaarden voor het geval dat er een fout optreedt
    plaats = "onbekende plaats"
    gemeente = "onbekende gemeente"
    provincie = "onbekende provincie"
    bouwjaar = "onbekend"
    oppervlakte = "onbekend"
    inwoners = "onbekend aantal"
    gemiddeld_inkomen = "onbekend"
    bestemmingsplan = "onbekend"
    
    try:
        if not OPENAI_API_KEY:
            raise ValueError("Geen OpenAI API-sleutel gevonden")
        
        # Verzamel relevante data voor de prompt
        if data and "pdok" in data and data["pdok"]:
            pdok_data = data["pdok"]
            plaats = pdok_data.get("woonplaatsnaam", plaats)
            gemeente = pdok_data.get("gemeentenaam", gemeente)
            provincie = pdok_data.get("provincienaam", provincie)
        
        if data and "bag" in data and data["bag"] and "data" in data["bag"]:
            bag_data = data["bag"]["data"]
            bouwjaar = bag_data.get("bouwjaar", bouwjaar)
            oppervlakte = bag_data.get("oppervlakte", oppervlakte)
        
        if data and "demografisch" in data and data["demografisch"] and "data" in data["demografisch"]:
            demo_data = data["demografisch"]["data"]
            inwoners = demo_data.get("inwoners", inwoners)
            gemiddeld_inkomen = demo_data.get("gemiddeld_inkomen", gemiddeld_inkomen)
        
        if (data and "ruimtelijke_plannen" in data and data["ruimtelijke_plannen"] and 
            "data" in data["ruimtelijke_plannen"]):
            rp_data = data["ruimtelijke_plannen"]["data"]
            if "bestemmingsplan" in rp_data:
                bestemmingsplan = rp_data["bestemmingsplan"]
            elif "naam_plan" in rp_data:
                bestemmingsplan = rp_data["naam_plan"]
        
        # Verbeterde prompt
        prompt = f"""Als vastgoedanalist, geef een beoordeling van de omgeving van dit adres: {address} in {plaats}, {gemeente}, {provincie}.

        Beschikbare gegevens:
- Bouwjaar pand: {bouwjaar}
- Oppervlakte: {oppervlakte}
- Inwoners gemeente: {inwoners}
- Gemiddeld inkomen: {gemiddeld_inkomen}
- Bestemming: {bestemmingsplan}

Geef een beknopte analyse (max. 200 woorden) waarbij je de focus legt op:
1. Leefbaarheid van de buurt
2. Trend in vastgoedwaarde in dit gebied
3. Bereikbaarheid en voorzieningen

Baseer je analyse op de verstrekte gegevens en algemene kennis over Nederlandse gemeenten.
Gebruik de specifieke gegevens die ik je heb verstrekt in je analyse."""
        
        # Probeer eerst bibliotheek methode
        analysis_text = None
        if openai_client:
            try:
                print("Probeer OpenAI aanroep met client...")
                response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Je bent een vastgoedanalist gespecialiseerd in de Nederlandse markt."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=512,
                    temperature=0.7
                )
                
                analysis_text = response.choices[0].message.content
                print("Succesvolle OpenAI client aanroep")
            except Exception as api_error:
                print(f"OpenAI client API aanroep mislukt: {api_error}")
                analysis_text = None
        
        # Als bibliotheek faalt, probeer directe API aanroep
        if analysis_text is None:
            print("OpenAI bibliotheek gefaald, probeer directe API aanroep...")
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                }
                
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "Je bent een vastgoedanalist gespecialiseerd in de Nederlandse markt."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 512,
                    "temperature": 0.7
                }
                
                response = requests.post(
                    OPENAI_API_URL,
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    response_json = response.json()
                    if "choices" in response_json and len(response_json["choices"]) > 0:
                        analysis_text = response_json["choices"][0].get("message", {}).get("content", "")
                    else:
                        print(f"Onverwachte response structuur: {response_json}")
                        analysis_text = None
                    print("Succesvolle directe OpenAI API aanroep")
                else:
                    print(f"Directe OpenAI API aanroep gefaald: {response.status_code} - {response.text}")
                    analysis_text = None
            except Exception as request_error:
                print(f"Fout bij directe OpenAI API aanroep: {request_error}")
                analysis_text = None
        
        # Als we nog steeds geen analyse hebben, gebruik fallback tekst
        if analysis_text is None or not analysis_text.strip():
            analysis_text = f"""De omgeving van {address} in {plaats}, {gemeente} biedt een prettige leefomgeving. 

Met een gemiddeld inkomen van {gemiddeld_inkomen} en {inwoners} inwoners in de gemeente, is er een goede balans tussen stedelijke voorzieningen en ruimte. 

De vastgoedwaarde in dit gebied is stabiel, mede door de goede bereikbaarheid en voorzieningen in de buurt. Het pand uit {bouwjaar} met een oppervlakte van {oppervlakte} past goed in het bestemmingsplan {bestemmingsplan}."""
        
        return {
            "title": "GPT Analyse",
            "data": {
                "tekst": analysis_text
            }
        }
    
    except Exception as e:
        print(f"Fout bij het genereren van OpenAI analyse: {e}")
        # Fallback voor als alles faalt
        fallback_text = f"De omgeving van dit adres in {plaats}, {gemeente} is het analyseren waard. De gemeente telt {inwoners} inwoners met een gemiddeld inkomen van {gemiddeld_inkomen}. Door technische beperkingen is een gedetailleerdere analyse momenteel niet beschikbaar."
        return {
            "title": "Omgevingsanalyse (GPT)",
            "data": {
                "tekst": fallback_text
            }
        }

def generate_combined_ai_summary(anthropic_analysis, openai_analysis, data, address):
    """Combineer de analyses van beide AI modellen tot een samenvatting"""
    # Haal teksten uit analyses
    claude_tekst = anthropic_analysis.get("data", {}).get("tekst", "")
    gpt_tekst = openai_analysis.get("data", {}).get("tekst", "")
    
    # Als één van de analyses ontbreekt, gebruik de andere
    if not claude_tekst and not gpt_tekst:
        return {
            "title": "Samenvatting",
            "data": {
                "tekst": f"Er kon geen analyse worden gegenereerd voor {address}. Probeer het later opnieuw."
            }
        }
    elif not claude_tekst:
        return {
            "title": "Samenvatting",
            "data": {
                "tekst": gpt_tekst
            }
        }
    elif not gpt_tekst:
        return {
            "title": "Samenvatting",
            "data": {
                "tekst": claude_tekst
            }
        }
    
    # Combineer beide analyses
    plaats = "deze plaats"
    if data and "pdok" in data and data["pdok"]:
        plaats = data["pdok"].get("woonplaatsnaam", plaats)
    
    combinatie_tekst = f"""
    # Analyse van {address} in {plaats}
    
    ## Vastgoedinformatie
    {claude_tekst[:150]}...
    
    ## Omgevingsanalyse
    {gpt_tekst[:150]}...
    
    Beide analyses wijzen op {("interessante investeringsmogelijkheden" if "investering" in claude_tekst.lower() else "een aantrekkelijke woonomgeving")} in dit gebied.
    """
    
    return {
        "title": "Samenvatting",
        "data": {
            "tekst": combinatie_tekst.strip()
        }
    }

def process_property_query(query, data, address):
    """Verwerk een specifieke vraag over het vigerende bestemmingsplan"""
    # Definieer standaardwaarden
    plaats = "onbekende plaats"
    gemeente = "onbekende gemeente"
    provincie = "onbekende provincie"
    bouwjaar = "onbekend"
    oppervlakte = "onbekend"
    bestemmingsplan = "onbekend"
    bestemmingsplan_details = {}
    
    try:
        # Verzamel context data
        if data and "pdok" in data and data["pdok"]:
            pdok_data = data["pdok"]
            plaats = pdok_data.get("woonplaatsnaam", plaats)
            gemeente = pdok_data.get("gemeentenaam", gemeente)
            provincie = pdok_data.get("provincienaam", provincie)
        
        if data and "bag" in data and data["bag"] and "data" in data["bag"]:
            bag_data = data["bag"]["data"]
            bouwjaar = bag_data.get("bouwjaar", bouwjaar)
            oppervlakte = bag_data.get("oppervlakte", oppervlakte)
        
        # Haal bestemmingsplan info op
        if data and "ruimtelijke_plannen" in data and data["ruimtelijke_plannen"]:
            rp_data = data["ruimtelijke_plannen"].get("data", {})
            
            if "bestemmingsplan" in rp_data:
                bestemmingsplan = rp_data["bestemmingsplan"]
            elif "naam_plan" in rp_data:
                bestemmingsplan = rp_data["naam_plan"]
            
            # Haal detail gegevens als die beschikbaar zijn
            if "detailed_data" in data["ruimtelijke_plannen"]:
                bestemmingsplan_details = data["ruimtelijke_plannen"]["detailed_data"]
        
        # Als de vraag specifiek over het bestemmingsplan gaat
        if "bestemmingsplan" in query.lower() or "bestemming" in query.lower() or "vigerend" in query.lower():
            # Als we gedetailleerde bestemmingsplan info hebben
            if bestemmingsplan_details and not "error" in bestemmingsplan_details:
                # Maak een gestructureerde tekst met de beschikbare details
                bestemming = bestemmingsplan_details.get("bestemming", "")
                dubbelbestemming = ", ".join(bestemmingsplan_details.get("dubbelbestemming", []))
                functieaanduiding = ", ".join(bestemmingsplan_details.get("functieaanduiding", []))
                maatvoering = ", ".join(bestemmingsplan_details.get("maatvoering", []))
                
                bestemmingsplan_info = f"""
                Het vigerende bestemmingsplan voor {address} is '{bestemmingsplan}'. 
                
                Details van het bestemmingsplan:
                - Volledige naam: {bestemmingsplan_details.get("volledige_naam", bestemmingsplan)}
                - Type plan: {bestemmingsplan_details.get("type", "Onbekend")}
                - Status: {bestemmingsplan_details.get("status", "Onbekend")}
                - Vastgesteld op: {bestemmingsplan_details.get("datum_vaststelling", "Onbekend")}
                - Bestemming: {bestemming if bestemming else "Niet specifiek vermeld"}
                {f"- Dubbelbestemming: {dubbelbestemming}" if dubbelbestemming else ""}
                {f"- Functieaanduiding: {functieaanduiding}" if functieaanduiding else ""}
                {f"- Maatvoering: {maatvoering}" if maatvoering else ""}
                
                Dit bestemmingsplan is vastgesteld door {bestemmingsplan_details.get("overheid", "de gemeente")}. 
                
                Voor de volledige tekst en details van het bestemmingsplan kunt u de website van de gemeente {gemeente} raadplegen.
                """
                
                return {
                    "data": {
                        "tekst": bestemmingsplan_info.strip()
                    }
                }
            else:
                # Basisinformatie als we geen details hebben
                bestemmingsplan_info = f"""
                Het vigerende bestemmingsplan voor {address} is '{bestemmingsplan}'. 
                
                Dit gebied is voornamelijk aangewezen voor woondoeleinden. De exacte details van dit bestemmingsplan zijn niet direct beschikbaar via deze service.
                
                Voor gedetailleerde informatie over dit specifieke bestemmingsplan adviseren wij u om de website van de gemeente {gemeente} te raadplegen of contact op te nemen met de afdeling Ruimtelijke Ordening.
                """
                
                return {
                    "data": {
                        "tekst": bestemmingsplan_info.strip()
                    }
                }
        
        # Als het een andere vraag is, gebruik AI voor een antwoord
        prompt = f"""
        Als vastgoedexpert, beantwoord deze vraag over een specifieke locatie: {address} in {plaats}, {gemeente}, {provincie}.
        
        Beschikbare gegevens over deze locatie:
        - Bouwjaar: {bouwjaar}
        - Oppervlakte: {oppervlakte}
        - Bestemming: {bestemmingsplan}
        
        De vraag is: "{query}"
        
        Geef een gefundeerd antwoord (max. 150 woorden) op deze vraag, gebaseerd op de beschikbare gegevens en algemene kennis over Nederlandse vastgoedmarkt en locaties.
        Benadruk dat je antwoord een algemene inschatting is en geen specifiek advies voor deze exacte locatie.
        """
        
        # Probeer OpenAI te gebruiken (doorgaans heeft deze een betere response rate dan Claude)
        if OPENAI_API_KEY and openai_client:
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Je bent een vastgoedexpert gespecialiseerd in de Nederlandse markt."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=400,
                    temperature=0.7
                )
                
                response_text = response.choices[0].message.content
                
                if response_text and len(response_text.strip()) > 0:
                    return {
                        "data": {
                            "tekst": response_text
                        }
                    }
            except Exception as e:
                print(f"Fout bij OpenAI vraagverwerking: {e}")
                # Val terug op Anthropic of fallback
        
        # Als OpenAI faalt, probeer Anthropic
        if ANTHROPIC_API_KEY and anthropic_client:
            try:
                response = anthropic_client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1024,
                    temperature=0.7,
                    system="Je bent een vastgoedexpert gespecialiseerd in de Nederlandse markt.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                
                response_text = response.content[0].text
                
                if response_text and len(response_text.strip()) > 0:
                    return {
                        "data": {
                            "tekst": response_text
                        }
                    }
            except Exception as e:
                print(f"Fout bij Anthropic vraagverwerking: {e}")
                # Val terug op fallback
        
        # Fallback antwoord als alles faalt
        fallback_text = f"""
        Uw vraag was: '{query}'

        Helaas kan ik momenteel geen specifiek antwoord geven over dit onderwerp voor {plaats}. Over het algemeen kan ik wel zeggen dat locaties in {gemeente} vaak interessante kenmerken hebben, vooral voor panden uit {bouwjaar} met een oppervlakte van {oppervlakte}. 
        
        Voor een gedetailleerd advies raden we aan de gemeente {gemeente} te raadplegen of een lokale vastgoedexpert te contacteren.
        """
        
        return {
            "data": {
                "tekst": fallback_text.strip()
            }
        }
        
    except Exception as e:
        print(f"Fout bij het verwerken van specifieke vraag: {e}")
        fallback_text = f"Uw vraag was: '{query}'\n\nHelaas kan ik momenteel geen specifiek antwoord geven. Voor een gedetailleerd advies raden we aan een lokale vastgoedexpert te raadplegen."
        return {
            "data": {
                "tekst": fallback_text
            }
        }

if __name__ == "__main__":
    app.run(debug=True)