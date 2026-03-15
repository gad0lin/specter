"""
scan/forensics.py — Crime scene / forensics documentation mode.

Autonomous space documentation that generates a structured, court-defensible
case file from robot camera feeds.

Output: ForensicsReport with spatial map, anomalies, cross-references, LLM summary
"""
import os
import json
import time
import base64
from dataclasses import dataclass, field
from openai import OpenAI

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
NIM_MODEL = os.environ.get("NIM_MODEL", "Qwen/Qwen2-VL-72B-Instruct")
LLM_MODEL = os.environ.get("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
from src.story.llm_client import get_client as _get_llm_client

FORENSICS_SCAN_PROMPT = """You are a forensic AI assistant documenting a scene for law enforcement.
Analyze this image with maximum detail and return a structured JSON report:
{
  "scene_type": "indoor/outdoor/vehicle/etc",
  "lighting": "description",
  "objects": [
    {
      "id": "obj_001",
      "type": "object category",
      "description": "precise description",
      "position_estimate": "relative to frame: top-left/center/etc",
      "condition": "intact/damaged/disturbed/etc",
      "anomaly": "anything unusual or out of place, null if normal",
      "text_visible": "any readable text, null if none",
      "searchable": true/false
    }
  ],
  "spatial_relationships": ["object A is 30cm from object B", "door is open facing north"],
  "anomalies": ["list of anything that seems out of place"],
  "time_indicators": ["any clues about when this happened: warm coffee, wet floor, etc"],
  "entry_exit_points": ["visible doors, windows, other access points"],
  "evidence_priority": ["top 3 items that warrant immediate attention"]
}
Be precise. Flag anything unusual. Return ONLY valid JSON."""


@dataclass
class ForensicObject:
    id: str
    type: str
    description: str
    position_estimate: str
    condition: str
    anomaly: str | None
    text_visible: str | None
    searchable: bool
    tavily_result: str | None = None


@dataclass
class ForensicsReport:
    case_id: str
    timestamp: str
    scene_type: str
    scan_count: int
    objects: list[ForensicObject]
    spatial_relationships: list[str]
    anomalies: list[str]
    time_indicators: list[str]
    entry_exit_points: list[str]
    evidence_priority: list[str]
    tavily_findings: list[dict]
    llm_summary: str
    llm_theory: str


def _nim_client():
    return OpenAI(base_url=NEBIUS_BASE_URL, api_key=NEBIUS_API_KEY)


def scan_scene(image_bytes: bytes, location_note: str = "") -> dict:
    """NIM vision forensic scan of a single frame."""
    b64 = base64.b64encode(image_bytes).decode()
    prompt = FORENSICS_SCAN_PROMPT
    if location_note:
        prompt += f"\n\nLocation note: {location_note}"

    client = _nim_client()
    resp = client.chat.completions.create(
        model=NIM_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]}],
        max_tokens=1000,
        temperature=0.1,
    )
    raw = resp.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1].lstrip("json").strip()
    return json.loads(raw)


def _tavily_search(query: str) -> str | None:
    """Cross-reference an object or text with Tavily."""
    if not TAVILY_API_KEY or not query:
        return None
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        result = client.search(
            query=f"forensic investigation {query}",
            search_depth="basic",
            max_results=2,
            include_answer=True,
        )
        return result.get("answer") or None
    except Exception as e:
        print(f"⚠️  Tavily search failed: {e}")
        return None


