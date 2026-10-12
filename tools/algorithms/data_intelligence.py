"""
tools/algorithms/data_intelligence.py
Intelligence de données, statistiques et traitements NLP locaux
"""

import math
import re
from collections import Counter

class DataIntelligence:
    def analyze_dataset_summary(self, data: list[dict]) -> dict:
        """1. Analyse statistique automatique de listes de dictionnaires."""
        if not data:
            return {"count": 0}
        keys = list(data[0].keys())
        summary = {"count": len(data), "keys": keys, "numeric_stats": {}}
        
        for k in keys:
            vals = [d[k] for d in data if isinstance(d.get(k), (int, float))]
            if vals:
                summary["numeric_stats"][k] = {
                    "mean": round(sum(vals) / len(vals), 2),
                    "min": min(vals),
                    "max": max(vals)
                }
        return summary

    def detect_anomalies_zscore(self, numbers: list[float], threshold: float = 2.0) -> list[float]:
        """2. Détecteur d'anomalies par score Z."""
        if len(numbers) < 3:
            return []
        mean = sum(numbers) / len(numbers)
        variance = sum((x - mean) ** 2 for x in numbers) / len(numbers)
        std_dev = math.sqrt(variance)
        if std_dev == 0:
            return []
        
        anomalies = []
        for x in numbers:
            z_score = abs(x - mean) / std_dev
            if z_score > threshold:
                anomalies.append(x)
        return anomalies

    def analyze_trends(self, time_series: list[float]) -> str:
        """3. Analyse de tendance temporelle simple."""
        if len(time_series) < 2:
            return "Insuffisant de données"
        diff = time_series[-1] - time_series[0]
        if diff > 0.05 * time_series[0]:
            return "Tendance à la hausse"
        elif diff < -0.05 * time_series[0]:
            return "Tendance à la baisse"
        return "Tendance stable"

    def generate_ascii_chart(self, values: list[float], labels: list[str] = None) -> str:
        """4. Générateur de graphique ASCII léger."""
        if not values:
            return ""
        max_v = max(values) or 1.0
        chart = ""
        for idx, v in enumerate(values):
            bar_len = int((v / max_v) * 20)
            label = labels[idx] if labels and idx < len(labels) else f"Item {idx+1}"
            chart += f"{label[:10]:<10} | {'█' * bar_len} ({v})\n"
        return chart

    def nlp_sentiment_analysis(self, text: str) -> dict:
        """5. Analyseur de sentiment NLP local à base de lexique."""
        pos_words = {"super", "excellent", "génial", "bon", "parfait", "bien", "bravo", "merci", "formidable"}
        neg_words = {"mauvais", "erreur", "bug", "problème", "nul", "échec", "lent", "horrible", "cassé"}
        
        words = set(re.findall(r'\w+', text.lower()))
        pos_count = len(words.intersection(pos_words))
        neg_count = len(words.intersection(neg_words))
        
        if pos_count > neg_count:
            sentiment = "Positif"
        elif neg_count > pos_count:
            sentiment = "Négatif"
        else:
            sentiment = "Neutre"
            
        return {"sentiment": sentiment, "score": pos_count - neg_count}

    def extract_named_entities(self, text: str) -> dict:
        """6. Extracteur d'entités (emails, URLs, dates, téléphones)."""
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        urls = re.findall(r'https?://[^\s]+', text)
        dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text)
        phones = re.findall(r'\b(?:\+33|0)[1-9](?:[\s.-]?\d{2}){4}\b', text)
        
        return {
            "emails": emails,
            "urls": urls,
            "dates": dates,
            "phones": phones
        }

    def classify_text_intent(self, text: str) -> str:
        """7. Classifieur de texte d'intention rapide."""
        text_l = text.lower()
        if any(w in text_l for w in ["aide", "comment", "explication"]):
            return "Demande d'information"
        elif any(w in text_l for w in ["bug", "erreur", "problème", "fix"]):
            return "Signalement de problème"
        elif any(w in text_l for w in ["crée", "ajoute", "fais", "génère"]):
            return "Ordre / Action"
        return "General"

    def build_regex_pattern(self, example: str) -> str:
        """8. Constructeur de Regex à partir d'exemples."""
        if re.match(r'^\d+$', example):
            return r'\d+'
        elif re.match(r'^[a-zA-Z]+$', example):
            return r'[a-zA-Z]+'
        elif "@" in example:
            return r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        return r'\s+'

    def validate_json_schema(self, data: dict, required_keys: list[str]) -> tuple[bool, list[str]]:
        """9. Validateur de schémas de données."""
        missing = [k for k in required_keys if k not in data]
        return (len(missing) == 0, missing)

    def generate_markdown_report(self, title: str, sections: dict) -> str:
        """10. Générateur automatique de rapports Markdown."""
        report = f"# {title}\n\n"
        for sec_name, content in sections.items():
            report += f"## {sec_name}\n{content}\n\n"
        report += "---\n*Rapport généré automatiquement par Onyx Data Intelligence*\n"
        return report
