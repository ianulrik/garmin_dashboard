"""Enkel regelbasert anbefaling for dagens økt, basert på gårsdagens/nattens
data. Ikke en periodisert treningsplan — bare et raskt "bør jeg presse i dag
eller ta det med ro?"-signal fra tallene vi allerede henter.

Merk: statusverdiene fra Garmin ("BALANCED", "OPTIMAL", osv.) er ikke
offisielt dokumentert — reglene her er skrevet mot det vi faktisk har sett
fra egen konto, og bør justeres om du ser andre verdier over tid.
"""


def build_recommendation(snapshot: dict) -> dict:
    flags: list[str] = []
    positives: list[str] = []

    sovn = snapshot.get("sovn") or {}
    if (sovn.get("score") or 0) and sovn["score"] < 60:
        flags.append(f"Lav søvn-score ({sovn['score']}) — kroppen har ikke restituert fullt ut.")
    elif sovn.get("score"):
        positives.append(f"God søvn-score ({sovn['score']}).")

    hrv = snapshot.get("hrv") or {}
    hrv_status = hrv.get("status")
    if hrv_status and "BALANCED" not in hrv_status:
        flags.append(f"HRV-status er '{hrv_status}', ikke balansert — kroppen er under stress.")
    elif hrv_status:
        positives.append("HRV er i balanse.")

    trening = snapshot.get("trening") or {}
    ratio = trening.get("belastningsforhold")
    load_status = trening.get("belastning_status")
    if ratio is not None and ratio > 1.5:
        flags.append(f"Akutt/kronisk belastningsforhold er høyt ({ratio}) — skaderisiko øker.")
    elif load_status and load_status != "OPTIMAL":
        flags.append(f"Belastningsstatus er '{load_status}', ikke optimal.")
    elif ratio is not None:
        positives.append(f"Belastningsforhold ser greit ut ({ratio}).")

    bb = snapshot.get("body_battery") or {}
    if bb.get("naa") is not None and bb["naa"] < 30:
        flags.append(f"Body Battery er lav ({bb['naa']}/100).")

    if len(flags) >= 2:
        verdict = "Hviledag eller lett økt"
    elif len(flags) == 1:
        verdict = "Ta det litt roligere i dag"
    elif ratio is not None and ratio < 0.8:
        verdict = "Klar for en hardøkt"
        positives.append("Belastningen er lav relativt til kapasitet — rom for å presse på.")
    else:
        verdict = "Normal treningsdag"

    return {"verdict": verdict, "flags": flags, "positives": positives}
