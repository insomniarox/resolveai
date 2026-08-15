"""Configure opt-in local OpenTelemetry trace export."""

import os
from threading import Lock

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_TRACE_CONSOLE_ENV = "RESOLVEAI_TRACE_CONSOLE"
_configuration_lock = Lock()
_console_provider: TracerProvider | None = None


def configure_console_tracing() -> TracerProvider | None:
    """Configure one process-wide console exporter when explicitly enabled."""
    global _console_provider

    if os.environ.get(_TRACE_CONSOLE_ENV) != "1":
        return None

    with _configuration_lock:
        if _console_provider is not None:
            return _console_provider

        provider = TracerProvider(
            resource=Resource.create({"service.name": "resolveai"}),
        )
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _console_provider = provider
        return provider


def force_flush_console_tracing() -> bool:
    """Flush locally configured spans before a short-lived process exits."""
    if _console_provider is None:
        return True
    return _console_provider.force_flush()
