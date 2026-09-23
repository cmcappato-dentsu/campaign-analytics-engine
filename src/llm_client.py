"""Cliente LLM opcional para generación de narrativas (Ollama local)."""

import os
from typing import Optional


class LLMClient:
    """Cliente para generación de texto con LLM local (Ollama)."""

    def __init__(
        self,
        model: str = "llama3.1:8b",
        host: str | None = None,
        timeout: int = 120,
    ):
        self.model = model
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.timeout = timeout
        self._client = None
        self._available = None

    def _get_client(self):
        """Lazy load del cliente Ollama."""
        if self._client is None:
            try:
                import ollama
                self._client = ollama.Client(host=self.host, timeout=self.timeout)
            except ImportError:
                self._client = False
        return self._client

    def is_available(self) -> bool:
        """Verifica si Ollama está disponible y el modelo existe."""
        if self._available is not None:
            return self._available

        client = self._get_client()
        if not client:
            self._available = False
            return False

        try:
            models = client.list()
            model_items = (
                models.get("models", [])
                if isinstance(models, dict)
                else getattr(models, "models", [])
            )
            model_names = [
                m.get("name", m.get("model", ""))
                if isinstance(m, dict)
                else getattr(m, "name", getattr(m, "model", ""))
                for m in model_items
            ]
            self._available = any(self.model in name for name in model_names)
        except Exception:
            self._available = False

        return self._available

    def generate(self, prompt: str, system_prompt: str | None = None) -> Optional[str]:
        """
        Genera texto con el LLM.
        Retorna None si no está disponible o hay error.
        """
        if not self.is_available():
            return None

        client = self._get_client()
        if not client:
            return None

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat(model=self.model, messages=messages)
            return response.get("message", {}).get("content", "").strip()
        except Exception:
            return None


def build_report_context(
    insights,
    df_campaign,
    top_n: int = 5,
) -> str:
    """
    Construye contexto comprimido para el LLM (~500 tokens).
    Solo pasa lo esencial: KPIs globales + top hallazgos + Pareto.
    """
    total_spend = df_campaign["spend_usd"].sum()
    total_conv = df_campaign["conversions"].sum()
    total_clicks = int(df_campaign["clicks"].sum())
    total_impr = int(df_campaign["impressions"].sum())
    ctr = total_clicks / total_impr if total_impr > 0 else 0
    cpa = total_spend / total_conv if total_conv > 0 else 0

    # Top hallazgos scored
    findings_text = []
    for i, f in enumerate(insights[:top_n], 1):
        findings_text.append(
            f"{i}. {f.rule_name} ({f.campaign}): {f.message[:150]}"
        )

    # Pareto rápido
    pareto = df_campaign.nlargest(3, "spend_usd")[["campaign", "spend_usd", "conversions"]]
    pareto_text = "; ".join(
        f"{r['campaign']}: ${r['spend_usd']:,.0f} ({r['conversions']:.1f} conv)"
        for _, r in pareto.iterrows()
    )

    return f"""
KPIs GLOBALES:
- Inversión: ${total_spend:,.0f}
- Impresiones: {total_impr:,}
- Clics: {total_clicks:,} (CTR: {ctr:.1%})
- Conversiones: {total_conv:.1f} (CPA: ${cpa:,.0f})

TOP 3 CAMPANAS POR INVERSIÓN:
{pareto_text}

HALLAZGOS PRIORIZADOS (top {top_n}):
{chr(10).join(findings_text)}
""".strip()


SYSTEM_PROMPT = """Sos un analista senior de Paid Media (Google Ads).
Generás reportes ejecutivos en español, concisos y accionables.
Estructura obligatoria (máx 300 palabras):

1. RESUMEN EJECUTIVO (2-3 líneas): qué pasó en la semana
2. HALLAZGOS CLAVE (bullets): top 3-5 problemas/oportunidades con campaña y métrica
3. OPORTUNIDADES: dónde escalar o invertir más
4. RIESGOS/ACCIONES: qué revisar urgente

Tono: profesional, directo, sin fluff. Usá formato Markdown."""


def generate_llm_narrative(
    insights,
    df_campaign,
    model: str = "llama3.1:8b",
) -> Optional[str]:
    """
    Función de conveniencia: genera narrativa completa.
    Retorna None si LLM no disponible (fallback a templates).
    """
    client = LLMClient(model=model)
    if not client.is_available():
        return None

    context = build_report_context(insights, df_campaign)
    prompt = f"Datos de la semana:\n{context}\n\nGenerá el reporte ejecutivo."
    return client.generate(prompt, SYSTEM_PROMPT)