def generate_report(scan_results: list[dict], case_id: str | None = None) -> ForensicsReport:
    """
    Aggregate multiple scans into a full forensics report.
    Cross-references suspicious items with Tavily.
    Generates LLM summary and investigative theory.
    """
    import uuid
    case_id = case_id or f"CASE-{str(uuid.uuid4())[:8].upper()}"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Aggregate all scan data
    all_objects = []
    all_anomalies = []
    all_relationships = []
    all_time_indicators = []
    all_entry_exit = []
    all_priority = []
    scene_type = "unknown"

    obj_counter = 1
    for scan in scan_results:
        scene_type = scan.get("scene_type", scene_type)
        all_anomalies.extend(scan.get("anomalies", []))
        all_relationships.extend(scan.get("spatial_relationships", []))
        all_time_indicators.extend(scan.get("time_indicators", []))
        all_entry_exit.extend(scan.get("entry_exit_points", []))
        all_priority.extend(scan.get("evidence_priority", []))

        for obj_data in scan.get("objects", []):
            obj = ForensicObject(
                id=f"obj_{obj_counter:03d}",
                type=obj_data.get("type", "unknown"),
                description=obj_data.get("description", ""),
                position_estimate=obj_data.get("position_estimate", ""),
                condition=obj_data.get("condition", "unknown"),
                anomaly=obj_data.get("anomaly"),
                text_visible=obj_data.get("text_visible"),
                searchable=obj_data.get("searchable", False),
            )
            all_objects.append(obj)
            obj_counter += 1

    # Tavily cross-reference for searchable + anomalous items
    tavily_findings = []
    print(f"🔍 Cross-referencing {len(all_objects)} objects via Tavily...")
    for obj in all_objects:
        if obj.searchable or obj.anomaly:
            query = obj.text_visible or f"{obj.type} forensic significance {obj.anomaly or ''}"
            result = _tavily_search(query[:100])
            if result:
                obj.tavily_result = result
                tavily_findings.append({"object": obj.id, "query": query[:60], "finding": result[:200]})

    # LLM summary + theory
    print(f"🧠 Generating investigative summary via Nebius ({LLM_MODEL})...")
    client = _nim_client()

    context = f"""
FORENSICS REPORT — {case_id}
Scene: {scene_type}
Objects found: {len(all_objects)}
Anomalies: {json.dumps(all_anomalies[:5])}
Time indicators: {json.dumps(all_time_indicators)}
Evidence priority: {json.dumps(all_priority[:5])}
Spatial relationships: {json.dumps(all_relationships[:5])}
Tavily cross-references: {json.dumps(tavily_findings[:3])}
"""
    summary_resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": f"""You are a senior forensic analyst.
Based on this scene data, provide:
1. A 3-sentence factual summary of what was found
2. A 2-sentence investigative theory (most likely explanation)

{context}

Return JSON: {{"summary": "...", "theory": "..."}}"""}],
        max_tokens=300,
        temperature=0.3,
    )
    raw = summary_resp.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        llm_out = json.loads(raw)
    except Exception:
        llm_out = {"summary": raw[:300], "theory": "Further analysis required."}

    return ForensicsReport(
        case_id=case_id,
        timestamp=timestamp,
        scene_type=scene_type,
        scan_count=len(scan_results),
        objects=all_objects,
        spatial_relationships=list(set(all_relationships)),
        anomalies=list(set(all_anomalies)),
        time_indicators=list(set(all_time_indicators)),
        entry_exit_points=list(set(all_entry_exit)),
        evidence_priority=all_priority[:5],
        tavily_findings=tavily_findings,
        llm_summary=llm_out.get("summary", ""),
        llm_theory=llm_out.get("theory", ""),
    )


def report_to_json(report: ForensicsReport) -> dict:
    """Serialize report to JSON-safe dict."""
    return {
        "case_id": report.case_id,
        "timestamp": report.timestamp,
        "scene_type": report.scene_type,
        "scan_count": report.scan_count,
        "llm_summary": report.llm_summary,
        "llm_theory": report.llm_theory,
        "evidence_priority": report.evidence_priority,
        "anomalies": report.anomalies,
        "time_indicators": report.time_indicators,
        "entry_exit_points": report.entry_exit_points,
        "spatial_relationships": report.spatial_relationships,
        "objects": [
            {
                "id": o.id,
                "type": o.type,
                "description": o.description,
                "condition": o.condition,
                "anomaly": o.anomaly,
                "text_visible": o.text_visible,
                "tavily_result": o.tavily_result,
            }
            for o in report.objects
        ],
        "tavily_findings": report.tavily_findings,
    }
