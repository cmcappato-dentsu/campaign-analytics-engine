"""Cliente LLM para generación de narrativas - Groq (cloud) y fallback sin IA."""

import os
from typing import Optional, Literal
from abc import ABC, abstractmethod


LLMProvider = Literal["groq"]


class BaseLLMClient(ABC):
    """Interfaz base para clientes LLM."""
    
    @abstractmethod
    def is_available(self) -> bool:
        pass
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> Optional[str]:
        pass


class GroqClient(BaseLLMClient):
    """Cliente para Groq API (cloud, gratis, ultra-rápido)."""
    
    # Modelos a probar en orden de preferencia (actualizados para Groq 2026)
    MODEL_CANDIDATES = [
        "openai/gpt-oss-20b",      # Rápido, 20B params
        "qwen/qwen3.8-27b",        # Buena calidad, 27B params  
        "allam-2-7b",              # Ligero, 7B params
        "meta-llama/llama-prompt-guard-2-86m",  # Fallback: moderación (no generativo)
    ]
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        self.timeout = timeout
        self._client = None
        self._available = None
        self._working_model = None
    
    def _get_client(self):
        if self._client is None and self.api_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key, timeout=self.timeout)
            except ImportError:
                self._client = False
        return self._client
    
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        
        if not self.api_key:
            self._available = False
            return False
        
        client = self._get_client()
        if not client:
            self._available = False
            return False
        
        try:
            # Detectar modelo que funcione
            self._working_model = self._detect_working_model(client)
            self._available = self._working_model is not None
        except Exception:
            self._available = False
        
        return self._available
    
    def _detect_working_model(self, client) -> str | None:
        """Prueba modelos candidatos hasta encontrar uno que funcione."""
        for model in self.MODEL_CANDIDATES:
            # Saltar modelos de moderación (guard) - no son generativos
            if "prompt-guard" in model or "guard" in model:
                continue
            try:
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=5,
                )
                return model
            except Exception:
                continue
        return None
    
    def generate(self, prompt: str, system_prompt: str | None = None) -> Optional[str]:
        if not self.is_available():
            return None
        
        client = self._get_client()
        if not client or not self._working_model:
            return None
        
        try:
            is_guard = "prompt-guard" in self._working_model
            
            # Para guard model: límite estricto de contexto (512 tokens total)
            if is_guard:
                # Estimar tokens (aprox 4 chars = 1 token)
                prompt_tokens = len(prompt) // 4
                system_tokens = len(system_prompt) // 4 if system_prompt else 0
                max_input_tokens = 512 - 100  # dejar 100 tokens para respuesta
                
                if system_prompt and (prompt_tokens + system_tokens) > max_input_tokens:
                    # Truncar system_prompt para que quepa
                    max_system_chars = (max_input_tokens - prompt_tokens) * 4
                    if max_system_chars > 50:
                        system_prompt = system_prompt[:max_system_chars]
                    else:
                        system_prompt = None
                
                # Guard model no soporta system prompt - prepend to user message
                if system_prompt:
                    prompt = f"{system_prompt}\n\n{prompt}"
                    system_prompt = None
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            max_tokens = 100 if "prompt-guard" in self._working_model else 3000
            response = client.chat.completions.create(
                model=self._working_model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                return None
            content = content.strip()
            
            # Detectar si el modelo es guard model (devuelve score numérico)
            if "prompt-guard" in self._working_model:
                try:
                    score = float(content)
                    return f"[Guard model score: {score:.4f} - modelo de moderación, no generativo]"
                except ValueError:
                    pass
            
            return content
        except Exception:
            return None


def get_llm_client(
    api_key: str | None = None,
) -> BaseLLMClient:
    """Factory para obtener cliente Groq."""
    return GroqClient(api_key=api_key)


class _NullClient(BaseLLMClient):
    """Cliente nulo - siempre retorna None (fallback a templates)."""
    
    def is_available(self) -> bool:
        return False
    
    def generate(self, prompt: str, system_prompt: str | None = None) -> Optional[str]:
        return None


SYSTEM_PROMPT = """Sos un analista senior de Paid Media (Google Ads).
Generás un RESUMEN EJECUTIVO del análisis semanal de campañas de Búsqueda.
Estructura obligatoria (máx 350 palabras), siguiendo el razonamiento del analista:

**1. QUÉ PASÓ (Resumen general)**
- Inversión total, impresiones, clics, conversiones, CTR, CPA principales

**2. CONCENTRACIÓN (Pregunta 2)**
- Qué campañas concentran 80% inversión vs 80% resultados
- Si hay desalineación gasto/resultados

**3. PRESUPUESTO DESPERDICIADO (Pregunta 3)**
- Red de Display en Búsqueda (config error)
- Gasto sin clics/conversiones
- Campañas con volumen insuficiente pero gasto

**4. OPORTUNIDADES DE ESCALA (Pregunta 4)**
- Campañas eficientes con buen ROAS/CPA limitadas por presupuesto
- Campañas con resultados pero poca inversión (Pareto conv ≠ Pareto inv)

**5. VISIBILIDAD (Pregunta 5)**
- Campañas perdiendo Impression Share vs benchmark histórico
- Por ranking vs por presupuesto

**6. CLICS VS CONVERSIONES (Pregunta 6)**
- CTR alto/bajo vs benchmark
- Tasa conversión cayendo con clics estables (landing/oferta)

**7. CPA ALTO (Pregunta 7)**
- Campañas con CPA significativamente sobre benchmark
- Outliers críticos de CPA

**8. DATOS INSUFICIENTES (Pregunta 8)**
- Campañas nuevas (<7 días) o bajo volumen

**9. TOP 5 HALLAZGOS (Pregunta 9)**
- Los 2-5 hallazgos más relevantes priorizados por score (impacto × magnitud)
- Outliers críticos siempre incluidos

Reglas estrictas:
- NO des recomendaciones de acción ("subir presupuesto", "pausar campaña")
- SOLO reportá patrones detectados: "Campaña X tiene CPA 40% sobre benchmark"
- Usá nombres reales de campañas y métricas con valores
- Tono: profesional, objetivo, analítico
- Formato: Markdown con headers ##"""


def build_report_context(
    insights,
    df_campaign,
    scored_findings: list | None = None,
    top_n: int = 5,
) -> str:
    """
    Construye contexto comprimido para el LLM (~800 tokens).
    Estructurado según las 9 preguntas del roadmap.
    """
    total_spend = df_campaign["spend_usd"].sum()
    total_conv = df_campaign["conversions"].sum()
    total_clicks = int(df_campaign["clicks"].sum())
    total_impr = int(df_campaign["impressions"].sum())
    ctr = total_clicks / total_impr if total_impr > 0 else 0
    cpa = total_spend / total_conv if total_conv > 0 else 0

    # Pregunta 1: KPIs globales
    p1 = f"1. QUÉ PASÓ: Inversión ${total_spend:,.0f} | Impr {total_impr:,} | Clics {total_clicks:,} (CTR {ctr:.1%}) | Conv {total_conv:.1f} (CPA ${cpa:,.0f})"

    # Pregunta 2: Concentración (Pareto)
    pareto = df_campaign.nlargest(5, "spend_usd")[["campaign", "spend_usd", "conversions"]]
    spend_pct = pareto["spend_usd"].sum() / total_spend * 100
    conv_pct = pareto["conversions"].sum() / total_conv * 100 if total_conv > 0 else 0
    pareto_lines = "; ".join(f"{r['campaign']}: ${r['spend_usd']:,.0f} ({r['conversions']:.1f} conv)" for _, r in pareto.iterrows())
    p2 = f"2. CONCENTRACIÓN: Top 5 = {spend_pct:.0f}% gasto, {conv_pct:.0f}% conv | {pareto_lines}"

    # Helper para buscar en insights
    def find_insights(keywords):
        found = []
        for ins in insights:
            ans = getattr(ins, 'answer', '').lower()
            if any(kw.lower() in ans for kw in keywords):
                found.append(ins)
        return found

    def extract_msg(insights_list, max_chars=100):
        return "; ".join([getattr(i, 'answer', '')[:max_chars] for i in insights_list[:3]])

    # Pregunta 3: Presupuesto desperdiciado
    disp = find_insights(["display", "red de display"])
    spend_nr = find_insights(["gasto sin", "sin clic", "sin convers"])
    p3_parts = []
    if disp:
        p3_parts.append(f"Display en Search: {len(disp)} campaña(s)")
    if spend_nr:
        p3_parts.append(f"Gasto sin resultados: {len(spend_nr)} campaña(s)")
    p3 = f"3. DESPERDICIO: {'; '.join(p3_parts) if p3_parts else 'Sin desperdicios detectados'}"

    # Pregunta 4: Oportunidades de escala
    scale = find_insights(["escal", "oportunidad", "pareto oportunidad"])
    p4 = f"4. ESCALA: {extract_msg(scale) if scale else 'Sin oportunidades claras'}"

    # Pregunta 5: Visibilidad
    vis = find_insights(["visibilidad", "impression share", "impr share", "cuota de impres"])
    p5 = f"5. VISIBILIDAD: {extract_msg(vis) if vis else 'Sin pérdidas significativas de IS'}"

    # Pregunta 6: Clicks vs Conversiones
    ctr_f = find_insights(["ctr", "tasa de clic"])
    cvr_f = find_insights(["tasa de convers", "conversion rate", "conversiones vs"])
    p6_parts = []
    if ctr_f:
        p6_parts.append(f"CTR: {len(ctr_f)} variación(es)")
    if cvr_f:
        p6_parts.append(f"Tasa conv: {len(cvr_f)} variación(es)")
    p6 = f"6. CLICS VS CONV: {'; '.join(p6_parts) if p6_parts else 'CTR y tasa conv en rangos normales'}"

    # Pregunta 7: CPA alto
    cpa_f = find_insights(["cpa alto", "cpa elevad", "costo por resultado", "sobre benchmark"])
    p7 = f"7. CPA ALTO: {extract_msg(cpa_f) if cpa_f else 'CPAs en rangos normales'}"

    # Pregunta 8: Datos insuficientes
    insuff = find_insights(["insuficiente", "esperar", "pocos datos"])
    p8 = f"8. DATOS INSUFICIENTES: {extract_msg(insuff) if insuff else 'Todas con datos suficientes'}"

    # Pregunta 9: Top hallazgos
    if scored_findings:
        findings_text = []
        for i, f in enumerate(scored_findings[:top_n], 1):
            outlier = " ⚡" if getattr(f, 'is_outlier', False) else ""
            findings_text.append(f"{i}. {f.rule_name} ({f.campaign}){outlier}: {f.message[:120]}")
        p9 = "9. TOP 5 HALLAZGOS:\n" + "\n".join(findings_text)
    else:
        top_h = find_insights(["top ", "hallazg", "relevant"])
        p9 = f"9. TOP HALLAZGOS: {extract_msg(top_h) if top_h else 'Ver lista completa'}"

    return "\n\n".join([p1, p2, p3, p4, p5, p6, p7, p8, p9])


def generate_llm_narrative(
    insights,
    df_campaign,
    scored_findings: list | None = None,
    api_key: str | None = None,
) -> Optional[str]:
    """
    Genera narrativa ejecutiva con Groq.
    Retorna None si no disponible (fallback a templates).
    """
    client = get_llm_client(api_key=api_key)
    if not client.is_available():
        return None

    context = build_report_context(insights, df_campaign, scored_findings=scored_findings)
    prompt = f"Datos de la semana:\n{context}\n\nGenerá el resumen ejecutivo."
    return client.generate(prompt, SYSTEM_PROMPT)