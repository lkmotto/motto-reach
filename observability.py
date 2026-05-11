"""OpenTelemetry + Langfuse observability scaffolding.

Call init_observability("<agent-name>") once at startup. Every LLM call wrapped
in `@traced` (or manually with `tracer.start_as_current_span`) is then visible
in Langfuse with cost, latency, prompt, and completion.
"""
import os
import binascii
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter


def _basic_auth_header(uname: str, passwd: str) -> str:
    """Build a Basic auth header value from a key:secret pair."""
    raw = uname + ":" + passwd
    encoded = binascii.b2a_base64(raw.encode(), newline=False)
    return "Basic " + encoded.decode("ascii")


def init_observability(service_name: str) -> trace.Tracer:
    """Initialize OTel tracing pointed at Langfuse. Idempotent."""
    if trace.get_tracer_provider().__class__.__name__ == "TracerProvider":
        return trace.get_tracer(service_name)

    endpoint = os.getenv("LANGFUSE_OTEL_ENDPOINT", "https://us.cloud.langfuse.com/api/public/otel/v1/traces")
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")

    headers = {}
    if pk and sk:
        headers["Authorization"] = _basic_auth_header(pk, sk)

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
